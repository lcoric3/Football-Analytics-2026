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

from src import season_config
from src.scouting_scores import MIN_MINUTES_FOR_SCORES

logger = logging.getLogger(__name__)

SCORED_CSV_PATH = season_config.processed_path("hnl_player_scored")
ML_FEATURES_CSV_PATH = season_config.processed_path("hnl_ml_features")
SIMILARITY_OUTPUT_CSV_PATH = season_config.output_path("player_similarity_results")
CLUSTERS_OUTPUT_CSV_PATH = season_config.output_path("player_clusters")
CLUSTER_PROFILES_REPORT_PATH = season_config.cluster_profiles_report_path()

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
    # goalkeeper: shot-stopping volume, match outcomes, goals conceded, and
    # distribution accuracy - the same ingredients as goalkeeper_score in
    # scouting_scores.py. Comparing a goalkeeper's near-zero outfield stats
    # to an outfielder's real ones is meaningless, so a "goalkeeper" search
    # should almost always be combined with same_position_only=True (see
    # find_similar_players below).
    "goalkeeper": [
        "saves_per90", "clean_sheet_rate", "goals_conceded_per90", "pass_accuracy_ratio",
    ],
}

# Goalkeeper-specific per-90/ratio columns - not part of ML_FEATURE_COLS
# (they'd just be a near-constant 0 for every outfield player and add noise
# to the "overall" role's comparison), but needed in the ML dataset for the
# "goalkeeper" role above.
GOALKEEPER_ONLY_FEATURE_COLS = ["saves_per90", "clean_sheet_rate", "goals_conceded_per90"]

# Raw counting stats that don't already encode "goals" - safe to use as
# predictors when the target is goals, without leaking the answer.
GOALS_PREDICTION_FEATURES = [
    "minutes", "shots", "shots_on_target", "passes", "assists",
    "tackles", "interceptions", "duels_won",
]

MIN_SAMPLES_FOR_ML = 30

# --- Player clustering (Stage B5) -----------------------------------------
# Goalkeepers are clustered separately from outfield players (see
# cluster_players below) - their near-zero outfield numbers would
# otherwise just collapse into one arbitrary "goalkeeper" cluster and add
# noise to the outfield archetypes.
N_OUTFIELD_CLUSTERS = 8
N_GOALKEEPER_CLUSTERS = 2

# A cluster only earns a named archetype label if its z-scored profile
# clears this bar against that archetype's "signature" (below) - below it,
# the profile isn't distinctive enough to name confidently, so it falls
# back to a neutral "balanced profile" label instead of a forced/
# misleading one.
CLUSTER_NAME_CONFIDENCE = 0.5

# Each archetype signature lists features that should sit notably above
# (weight +1, or +0.5 for "somewhat") or below (weight -1) the population
# average for a cluster to earn that name - built from the same per-90/
# ratio features as the rest of this project's scores, not a new stat
# vocabulary. A cluster's fit score for an archetype is the weighted
# average of its own z-scores on these features (see _name_cluster).
OUTFIELD_ARCHETYPE_SIGNATURES = {
    "target forwards": {
        "goals_per90": 1, "aerials_won_per90": 1, "shots_on_target_per90": 1,
        "passes_per90": -1, "key_passes_per90": -1,
    },
    "high-volume finishers": {
        "shots_per90": 1, "goals_per90": 1, "goal_contribution_per90": 1,
        "tackles_per90": -1,
    },
    "dribbling creators": {
        "successful_dribbles_per90": 1, "dribble_success_rate": 1,
        "key_passes_per90": 1, "assists_per90": 1,
    },
    "creative midfielders": {
        "key_passes_per90": 1, "assists_per90": 1, "passes_per90": 1,
        "successful_dribbles_per90": 1,
    },
    "progressive distributors": {
        "long_balls_per90": 1, "accurate_long_balls_per90": 1,
        "passes_per90": 1, "key_passes_per90": 0.5,
    },
    "safe passers": {
        "passes_per90": 1, "pass_accuracy_ratio": 1,
        "key_passes_per90": -1, "long_balls_per90": -1,
    },
    "ball-playing defenders": {
        "tackles_per90": 1, "interceptions_per90": 1, "passes_per90": 1,
        "accurate_long_balls_per90": 1, "pass_accuracy_ratio": 1,
    },
    "defensive ball winners": {
        "tackles_per90": 1, "interceptions_per90": 1, "duel_success_rate": 1,
        "passes_per90": -1, "key_passes_per90": -1,
    },
}

