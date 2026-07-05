"""
Stage 5: ranking analysis - turn scored player data into scouting lists.

Football data science logic:
"Top scorers" and "top assists" are traditional counting-stat leaderboards
(like a Golden Boot table), so those two use raw totals rather than
per-90 rates. Every other list here is about *who to watch/sign*, which
per-90 rates and scouting scores (from scouting_scores.py) answer better
than raw totals, since they're not biased by who happened to play more
minutes.

Position-based lists (defenders, creators, attackers, by-position) match
loosely on the `position` string (e.g. "Centre-Back" still counts as a
defender) rather than requiring an exact value, since SportMonks position
names can be more specific than a simple back/mid/forward split.
"""
import logging
import os

import pandas as pd

logger = logging.getLogger(__name__)

SCORED_CSV_PATH = "data/processed/hnl_player_scored_2025_2026.csv"
OUTPUT_CSV_PATH = "data/output/top_players_hnl_2025_2026.csv"

TOP_N = 15
U23_AGE_LIMIT = 23

# SportMonks squad data sometimes lists non-playing staff (e.g. a manager)
# alongside players, with a "position" like "Coach". Those aren't players,
# so they're excluded from the by-position rankings below.
NON_PLAYER_POSITIONS = {"coach"}

OUTPUT_COLUMNS = [
    "category", "rank", "player_id", "player_name", "team_name", "position",
    "age", "minutes", "goals", "assists", "goals_per90", "assists_per90",
    "attacking_score", "creative_score", "defensive_score",
    "discipline_score", "overall_score",
]


def _position_matches(df, keyword):
    return df["position"].astype(str).str.contains(keyword, case=False, na=False)


def _rank_table(df, category, sort_col, top_n=TOP_N):
    """Sort by sort_col (descending), keep the top_n rows, and label them
    with a category name and a 1-based rank within that category."""
    table = df.sort_values(sort_col, ascending=False).head(top_n).copy()
    table.insert(0, "category", category)
    table.insert(1, "rank", range(1, len(table) + 1))
    return table


def build_rankings(df):
    tables = []

    tables.append(_rank_table(df, "top_scorers", "goals"))
    tables.append(_rank_table(df, "top_assists", "assists"))

    if "age" in df.columns and df["age"].notna().any():
        u23 = df[df["age"] <= U23_AGE_LIMIT]
        tables.append(_rank_table(u23, "best_u23", "overall_score"))

    defenders = df[_position_matches(df, "def") | _position_matches(df, "back")]
    tables.append(_rank_table(defenders, "best_defenders", "defensive_score"))

    midfielders = df[_position_matches(df, "mid")]
    tables.append(_rank_table(midfielders, "best_midfield_creators", "creative_score"))

    attackers = df[_position_matches(df, "attack") | _position_matches(df, "forward") | _position_matches(df, "wing")]
    tables.append(_rank_table(attackers, "best_attackers", "attacking_score"))

    tables.append(_rank_table(df, "best_overall", "overall_score"))

    positions = [
        p for p in sorted(df["position"].dropna().unique())
        if p.lower() not in NON_PLAYER_POSITIONS
    ]
    for position in positions:
        subset = df[df["position"] == position]
        tables.append(_rank_table(subset, f"best_{position.lower().replace(' ', '_')}", "overall_score"))

    result = pd.concat(tables, ignore_index=True)
    return result[OUTPUT_COLUMNS]


def run():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if not os.path.exists(SCORED_CSV_PATH):
        raise FileNotFoundError(f"{SCORED_CSV_PATH} not found. Run scouting_scores.run() first.")

    df = pd.read_csv(SCORED_CSV_PATH)
    rankings = build_rankings(df)

    os.makedirs(os.path.dirname(OUTPUT_CSV_PATH), exist_ok=True)
    rankings.to_csv(OUTPUT_CSV_PATH, index=False)
    logger.info(
        "Saved %d ranking rows across %d categories to %s",
        len(rankings), rankings["category"].nunique(), OUTPUT_CSV_PATH,
    )
    return rankings


if __name__ == "__main__":
    run()
