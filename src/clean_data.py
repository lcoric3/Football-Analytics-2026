"""
Stage 2: turn raw SportMonks squad+statistics data into one clean,
flat table with the columns the rest of the pipeline expects.

Football data science logic:
SportMonks nests a player's statistics as a list of "details", each with
a `type_id` (e.g. 52 = "Goals", 79 = "Assists") and a `value` object
(usually `{"total": X}`). That's flexible for the API but useless for
analysis - we want one row per player with one column per stat.

We match on the numeric `type_id` rather than a `type.name` string because
fetch_data.py can't request the `.type` include (SportMonks caps nested
includes at 3 levels for this endpoint, and `.type` would be a 4th).
STAT_TYPE_MAP below was built by looking up SportMonks' `/core/types`
reference list once for the ids this project needs; that reference list
is stable (it's SportMonks' shared statistic vocabulary, not season data),
so hardcoding these ids does not need refreshing per season. If a stat you
expect is missing after running this, check the "Unmapped statistic type
ids" log line it prints - that lists every raw id we saw but didn't
recognize, look it up in `/core/types` and add it to the map.
"""
import json
import logging
import os
from datetime import date

import pandas as pd

logger = logging.getLogger(__name__)

RAW_JSON_PATH = "data/raw/hnl_player_stats_raw_2025_2026.json"
CLEAN_CSV_PATH = "data/processed/hnl_player_stats_clean_2025_2026.csv"

# Maps a SportMonks statistic type_id (from /core/types) -> our column name.
# Add entries here if the log reports unmapped type ids for your data.
STAT_TYPE_MAP = {
    321: "appearances",       # Appearances
    119: "minutes",           # Minutes Played
    52: "goals",              # Goals
    79: "assists",            # Assists
    42: "shots",              # Shots Total
    86: "shots_on_target",    # Shots On Target
    80: "passes",             # Passes
    116: "passes_accurate",   # Accurate Passes
    78: "tackles",            # Tackles
    100: "interceptions",     # Interceptions
    105: "duels",             # Total Duels
    106: "duels_won",         # Duels Won
    84: "yellow_cards",       # Yellowcards
    83: "red_cards",          # Redcards
    118: "rating",            # Rating
}

# Some stat values carry the number we want under a key other than "total".
VALUE_KEY_OVERRIDES = {
    118: "average",  # Rating
}

CLEAN_COLUMNS = [
    "player_id", "player_name", "team_name", "position", "age", "nationality",
    "appearances", "minutes", "goals", "assists", "shots", "shots_on_target",
    "passes", "pass_accuracy", "tackles", "interceptions", "duels", "duels_won",
    "yellow_cards", "red_cards", "rating",
]


def _compute_age(date_of_birth):
    """SportMonks gives a date_of_birth, not a ready-made age - derive it."""
    if not date_of_birth:
        return None
    try:
        dob = date.fromisoformat(str(date_of_birth)[:10])
    except ValueError:
        return None
    today = date.today()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


def _extract_player_stats(player, season_id=None):
    """Flatten one player's nested `statistics.details` list into a dict."""
    stats = {}
    unmapped = set()

    for season_stats in player.get("statistics", []) or []:
        if season_id is not None and season_stats.get("season_id") not in (season_id, None):
            continue
        for detail in season_stats.get("details", []) or []:
            type_id = detail.get("type_id")
            value = detail.get("value") or {}
            if type_id is None:
                continue
            column = STAT_TYPE_MAP.get(type_id)
            if not column:
                unmapped.add(type_id)
                continue
            value_key = VALUE_KEY_OVERRIDES.get(type_id, "total")
            stats[column] = value.get(value_key, value.get("total"))

    return stats, unmapped


def clean(entries, season_id=None):
    """Turn the list of raw squad entries into one clean DataFrame."""
    rows = []
    all_unmapped = set()

    for entry in entries:
        player = entry.get("player") or {}
        if not player:
            continue

        stats, unmapped = _extract_player_stats(player, season_id)
        all_unmapped |= unmapped

        # Passes: pass_accuracy is derived here (accurate/total), while
        # other per-90 ratios are left for feature_engineering.py.
        passes = stats.get("passes")
        passes_accurate = stats.get("passes_accurate")
        pass_accuracy = (
            round(100 * passes_accurate / passes, 2)
            if passes and passes_accurate is not None
            else None
        )

        rows.append({
            "player_id": player.get("id"),
            "player_name": player.get("display_name") or player.get("name"),
            "team_name": entry.get("team_name"),
            "position": (player.get("position") or {}).get("name"),
            "age": _compute_age(player.get("date_of_birth")),
            "nationality": (player.get("nationality") or {}).get("name"),
            "appearances": stats.get("appearances"),
            "minutes": stats.get("minutes"),
            "goals": stats.get("goals"),
            "assists": stats.get("assists"),
            "shots": stats.get("shots"),
            "shots_on_target": stats.get("shots_on_target"),
            "passes": passes,
            "pass_accuracy": pass_accuracy,
            "tackles": stats.get("tackles"),
            "interceptions": stats.get("interceptions"),
            "duels": stats.get("duels"),
            "duels_won": stats.get("duels_won"),
            "yellow_cards": stats.get("yellow_cards"),
            "red_cards": stats.get("red_cards"),
            "rating": stats.get("rating"),
        })

    if all_unmapped:
        logger.warning(
            "Unmapped statistic type ids seen (look these up in "
            "/core/types and add them to STAT_TYPE_MAP in clean_data.py "
            "if you need them): %s", sorted(all_unmapped),
        )

    df = pd.DataFrame(rows, columns=CLEAN_COLUMNS)

    # A player needs at least some minutes to be useful for per-90 analysis
    # later - drop rows with no player_id or zero/missing minutes.
    df = df.dropna(subset=["player_id"])
    df = df[df["minutes"].fillna(0) > 0].reset_index(drop=True)

    # Zero-fill count-style stats (a missing "assists" means 0 assists), but
    # leave age/rating as NaN when unknown - 0 would look like a real value
    # (e.g. would wrongly qualify as "youngest player" or a 0.0 rating).
    zero_fill_cols = [c for c in CLEAN_COLUMNS if c not in
                      ("player_id", "player_name", "team_name", "position",
                       "nationality", "age", "rating")]
    for col in zero_fill_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
    for col in ("age", "rating"):
        df[col] = pd.to_numeric(df[col], errors="coerce")

    return df


def run():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if not os.path.exists(RAW_JSON_PATH):
        raise FileNotFoundError(
            f"{RAW_JSON_PATH} not found. Run fetch_data.run() first."
        )

    with open(RAW_JSON_PATH, "r", encoding="utf-8") as f:
        entries = json.load(f)

    df = clean(entries)

    os.makedirs(os.path.dirname(CLEAN_CSV_PATH), exist_ok=True)
    df.to_csv(CLEAN_CSV_PATH, index=False)
    logger.info("Saved %d clean player rows to %s", len(df), CLEAN_CSV_PATH)
    return df


if __name__ == "__main__":
    run()
