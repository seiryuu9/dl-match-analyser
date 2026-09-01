package org.example;

import com.google.gson.GsonBuilder;
import skadistats.clarity.event.Insert;
import skadistats.clarity.model.Entity;
import skadistats.clarity.model.FieldPath;
import skadistats.clarity.processor.entities.*;
import skadistats.clarity.processor.runner.Context;
import skadistats.clarity.processor.runner.SimpleRunner;
import skadistats.clarity.source.MappedFileSource;

import java.io.FileWriter;
import java.util.*;

@UsesEntities
public class App {

    private static final double TICKS_PER_SECOND = 64.0;

    private static final Map<String, String> STRUCTURE_TYPES = Map.of(
            "CNPC_Boss_Tier2", "Tier1Structure",
            "CNPC_TrooperBoss", "Tier2Structure",
            "CNPC_BarrackBoss", "BaseGuardian",
            "CCitadel_Destroyable_Building", "InnerTower"
    );

    @Insert
    private Context ctx;

    private final Map<Integer, Integer> playerTeams = new HashMap<>();
    private final Map<Integer, Integer> lastPlayerLifeState = new HashMap<>();
    private final Map<Integer, Double> lastDeathTime = new HashMap<>();

    private final Map<Integer, Integer> structureTeams = new HashMap<>();
    private final Map<Integer, Integer> patronLifeState = new HashMap<>();
    private final Map<Integer, Integer> midBossLifeState = new HashMap<>();

    private final List<Map<String, Object>> deaths = new ArrayList<>();
    private final List<Map<String, Object>> structuresDestroyed = new ArrayList<>();
    private final List<Map<String, Object>> patronEvents = new ArrayList<>();
    private final List<Map<String, Object>> midBossKills = new ArrayList<>();
    private final List<Map<String, Object>> riftCaptures = new ArrayList<>();
    private final List<Map<String, Object>> urnPickups = new ArrayList<>();

    private final Map<Integer, Double> pendingRiftSpawns = new HashMap<>();
    private final Map<Integer, Double> pendingUrnSpawns = new HashMap<>();

    private double tickToSeconds(int tick) {
        return tick / TICKS_PER_SECOND;
    }

    @OnEntityCreated
    public void onEntityCreated(Entity e) {
        String typeName = e.getDtClass().getDtName();

        if (typeName.equals("CCitadelPlayerPawn") && e.hasProperty("m_iTeamNum")) {
            playerTeams.put(e.getIndex(), (Integer) e.getProperty("m_iTeamNum"));
        }

        if (STRUCTURE_TYPES.containsKey(typeName) && e.hasProperty("m_iTeamNum")) {
            structureTeams.put(e.getIndex(), (Integer) e.getProperty("m_iTeamNum"));
        }

        // Rift (formerly mislabeled as "Koth")
        if (typeName.equals("CCitadelItemKothSpawner")) {
            pendingRiftSpawns.put(e.getIndex(), tickToSeconds(ctx.getTick()));
        }
        if (typeName.equals("CCitadel_KothCashIn")) {
            Map<String, Object> r = new LinkedHashMap<>();
            r.put("cashin_time_s", tickToSeconds(ctx.getTick()));
            if (!pendingRiftSpawns.isEmpty()) {
                r.put("spawn_time_s", Collections.max(pendingRiftSpawns.values()));
            }
            riftCaptures.add(r);
        }

        // Urn (Idol)
        if (typeName.equals("CCitadelItemPickupIdol")) {
            pendingUrnSpawns.put(e.getIndex(), tickToSeconds(ctx.getTick()));
        }
    }

