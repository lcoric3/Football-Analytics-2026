"""
Stage 7: ML-ready dataset and simple ML models.

Football data science logic:
This dataset has ~300-400 players and a few dozen features - too small
for a neural network to reliably beat simpler methods, so this module
uses scikit-learn (RandomForestRegressor, KMeans, cosine similarity)
rather than a deep learning model. Similarity and clustering are
*unsupervised* - they need no target/label, just "which players look
alike statistically" - which is exactly what scouting comparisons need.

Supervised prediction (rating, goals) is included as *optional*, because
this season's dataset doesn't yet have a strong causal target:
  - `rating` is itself partly derived from the same match events as our
    features, so a good R2 mostly confirms the features are sensible
    rather than "predicting" something new.
  - `goals` is directly determined by shot volume + finishing, so a model
    can only be informative if it's kept free of features that already
    encode goals (goals_per90, goal_conversion, etc. are excluded below
    to avoid leaking the answer into the input).
Both are skipped automatically (with an explanation logged) if there
isn't enough data to split into a meaningful train/test set.
"""
import logging
import os

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

from src.scouting_scores import MIN_MINUTES_FOR_SCORES

logger = logging.getLogger(__name__)

SCORED_CSV_PATH = "data/processed/hnl_player_scored_2025_2026.csv"
ML_FEATURES_CSV_PATH = "data/processed/hnl_ml_features_2025_2026.csv"

# Per-90 rates and ratios (not raw totals) - these are what make players
# comparable to each other regardless of how many minutes they played.
ML_FEATURE_COLS = [
    "goals_per90", "assists_per90", "shots_per90", "shots_on_target_per90",
    "passes_per90", "tackles_per90", "interceptions_per90", "cards_per90",
    "shot_accuracy", "goal_conversion", "pass_accuracy_ratio",
    "duel_success_rate", "minutes_per_appearance", "goal_contribution_per90",
]

# Raw counting stats that don't already encode "goals" - safe to use as
# predictors when the target is goals, without leaking the answer.
GOALS_PREDICTION_FEATURES = [
    "minutes", "shots", "shots_on_target", "passes", "assists",
    "tackles", "interceptions", "duels_won",
]

MIN_SAMPLES_FOR_ML = 30
N_CLUSTERS = 4


def build_ml_dataset(df):
    """Keep only players with enough minutes for their per-90 rates to be
    meaningful (same threshold used for scouting scores), and only the
    columns useful for similarity/clustering/prediction."""
    eligible = df[df["minutes"] >= MIN_MINUTES_FOR_SCORES].copy()
    keep_cols = (
        ["player_id", "player_name", "team_name", "position", "age", "minutes", "rating"]
        + ML_FEATURE_COLS
        + ["attacking_score", "creative_score", "defensive_score", "discipline_score", "overall_score"]
    )
    return eligible[keep_cols].reset_index(drop=True)


def find_similar_players(ml_df, player_name, top_n=5):
    """
    Cosine similarity: standardize each feature (so no single metric like
    passes_per90 dominates just because it has bigger numbers), then treat
    each player as a vector and measure the angle between vectors. Players
    with a similar statistical *profile* (not just similar totals) end up
    with a similarity close to 1.0.
    """
    if player_name not in ml_df["player_name"].values:
        raise ValueError(f"'{player_name}' not found in the ML dataset.")

    X = StandardScaler().fit_transform(ml_df[ML_FEATURE_COLS])
    similarity_matrix = cosine_similarity(X)

    idx = ml_df.index[ml_df["player_name"] == player_name][0]
    scores = pd.Series(similarity_matrix[idx], index=ml_df.index)
    scores = scores.drop(index=idx).sort_values(ascending=False)

    top_matches = ml_df.loc[scores.index[:top_n], ["player_name", "team_name", "position"]].copy()
    top_matches["similarity"] = scores.values[:top_n]
    return top_matches