GOALKEEPER_ARCHETYPE_SIGNATURES = {
    "shot-stoppers": {
        "saves_per90": 1, "clean_sheet_rate": 1, "goals_conceded_per90": -1,
        "pass_accuracy_ratio": -1,
    },
    "goalkeeper distributors": {
        "pass_accuracy_ratio": 1, "saves_per90": -1,
    },
}

# Some archetype names above assert a specific position (e.g. "ball-playing
# defenders" implies mostly Defenders) - but clustering never looks at the
# `position` column, only at per-90 stats, so a cluster can match that
# signature without actually being made up of that position (e.g. a group
# of ball-winning, accurate-passing central midfielders can statistically
# resemble "ball-playing defenders"). _name_cluster checks each of these
# against the cluster's actual position makeup and swaps in the neutral
# alternative if that position isn't an outright majority (>50%) of the
# cluster - "don't force a position-specific name the data doesn't support".
POSITION_IMPLIED_ARCHETYPES = {
    "target forwards": ("Attacker", "high-aerial-target profile"),
    "creative midfielders": ("Midfielder", "creative playmaking profile"),
    "ball-playing defenders": ("Defender", "defensive distributors"),
}


def build_ml_dataset(df):
    """Keep only players with enough minutes for their per-90 rates to be
    meaningful (same threshold used for scouting scores), and only the
    columns useful for similarity/clustering/prediction."""
    eligible = df[df["minutes"] >= MIN_MINUTES_FOR_SCORES].copy()
    keep_cols = (
        ["player_id", "player_name", "team_name", "position", "age", "minutes", "rating"]
        + ML_FEATURE_COLS
        + GOALKEEPER_ONLY_FEATURE_COLS
        + [
            "attacking_score", "creative_score", "defensive_score",
            "discipline_score", "overall_score",
            "dribbling_score", "passing_score", "duel_defending_score",
            "progressive_midfielder_score", "passer_defender_score",
            "goalkeeper_score",
            # Stage B1/B2 scores - kept here so downstream ML tooling (e.g.
            # Stage B4's replacement scouting) doesn't need to re-read the
            # scored CSV separately just for these.
            "age_bonus", "reliability_bonus", "age_potential_score",
            "team_average_score", "score_above_team_average",
            "standout_bonus", "weak_team_bonus", "underrated_score",
        ]
    )
    return eligible[keep_cols].reset_index(drop=True)


