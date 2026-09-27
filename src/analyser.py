import json
import subprocess
import pandas as pd
import numpy as np
import torch
import torch.nn as nn
from pathlib import Path

# 1. CONSTANTS & CONFIGURATION
PROJECT_ROOT = Path(__file__).resolve().parent.parent  # points to dl-match-analyser

STRUCTURE_DISPLAY_NAMES = {
    "Tier1Structure": "Guardian",
    "Tier2Structure": "Walker",
    "BaseGuardian": "Base Guardian",
    "InnerTower": "Shrine",
    "Patron": "Patron"
}
QUIET_NET_CHANGE_THRESHOLD = 10
FAST_RESPAWN_THRESHOLD_S = 4.0
REJUV_WINDOW_S = 180
TEAM_MAPPING = {2: "Team0", 3: "Team1"}


# 2. ML MODEL DEFINITION
class WinProbabilityLSTM(nn.Module):
    def __init__(self, input_size, hidden_size=32, num_layers=1):
        super().__init__()
        self.lstm = nn.LSTM(input_size=input_size, hidden_size=hidden_size, num_layers=num_layers, batch_first=True)
        self.fc = nn.Linear(hidden_size, 1)

    def forward(self, x):
        lstm_out, _ = self.lstm(x)
        return self.fc(lstm_out).squeeze(-1)


