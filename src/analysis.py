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
SPECIALIST_OUTPUT_CSV_PATH = "data/output/specialist_rankings_hnl_2025_2026.csv"

TOP_N = 15
U23_AGE_LIMIT = 23
U21_AGE_LIMIT = 21

# SportMonks squad data sometimes lists non-playing staff (e.g. a manager)
# alongside players, with a "position" like "Coach". Those aren't players,
# so they're excluded from the by-position rankings below.
NON_PLAYER_POSITIONS = {"coach"}

# overall_score is built entirely from outfield actions (goals, assists,
# tackles, passes...) - a goalkeeper's version of it is close to noise (see
# scouting_scores.py's module docstring), so goalkeepers are excluded from
# every ranking that sorts by overall_score and get their own
# goalkeeper_score-based ranking (best_goalkeepers) instead.
OUTFIELD_ONLY_POSITIONS = {"goalkeeper"}

OUTPUT_COLUMNS = [
    "category", "rank", "player_id", "player_name", "team_name", "position",
    "age", "minutes", "goals", "assists", "goals_per90", "assists_per90",
    "attacking_score", "creative_score", "defensive_score",
    "discipline_score", "overall_score",
    # Stage 2: included here too so every existing category's rows also show
    # how that player scores on the newer specialist dimensions.
    "dribbling_score", "passing_score", "duel_defending_score",
    "progressive_midfielder_score", "passer_defender_score",
    # Stage 4 fix: goalkeeper_score, for the separate best_goalkeepers ranking.
    "goalkeeper_score",
    # Stage B1: age_potential_score and its two components, for the
    # young-talent rankings below (best_young_talents, best_u21_players,
    # best_u23_players_by_potential).
    "age_bonus", "reliability_bonus", "age_potential_score",
    # Stage B2: team-context scoring and its two bonuses, for the
    # underrated_players/hidden_gems/small_club_standouts rankings below.
    "team_average_score", "score_above_team_average",
    "standout_bonus", "weak_team_bonus", "underrated_score",
]

