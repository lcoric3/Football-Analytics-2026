"""
Stage 4: explainable scouting scores.

Football data science logic:
Per-90 metrics live on very different scales - a good goals_per90 is
~0.5, a good passes_per90 is ~50. You can't just average them together.

The simple, explainable fix used here is a *percentile rank*: for each
metric, every player gets a score from 0 to 100 for where they rank
compared to every other player in this dataset ("you are better than X%
of HNL players in this stat"). Percentiles are unitless and always on a
0-100 scale, so they can be safely averaged into a composite score.

This is deliberately simple over "correct": percentiles are computed
across the whole player pool, not per position, so e.g. a defender will
rarely have a high attacking_score. analysis.py handles position-specific
rankings (e.g. "best defenders") by filtering on `position` *and* sorting
by the relevant score, rather than trying to make one score position-aware.

Small-sample guard: per-90 rates are noisy for players with little playing
time (one substitute appearance with a lucky goal can produce an absurd
goals_per90). Players below MIN_MINUTES_FOR_SCORES are excluded from the
percentile calculation entirely and get a NaN score, rather than letting
them distort the ranking or occupy a false top spot.
"""
import logging
import os

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

FEATURES_CSV_PATH = "data/processed/hnl_player_features_2025_2026.csv"
SCORED_CSV_PATH = "data/processed/hnl_player_scored_2025_2026.csv"

# ~5 full matches - below this, per-90 rates are considered too noisy to score.
MIN_MINUTES_FOR_SCORES = 450


def _percentile(series, eligible):
    """Rank a metric from 0 (worst) to 100 (best), computed only among
    `eligible` players; ineligible players get NaN instead of a score."""
    result = pd.Series(np.nan, index=series.index)
    result.loc[eligible] = series.loc[eligible].rank(pct=True, method="average") * 100
    return result


def add_scores(df):
    df = df.copy()
    eligible = df["minutes"] >= MIN_MINUTES_FOR_SCORES

    # attacking_score: how much of a goal threat is this player?
    # (goal output, shot volume on target, and finishing quality)
    df["attacking_score"] = (
        _percentile(df["goals_per90"], eligible)
        + _percentile(df["shots_on_target_per90"], eligible)
        + _percentile(df["goal_conversion"], eligible)
    ) / 3

    # creative_score: how much does this player create/build play?
    # (assists, passing volume, passing quality)
    df["creative_score"] = (
        _percentile(df["assists_per90"], eligible)
        + _percentile(df["passes_per90"], eligible)
        + _percentile(df["pass_accuracy_ratio"], eligible)
    ) / 3

    # defensive_score: how much defensive work does this player do, and win?
    # (tackles, interceptions, duel success rate)
    df["defensive_score"] = (
        _percentile(df["tackles_per90"], eligible)
        + _percentile(df["interceptions_per90"], eligible)
        + _percentile(df["duel_success_rate"], eligible)
    ) / 3

    # discipline_score: fewer cards per 90 = higher score (100 - percentile
    # of cards_per90, so a player with the most cards scores near 0).
    df["discipline_score"] = 100 - _percentile(df["cards_per90"], eligible)

    # overall_score: weighted blend of the four scores above.
    # Attacking/creative/defensive are weighted equally (0.3 each) since a
    # scouting view should value all three roles similarly; discipline is
    # a smaller factor (0.1) - it matters, but shouldn't dominate the
    # ranking of an otherwise excellent player.
    df["overall_score"] = (
        0.3 * df["attacking_score"]
        + 0.3 * df["creative_score"]
        + 0.3 * df["defensive_score"]
        + 0.1 * df["discipline_score"]
    )

    return df


def run():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if not os.path.exists(FEATURES_CSV_PATH):
        raise FileNotFoundError(f"{FEATURES_CSV_PATH} not found. Run feature_engineering.run() first.")

    df = pd.read_csv(FEATURES_CSV_PATH)
    df = add_scores(df)

    os.makedirs(os.path.dirname(SCORED_CSV_PATH), exist_ok=True)
    df.to_csv(SCORED_CSV_PATH, index=False)
    logger.info("Saved %d rows with scouting scores to %s", len(df), SCORED_CSV_PATH)
    return df


if __name__ == "__main__":
    run()