def find_similar_players(
    ml_df, player_name, role="overall", top_n=10,
    same_position_only=False, same_team_exclude=False,
    min_minutes=None, max_age=None,
):
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

    Stage B3 filters (all optional, applied to *candidates* only). Cosine
    similarity is always computed once, against the full `ml_df` population,
    *before* any filter narrows the candidate list - so which players
    qualify can change, but what "similar" means for the ones that do
    doesn't shift depending on which filters happen to be active:
      - same_position_only: keep only candidates sharing the query player's
        exact `position` value (e.g. "Midfielder" vs. "Midfielder") - a
        stricter, like-for-like comparison. Recommended for the
        "goalkeeper" role, since a goalkeeper's near-zero outfield numbers
        otherwise still get compared against every outfield player.
      - same_team_exclude: drop candidates from the query player's own
        `team_name` - useful when scouting for external alternatives rather
        than internal cover.
      - min_minutes: drop candidates with fewer minutes played than this -
        a reliability filter, so a matching statistical shape from a
        handful of cameos doesn't outrank a proven starter.
      - max_age: drop candidates older than this - e.g. for "similar young
        players" searches.
    """
    if role not in ROLE_FEATURE_SETS:
        raise ValueError(f"Unknown role '{role}'. Choose from: {sorted(ROLE_FEATURE_SETS)}")
    if player_name not in ml_df["player_name"].values:
        raise ValueError(f"'{player_name}' not found in the ML dataset.")

    feature_cols = ROLE_FEATURE_SETS[role]
    X = StandardScaler().fit_transform(ml_df[feature_cols])
    similarity_matrix = cosine_similarity(X)

    idx = ml_df.index[ml_df["player_name"] == player_name][0]
    query_row = ml_df.loc[idx]
    scores = pd.Series(similarity_matrix[idx], index=ml_df.index)
    scores = scores.drop(index=idx)

    candidates = ml_df.drop(index=idx)
    if same_position_only:
        candidates = candidates[candidates["position"] == query_row["position"]]
    if same_team_exclude:
        candidates = candidates[candidates["team_name"] != query_row["team_name"]]
    if min_minutes is not None:
        candidates = candidates[candidates["minutes"] >= min_minutes]
    if max_age is not None:
        candidates = candidates[candidates["age"] <= max_age]

    scores = scores.loc[candidates.index].sort_values(ascending=False)

    top_matches = ml_df.loc[scores.index[:top_n], ["player_name", "team_name", "position"]].copy()
    top_matches.insert(0, "rank", range(1, len(top_matches) + 1))
    top_matches["similarity"] = scores.values[:top_n]
    top_matches.insert(0, "role", role)
    top_matches.insert(0, "query_player", player_name)
    return top_matches


# A handful of representative searches, saved to
# SIMILARITY_OUTPUT_CSV_PATH on every pipeline run so the feature -
# including the Stage B3 filters - is demonstrated without requiring an
# interactive session.
EXAMPLE_SIMILARITY_QUERIES = [
    # same_position_only=True: a stricter, like-for-like comparison - only
    # other midfielders are considered, not just "similar per-90 shape"
    # regardless of role.
    {"player_name": "Ismaël Bennacer", "role": "midfielder", "same_position_only": True},
    {"player_name": "Dion Beljo", "role": "attacker"},
    {"player_name": "Sergi Domínguez", "role": "passer_defender"},
    # "Similar young players": no skill-specific role, just overall
    # statistical shape, filtered to this project's U23 cutoff (age <= 23).
    {"player_name": "Adriano Jagusic", "role": "overall", "max_age": 23},
]


def _describe_filters(query):
    """Human-readable summary of which Stage B3 filters a query used, for
    the saved CSV - e.g. "same_position_only=True", or "" if none were set."""
    parts = []
    if query.get("same_position_only"):
        parts.append("same_position_only=True")
    if query.get("same_team_exclude"):
        parts.append("same_team_exclude=True")
    if query.get("min_minutes") is not None:
        parts.append(f"min_minutes>={query['min_minutes']}")
    if query.get("max_age") is not None:
        parts.append(f"max_age<={query['max_age']}")
    return ", ".join(parts)


def build_similarity_examples(ml_df, queries=EXAMPLE_SIMILARITY_QUERIES, top_n=10):
    tables = []
    for query in queries:
        player_name = query["player_name"]
        filter_kwargs = {k: v for k, v in query.items() if k != "player_name"}
        try:
            table = find_similar_players(ml_df, player_name, top_n=top_n, **filter_kwargs)
            table.insert(2, "filters", _describe_filters(query))
            tables.append(table)
        except ValueError as exc:
            logger.warning("Similarity example skipped: %s", exc)
    if not tables:
        return pd.DataFrame(columns=[
            "query_player", "role", "filters", "rank", "player_name",
            "team_name", "position", "similarity",
        ])
    return pd.concat(tables, ignore_index=True)


def _cluster_population_zscores(df, feature_cols):
    """Per-feature mean/std of the whole population - the reference frame
    every individual cluster's own mean gets compared against in
    _name_cluster. std of 0 (a constant feature) is replaced with 1 to
    avoid a division by zero."""
    means = df[feature_cols].mean()
    stds = df[feature_cols].std().replace(0, 1)
    return means, stds


def _name_cluster(cluster_mean_z, signatures, used_names, position_counts):
    """Pick the best-matching archetype name for one cluster's z-scored
    profile - the archetype whose signature's weighted-average z-score is
    highest, as long as it clears CLUSTER_NAME_CONFIDENCE. Returns None if
    no archetype fits confidently (caller assigns a neutral fallback name),
    so a cluster is never forced into a label the data doesn't support.

    If the best match is one of POSITION_IMPLIED_ARCHETYPES (a name that
    asserts a specific position), `position_counts` - the cluster's own
    position value-counts - is checked: the implied position must be an
    outright majority (>50%) of the cluster, or the neutral alternative is
    used instead (see POSITION_IMPLIED_ARCHETYPES above).

    If an archetype was already used for an earlier cluster in the same
    population, later clusters get a "(variant N)" suffix rather than an
    identical, ambiguous duplicate label."""
    best_name, best_score = None, CLUSTER_NAME_CONFIDENCE
    for name, signature in signatures.items():
        score = sum(
            weight * cluster_mean_z.get(feature, 0.0) for feature, weight in signature.items()
        ) / len(signature)
        if score > best_score:
            best_name, best_score = name, score

    if best_name is None:
        return None

    if best_name in POSITION_IMPLIED_ARCHETYPES:
        implied_position, neutral_alternative = POSITION_IMPLIED_ARCHETYPES[best_name]
        total = position_counts.sum()
        implied_share = position_counts.get(implied_position, 0) / total if total else 0
        if implied_share <= 0.5:
            best_name = neutral_alternative

    occurrence = used_names.get(best_name, 0) + 1
    used_names[best_name] = occurrence
    return best_name if occurrence == 1 else f"{best_name} (variant {occurrence})"


def _cluster_group(df, feature_cols, n_clusters, signatures, id_offset=0):
    """KMeans + z-score-based archetype naming for one player population
    (outfield or goalkeepers) - shared by both branches of
    cluster_players(). Returns (labeled_df, {cluster_id: zscore_series})."""
    X = StandardScaler().fit_transform(df[feature_cols])
    kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
    labels = kmeans.fit_predict(X) + id_offset

    result = df.copy()
    result["cluster_id"] = labels

    pop_means, pop_stds = _cluster_population_zscores(df, feature_cols)
    used_names = {}
    id_to_name = {}
    id_to_zscores = {}
    for cluster_id in sorted(result["cluster_id"].unique()):
        cluster_rows = result.loc[result["cluster_id"] == cluster_id]
        cluster_mean = cluster_rows[feature_cols].mean()
        cluster_mean_z = (cluster_mean - pop_means) / pop_stds
        position_counts = cluster_rows["position"].value_counts()
        name = _name_cluster(cluster_mean_z, signatures, used_names, position_counts)
        # No "Cluster N:" prefix baked in here - the report/CSV already show
        # cluster_id as its own column/heading, so adding it here would
        # duplicate it (e.g. "Cluster 3: Cluster 3: balanced profile").
        id_to_name[cluster_id] = name if name is not None else "balanced profile"
        id_to_zscores[cluster_id] = cluster_mean_z

    result["cluster_name"] = result["cluster_id"].map(id_to_name)
    return result, id_to_zscores


def cluster_players(
    ml_df, n_outfield_clusters=N_OUTFIELD_CLUSTERS, n_goalkeeper_clusters=N_GOALKEEPER_CLUSTERS,
):
    """
    Groups players into named statistical archetypes - NOT a quality
    ranking. KMeans has no notion of "good" or "bad", only "close together
    in feature space" - a cluster name describes a *playing style*, the
    same idea as the cosine-similarity search above, just grouping many
    players instead of comparing two.

    Outfield players and goalkeepers are clustered separately (see the
    module-level comment above N_OUTFIELD_CLUSTERS) using different
    feature sets: ML_FEATURE_COLS for outfield players,
    GOALKEEPER_ONLY_FEATURE_COLS + pass_accuracy_ratio for goalkeepers.

    Each cluster's own feature averages are compared against its
    population's (a z-score per feature - see _cluster_population_zscores),
    then matched against the archetype "signatures" defined above
    (OUTFIELD_ARCHETYPE_SIGNATURES / GOALKEEPER_ARCHETYPE_SIGNATURES). If a
    population is too small to cluster meaningfully (fewer players than
    clusters requested), it's skipped entirely and those rows get a
    "Not enough players to cluster" label instead of a forced grouping.

    The per-cluster z-score profiles are stashed on the returned
    DataFrame's `.attrs["cluster_zscores"]` (a {cluster_id: z-score
    Series} dict) so build_cluster_profiles_report can reuse them for its
    "playing style" explanations without recomputing anything.
    """
    outfield_df = ml_df[ml_df["position"] != "Goalkeeper"]
    goalkeeper_df = ml_df[ml_df["position"] == "Goalkeeper"]

    parts = []
    zscores = {}

    if len(outfield_df) >= n_outfield_clusters:
        clustered, cluster_z = _cluster_group(
            outfield_df, ML_FEATURE_COLS, n_outfield_clusters, OUTFIELD_ARCHETYPE_SIGNATURES,
        )
        parts.append(clustered)
        zscores.update(cluster_z)
    else:
        logger.info(
            "Not enough outfield players (%d) for %d clusters - skipping outfield clustering.",
            len(outfield_df), n_outfield_clusters,
        )
        skipped = outfield_df.copy()
        skipped["cluster_id"] = np.nan
        skipped["cluster_name"] = "Not enough players to cluster"
        parts.append(skipped)

    if len(goalkeeper_df) >= n_goalkeeper_clusters:
        goalkeeper_feature_cols = GOALKEEPER_ONLY_FEATURE_COLS + ["pass_accuracy_ratio"]
        clustered, cluster_z = _cluster_group(
            goalkeeper_df, goalkeeper_feature_cols, n_goalkeeper_clusters,
            GOALKEEPER_ARCHETYPE_SIGNATURES, id_offset=n_outfield_clusters,
        )
        parts.append(clustered)
        zscores.update(cluster_z)
    else:
        logger.info(
            "Not enough goalkeepers (%d) for %d clusters - skipping goalkeeper clustering.",
            len(goalkeeper_df), n_goalkeeper_clusters,
        )
        skipped = goalkeeper_df.copy()
        skipped["cluster_id"] = np.nan
        skipped["cluster_name"] = "Not enough players to cluster"
        parts.append(skipped)

    result = pd.concat(parts).sort_index()
    result.attrs["cluster_zscores"] = zscores
    return result


def _describe_cluster_style(cluster_mean_z, top_n=3):
    """Turn a cluster's z-scored profile into a short, plain-English
    description - the top `top_n` features by |z-score|, phrased as
    above/below the population average. Purely descriptive (not used for
    naming), so it stays honest even for a "balanced profile" cluster."""
    ranked = cluster_mean_z.abs().sort_values(ascending=False).head(top_n)
    parts = []
    for feature in ranked.index:
        z = cluster_mean_z[feature]
        direction = "above" if z > 0 else "below"
        parts.append(f"`{feature}` {direction} average ({z:+.1f}σ)")
    return "; ".join(parts)


def _md_cluster_table(df):
    """Tiny Markdown-table writer for the cluster profiles report -
    mirrors report.py's _md_table but kept local to avoid a cross-module
    import just for this."""
    columns = ["player_name", "team_name", "position", "age", "minutes", "quality_score"]
    headers = ["Player", "Team", "Position", "Age", "Minutes", "Quality Score"]
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join([":---"] * len(headers)) + "|"]
    for _, row in df.iterrows():
        age = f"{row['age']:.0f}" if pd.notna(row["age"]) else ""
        minutes = f"{row['minutes']:.0f}" if pd.notna(row["minutes"]) else ""
        quality = f"{row['quality_score']:.1f}" if pd.notna(row["quality_score"]) else ""
        lines.append(
            f"| {row['player_name']} | {row['team_name']} | {row['position']} | "
            f"{age} | {minutes} | {quality} |"
        )
    return "\n".join(lines)


def build_cluster_profiles_report(clustered_df, top_n_players=5):
    """Markdown summary of every cluster produced by cluster_players() -
    cluster_id, cluster_name, top players, average age/minutes, and a
    plain-English playing-style description built from the same z-scores
    used to name the cluster (see cluster_players' docstring)."""
    zscores = clustered_df.attrs.get("cluster_zscores", {})

    clustered_df = clustered_df.copy()
    # quality_score is only used to pick which players to *show* as
    # examples within a cluster - it plays no part in the clustering
    # itself, which never looks at overall_score/goalkeeper_score.
    clustered_df["quality_score"] = np.where(
        clustered_df["position"] == "Goalkeeper",
        clustered_df["goalkeeper_score"],
        clustered_df["overall_score"],
    )

    lines = ["# Player Cluster Profiles\n"]
    lines.append(
        "KMeans groups players purely by *statistical shape* - each cluster "
        "below is a playing style, not a quality tier. An elite and a "
        "modest player can land in the same cluster if their per-90 rates "
        "have a similar shape, the same idea as the cosine-similarity "
        "search explained in the README. `quality_score` (`overall_score` "
        "for outfield players, `goalkeeper_score` for goalkeepers) is only "
        "used below to choose which players to show as examples - it has "
        "no influence on which cluster a player was assigned to.\n\n"
        "**Cluster names describe playing style, not literal position.** "
        "Clustering looks only at per-90 stats, never at the `position` "
        "column, so an archetype name like \"ball-playing defenders\" can "
        "include a deep-lying midfielder whose tackle/pass profile matches "
        "that style - see each player's own `position` column for their "
        "actual role.\n"
    )

    cluster_ids = sorted(clustered_df["cluster_id"].dropna().unique())
    for cluster_id in cluster_ids:
        subset = clustered_df[clustered_df["cluster_id"] == cluster_id]
        name = subset["cluster_name"].iloc[0]

        lines.append(f"## Cluster {int(cluster_id)}: {name}\n")
        lines.append(f"- **Players in cluster:** {len(subset)}")
        lines.append(f"- **Average age:** {subset['age'].mean():.1f}")
        lines.append(f"- **Average minutes:** {subset['minutes'].mean():.0f}")

        cluster_z = zscores.get(cluster_id)
        if cluster_z is not None:
            lines.append(f"- **Playing style:** {_describe_cluster_style(cluster_z)}")
        lines.append("")

        top_players = subset.sort_values("quality_score", ascending=False).head(top_n_players)
        lines.append("**Top players in this cluster:**\n")
        lines.append(_md_cluster_table(top_players))
        lines.append("")

    unclustered = clustered_df[clustered_df["cluster_id"].isna()]
    if not unclustered.empty:
        lines.append("## Not Clustered\n")
        lines.append(
            f"{len(unclustered)} player(s) belonged to a population too small "
            "to cluster meaningfully this run (see `cluster_name`).\n"
        )

    return "\n".join(lines) + "\n"


CLUSTER_CSV_COLUMNS = [
    "cluster_id", "cluster_name", "player_id", "player_name", "team_name",
    "position", "age", "minutes", "quality_score",
]


def save_cluster_outputs(clustered_df):
    """Saves CLUSTERS_OUTPUT_CSV_PATH (one row per player, sorted by
    cluster then quality_score) and CLUSTER_PROFILES_REPORT_PATH."""
    output_df = clustered_df.copy()
    output_df["quality_score"] = np.where(
        output_df["position"] == "Goalkeeper",
        output_df["goalkeeper_score"],
        output_df["overall_score"],
    )

    os.makedirs(os.path.dirname(CLUSTERS_OUTPUT_CSV_PATH), exist_ok=True)
    output_df[CLUSTER_CSV_COLUMNS].sort_values(
        ["cluster_id", "quality_score"], ascending=[True, False]
    ).to_csv(CLUSTERS_OUTPUT_CSV_PATH, index=False)
    logger.info(
        "Saved %d rows across %d clusters to %s",
        len(output_df), output_df["cluster_id"].nunique(), CLUSTERS_OUTPUT_CSV_PATH,
    )

    report_text = build_cluster_profiles_report(clustered_df)
    os.makedirs(os.path.dirname(CLUSTER_PROFILES_REPORT_PATH), exist_ok=True)
    with open(CLUSTER_PROFILES_REPORT_PATH, "w", encoding="utf-8") as f:
        f.write(report_text)
    logger.info("Saved cluster profiles report to %s", CLUSTER_PROFILES_REPORT_PATH)


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

    ml_df = cluster_players(ml_df)
    save_cluster_outputs(ml_df)

    predict_rating(ml_df)
    predict_goals(scored_df)

    os.makedirs(os.path.dirname(ML_FEATURES_CSV_PATH), exist_ok=True)
    ml_df.to_csv(ML_FEATURES_CSV_PATH, index=False)
    logger.info("Saved %d rows of ML-ready features to %s", len(ml_df), ML_FEATURES_CSV_PATH)
    return ml_df


if __name__ == "__main__":
    run()