# Columns shown for every row of specialist_rankings_hnl_2025_2026.csv - a
# mix of identity, the five specialist scores, and the underlying per-90/
# ratio stats those scores are built from, so a reader can see *why* a
# player ranked where they did without opening the scored CSV separately.
SPECIALIST_OUTPUT_COLUMNS = [
    "category", "rank", "player_id", "player_name", "team_name", "position",
    "age", "minutes",
    "dribbling_score", "passing_score", "duel_defending_score",
    "progressive_midfielder_score", "passer_defender_score",
    "creative_score", "defensive_score", "overall_score",
    "successful_dribbles_per90", "dribble_success_rate", "fouls_drawn_per90",
    "passes_per90", "key_passes_per90", "pass_accuracy",
    "accurate_long_balls_per90", "accurate_crosses_per90",
    "tackles_per90", "interceptions_per90", "aerials_won_per90",
    "clearances_per90", "duel_success_rate",
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

    outfield = df[~df["position"].astype(str).str.lower().isin(OUTFIELD_ONLY_POSITIONS)]

    if "age" in df.columns and df["age"].notna().any():
        u23 = outfield[outfield["age"] <= U23_AGE_LIMIT]
        tables.append(_rank_table(u23, "best_u23", "overall_score"))

        # Stage B1: young-talent rankings sorted by age_potential_score
        # (overall_score + age_bonus + reliability_bonus - see
        # scouting_scores.py) instead of raw overall_score. best_young_talents
        # and best_u23_players_by_potential use the exact same U23 pool and
        # sort order - they're kept as two category labels on purpose:
        # best_young_talents is the natural "headline" name for this list,
        # while best_u23_players_by_potential exists so it sits directly next
        # to best_u23 in the output and makes the "current output" vs.
        # "potential-adjusted" comparison for the same age bracket explicit.
        tables.append(_rank_table(u23, "best_young_talents", "age_potential_score"))
        tables.append(_rank_table(u23, "best_u23_players_by_potential", "age_potential_score"))

        u21 = outfield[outfield["age"] <= U21_AGE_LIMIT]
        tables.append(_rank_table(u21, "best_u21_players", "age_potential_score"))

    defenders = df[_position_matches(df, "def") | _position_matches(df, "back")]
    tables.append(_rank_table(defenders, "best_defenders", "defensive_score"))

    midfielders = df[_position_matches(df, "mid")]
    tables.append(_rank_table(midfielders, "best_midfield_creators", "creative_score"))

    attackers = df[_position_matches(df, "attack") | _position_matches(df, "forward") | _position_matches(df, "wing")]
    tables.append(_rank_table(attackers, "best_attackers", "attacking_score"))

    tables.append(_rank_table(outfield, "best_overall", "overall_score"))

    # Stage B2: team-context rankings built on scouting_scores.py's
    # underrated_score/standout_bonus/weak_team_bonus - replaces the old
    # hardcoded BIG_CLUBS proxy that used to live in report.py.
    #
    # underrated_players: the general "who's underrated" leaderboard, sorted
    # by the full underrated_score (overall_score + standout_bonus +
    # weak_team_bonus) - no extra filter.
    tables.append(_rank_table(outfield, "underrated_players", "underrated_score"))

    # hidden_gems: a stricter subset - only players who both outperform
    # their own teammates (standout_bonus > 0) *and* play for a squad below
    # the league's average team (weak_team_bonus > 0). Requiring both
    # signals at once is what makes this "hidden", not just "good relative
    # to a bad team" or "good on an average team".
    hidden_gems_pool = outfield[(outfield["standout_bonus"] > 0) & (outfield["weak_team_bonus"] > 0)]
    tables.append(_rank_table(hidden_gems_pool, "hidden_gems", "underrated_score"))

    # small_club_standouts: every eligible outfield player at a below-average
    # team (weak_team_bonus > 0), sorted by plain overall_score rather than
    # the blended underrated_score - this answers "who's the best individual
    # performer at a smaller club", regardless of how far above their own
    # teammates they sit.
    small_club_pool = outfield[outfield["weak_team_bonus"] > 0]
    tables.append(_rank_table(small_club_pool, "small_club_standouts", "overall_score"))

    positions = [
        p for p in sorted(df["position"].dropna().unique())
        if p.lower() not in NON_PLAYER_POSITIONS and p.lower() not in OUTFIELD_ONLY_POSITIONS
    ]
    for position in positions:
        subset = df[df["position"] == position]
        tables.append(_rank_table(subset, f"best_{position.lower().replace(' ', '_')}", "overall_score"))

    # Goalkeepers get their own ranking on goalkeeper_score (saves, clean
    # sheets, goals conceded, penalties saved, pass accuracy) instead of
    # overall_score - see OUTFIELD_ONLY_POSITIONS above and
    # scouting_scores.py for why.
    goalkeepers = df[df["position"].astype(str).str.lower() == "goalkeeper"]
    tables.append(_rank_table(goalkeepers, "best_goalkeepers", "goalkeeper_score"))

    result = pd.concat(tables, ignore_index=True)
    return result[OUTPUT_COLUMNS]


def build_specialist_rankings(df):
    """Stage 2: specialist scouting lists built on the five new scores from
    scouting_scores.py. See that module's docstring for why each score is
    computed the way it is; this function just decides *who* each list is
    filtered to and *which* score sorts it.

    Some categories are deliberately unrestricted (open to every position)
    because their underlying score is itself pool-wide/absolute - they
    answer "who's best at this skill in the whole league":
      - best_dribblers / best_passers / best_duel_defenders use
        dribbling_score / passing_score / duel_defending_score, which are
        pool-wide by design (see scouting_scores.py).
      - best_creators / best_ball_winners reuse the existing creative_score
        and defensive_score - both position-aware - as league-wide
        leaderboards. This gives a *different* lens than best_duel_defenders:
        defensive_score ranks "defensive contribution relative to your own
        position's peers" (so a defensively strong midfielder can appear),
        while duel_defending_score ranks "raw ball-winning output" against
        the whole pool regardless of role.

    Other categories are restricted to the position the score was designed
    for, per the original spec ("don't rank pure midfielders as passer
    defenders"):
      - best_progressive_midfielders / best_young_progressive_midfielders:
        position contains "mid".
      - best_passer_defenders / best_ball_playing_defenders /
        best_young_passer_defenders: position contains "def" or "back".

    best_passer_defenders and best_ball_playing_defenders share one column
    (passer_defender_score) rather than two formulas, per your Stage 1
    decision - so these two lists are currently identical rankings under
    two names. Split them later if you want two distinct defender profiles
    (e.g. a more attacking "ball-playing" weighting vs. a defense-leaning
    "passer defender" weighting).

    Every category here is outfield-only (goalkeepers excluded) - these
    scores are all built from outfield actions (dribbling, passing,
    tackling...) that don't apply to goalkeeping, same reasoning as
    excluding them from best_overall/best_u23 in build_rankings(). See
    scouting_scores.py's module docstring and best_goalkeepers in
    build_rankings() for their dedicated ranking instead.
    """
    outfield = df[~df["position"].astype(str).str.lower().isin(OUTFIELD_ONLY_POSITIONS)]
    tables = []

    tables.append(_rank_table(outfield, "best_dribblers", "dribbling_score"))
    tables.append(_rank_table(outfield, "best_passers", "passing_score"))
    tables.append(_rank_table(outfield, "best_duel_defenders", "duel_defending_score"))
    tables.append(_rank_table(outfield, "best_creators", "creative_score"))
    tables.append(_rank_table(outfield, "best_ball_winners", "defensive_score"))

    midfielders = outfield[_position_matches(outfield, "mid")]
    tables.append(_rank_table(midfielders, "best_progressive_midfielders", "progressive_midfielder_score"))

    defenders = outfield[_position_matches(outfield, "def") | _position_matches(outfield, "back")]
    tables.append(_rank_table(defenders, "best_passer_defenders", "passer_defender_score"))
    tables.append(_rank_table(defenders, "best_ball_playing_defenders", "passer_defender_score"))

    if "age" in outfield.columns and outfield["age"].notna().any():
        young_midfielders = midfielders[midfielders["age"] <= U23_AGE_LIMIT]
        tables.append(_rank_table(young_midfielders, "best_young_progressive_midfielders", "progressive_midfielder_score"))

        young = outfield[outfield["age"] <= U23_AGE_LIMIT]
        tables.append(_rank_table(young, "best_young_dribblers", "dribbling_score"))

        young_defenders = defenders[defenders["age"] <= U23_AGE_LIMIT]
        tables.append(_rank_table(young_defenders, "best_young_passer_defenders", "passer_defender_score"))

    result = pd.concat(tables, ignore_index=True)
    return result[SPECIALIST_OUTPUT_COLUMNS]


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

    specialist_rankings = build_specialist_rankings(df)
    os.makedirs(os.path.dirname(SPECIALIST_OUTPUT_CSV_PATH), exist_ok=True)
    specialist_rankings.to_csv(SPECIALIST_OUTPUT_CSV_PATH, index=False)
    logger.info(
        "Saved %d specialist ranking rows across %d categories to %s",
        len(specialist_rankings), specialist_rankings["category"].nunique(), SPECIALIST_OUTPUT_CSV_PATH,
    )

    return rankings, specialist_rankings


if __name__ == "__main__":
    run()
