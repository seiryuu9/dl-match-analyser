import requests
import json
import time
import os

BASE = "https://api.deadlock-api.com"
RAW_DIR = "raw"

os.makedirs(RAW_DIR, exist_ok=True)


def get_match_ids(limit=50):
    
    resp = requests.get(f"{BASE}/v1/matches/recently-fetched")
    resp.raise_for_status()
    matches = resp.json()
    match_ids = [m["match_id"] for m in matches if m.get("duration_s", 0) > 300]
    return match_ids[:limit]


def fetch_match(match_id):
    r = requests.get(f"{BASE}/v1/matches/{match_id}/metadata")
    r.raise_for_status()
    return r.json()


def main():
    match_ids = get_match_ids(limit=50)
    print(f"Found {len(match_ids)} match_ids to fetch")

    for i, match_id in enumerate(match_ids):
        out_path = f"{RAW_DIR}/{match_id}.json"

        if os.path.exists(out_path):
            print(f"[{i+1}/{len(match_ids)}] {match_id} already saved, skipping")
            continue

        try:
            data = fetch_match(match_id)
            with open(out_path, "w") as f:
                json.dump(data, f)
            print(f"[{i+1}/{len(match_ids)}] Saved {match_id}")
        except requests.exceptions.HTTPError as e:
            print(f"[{i+1}/{len(match_ids)}] FAILED {match_id}: {e}")

        time.sleep(0.5)


if __name__ == "__main__":
    main()