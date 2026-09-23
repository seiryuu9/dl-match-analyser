package org.example;

import com.google.gson.GsonBuilder;
import com.google.protobuf.ByteString;
import skadistats.clarity.event.Insert;
import skadistats.clarity.model.Entity;
import skadistats.clarity.model.FieldPath;
import skadistats.clarity.model.StringTable;
import skadistats.clarity.processor.entities.*;
import skadistats.clarity.processor.runner.Context;
import skadistats.clarity.processor.runner.SimpleRunner;
import skadistats.clarity.processor.stringtables.OnStringTableEntry;
import skadistats.clarity.processor.stringtables.UsesStringTable;
import skadistats.clarity.source.MappedFileSource;

import java.io.FileWriter;
import java.util.*;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

@UsesEntities
@UsesStringTable("userinfo")
public class App {

    private static final double TICKS_PER_SECOND = 64.0;
    private static final int SAMPLE_INTERVAL_SECONDS = 15;

    private static final Map<String, String> STRUCTURE_TYPES = Map.of(
            "CNPC_Boss_Tier2", "Tier1Structure",
            "CNPC_TrooperBoss", "Tier2Structure",
            "CNPC_BarrackBoss", "BaseGuardian",
            "CCitadel_Destroyable_Building", "InnerTower"
    );

    private static final Pattern PRINTABLE_RUN = Pattern.compile("[\\x20-\\x7E]{2,32}");

    @Insert
    private Context ctx;

    private final Map<Integer, Integer> playerTeams = new HashMap<>();
    private final Map<Integer, Integer> controllerToPawn = new HashMap<>();
    private final Map<Integer, Integer> controllerTeams = new HashMap<>();
    private final Map<Integer, Integer> lastPlayerLifeState = new HashMap<>();
    private final Map<Integer, Double> lastDeathTime = new HashMap<>();
    private final Map<Integer, String> userinfoNames = new TreeMap<>();

    private final Map<Integer, Integer> structureTeams = new HashMap<>();
    private final Map<Integer, Integer> patronLifeState = new HashMap<>();
    private final Map<Integer, Integer> midBossLifeState = new HashMap<>();
    private final Map<Integer, Boolean> hasRejuvenatorMap = new HashMap<>();

    private final List<Map<String, Object>> deaths = new ArrayList<>();
    private final List<Map<String, Object>> structuresDestroyed = new ArrayList<>();
    private final List<Map<String, Object>> patronEvents = new ArrayList<>();
    private final List<Map<String, Object>> midBossKills = new ArrayList<>();
    private final List<Map<String, Object>> riftCaptures = new ArrayList<>();
    private final List<Map<String, Object>> urnPickups = new ArrayList<>();
    private final List<Map<String, Object>> rejuvenatorClaims = new ArrayList<>();

    private final Map<Integer, Double> pendingRiftSpawns = new HashMap<>();
    private final Map<Integer, Double> pendingUrnSpawns = new HashMap<>();

    private final Map<Integer, PlayerStats> playerStats = new TreeMap<>();
    private final List<Map<String, Object>> statSnapshots = new ArrayList<>();
    private int nextSampleTick = 0;

    private static class PlayerStats {
        int kills = 0, deaths = 0, assists = 0, heroDamage = 0, objectiveDamage = 0, goldNetWorth = 0;
    }

    private double tickToSeconds(int tick) {
        return tick / TICKS_PER_SECOND;
    }

    private int pawnIndexFromHandle(int rawHandle) {
        return rawHandle & 0x3FFF;
    }

    private String extractName(ByteString value) {
        if (value == null) return null;
        Matcher m = PRINTABLE_RUN.matcher(value.toStringUtf8());
        return m.find() ? m.group().trim() : null;
    }

    private String resolveUsernameForPawn(int pawnIndex) {
        for (Map.Entry<Integer, Integer> entry : controllerToPawn.entrySet()) {
            if (entry.getValue() == pawnIndex) {
                return userinfoNames.get(entry.getKey() - 1);
            }
        }
        return null;
    }

    @OnStringTableEntry("userinfo")
    public void onStringTableEntry(StringTable table, int index, String key, ByteString value) {
        String name = extractName(value);
        if (name != null && !name.isBlank()) {
            userinfoNames.put(index, name);
        }
    }

