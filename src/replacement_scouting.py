"""
Stage B4: replacement scouting - given a departing player, find a
statistical shortlist of replacement targets.

Football data science logic:
This is deliberately NOT a transfer recommendation. It's a reproducible
way to turn "who plays like this player, is a smart pick right now, and
might be undervalued" into a ranked list - a starting point for a human
scout, not a substitute for one. It says nothing about video-scouted
technique/decision-making, tactical fit, injury history, character, or
transfer feasibility (fee, release clause, wage demands, contract
length). See replacement_score below for exactly what does go into it.
"""
import logging
import os

import pandas as pd

from src import ml_models

logger = logging.getLogger(__name__)

REPLACEMENT_OUTPUT_CSV_PATH = "data/output/replacement_targets.csv"

# "Same or similar role": when the caller doesn't pick an ml_models role
# explicitly, default to the role that matches the departing player's own
# position, so a caller doesn't need to know ml_models' role names to get
# a sensible first search.
DEFAULT_ROLE_BY_POSITION = {
    "Attacker": "attacker",
    "Midfielder": "midfielder",
    "Defender": "defender",
    "Goalkeeper": "goalkeeper",
}

# --- replacement_score weights (Stage B4) ---------------------------------
# replacement_score is a weighted sum of four 0-100-ish signals, plus one
# optional flat bonus - every point is traceable to one of these five
# ingredients, not a black-box blend:
#
#   replacement_score = SIMILARITY_WEIGHT      * (similarity * 100)
#                      + AGE_POTENTIAL_WEIGHT   * age_potential_score
#                      + UNDERRATED_WEIGHT      * underrated_score
#                      + RELIABILITY_WEIGHT     * reliability_percentile
#                      + younger_bonus
#
# Weights sum to 1.0 across the four percentage-based ingredients:
#   - similarity (0.4, the largest share): is this candidate actually the
#     same *kind* of player? Weighted highest because a statistically
#     dissimilar player isn't a real replacement no matter how good their
#     other numbers are. Scaled from its native 0-1 range to 0-100 so it
#     sits on the same scale as the other three ingredients.
#   - age_potential_score (0.3): current output *and* age/reliability
#     upside (see scouting_scores.py) - prefer a replacement who's good
#     now and has runway to keep improving, not just a like-for-like match.
#   - underrated_score (0.2): current output plus a team-context bonus for
#     outperforming their own team / playing at a smaller club (see
#     scouting_scores.py) - a nod toward "good value", not just "good".
#   - reliability_percentile (0.1): percentile rank of minutes played,
#     *among this candidate pool only* (not the whole league) - has this
#     candidate already proven they can hold down a starting role among
#     the realistic options for this specific search? Smallest weight -
#     useful as a tie-breaker, not a dominant factor.
SIMILARITY_WEIGHT = 0.4
AGE_POTENTIAL_WEIGHT = 0.3
UNDERRATED_WEIGHT = 0.2
RELIABILITY_WEIGHT = 0.1

# younger_bonus: a flat, capped nudge (not a percentage weight) - a
# replacement younger than the departing player is often the better
# squad-building outcome, all else being close to equal, but this should
# only break near-ties, not override a clearly better statistical match.
YOUNGER_BONUS = 5.0


