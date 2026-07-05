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

logger = logging.getLogger(__name__)

CLEAN_CSV_PATH = "data/processed/hnl_player_stats_clean_2025_2026.csv"
FEATURES_CSV_PATH = "data/processed/hnl_player_features_2025_2026.csv"


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
