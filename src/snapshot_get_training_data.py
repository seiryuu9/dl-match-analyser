# snapshot from 16/07/2026 (I will retrain the model every few patches)

import duckdb
from pathlib import Path

DUCKLAKE_URL = "ducklake:https://s3-cache.deadlock-api.com/fast/db_snapshot.ducklake"
TARGET_MATCHES = 10000


PROJECT_ROOT = Path(__file__).resolve().parent.parent

OUTPUT_DIR = PROJECT_ROOT / "data" / "snapshot_data" / "training_raw"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

MATCHES_OUTPUT = OUTPUT_DIR / "training_matches.parquet"
OBJECTIVES_OUTPUT = OUTPUT_DIR / "training_objectives.parquet"

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

print("Listing underlying files for match_player")
files = con.sql("SELECT file FROM glob('s3://db-snapshot/public/match_player/*.parquet')").fetchall()
files = [f[0] for f in files]
print(f"Found {len(files)} underlying parquet files")

good_files = []
for f in files:
    try:
        con.sql(f"SELECT 1 FROM read_parquet('{f}') LIMIT 1")
        good_files.append(f)
    except Exception as e:
        print(f"Skipping broken file: {f} ({e})")

print(f"{len(good_files)} / {len(files)} files are readable")

if not good_files:
    raise RuntimeError("No readable files found — check bucket path / credentials")

file_list_sql = ", ".join(f"'{f}'" for f in good_files)

print(f"Selecting {TARGET_MATCHES} target matches")
con.sql(f"""
    CREATE OR REPLACE TABLE memory.target_matches AS
    SELECT DISTINCT match_id
    FROM read_parquet([{file_list_sql}])
    WHERE duration_s > 900 AND duration_s < 3600
    LIMIT {TARGET_MATCHES}
""")
n_matches = con.sql("SELECT COUNT(*) FROM memory.target_matches").fetchone()[0]
print(f"Got {n_matches} unique match_ids")

print("Exporting match summary + player stats")
con.sql(f"""
    COPY (
        SELECT
            mp.match_id,
            mp.account_id,
            mp.hero_id,
            mp.team,
            mp.won,
            mp.duration_s,
            mp.kills,
            mp.deaths,
            mp.assists,
            mp.net_worth,
            mp.last_hits,
            mp.denies,
            mp.player_level,
            mp."stats.time_stamp_s"    AS ts_time,
            mp."stats.net_worth"       AS ts_net_worth,
            mp."stats.kills"           AS ts_kills,
            mp."stats.deaths"          AS ts_deaths,
            mp."stats.player_damage"   AS ts_player_damage
        FROM read_parquet([{file_list_sql}]) mp
        JOIN memory.target_matches tm USING (match_id)
    ) TO '{MATCHES_OUTPUT}' (FORMAT PARQUET)
""")
print("Done. Saved to training_matches.parquet")

print("Exporting objectives")
con.sql(f"""
    COPY (
        SELECT DISTINCT
            mp.match_id,
            mp."objectives.team_objective"   AS objective_ids,
            mp."objectives.team"             AS teams,
            mp."objectives.destroyed_time_s" AS destroyed_times
        FROM read_parquet([{file_list_sql}]) mp
        JOIN memory.target_matches tm USING (match_id)
    ) TO '{OBJECTIVES_OUTPUT}' (FORMAT PARQUET)
""")
print("Done. Saved to training_objectives.parquet")

con.close()