# 3. HELPER FUNCTIONS
def format_time(seconds):
    m = int(seconds // 60)
    s = int(seconds % 60)
    return f"{m}:{s:02d}"


def get_win_prob_pct(prob):
    return prob * 100


def structure_name(event_or_row):
    if isinstance(event_or_row, dict):
        raw_type = event_or_row.get('structure_type', '')
        lane = event_or_row.get('lane')
    else:
        raw_type = event_or_row['structure_type']
        lane = event_or_row.get('lane') if 'lane' in event_or_row else None

    base_name = STRUCTURE_DISPLAY_NAMES.get(raw_type, raw_type)
    if lane is not None and pd.notna(lane):
        return f"{str(lane).capitalize()} {base_name}"
    return base_name


def get_event_polarity(event, user_raw_team):
    is_user_team = event.get("team") == user_raw_team
    if event["type"] == "death":
        return -1 if is_user_team else 1
    elif event["type"] == "structure":
        return -1 if is_user_team else 1
    elif event["type"] == "mid_boss":
        return 1 if event["team_claimed"] == user_raw_team else -1
    elif event["type"] in ["urn_pickup", "rift_capture"]:
        return 1 if event["team"] == user_raw_team else -1
    return 0


def event_to_phrase(event, user_raw_team):
    is_user_team = event.get("team") == user_raw_team
    if event["type"] == "death":
        possessive = "your teammate" if is_user_team else "the enemy"
        return f"{possessive} {event['username']} died at {format_time(event['time'])}"
    if event["type"] == "structure":
        return f"{'the enemy' if is_user_team else 'your team'} destroyed {'your' if is_user_team else 'an enemy'} {structure_name(event)} at {format_time(event['time'])}"
    if event["type"] == "mid_boss":
        return f"{'your team' if event['team_claimed'] == user_raw_team else 'the enemy'} claimed the Mid Boss Rejuvenator at {format_time(event['time'])}"
    if event["type"] in ["urn_pickup", "rift_capture"]:
        action = "secured the Urn" if event["type"] == "urn_pickup" else "cashed in the Rift"
        return f"{'your team' if event['team'] == user_raw_team else 'the enemy'} {action} at {format_time(event['time'])}"
    return None


def find_followup_structure(claiming_team, after_time, structures_df, window_s=90):
    candidates = structures_df[
        (structures_df["team"] != claiming_team) &
        (structures_df["destroyed_time_s"] >= after_time) &
        (structures_df["destroyed_time_s"] <= after_time + window_s)
        ].sort_values("destroyed_time_s")
    return candidates.iloc[0] if not candidates.empty else None


def find_followup_structure_after_death(death_team, death_time, structures_df, window_s=90):
    candidates = structures_df[
        (structures_df["team"] == death_team) &
        (structures_df["destroyed_time_s"] >= death_time) &
        (structures_df["destroyed_time_s"] <= death_time + window_s)
        ].sort_values("destroyed_time_s")
    return candidates.iloc[0] if not candidates.empty else None


def get_dynamic_threshold(game_time_s):
    minutes = game_time_s / 60
    if minutes < 10:
        return 0.08
    elif minutes < 25:
        return 0.05
    else:
        return 0.03


def infer_team_from_net_worth_spike(event_time, merged_df):
    before = merged_df[merged_df["game_time_s"] <= event_time].tail(1)
    after = merged_df[merged_df["game_time_s"] >= event_time].head(1)
    if before.empty or after.empty: return None
    delta_0 = after["gold_net_worth_team0"].values[0] - before["gold_net_worth_team0"].values[0]
    delta_1 = after["gold_net_worth_team1"].values[0] - before["gold_net_worth_team1"].values[0]
    return 2 if delta_0 > delta_1 else 3 if delta_1 > delta_0 else None


def assign_credits_to_claims(deaths_df, rejuvenator_df):
    fast_deaths = deaths_df[deaths_df["death_duration_s"] < FAST_RESPAWN_THRESHOLD_S].copy()
    claim_counts = {}
    for _, d in fast_deaths.iterrows():
        team_claims = rejuvenator_df[
            (rejuvenator_df["team"] == d["team"]) & (rejuvenator_df["game_time_s"] <= d["game_time_s"])].sort_values(
            "game_time_s")
        if team_claims.empty: continue
        nearest_claim_time = team_claims.iloc[-1]["game_time_s"]
        if d["game_time_s"] - nearest_claim_time > REJUV_WINDOW_S: continue
        used_so_far = claim_counts.get(nearest_claim_time, 0)
        if used_so_far >= 3: continue
        claim_counts[nearest_claim_time] = used_so_far + 1
    return claim_counts


def find_nearest_events(swing_time, deaths_df, structures_df, mid_boss_df, rejuvenator_df, urn_df, rift_df,
                        lookback_s=30):
    events = []

    for _, d in deaths_df[
        (deaths_df["game_time_s"] <= swing_time) & (deaths_df["game_time_s"] >= swing_time - lookback_s)].iterrows():
        events.append({"type": "death", "time": d["game_time_s"], "team": d["team"], "player_index": d["player_index"],
                       "username": d["username"]})

    for _, s in structures_df[(structures_df["destroyed_time_s"] <= swing_time) & (
            structures_df["destroyed_time_s"] >= swing_time - lookback_s)].iterrows():
        events.append({"type": "structure", "time": s["destroyed_time_s"], "team": s["team"],
                       "structure_type": s["structure_type"], "lane": s.get("lane")})

    for _, mb in mid_boss_df[(mid_boss_df["killed_time_s"] <= swing_time) & (
            mid_boss_df["killed_time_s"] >= swing_time - lookback_s)].iterrows():
        events.append({"type": "mid_boss", "time": mb["killed_time_s"], "team_claimed": mb["team_claimed"]})

    for _, r in rejuvenator_df[(rejuvenator_df["game_time_s"] <= swing_time) & (
            rejuvenator_df["game_time_s"] >= swing_time - lookback_s)].iterrows():
        events.append({"type": "rejuv_claim", "time": r["game_time_s"], "team": r["team"]})

    for _, u in urn_df[
        (urn_df["pickup_time_s"] <= swing_time) & (urn_df["pickup_time_s"] >= swing_time - lookback_s)].iterrows():
        events.append({"type": "urn_pickup", "time": u["pickup_time_s"], "team": u["team"]})

    for _, r in rift_df[
        (rift_df["cashin_time_s"] <= swing_time) & (rift_df["cashin_time_s"] >= swing_time - lookback_s)].iterrows():
        events.append({"type": "rift_capture", "time": r["cashin_time_s"], "team": r["team"]})

    return sorted(events, key=lambda e: e["time"], reverse=True)


# 4. CORE PIPELINE FUNCTIONS
def parse_replay_with_java(dem_path, output_json_path, parser_jar_path):
    print(f"Parsing replay: {dem_path}...", file=sys.stderr)
    subprocess.run(["java", "-jar", parser_jar_path, dem_path, output_json_path], check=True)
    print("Parsing complete.", file=sys.stderr)


def analyze_match(json_path, target_username, model_path):
    # 1. Load JSON Data
    with open(json_path, "r") as f:
        data = json.load(f)

    players_df = pd.DataFrame(data["players"])
    deaths_df = pd.DataFrame(data["deaths"])
    structures_df = pd.DataFrame(data["structures_destroyed"])
    mid_boss_df = pd.DataFrame(data["mid_boss_kills"])
    rejuvenator_df = pd.DataFrame(data["rejuvenator_claims"])
    urn_df = pd.DataFrame(data.get("urn_pickups", []))
    rift_df = pd.DataFrame(data.get("rift_captures", []))

    # Identify user
    match = players_df[players_df["username"] == target_username]
    if match.empty: raise ValueError(f"No player found with username '{target_username}'")
    user_raw_team = match.iloc[0]["team"]

    # 2. Build Stat Snapshots
    rows = []
    for snap in data["stat_snapshots"]:
        t = snap["game_time_s"]
        for p in snap["players"]:
            p["game_time_s"] = t
            rows.append(p)

    team_snapshots = pd.DataFrame(rows).groupby(["game_time_s", "team"], as_index=False).agg({
        "kills": "sum", "deaths": "sum", "assists": "sum",
        "hero_damage": "sum", "objective_damage": "sum", "gold_net_worth": "sum"
    })

    team_wide = team_snapshots.pivot(index="game_time_s", columns="team")
    team_wide.columns = [f"{stat}_team{0 if team == 2 else 1}" for stat, team in team_wide.columns]
    team_wide = team_wide.reset_index().sort_values("game_time_s")

    # 3. Structures & Mid Boss
    if not structures_df.empty:
        structures_df["destroying_team"] = structures_df["team"].map({2: 3, 3: 2})
        structures_df["perspective_team"] = structures_df["destroying_team"].map(TEAM_MAPPING)
        structures_df = structures_df.sort_values("destroyed_time_s")
        structures_df["team0_cumulative"] = (structures_df["perspective_team"] == "Team0").cumsum()
        structures_df["team1_cumulative"] = (structures_df["perspective_team"] == "Team1").cumsum()

    mb_list = []
    for _, boss in mid_boss_df.iterrows():
        b_time = boss["killed_time_s"]
        claims = rejuvenator_df[
            (rejuvenator_df["game_time_s"] >= b_time) & (rejuvenator_df["game_time_s"] <= b_time + 30)].sort_values(
            "game_time_s")
        team = claims.iloc[0]["team"] if not claims.empty else None
        mb_list.append({"killed_time_s": b_time, "team_claimed": team, "perspective_team": TEAM_MAPPING.get(team)})

    mid_boss_df = pd.DataFrame(mb_list).sort_values("killed_time_s") if mb_list else pd.DataFrame(
        columns=["killed_time_s", "team_claimed", "perspective_team"])
    if not mid_boss_df.empty:
        mid_boss_df["team0_cumulative"] = (mid_boss_df["perspective_team"] == "Team0").cumsum()
        mid_boss_df["team1_cumulative"] = (mid_boss_df["perspective_team"] == "Team1").cumsum()

    # 4. Merge All Features
    merged = team_wide.copy()
    if not structures_df.empty:
        merged = pd.merge_asof(merged,
                               structures_df[['destroyed_time_s', 'team0_cumulative', 'team1_cumulative']].rename(
                                   columns={'team0_cumulative': 'own_objectives_cumulative',
                                            'team1_cumulative': 'enemy_objectives_cumulative'}), left_on="game_time_s",
                               right_on="destroyed_time_s", direction="backward")
    if not mid_boss_df.empty:
        merged = pd.merge_asof(merged, mid_boss_df[['killed_time_s', 'team0_cumulative', 'team1_cumulative']].rename(
            columns={'team0_cumulative': 'own_mid_boss_claims', 'team1_cumulative': 'enemy_mid_boss_claims'}),
                               left_on="game_time_s", right_on="killed_time_s", direction="backward")

    for col in ["own_objectives_cumulative", "enemy_objectives_cumulative", "own_mid_boss_claims",
                "enemy_mid_boss_claims"]:
        if col in merged.columns: merged[col] = merged[col].fillna(0).astype("int64")

    if not urn_df.empty: urn_df["team"] = urn_df["pickup_time_s"].apply(
        lambda t: infer_team_from_net_worth_spike(t, merged))
    if not rift_df.empty: rift_df["team"] = rift_df["cashin_time_s"].apply(
        lambda t: infer_team_from_net_worth_spike(t, merged))

    # 5. Build Final Target Features
    own_col, enemy_col = ("team0", "team1") if user_raw_team == 2 else ("team1", "team0")
    merged['net_worth_diff'] = merged[f'gold_net_worth_{own_col}'] - merged[f'gold_net_worth_{enemy_col}']
    merged['kills_diff'] = merged[f'kills_{own_col}'] - merged[f'kills_{enemy_col}']
    merged['deaths_diff'] = merged[f'deaths_{own_col}'] - merged[f'deaths_{enemy_col}']
    merged['damage_diff'] = merged[f'hero_damage_{own_col}'] - merged[f'hero_damage_{enemy_col}']

    if user_raw_team == 3:
        if 'own_objectives_cumulative' in merged.columns: merged[
            ['own_objectives_cumulative', 'enemy_objectives_cumulative']] = merged[
            ['enemy_objectives_cumulative', 'own_objectives_cumulative']].values
        if 'own_mid_boss_claims' in merged.columns: merged[['own_mid_boss_claims', 'enemy_mid_boss_claims']] = merged[
            ['enemy_mid_boss_claims', 'own_mid_boss_claims']].values

    merged['objectives_diff'] = merged.get('own_objectives_cumulative', 0) - merged.get('enemy_objectives_cumulative',
                                                                                        0)
    merged['mid_boss_diff'] = merged.get('own_mid_boss_claims', 0) - merged.get('enemy_mid_boss_claims', 0)
    merged['own_deaths_cumulative'] = merged[f'deaths_{own_col}']
    merged['enemy_deaths_cumulative'] = merged[f'deaths_{enemy_col}']
    merged['deaths_cumulative_diff'] = merged['own_deaths_cumulative'] - merged['enemy_deaths_cumulative']

    # 6. Run PyTorch Inference
    checkpoint = torch.load(model_path, map_location="cpu", weights_only=False)
    model = WinProbabilityLSTM(input_size=checkpoint["input_size"], hidden_size=checkpoint["hidden_size"])
    model.load_state_dict(checkpoint["model_state_dict"])
    model.eval()

    feature_array = merged[checkpoint["feature_cols"]].fillna(0).values.astype("float32")
    with torch.no_grad():
        win_probs = torch.sigmoid(model(torch.tensor(feature_array).unsqueeze(0))).squeeze(0).numpy()

    merged["win_prob_own"] = win_probs
    merged["win_prob_smoothed"] = merged["win_prob_own"].rolling(window=3, center=True, min_periods=1).mean()
    merged["win_prob_delta_smoothed"] = merged["win_prob_smoothed"].diff(periods=2)

    # 7. Find Swings
    thresholds = merged["game_time_s"].apply(get_dynamic_threshold)
    swings = merged[merged["win_prob_delta_smoothed"].abs() >= thresholds]

    attributed_swings = []
    for _, row in swings.iterrows():
        t, delta = row["game_time_s"], row["win_prob_delta_smoothed"]
        events = find_nearest_events(t, deaths_df, structures_df, mid_boss_df, rejuvenator_df, urn_df, rift_df)
        attributed_swings.append({
            "swing_time_s": t, "win_prob_after": row["win_prob_smoothed"],
            "delta": delta, "nearest_events": events
        })

    # 8. Generate Narrative
    credit_counts_by_claim_time = assign_credits_to_claims(deaths_df, rejuvenator_df)

    timeline = []
    for s in attributed_swings:
        timeline.append({"time": s["swing_time_s"], "kind": "swing", "data": s})
    for _, mb in mid_boss_df.iterrows():
        matching = rejuvenator_df[(rejuvenator_df["team"] == mb["team_claimed"]) & (
                    rejuvenator_df["game_time_s"] >= mb["killed_time_s"])].sort_values("game_time_s")
        c_time = matching["game_time_s"].iloc[0] if not matching.empty else None
        timeline.append({"time": mb["killed_time_s"], "kind": "mid_boss", "data": {"team_claimed": mb["team_claimed"],
                                                                                   "credits_used": credit_counts_by_claim_time.get(
                                                                                       c_time, 0)}})
    timeline.sort(key=lambda x: x["time"])

    lines = []
    seen_events = set()
    quiet_start_time = merged["game_time_s"].min()
    quiet_start_prob = get_win_prob_pct(merged["win_prob_smoothed"].iloc[0])
    last_known_prob = quiet_start_prob
    biggest_swing = None

    def flush_quiet(end_time, end_prob):
        nonlocal quiet_start_time, quiet_start_prob
        net_change = end_prob - quiet_start_prob
        if abs(net_change) >= QUIET_NET_CHANGE_THRESHOLD:
            verb = "pulled ahead" if net_change > 0 else "fell behind"
            lines.append(
                f"From {format_time(quiet_start_time)} to {format_time(end_time)}, your team steadily {verb} with no single decisive event, win chance moving from {quiet_start_prob:.0f}% to {end_prob:.0f}%.")
        quiet_start_time, quiet_start_prob = end_time, end_prob

    for item in timeline:
        t = item["time"]
        if item["kind"] == "mid_boss":
            flush_quiet(t, last_known_prob)
            claimer = "Your team" if item["data"]["team_claimed"] == user_raw_team else "The enemy"
            line = f"{claimer} claimed the Mid Boss Rejuvenator at {format_time(t)}, gaining a team-wide buff."
            if item["data"]["credits_used"] > 0:
                line += f" Over the next few minutes, they used {item['data']['credits_used']} rejuv{'s' if item['data']['credits_used'] != 1 else ''}."
            followup = find_followup_structure(item["data"]["team_claimed"], t, structures_df)
            if followup is not None:
                line += f" Riding that advantage, they pushed and destroyed a {structure_name(followup)} at {format_time(followup['destroyed_time_s'])}."
            lines.append(line)

        elif item["kind"] == "swing":
            s = item["data"]
            delta_pct = abs(s["delta"]) * 100
            prob_pct = get_win_prob_pct(s["win_prob_after"])
            is_pos = s["delta"] > 0

            event_phrase, event_type, trig = None, None, None
            for e in s["nearest_events"]:
                if (e["type"], e["time"]) not in seen_events:
                    event_phrase, event_type, trig = event_to_phrase(e, user_raw_team), e["type"], e
                    seen_events.add((e["type"], e["time"]))
                    break

            if event_phrase:
                flush_quiet(t, last_known_prob)
                pol = get_event_polarity(trig, user_raw_team)
                cap = event_phrase[0].upper() + event_phrase[1:]

                if is_pos and pol >= 0:
                    line = f"{cap}, which boosted your win chance by {delta_pct:.0f}% (now {prob_pct:.0f}% win chance)."
                elif not is_pos and pol <= 0:
                    line = f"{cap}, which hurt your win chance by {delta_pct:.0f}% (now {prob_pct:.0f}% win chance)."
                elif is_pos and pol == -1:
                    line = f"Even though {event_phrase}, your team pulled ahead overall, boosting your win chance by {delta_pct:.0f}% (now {prob_pct:.0f}%)."
                elif not is_pos and pol == 1:
                    line = f"Even though {event_phrase}, the enemy pressed their advantage overall, dropping your win chance by {delta_pct:.0f}% (now {prob_pct:.0f}%)."

                if event_type == "rift_capture" and pol == 1 and is_pos:
                    f_up = find_followup_structure(trig["team"], trig["time"], structures_df)
                    if f_up is not None: line += f" {'Your team' if trig['team'] == user_raw_team else 'The enemy'} used the advantage to destroy an enemy {structure_name(f_up)} at {format_time(f_up['destroyed_time_s'])}."
                elif event_type == "death" and pol == -1 and not is_pos:
                    f_up = find_followup_structure_after_death(trig["team"], trig["time"], structures_df)
                    if f_up is not None: line += f" With a player down, {'your team' if trig['team'] == user_raw_team else 'the enemy'} lost a {structure_name(f_up)} shortly after, at {format_time(f_up['destroyed_time_s'])}."

                lines.append(line)
                quiet_start_time, quiet_start_prob = t, prob_pct

            if t >= (merged["game_time_s"].max() / 2) and not is_pos and pol == -1:
                if biggest_swing is None or delta_pct > biggest_swing["delta_pct"]:
                    biggest_swing = {"time": trig["time"] if trig else t, "delta_pct": delta_pct,
                                     "phrase": event_phrase}

            last_known_prob = prob_pct

    flush_quiet(merged["game_time_s"].max(), last_known_prob)
    final_prob = get_win_prob_pct(merged["win_prob_smoothed"].iloc[-1])
    lines.append(
        f"\nBy the end of the game, your team {'led' if final_prob >= 50 else 'trailed'} with a {final_prob:.0f}% win chance.")
    if biggest_swing:
        lines.append(
            f"The fatal turning point came when {biggest_swing['phrase'] or 'a shift in momentum'}, a {biggest_swing['delta_pct']:.0f}% swing that let the enemy press their advantage from there.")

    chart_data = [
        {"time_m": round(row["game_time_s"] / 60, 1), "win_prob": round(get_win_prob_pct(row["win_prob_smoothed"]), 1)}
        for _, row in merged.iterrows()]

    return {
        "match_id": Path(json_path).stem,
        "user": target_username,
        "final_win_prob": final_prob,
        "outcome": "Victory" if final_prob >= 50 else "Defeat",
        "chart_data": chart_data,
        "timeline_events": lines
    }


# 5. CLI EXECUTION
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print(json.dumps({"error": "Missing arguments"}), file=sys.stderr)
        sys.exit(1)

    command = sys.argv[1]

    if command == "get_players":
        dem_path = sys.argv[2]
        
        # we will later call the java parser heree
        json_path = PROJECT_ROOT / "replay_parser" / "output" / "parsed_match.json"
        
        with open(json_path, "r") as f:
            data = json.load(f)
            
        # Extract only what the React frontend needs
        players = [{"username": p["username"], "team": p["team"]} for p in data["players"]]
        
        # Print exactly ONE thing to stdout: the final JSON
        print(json.dumps(players))

    elif command == "analyze":
        json_path = sys.argv[2]
        target_username = sys.argv[3]
        model_path = PROJECT_ROOT / "models" / "win_probability_lstm_v1.pt"

        try:
            report = analyze_match(json_path, target_username=target_username, model_path=model_path)
            print(json.dumps(report))
        except Exception as e:
            print(json.dumps({"error": str(e)}))
            sys.exit(1)