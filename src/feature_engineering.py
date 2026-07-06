"""
Stage 3: feature engineering - per-90 metrics and ratio features.

Football data science logic:
Raw counting stats (goals, tackles, passes...) aren't comparable between
players directly, because playing time varies - a player with 5 goals in
900 minutes is doing much better than one with 5 goals in 2700 minutes.

"Per-90" normalizes every counting stat to "per 90 minutes played" (i.e.
per full match), which is the standard unit in football analytics. It
lets you compare a squad player and a starter on equal footing.

Ratios (accuracy, conversion, success rate) capture *quality* rather than
*volume* - e.g. two players can have the same shots_per90, but one scores
far more often because their shot selection/finishing is better.
"""
import logging
import os

import numpy as np
import pandas as pd

from src import season_config

logger = logging.getLogger(__name__)

CLEAN_CSV_PATH = season_config.processed_path("hnl_player_stats_clean")
FEATURES_CSV_PATH = season_config.processed_path("hnl_player_features")


def _safe_div(numerator, denominator):
    """Elementwise division that returns 0 instead of NaN/inf when the
    denominator is 0 (e.g. a player with 0 shots has 0% shot accuracy,
    not an undefined value)."""
    with np.errstate(divide="ignore", invalid="ignore"):
        result = numerator / denominator
    return result.replace([np.inf, -np.inf], 0).fillna(0)


def add_features(df):
    df = df.copy()
    minutes = df["minutes"]

    # --- Per-90 metrics: raw count / minutes * 90 -----------------------
    df["goals_per90"] = _safe_div(df["goals"] * 90, minutes)
    df["assists_per90"] = _safe_div(df["assists"] * 90, minutes)
    df["shots_per90"] = _safe_div(df["shots"] * 90, minutes)
    df["shots_on_target_per90"] = _safe_div(df["shots_on_target"] * 90, minutes)
    df["passes_per90"] = _safe_div(df["passes"] * 90, minutes)
    df["tackles_per90"] = _safe_div(df["tackles"] * 90, minutes)
    df["interceptions_per90"] = _safe_div(df["interceptions"] * 90, minutes)
    df["cards_per90"] = _safe_div((df["yellow_cards"] + df["red_cards"]) * 90, minutes)

    # --- New per-90 metrics: dribbling, crossing, long passing ----------
    # These feed the new dribbling/passing/duel-defending scouting scores.
    df["dribble_attempts_per90"] = _safe_div(df["dribble_attempts"] * 90, minutes)
    df["successful_dribbles_per90"] = _safe_div(df["successful_dribbles"] * 90, minutes)
    df["dribbled_past_per90"] = _safe_div(df["dribbled_past"] * 90, minutes)
    df["fouls_drawn_per90"] = _safe_div(df["fouls_drawn"] * 90, minutes)
    df["crosses_per90"] = _safe_div(df["crosses"] * 90, minutes)
    df["accurate_crosses_per90"] = _safe_div(df["accurate_crosses"] * 90, minutes)
    df["long_balls_per90"] = _safe_div(df["long_balls"] * 90, minutes)
    df["accurate_long_balls_per90"] = _safe_div(df["accurate_long_balls"] * 90, minutes)
    df["key_passes_per90"] = _safe_div(df["key_passes"] * 90, minutes)
    df["aerials_won_per90"] = _safe_div(df["aerials_won"] * 90, minutes)
    df["clearances_per90"] = _safe_div(df["clearances"] * 90, minutes)

    # --- Goalkeeper per-90 metrics (only meaningful for Goalkeeper rows) --
    # Feed goalkeeper_score in scouting_scores.py, kept separate from the
    # outfield scores since goalkeeping is a fundamentally different job.
    df["saves_per90"] = _safe_div(df["saves"] * 90, minutes)
    df["goals_conceded_per90"] = _safe_div(df["goals_conceded"] * 90, minutes)
    # clean sheets as a rate of appearances, not a per-90 count (a clean
    # sheet is a per-match outcome, not something that scales within a match)
    df["clean_sheet_rate"] = _safe_div(df["clean_sheets"] * 100, df["appearances"])

    # --- Ratios: quality, not volume -------------------------------------
    # % of shots that are on target
    df["shot_accuracy"] = _safe_div(df["shots_on_target"] * 100, df["shots"])
    # % of shots that result in a goal ("finishing" quality)
    df["goal_conversion"] = _safe_div(df["goals"] * 100, df["shots"])
    # pass_accuracy (from clean_data.py) as a 0-1 ratio, for use in scores
    df["pass_accuracy_ratio"] = (df["pass_accuracy"] / 100).fillna(0)
    # % of ground/aerial duels won
    df["duel_success_rate"] = _safe_div(df["duels_won"] * 100, df["duels"])
    # average minutes played per appearance (starter vs. substitute signal)
    df["minutes_per_appearance"] = _safe_div(minutes, df["appearances"])
    # goals + assists per 90 - overall attacking output regardless of role
    df["goal_contribution_per90"] = df["goals_per90"] + df["assists_per90"]
    # % of dribble attempts that succeed - beating a man cleanly, not just trying one
    df["dribble_success_rate"] = _safe_div(df["successful_dribbles"] * 100, df["dribble_attempts"])
    # % of crosses that find a teammate
    df["cross_accuracy"] = _safe_div(df["accurate_crosses"] * 100, df["crosses"])
    # % of long balls that find a teammate
    df["long_ball_accuracy"] = _safe_div(df["accurate_long_balls"] * 100, df["long_balls"])

    return df


def run():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if not os.path.exists(CLEAN_CSV_PATH):
        raise FileNotFoundError(f"{CLEAN_CSV_PATH} not found. Run clean_data.run() first.")

    df = pd.read_csv(CLEAN_CSV_PATH)
    df = add_features(df)

    os.makedirs(os.path.dirname(FEATURES_CSV_PATH), exist_ok=True)
    df.to_csv(FEATURES_CSV_PATH, index=False)
    logger.info("Saved %d rows with engineered features to %s", len(df), FEATURES_CSV_PATH)
    return df


if __name__ == "__main__":
    run()
