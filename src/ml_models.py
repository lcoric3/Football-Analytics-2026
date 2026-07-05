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
SIMILARITY_OUTPUT_CSV_PATH = "data/output/player_similarity_results.csv"

# Per-90 rates and ratios (not raw totals) - these are what make players
# comparable to each other regardless of how many minutes they played.
ML_FEATURE_COLS = [
    "goals_per90", "assists_per90", "shots_per90", "shots_on_target_per90",
    "passes_per90", "tackles_per90", "interceptions_per90", "cards_per90",
    "shot_accuracy", "goal_conversion", "pass_accuracy_ratio",
    "duel_success_rate", "minutes_per_appearance", "goal_contribution_per90",
    # Added alongside Stage 1's dribbling/passing/duel-defending scores.
    "successful_dribbles_per90", "dribble_success_rate", "fouls_drawn_per90",
    "crosses_per90", "accurate_crosses_per90", "cross_accuracy",
    "long_balls_per90", "accurate_long_balls_per90", "long_ball_accuracy",
    "key_passes_per90", "aerials_won_per90", "clearances_per90",
]

# Role-based similarity search: comparing a striker to a centre-back on
# "shots_per90" is meaningless (the CB will always look like an outlier),
# so each role compares players on only the stats relevant to that role,
# not the full statistical profile. "overall" is the exception - it
# deliberately uses every feature, for a general "who plays like this
# player, period" comparison.
ROLE_FEATURE_SETS = {
    "overall": ML_FEATURE_COLS,
    "attacker": [
        "goals_per90", "shots_per90", "shots_on_target_per90",
        "shot_accuracy", "goal_conversion", "goal_contribution_per90",
    ],
    "midfielder": [
        "passes_per90", "key_passes_per90", "assists_per90",
        "tackles_per90", "interceptions_per90",
        "successful_dribbles_per90", "pass_accuracy_ratio",
    ],
    "defender": [
        "tackles_per90", "interceptions_per90", "duel_success_rate",
        "aerials_won_per90", "clearances_per90", "cards_per90",
    ],
    "dribbler": [
        "successful_dribbles_per90", "dribble_success_rate", "fouls_drawn_per90",
    ],
    "passer": [
        "passes_per90", "key_passes_per90", "pass_accuracy_ratio",
        "accurate_long_balls_per90", "accurate_crosses_per90",
    ],
    "progressive_midfielder": [
        "key_passes_per90", "long_balls_per90",
        "successful_dribbles_per90", "assists_per90",
    ],
    "duel_defender": [
        "tackles_per90", "interceptions_per90", "duel_success_rate",
        "aerials_won_per90", "clearances_per90",
    ],
    # passer_defender and ball_playing_defender intentionally share the same
    # feature set - scouting_scores.py backs both rankings with one shared
    # passer_defender_score (Stage 1/2 decision), so a role-consistent
    # similarity search should compare players the same way too.
    "passer_defender": [
        "passes_per90", "pass_accuracy_ratio", "accurate_long_balls_per90",
        "key_passes_per90", "tackles_per90", "interceptions_per90", "duel_success_rate",
    ],
    "ball_playing_defender": [
        "passes_per90", "pass_accuracy_ratio", "accurate_long_balls_per90",
        "key_passes_per90", "tackles_per90", "interceptions_per90", "duel_success_rate",
    ],
}

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
        + [
            "attacking_score", "creative_score", "defensive_score",
            "discipline_score", "overall_score",
            "dribbling_score", "passing_score", "duel_defending_score",
            "progressive_midfielder_score", "passer_defender_score",
            "goalkeeper_score",
        ]
    )
    return eligible[keep_cols].reset_index(drop=True)


def find_similar_players(ml_df, player_name, role="overall", top_n=10):
    """
    Find the top_n players most similar to `player_name`, using only the
    stats relevant to `role` (see ROLE_FEATURE_SETS above).

    Cosine similarity, in scouting terms: think of each player as a list of
    numbers (their per-90 rates and ratios for the chosen role - e.g. for
    "attacker" that's [goals_per90, shots_per90, shot_accuracy, ...]). That
    list is a *vector* - a point in space, one axis per stat. Cosine
    similarity measures the *angle* between two players' vectors, not the
    distance between them. That matters because it compares *shape* rather
    than *size*: a squad player with 300 minutes and a nailed-on starter
    with 2500 minutes can have nearly identical *rates* (goals per90, pass
    accuracy, etc.) even though their raw totals are worlds apart - cosine
    similarity says "these two play the same way", where a raw-number
    comparison would wrongly say "these two are nothing alike" just because
    one has played far more. A score of 1.0 means identical shape/style;
    0 means no relationship; scores are standardized first (each stat
    rescaled to the same spread) so a big-number stat like passes_per90
    doesn't automatically outweigh a small-number stat like goals_per90.
    """
    if role not in ROLE_FEATURE_SETS:
        raise ValueError(f"Unknown role '{role}'. Choose from: {sorted(ROLE_FEATURE_SETS)}")
    if player_name not in ml_df["player_name"].values:
        raise ValueError(f"'{player_name}' not found in the ML dataset.")

    feature_cols = ROLE_FEATURE_SETS[role]
    X = StandardScaler().fit_transform(ml_df[feature_cols])
    similarity_matrix = cosine_similarity(X)

    idx = ml_df.index[ml_df["player_name"] == player_name][0]
    scores = pd.Series(similarity_matrix[idx], index=ml_df.index)
    scores = scores.drop(index=idx).sort_values(ascending=False)

    top_matches = ml_df.loc[scores.index[:top_n], ["player_name", "team_name", "position"]].copy()
    top_matches.insert(0, "rank", range(1, len(top_matches) + 1))
    top_matches["similarity"] = scores.values[:top_n]
    top_matches.insert(0, "role", role)
    top_matches.insert(0, "query_player", player_name)
    return top_matches


# A handful of representative searches, saved to
# data/output/player_similarity_results.csv on every pipeline run so the
# feature is demonstrated without requiring an interactive session.
EXAMPLE_SIMILARITY_QUERIES = [
    ("Ismaël Bennacer", "overall"),
    ("Sergi Domínguez", "passer_defender"),
    ("Dion Beljo", "attacker"),
]


def build_similarity_examples(ml_df, queries=EXAMPLE_SIMILARITY_QUERIES, top_n=10):
    tables = []
    for player_name, role in queries:
        try:
            tables.append(find_similar_players(ml_df, player_name, role=role, top_n=top_n))
        except ValueError as exc:
            logger.warning("Similarity example skipped: %s", exc)
    if not tables:
        return pd.DataFrame(columns=["query_player", "role", "rank", "player_name", "team_name", "position", "similarity"])
    return pd.concat(tables, ignore_index=True)


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
        similarity_examples = build_similarity_examples(ml_df)
        if not similarity_examples.empty:
            os.makedirs(os.path.dirname(SIMILARITY_OUTPUT_CSV_PATH), exist_ok=True)
            similarity_examples.to_csv(SIMILARITY_OUTPUT_CSV_PATH, index=False)
            logger.info(
                "Saved %d similarity example rows to %s",
                len(similarity_examples), SIMILARITY_OUTPUT_CSV_PATH,
            )

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
