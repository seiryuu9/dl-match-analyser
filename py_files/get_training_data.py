import duckdb

DUCKLAKE_URL = "ducklake:https://s3-cache.deadlock-api.com/fast/db_snapshot.ducklake"

con = duckdb.connect()

con.execute("""
    INSTALL ducklake;
    LOAD ducklake;
    INSTALL httpfs;
    LOAD httpfs;
    CREATE OR REPLACE SECRET deadlock_s3 (
        TYPE S3,
        KEY_ID '',
        SECRET '',
        ENDPOINT 's3-cache.deadlock-api.com',
        URL_STYLE 'path',
        USE_SSL true
    );
""")
con.execute(f"ATTACH '{DUCKLAKE_URL}' AS db (READ_ONLY)")
con.execute("USE db.main")

print("Exporting match summary + player stats")

con.sql("""
    COPY (
        SELECT
            match_id,
            account_id,
            hero_id,
            team,
            won,
            duration_s,
            kills,
            deaths,
            assists,
            net_worth,
            last_hits,
            denies,
            player_level,
            "stats.time_stamp_s"    AS ts_time,
            "stats.net_worth"       AS ts_net_worth,
            "stats.kills"           AS ts_kills,
            "stats.deaths"          AS ts_deaths,
            "stats.player_damage"   AS ts_player_damage
        FROM match_player
        WHERE duration_s > 900 AND duration_s < 3600  
        LIMIT 5000
    ) TO 'training_matches.parquet' (FORMAT PARQUET)
""")

print("Done. Saved to training_matches.parquet")

con.sql("""
    COPY (
        SELECT DISTINCT
            match_id,
            "objectives.team_objective"   AS objective_ids,
            "objectives.team"             AS teams,
            "objectives.destroyed_time_s" AS destroyed_times
        FROM match_player
        WHERE duration_s > 900 AND duration_s < 3600
        LIMIT 5000
    ) TO 'training_objectives.parquet' (FORMAT PARQUET)
""")

print("Done. Saved to training_objectives.parquet")

con.close()