    @OnEntityUpdated
    public void onEntityUpdated(Entity e, FieldPath[] updatedPaths, int updateCount) {
        String typeName = e.getDtClass().getDtName();

        if (typeName.equals("CCitadelPlayerPawn") && e.hasProperty("m_lifeState")) {
            Integer newState = (Integer) e.getProperty("m_lifeState");
            Integer oldState = lastPlayerLifeState.get(e.getIndex());
            if (newState != null && !newState.equals(oldState)) {
                lastPlayerLifeState.put(e.getIndex(), newState);
                double t = tickToSeconds(ctx.getTick());
                if (newState == 2 && (oldState == null || oldState == 0)) {
                    lastDeathTime.put(e.getIndex(), t);
                    Map<String, Object> d = new LinkedHashMap<>();
                    d.put("team", playerTeams.get(e.getIndex()));
                    d.put("player_index", e.getIndex());
                    d.put("game_time_s", t);
                    d.put("death_duration_s", null);
                    deaths.add(d);
                } else if (newState == 0 && oldState != null && oldState == 2) {
                    Double deathTime = lastDeathTime.get(e.getIndex());
                    if (deathTime != null) {
                        for (int i = deaths.size() - 1; i >= 0; i--) {
                            Map<String, Object> d = deaths.get(i);
                            if (d.get("player_index").equals(e.getIndex()) && d.get("death_duration_s") == null) {
                                d.put("death_duration_s", t - deathTime);
                                break;
                            }
                        }
                    }
                }
            }
        }

        if (typeName.equals("CNPC_Boss_Tier3") && e.hasProperty("m_lifeState")) {
            Integer newState = (Integer) e.getProperty("m_lifeState");
            Integer oldState = patronLifeState.get(e.getIndex());
            if (newState != null && !newState.equals(oldState)) {
                patronLifeState.put(e.getIndex(), newState);
                if (newState != 0 && (oldState == null || oldState == 0)) {
                    Map<String, Object> p = new LinkedHashMap<>();
                    p.put("team", e.hasProperty("m_iTeamNum") ? e.getProperty("m_iTeamNum") : null);
                    p.put("game_time_s", tickToSeconds(ctx.getTick()));
                    patronEvents.add(p);
                }
            }
        }

        if (typeName.equals("CNPC_MidBoss") && e.hasProperty("m_lifeState")) {
            Integer newState = (Integer) e.getProperty("m_lifeState");
            Integer oldState = midBossLifeState.get(e.getIndex());
            if (newState != null && !newState.equals(oldState)) {
                midBossLifeState.put(e.getIndex(), newState);
                if (newState != 0 && (oldState == null || oldState == 0)) {
                    Map<String, Object> mb = new LinkedHashMap<>();
                    mb.put("killed_time_s", tickToSeconds(ctx.getTick()));
                    midBossKills.add(mb);
                }
            }
        }
    }

    @OnEntityDeleted
    public void onEntityDeleted(Entity e) {
        String typeName = e.getDtClass().getDtName();

        if (STRUCTURE_TYPES.containsKey(typeName)) {
            Map<String, Object> s = new LinkedHashMap<>();
            s.put("structure_type", STRUCTURE_TYPES.get(typeName));
            s.put("team", structureTeams.get(e.getIndex()));
            s.put("destroyed_time_s", tickToSeconds(ctx.getTick()));
            structuresDestroyed.add(s);
        }

        if (typeName.equals("CCitadelItemPickupIdol")) {
            Double spawnTime = pendingUrnSpawns.remove(e.getIndex());
            Map<String, Object> u = new LinkedHashMap<>();
            u.put("spawn_time_s", spawnTime);
            u.put("pickup_time_s", tickToSeconds(ctx.getTick()));
            urnPickups.add(u);
        }
    }

    public void writeToJson(String outputPath) throws Exception {
        Map<String, Object> output = new LinkedHashMap<>();
        output.put("deaths", deaths);
        output.put("structures_destroyed", structuresDestroyed);
        output.put("patron_events", patronEvents);
        output.put("mid_boss_kills", midBossKills);
        output.put("rift_captures", riftCaptures);
        output.put("urn_pickups", urnPickups);

        var gson = new GsonBuilder().setPrettyPrinting().create();
        try (FileWriter writer = new FileWriter(outputPath)) {
            gson.toJson(output, writer);
        }
    }

    public static void main(String[] args) throws Exception {
        String replayPath = "replays/sample.dem";
        String outputPath = "output/parsed_match.json";
        new java.io.File("output").mkdirs();

        App app = new App();
        new SimpleRunner(new MappedFileSource(replayPath)).runWith(app);
        app.writeToJson(outputPath);

        System.out.println("Wrote " + app.deaths.size() + " deaths, " +
                app.structuresDestroyed.size() + " structures, " +
                app.patronEvents.size() + " patron events, " +
                app.midBossKills.size() + " mid boss kills, " +
                app.riftCaptures.size() + " rift captures, " +
                app.urnPickups.size() + " urn pickups to " + outputPath);
    }
}