    @OnEntityCreated
    public void onEntityCreated(Entity e) {
        String typeName = e.getDtClass().getDtName();

        if (typeName.equals("CCitadelPlayerPawn") && e.hasProperty("m_iTeamNum")) {
            Integer team = (Integer) e.getProperty("m_iTeamNum");
            if (team != null && (team == 2 || team == 3)) {
                playerTeams.put(e.getIndex(), team);
            }
        }

        if (STRUCTURE_TYPES.containsKey(typeName) && e.hasProperty("m_iTeamNum")) {
            structureTeams.put(e.getIndex(), (Integer) e.getProperty("m_iTeamNum"));
        }

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

        if (typeName.equals("CCitadelItemPickupIdol")) {
            pendingUrnSpawns.put(e.getIndex(), tickToSeconds(ctx.getTick()));
        }
    }

    @OnEntityUpdated
    public void onEntityUpdated(Entity e, FieldPath[] updatedPaths, int updateCount) {
        String typeName = e.getDtClass().getDtName();

        if (typeName.equals("CCitadelPlayerPawn")) {
            if (e.hasProperty("m_iTeamNum")) {
                Integer team = (Integer) e.getProperty("m_iTeamNum");
                if (team != null && (team == 2 || team == 3)) {
                    int pawnIndex = e.getIndex();
                    playerTeams.put(pawnIndex, team);
                    for (Map.Entry<Integer, Integer> entry : controllerToPawn.entrySet()) {
                        if (entry.getValue() == pawnIndex) {
                            controllerTeams.put(entry.getKey(), team);
                        }
                    }
                }
            }

            if (e.hasProperty("m_lifeState")) {
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
                        d.put("username", resolveUsernameForPawn(e.getIndex()));
                        d.put("game_time_s", t);
                        d.put("death_duration_s", null);
                        d.put("respawn_full_health", null);
                        deaths.add(d);
                    } else if (newState == 0 && oldState != null && oldState == 2) {
                        Double deathTime = lastDeathTime.get(e.getIndex());
                        if (deathTime != null) {
                            double respawnDuration = t - deathTime;
                            Integer health = e.hasProperty("m_iHealth") ? (Integer) e.getProperty("m_iHealth") : null;
                            Integer healthMax = e.hasProperty("m_iHealthMax") ? (Integer) e.getProperty("m_iHealthMax") : null;
                            boolean fullHealth = health != null && healthMax != null && health.equals(healthMax);

                            for (int i = deaths.size() - 1; i >= 0; i--) {
                                Map<String, Object> d = deaths.get(i);
                                if (d.get("player_index").equals(e.getIndex()) && d.get("death_duration_s") == null) {
                                    d.put("death_duration_s", respawnDuration);
                                    d.put("respawn_full_health", fullHealth);
                                    break;
                                }
                            }
                        }
                    }
                }
            }
        }

        if (typeName.equals("CCitadelPlayerController")) {
            if (e.hasProperty("m_hPawn")) {
                Integer rawHandle = (Integer) e.getProperty("m_hPawn");
                if (rawHandle != null) {
                    int pawnIndex = pawnIndexFromHandle(rawHandle);
                    if (pawnIndex != 16383) {
                        int controllerIndex = e.getIndex();
                        controllerToPawn.put(controllerIndex, pawnIndex);
                        Integer team = playerTeams.get(pawnIndex);
                        if (team != null) {
                            controllerTeams.put(controllerIndex, team);
                        }
                    }
                }
            }

            PlayerStats stats = playerStats.computeIfAbsent(e.getIndex(), k -> new PlayerStats());
            if (e.hasProperty("m_iPlayerKills")) stats.kills = (Integer) e.getProperty("m_iPlayerKills");
            if (e.hasProperty("m_iDeaths")) stats.deaths = (Integer) e.getProperty("m_iDeaths");
            if (e.hasProperty("m_iPlayerAssists")) stats.assists = (Integer) e.getProperty("m_iPlayerAssists");
            if (e.hasProperty("m_iHeroDamage")) stats.heroDamage = (Integer) e.getProperty("m_iHeroDamage");
            if (e.hasProperty("m_iObjectiveDamage")) stats.objectiveDamage = (Integer) e.getProperty("m_iObjectiveDamage");
            if (e.hasProperty("m_iGoldNetWorth")) stats.goldNetWorth = (Integer) e.getProperty("m_iGoldNetWorth");

            if (e.hasProperty("m_bHasRejuvenator")) {
                Boolean hasRejuvenator = (Boolean) e.getProperty("m_bHasRejuvenator");
                Boolean oldValue = hasRejuvenatorMap.get(e.getIndex());

                if (Boolean.TRUE.equals(hasRejuvenator) && !Boolean.TRUE.equals(oldValue)) {
                    double t = tickToSeconds(ctx.getTick());
                    Map<String, Object> rc = new LinkedHashMap<>();
                    rc.put("controller_index", e.getIndex());
                    rc.put("team", controllerTeams.get(e.getIndex()));
                    rc.put("game_time_s", t);
                    rejuvenatorClaims.add(rc);
                }

                hasRejuvenatorMap.put(e.getIndex(), hasRejuvenator);
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

        maybeSampleStats();
    }

    private void maybeSampleStats() {
        int currentTick = ctx.getTick();
        if (currentTick < nextSampleTick) return;

        Map<String, Object> snapshot = new LinkedHashMap<>();
        snapshot.put("game_time_s", tickToSeconds(currentTick));

        List<Map<String, Object>> playerList = new ArrayList<>();
        for (Map.Entry<Integer, PlayerStats> entry : playerStats.entrySet()) {
            int controllerIndex = entry.getKey();
            PlayerStats s = entry.getValue();
            Integer team = controllerTeams.get(controllerIndex);
            if (team == null) continue;

            Map<String, Object> p = new LinkedHashMap<>();
            p.put("controller_index", controllerIndex);
            p.put("team", team);
            p.put("kills", s.kills);
            p.put("deaths", s.deaths);
            p.put("assists", s.assists);
            p.put("hero_damage", s.heroDamage);
            p.put("objective_damage", s.objectiveDamage);
            p.put("gold_net_worth", s.goldNetWorth);
            playerList.add(p);
        }
        snapshot.put("players", playerList);
        statSnapshots.add(snapshot);

        nextSampleTick = currentTick + (int) (SAMPLE_INTERVAL_SECONDS * TICKS_PER_SECOND);
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

    private List<Map<String, Object>> buildPlayerRoster() {
        List<Map<String, Object>> roster = new ArrayList<>();
        for (Map.Entry<Integer, Integer> entry : new TreeMap<>(controllerTeams).entrySet()) {
            int controllerIndex = entry.getKey();
            int team = entry.getValue();
            String username = userinfoNames.get(controllerIndex - 1);
            Integer pawnIndex = controllerToPawn.get(controllerIndex);

            Map<String, Object> p = new LinkedHashMap<>();
            p.put("controller_index", controllerIndex);
            p.put("pawn_index", pawnIndex);
            p.put("team", team);
            p.put("username", username);
            roster.add(p);
        }
        return roster;
    }

    public void writeToJson(String outputPath) throws Exception {
        Map<String, Object> output = new LinkedHashMap<>();
        output.put("players", buildPlayerRoster());
        output.put("deaths", deaths);
        output.put("structures_destroyed", structuresDestroyed);
        output.put("patron_events", patronEvents);
        output.put("mid_boss_kills", midBossKills);
        output.put("rift_captures", riftCaptures);
        output.put("urn_pickups", urnPickups);
        output.put("rejuvenator_claims", rejuvenatorClaims);
        output.put("stat_snapshots", statSnapshots);

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

        System.out.println("Wrote " + app.buildPlayerRoster().size() + " players, " +
                app.deaths.size() + " deaths, " +
                app.structuresDestroyed.size() + " structures, " +
                app.patronEvents.size() + " patron events, " +
                app.midBossKills.size() + " mid boss kills, " +
                app.riftCaptures.size() + " rift captures, " +
                app.urnPickups.size() + " urn pickups, " +
                app.rejuvenatorClaims.size() + " rejuvenator claims, " +
                app.statSnapshots.size() + " stat snapshots to " + outputPath);
    }
}