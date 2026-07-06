"""
Tests for src/replacement_scouting.py - replacement_score and the
find_replacement_targets shortlist search.
"""
from src import ml_models, replacement_scouting


def test_replacement_search_excludes_the_original_player(scored_df):
    ml_df = ml_models.build_ml_dataset(scored_df)

    result = replacement_scouting.find_replacement_targets(ml_df, "Attacker One")

    assert "Attacker One" not in result["player_name"].values


def test_same_team_exclude_drops_the_departing_players_teammates(scored_df):
    """Attacker One and Defender One both play for Team A - with
    same_team_exclude=True (the default), Defender One must never appear,
    even when same_position_only is relaxed to widen the candidate pool."""
    ml_df = ml_models.build_ml_dataset(scored_df)

    result = replacement_scouting.find_replacement_targets(
        ml_df, "Attacker One", role="overall", same_position_only=False,
        same_team_exclude=True,
    )

    assert "Defender One" not in result["player_name"].values
    assert "Team A" not in result["team_name"].values


def test_max_age_filters_out_older_candidates(scored_df):
    """Only Defender Two (age 21) is <= 21 among Midfielder One's
    candidates once same_position_only is relaxed (Midfielder One's only
    same-position peer, Midfielder Two, is age 30)."""
    ml_df = ml_models.build_ml_dataset(scored_df)

    result = replacement_scouting.find_replacement_targets(
        ml_df, "Midfielder One", role="overall", same_position_only=False,
        max_age=21,
    )

    assert set(result["player_name"]) == {"Defender Two"}


def test_replacement_score_exists_and_is_sorted_descending(scored_df):
    ml_df = ml_models.build_ml_dataset(scored_df)

    result = replacement_scouting.find_replacement_targets(
        ml_df, "Midfielder One", role="overall", same_position_only=False,
        same_team_exclude=False,
    )

    assert "replacement_score" in result.columns
    assert len(result) > 1
    scores = list(result["replacement_score"])
    assert scores == sorted(scores, reverse=True)


def test_unknown_player_raises_value_error(scored_df):
    ml_df = ml_models.build_ml_dataset(scored_df)

    try:
        replacement_scouting.find_replacement_targets(ml_df, "Nobody At All")
        assert False, "expected a ValueError for a player not in the dataset"
    except ValueError:
        pass
