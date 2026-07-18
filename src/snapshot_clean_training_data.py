# gets rid of broken matches

import pandas as pd
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

TRAINING_DATA_DIR = PROJECT_ROOT / "data" / "snapshot_data"

MATCHES_INPUT = TRAINING_DATA_DIR / "training_raw" / "training_matches.parquet"
OBJECTIVES_INPUT = TRAINING_DATA_DIR / "training_raw" / "training_objectives.parquet"

OUTPUT_DIR = TRAINING_DATA_DIR / "training_clean"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

MATCHES_OUTPUT = TRAINING_DATA_DIR / "training_clean" /"training_matches_clean.parquet"
OBJECTIVES_OUTPUT = TRAINING_DATA_DIR / "training_clean" /"training_objectives_clean.parquet"

matches = pd.read_parquet(MATCHES_INPUT)
objectives = pd.read_parquet(OBJECTIVES_INPUT)

print("CHECK: Identify and drop malformed matches")
rows_per_match = matches.groupby('match_id').size()
winners_per_match = matches.groupby('match_id')['won'].sum()

bad_row_count = rows_per_match[rows_per_match != 12].index
bad_winners = winners_per_match[winners_per_match != 6].index
bad_matches = set(bad_row_count) | set(bad_winners)

print(f"Bad match_ids found: {bad_matches}")
print(f"Dropping {len(bad_matches)} malformed matches out of {matches['match_id'].nunique()}")

matches_clean = matches[~matches['match_id'].isin(bad_matches)].copy()
objectives_clean = objectives[~objectives['match_id'].isin(bad_matches)].copy()

print(f"Remaining: {matches_clean['match_id'].nunique()} matches, {len(matches_clean)} rows")

print("\nCHECK: Objectives duplicate check")

obj_check = objectives_clean.copy()
for col in ['objective_ids', 'teams', 'destroyed_times']:
    if col in obj_check.columns:
        obj_check[col] = obj_check[col].apply(lambda x: str(list(x)) if hasattr(x, '__len__') else str(x))

dup_check = obj_check.groupby('match_id').apply(lambda x: x.duplicated().sum(), include_groups=False)
if dup_check.sum() > 0:
    print(f"Matches with duplicate objective rows:")
    print(dup_check[dup_check > 0].head(10))
else:
    print("No duplicate rows within any match's objectives.")

print("\nRe-verify cleaned data")
rows_per_match_clean = matches_clean.groupby('match_id').size()
print("Rows per match (should be all 12):")
print(rows_per_match_clean.value_counts())

winners_clean = matches_clean.groupby('match_id')['won'].sum()
print("\nWinners per match (should be all 6):")
print(winners_clean.value_counts())

print("\nSave cleaned versions")
matches_clean.to_parquet(MATCHES_OUTPUT)
objectives_clean.to_parquet(OBJECTIVES_OUTPUT)
print(f"Saved {MATCHES_OUTPUT} ({matches_clean.shape[0]} rows)")
print(f"Saved {OBJECTIVES_OUTPUT} ({objectives_clean.shape[0]} rows)")