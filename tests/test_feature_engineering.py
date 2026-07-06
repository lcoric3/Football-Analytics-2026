"""
Tests for src/feature_engineering.py - per-90 metrics and ratio features.
"""
import math

import pandas as pd

from src import feature_engineering


ZERO_MINUTES_ROW = {
    "minutes": 0, "goals": 0, "assists": 0, "shots": 0, "shots_on_target": 0,
    "passes": 0, "pass_accuracy": None, "tackles": 0, "interceptions": 0,
    "duels": 0, "duels_won": 0, "yellow_cards": 0, "red_cards": 0,
    "dribble_attempts": 0, "successful_dribbles": 0, "dribbled_past": 0,
    "fouls_drawn": 0, "crosses": 0, "accurate_crosses": 0, "long_balls": 0,
    "accurate_long_balls": 0, "key_passes": 0, "aerials_won": 0, "clearances": 0,
    "saves": 0, "goals_conceded": 0, "clean_sheets": 0, "appearances": 0,
}


def test_zero_minutes_produces_zero_not_nan_or_inf():
    """A player with 0 minutes has nothing to divide by - every per-90 rate
    and ratio should come back as 0, not NaN or +/-inf, so a zero-minutes
    row can't accidentally look missing or break downstream math."""
    df = pd.DataFrame([ZERO_MINUTES_ROW])

    result = feature_engineering.add_features(df)

    per90_cols = [c for c in result.columns if c.endswith("_per90")]
    ratio_cols = [
        "shot_accuracy", "goal_conversion", "pass_accuracy_ratio",
        "duel_success_rate", "minutes_per_appearance", "dribble_success_rate",
        "cross_accuracy", "long_ball_accuracy", "clean_sheet_rate",
    ]

    for col in per90_cols + ratio_cols:
        value = result.loc[0, col]
        assert not pd.isna(value), f"{col} was NaN for a zero-minutes player"
        assert not math.isinf(value), f"{col} was inf for a zero-minutes player"
        assert value == 0, f"{col} should be 0 for a zero-minutes player, got {value}"


def test_per90_scales_counting_stats_to_a_full_match(raw_df):
    """Sanity-check the actual formula on a known row: goals_per90 should
    equal goals / minutes * 90."""
    result = feature_engineering.add_features(raw_df)

    row = result[result["player_name"] == "Midfielder One"].iloc[0]
    expected_goals_per90 = row["goals"] * 90 / row["minutes"]

    assert row["goals_per90"] == expected_goals_per90
    assert row["goal_contribution_per90"] == row["goals_per90"] + row["assists_per90"]
