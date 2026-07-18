import requests
import json
import time
import pandas as pd
from pathlib import Path

BASE = "https://api.deadlock-api.com"

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT_CLEAN_DIR = PROJECT_ROOT / "data" / "snapshot_data" / "training_clean"
EVENT_RAW_DIR = PROJECT_ROOT / "data" / "event_data" / "raw"
EVENT_RAW_DIR.mkdir(parents=True, exist_ok=True)

MATCHES_INPUT = SNAPSHOT_CLEAN_DIR / "training_matches_clean.parquet"
OUTPUT_PATH = EVENT_RAW_DIR / "event_data.json"

BATCH_SIZE = 500
SLEEP_BETWEEN_BATCHES = 2.0
MAX_RETRIES = 5

def get_match_ids():
    matches = pd.read_parquet(MATCHES_INPUT)
    return matches['match_id'].unique().tolist()

def load_existing_results():
    if OUTPUT_PATH.exists():
        with open(OUTPUT_PATH, "r") as f:
            existing = json.load(f)
        existing_ids = {m["match_id"] for m in existing}
        print(f"Found {len(existing)} matches already saved, will skip these")
        return existing, existing_ids
    return [], set()

def fetch_batch(match_ids_batch):
    url = f"{BASE}/v1/matches/metadata"
    params = {
        "match_ids": ",".join(str(m) for m in match_ids_batch),
        "include_player_death_details": "true",
        "include_objectives": "true",
        "include_mid_boss": "true",
        "include_player_info": "true",
    }

    for attempt in range(1, MAX_RETRIES + 1):
        r = requests.get(url, params=params)
        if r.status_code == 429:
            wait = 2 ** attempt
            print(f"  Rate limited. Waiting {wait}s before retry {attempt}/{MAX_RETRIES}...")
            time.sleep(wait)
            continue
        r.raise_for_status()
        return r.json()

    raise RuntimeError(f"Failed after {MAX_RETRIES} retries due to rate limiting")

def main():
    all_match_ids = get_match_ids()
    print(f"Loaded {len(all_match_ids)} match_ids from snapshot data")

    all_results, existing_ids = load_existing_results()

    remaining_ids = [m for m in all_match_ids if m not in existing_ids]
    print(f"{len(remaining_ids)} match_ids remaining to fetch")

    for i in range(0, len(remaining_ids), BATCH_SIZE):
        batch = remaining_ids[i:i + BATCH_SIZE]
        try:
            data = fetch_batch(batch)
            all_results.extend(data)
            print(f"Fetched batch {i // BATCH_SIZE + 1} "
                  f"({i + len(batch)}/{len(remaining_ids)} remaining matches)")

            with open(OUTPUT_PATH, "w") as f:
                json.dump(all_results, f)

        except (requests.exceptions.HTTPError, RuntimeError) as e:
            print(f"FAILED batch starting at index {i}: {e}")

        time.sleep(SLEEP_BETWEEN_BATCHES)

    print(f"Done. Saved {len(all_results)} matches total to {OUTPUT_PATH}")

if __name__ == "__main__":
    main()