def find_replacement_targets(
    ml_df, player_name, role=None, top_n=10,
    same_position_only=True, same_team_exclude=True,
    min_minutes=None, max_age=None, younger_bonus=True,
):
    """
    Given a departing player, return a ranked shortlist of statistical
    replacement targets. NOT a transfer recommendation - see the module
    docstring and README's "Replacement scouting" section for the caveats.

    Built directly on ml_models.find_similar_players - reuses its cosine
    similarity search and every one of its filters:
      - role: defaults to DEFAULT_ROLE_BY_POSITION[player's own position]
        ("same or similar role") if not given explicitly.
      - same_position_only (default True here - a "replacement" is usually
        expected to play the same position as the departing player).
      - same_team_exclude (default True here - a replacement is usually
        sought *outside* the player's own squad, unlike a general
        similarity search where that defaults to False).
      - min_minutes, max_age: passed straight through.

    On top of the raw similarity results, this adds `replacement_score`
    (see the constants/comment above this function for the exact formula)
    and an optional `younger_bonus` for candidates younger than the
    departing player, then re-sorts by `replacement_score` instead of raw
    similarity - so the final ranking reflects "good replacement", not
    just "statistically similar".
    """
    if player_name not in ml_df["player_name"].values:
        raise ValueError(f"'{player_name}' not found in the ML dataset.")

    query_row = ml_df[ml_df["player_name"] == player_name].iloc[0]
    if role is None:
        role = DEFAULT_ROLE_BY_POSITION.get(query_row["position"], "overall")

    # Ask for every filtered-and-ranked candidate (not just top_n) so
    # replacement_score can re-rank the full pool before truncating.
    similar = ml_models.find_similar_players(
        ml_df, player_name, role=role, top_n=len(ml_df),
        same_position_only=same_position_only,
        same_team_exclude=same_team_exclude,
        min_minutes=min_minutes,
        max_age=max_age,
    )

    empty_columns = [
        "query_player", "role", "rank", "player_name", "team_name", "position",
        "age", "minutes", "similarity", "age_potential_score", "underrated_score",
        "reliability_percentile", "younger_bonus", "replacement_score",
    ]
    if similar.empty:
        return pd.DataFrame(columns=empty_columns)

    candidates = similar.drop(columns=["rank"]).merge(
        ml_df[["player_name", "age", "minutes", "age_potential_score", "underrated_score"]],
        on="player_name", how="left",
    )

    # reliability_percentile: minutes rank *within this candidate pool*
    # (not the whole league) - "who's the most proven starter among the
    # realistic options this specific search turned up".
    candidates["reliability_percentile"] = candidates["minutes"].rank(pct=True) * 100

    candidates["younger_bonus"] = 0.0
    if younger_bonus and pd.notna(query_row["age"]):
        candidates.loc[candidates["age"] < query_row["age"], "younger_bonus"] = YOUNGER_BONUS

    candidates["replacement_score"] = (
        SIMILARITY_WEIGHT * (candidates["similarity"] * 100)
        + AGE_POTENTIAL_WEIGHT * candidates["age_potential_score"]
        + UNDERRATED_WEIGHT * candidates["underrated_score"]
        + RELIABILITY_WEIGHT * candidates["reliability_percentile"]
        + candidates["younger_bonus"]
    )

    result = (
        candidates.dropna(subset=["replacement_score"])
        .sort_values("replacement_score", ascending=False)
        .head(top_n)
        .reset_index(drop=True)
    )
    result.insert(0, "rank", range(1, len(result) + 1))
    return result[empty_columns]


# A handful of representative searches, saved to
# data/output/replacement_targets.csv on every pipeline run so the feature
# is demonstrated without requiring an interactive session.
EXAMPLE_REPLACEMENT_QUERIES = [
    {"player_name": "Dion Beljo"},
    {"player_name": "Ismaël Bennacer"},
    {"player_name": "Sergi Domínguez"},
    # "if useful": a young-player example, restricted to candidates the
    # same age or younger so it reads as "who could develop into this
    # role next", not just "who plays like him right now".
    {"player_name": "Gabriel Vidovic", "max_age": 23},
]


def build_replacement_examples(ml_df, queries=EXAMPLE_REPLACEMENT_QUERIES, top_n=10):
    tables = []
    for query in queries:
        player_name = query["player_name"]
        filter_kwargs = {k: v for k, v in query.items() if k != "player_name"}
        try:
            tables.append(find_replacement_targets(ml_df, player_name, top_n=top_n, **filter_kwargs))
        except ValueError as exc:
            logger.warning("Replacement scouting example skipped: %s", exc)
    if not tables:
        return pd.DataFrame(columns=[
            "query_player", "role", "rank", "player_name", "team_name", "position",
            "age", "minutes", "similarity", "age_potential_score", "underrated_score",
            "reliability_percentile", "younger_bonus", "replacement_score",
        ])
    return pd.concat(tables, ignore_index=True)


def run(ml_df=None):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if ml_df is None:
        if not os.path.exists(ml_models.ML_FEATURES_CSV_PATH):
            raise FileNotFoundError(
                f"{ml_models.ML_FEATURES_CSV_PATH} not found. Run ml_models.run() first."
            )
        ml_df = pd.read_csv(ml_models.ML_FEATURES_CSV_PATH)

    examples = build_replacement_examples(ml_df)

    os.makedirs(os.path.dirname(REPLACEMENT_OUTPUT_CSV_PATH), exist_ok=True)
    examples.to_csv(REPLACEMENT_OUTPUT_CSV_PATH, index=False)
    logger.info(
        "Saved %d replacement-target rows to %s",
        len(examples), REPLACEMENT_OUTPUT_CSV_PATH,
    )
    return examples


if __name__ == "__main__":
    run()
