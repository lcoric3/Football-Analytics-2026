"""
Tests for src/scouting_scores.py - percentile-based scouting scores.
"""
import pandas as pd

from src import feature_engineering, scouting_scores

# These scores are plain averages of 0-100 percentile ranks, so they're
# mathematically guaranteed to stay in [0, 100].
BOUNDED_0_100_SCORES = [
    "attacking_score", "creative_score", "defensive_score", "discipline_score",
    "overall_score", "dribbling_score", "passing_score",
    "progressive_midfielder_score", "passer_defender_score", "goalkeeper_score",
]


def test_scores_stay_within_0_and_100(scored_df):
    for col in BOUNDED_0_100_SCORES:
        values = scored_df[col].dropna()
        assert not values.empty, f"{col} had no non-NaN values to check"
        assert (values >= 0).all(), f"{col} went below 0: {values.tolist()}"
        assert (values <= 100).all(), f"{col} went above 100: {values.tolist()}"


def test_duel_defending_score_bounds(scored_df):
    """duel_defending_score subtracts a small cards_per90 penalty (5% of one
    percentile rank), so unlike the other scores it isn't *strictly* bounded
    at 0 - but it should never drop far below 0."""
    values = scored_df["duel_defending_score"].dropna()
    assert not values.empty
    assert (values >= -5).all()
    assert (values <= 100).all()


def test_players_below_minutes_threshold_get_nan_scores(scored_df):
    """Attacker Three has 300 minutes, below MIN_MINUTES_FOR_SCORES (450) -
    their outfield scores should be NaN, not a noisy/misleading number from
    a tiny sample of playing time."""
    row = scored_df[scored_df["player_name"] == "Attacker Three"].iloc[0]

    assert row["minutes"] < scouting_scores.MIN_MINUTES_FOR_SCORES
    assert row[["attacking_score", "creative_score", "defensive_score", "overall_score"]].isna().all()


def test_goalkeeper_score_only_computed_for_goalkeepers(scored_df):
    outfield = scored_df[scored_df["position"] != "Goalkeeper"]
    goalkeepers = scored_df[scored_df["position"] == "Goalkeeper"]

    assert outfield["goalkeeper_score"].isna().all()
    assert goalkeepers["goalkeeper_score"].notna().all()


# --- age_potential_score (Stage B1) ----------------------------------------

def _make_scored_df(ages):
    """Build a scored dataframe for N identical players (same position and
    stats), varying only age - isolates age_bonus/reliability_bonus behavior
    from the rest of the (much noisier) shared scored_df fixture."""
    base_row = {
        "position": "Midfielder", "team_name": "Team A", "minutes": 1800, "appearances": 20,
        "goals": 5, "assists": 5, "shots": 20, "shots_on_target": 10,
        "passes": 500, "pass_accuracy": 80, "tackles": 20, "interceptions": 10,
        "duels": 50, "duels_won": 25, "yellow_cards": 2, "red_cards": 0,
        "dribble_attempts": 10, "successful_dribbles": 5, "dribbled_past": 5,
        "fouls_drawn": 5, "crosses": 5, "accurate_crosses": 2, "long_balls": 10,
        "accurate_long_balls": 5, "key_passes": 5, "aerials_won": 5,
        "clearances": 5, "saves": 0, "goals_conceded": 0, "clean_sheets": 0,
        "penalties_saved": 0,
    }
    rows = [dict(base_row, age=age) for age in ages]
    raw_df = pd.DataFrame(rows)
    features_df = feature_engineering.add_features(raw_df)
    return scouting_scores.add_scores(features_df)


def test_age_bonus_decreases_with_age_and_is_zero_at_and_above_cutoff():
    df = _make_scored_df([17, 20, 23, 30])
    bonuses = df.set_index("age")["age_bonus"]

    assert bonuses[17] > bonuses[20] > bonuses[23]
    assert bonuses[23] == 0
    assert bonuses[30] == 0


def test_age_bonus_is_capped_for_very_young_players():
    df = _make_scored_df([15, 16, 17])
    bonuses = df.set_index("age")["age_bonus"]

    # 15, 16, and 17 are all >= AGE_BONUS_CAP_YEARS below the cutoff (23),
    # so they should all hit the same capped bonus rather than growing
    # without bound the younger a player gets.
    assert bonuses[15] == bonuses[16] == bonuses[17]
    assert bonuses[15] == scouting_scores.AGE_BONUS_CAP_YEARS * scouting_scores.AGE_BONUS_PER_YEAR


def test_age_potential_score_never_below_overall_score(scored_df):
    """age_bonus and reliability_bonus are both >= 0, so age_potential_score
    should never rank a player below their own overall_score."""
    eligible = scored_df.dropna(subset=["overall_score", "age_potential_score"])
    assert not eligible.empty
    assert (eligible["age_potential_score"] >= eligible["overall_score"] - 1e-9).all()


def test_age_potential_score_nan_for_ineligible_players(scored_df):
    """Attacker Three (300 minutes) is below MIN_MINUTES_FOR_SCORES, so
    overall_score is NaN - age_potential_score must also come back NaN
    rather than silently falling back to just the age/reliability bonuses."""
    row = scored_df[scored_df["player_name"] == "Attacker Three"].iloc[0]
    assert pd.isna(row["age_potential_score"])


# --- team-context scoring / underrated_score (Stage B2) --------------------

def test_team_average_score_excludes_goalkeepers_and_ineligible_players(scored_df):
    """team_average_score must be computed only from a team's own eligible
    (minutes >= threshold) *outfield* players. Recomputed independently here
    and compared, so a regression that lets a goalkeeper or a low-minutes
    player leak into a team's average would be caught."""
    eligible_outfield = scored_df[
        (scored_df["minutes"] >= scouting_scores.MIN_MINUTES_FOR_SCORES)
        & (scored_df["position"] != "Goalkeeper")
    ]
    expected = eligible_outfield.groupby("team_name")["overall_score"].mean()

    for team_name, expected_avg in expected.items():
        actual = scored_df.loc[scored_df["team_name"] == team_name, "team_average_score"]
        assert (actual.round(6) == round(expected_avg, 6)).all(), team_name


def test_score_above_team_average_is_the_literal_gap(scored_df):
    eligible = scored_df.dropna(subset=["overall_score", "team_average_score"])
    expected_gap = eligible["overall_score"] - eligible["team_average_score"]

    assert not eligible.empty
    assert (eligible["score_above_team_average"].round(6) == expected_gap.round(6)).all()


def test_standout_bonus_is_never_negative_and_zero_below_team_average(scored_df):
    eligible = scored_df.dropna(subset=["standout_bonus", "score_above_team_average"])

    assert (eligible["standout_bonus"] >= 0).all()
    below_average = eligible[eligible["score_above_team_average"] < 0]
    assert (below_average["standout_bonus"] == 0).all()


def test_weak_team_bonus_is_never_negative(scored_df):
    values = scored_df["weak_team_bonus"].dropna()
    assert not values.empty
    assert (values >= 0).all()


def test_underrated_score_equals_overall_plus_both_bonuses(scored_df):
    eligible = scored_df.dropna(subset=["underrated_score"])
    expected = eligible["overall_score"] + eligible["standout_bonus"] + eligible["weak_team_bonus"]

    assert not eligible.empty
    assert (eligible["underrated_score"].round(6) == expected.round(6)).all()