def cluster_players(ml_df, n_clusters=N_CLUSTERS):
    """
    KMeans groups players into n_clusters based on statistical similarity,
    with no notion of "goals" or "position" - it just finds players whose
    per-90 profiles sit close together in feature space. In practice this
    tends to separate archetypes (e.g. high-tackle/low-pass "destroyers"
    vs. high-pass/low-tackle "deep playmakers") without us having to
    define those archetypes by hand.
    """
    X = StandardScaler().fit_transform(ml_df[ML_FEATURE_COLS])
    kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
    labels = kmeans.fit_predict(X)

    result = ml_df.copy()
    result["cluster"] = labels

    summary = result.groupby("cluster")[ML_FEATURE_COLS].mean().round(2)
    logger.info("Cluster profiles (mean per-90/ratio values):\n%s", summary)

    return result


def _evaluate_regressor(X, y, label):
    if len(X) < MIN_SAMPLES_FOR_ML:
        logger.info(
            "Skipping %s prediction: only %d eligible players, need at least %d. "
            "This dataset is currently better suited to scouting/ranking and "
            "unsupervised ML (similarity, clustering) than supervised prediction - "
            "a single HNL season just doesn't have enough rows yet.",
            label, len(X), MIN_SAMPLES_FOR_ML,
        )
        return None

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42
    )
    model = RandomForestRegressor(n_estimators=200, random_state=42)
    model.fit(X_train, y_train)
    predictions = model.predict(X_test)

    mae = mean_absolute_error(y_test, predictions)
    rmse = np.sqrt(mean_squared_error(y_test, predictions))
    r2 = r2_score(y_test, predictions)
    logger.info(
        "%s prediction (n=%d, %d train / %d test): MAE=%.3f RMSE=%.3f R2=%.3f",
        label, len(X), len(X_train), len(X_test), mae, rmse, r2,
    )
    return {"mae": mae, "rmse": rmse, "r2": r2}


def predict_rating(ml_df):
    data = ml_df.dropna(subset=["overall_score", "rating"])
    if data.empty:
        logger.info("No 'rating' data available - skipping rating prediction.")
        return None
    return _evaluate_regressor(data[ML_FEATURE_COLS], data["rating"], "Rating")


def predict_goals(scored_df):
    """Uses the full scored dataset (not the per-90 ML dataset) because the
    predictors here are raw counts, not per-90 rates."""
    data = scored_df[scored_df["minutes"] >= MIN_MINUTES_FOR_SCORES].dropna(
        subset=GOALS_PREDICTION_FEATURES + ["goals"]
    )
    return _evaluate_regressor(data[GOALS_PREDICTION_FEATURES], data["goals"], "Goals")


def run():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if not os.path.exists(SCORED_CSV_PATH):
        raise FileNotFoundError(f"{SCORED_CSV_PATH} not found. Run scouting_scores.run() first.")

    scored_df = pd.read_csv(SCORED_CSV_PATH)
    ml_df = build_ml_dataset(scored_df)

    if len(ml_df) >= 2:
        top_player = ml_df.sort_values("overall_score", ascending=False)["player_name"].iloc[0]
        try:
            similar = find_similar_players(ml_df, top_player, top_n=5)
            logger.info("Players most similar to %s:\n%s", top_player, similar.to_string(index=False))
        except ValueError as exc:
            logger.warning("Similarity demo skipped: %s", exc)

    if len(ml_df) >= N_CLUSTERS:
        ml_df = cluster_players(ml_df, n_clusters=N_CLUSTERS)
    else:
        logger.info("Not enough eligible players for %d clusters - skipping clustering.", N_CLUSTERS)

    predict_rating(ml_df)
    predict_goals(scored_df)

    os.makedirs(os.path.dirname(ML_FEATURES_CSV_PATH), exist_ok=True)
    ml_df.to_csv(ML_FEATURES_CSV_PATH, index=False)
    logger.info("Saved %d rows of ML-ready features to %s", len(ml_df), ML_FEATURES_CSV_PATH)
    return ml_df


if __name__ == "__main__":
    run()
