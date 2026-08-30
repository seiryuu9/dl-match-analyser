package org.example;

import skadistats.clarity.event.Insert;
import skadistats.clarity.model.Entity;
import skadistats.clarity.processor.entities.OnEntityCreated;
import skadistats.clarity.processor.entities.UsesEntities;
import skadistats.clarity.processor.runner.Context;
import skadistats.clarity.processor.runner.SimpleRunner;
import skadistats.clarity.source.MappedFileSource;

import java.util.Set;

@UsesEntities
public class App {

    @Insert
    private Context ctx;

    private static final Set<String> TARGET_TYPES = Set.of(
            "CCitadelItemKothSpawner",
            "CCitadel_KothCashIn",
            "CCitadelTriggerCapturePoint"
    );

    @OnEntityCreated
    public void onEntityCreated(Entity e) {
        String typeName = e.getDtClass().getDtName();
        if (TARGET_TYPES.contains(typeName)) {
            System.out.printf("tick %06d: CREATED %s (index %d)%n", ctx.getTick(), typeName, e.getIndex());
        }
    }

    public static void main(String[] args) throws Exception {
        String replayPath = "replays/sample.dem";
        new SimpleRunner(new MappedFileSource(replayPath)).runWith(new App());
    }

}

