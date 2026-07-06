"""
Tests for src/ml_models.py - ML-ready dataset and similarity search.
"""
from src import ml_models


def test_build_ml_dataset_keeps_goalkeepers(scored_df):
    """Goalkeepers are excluded from outfield *rankings* (analysis.py), but
    the ML dataset itself keeps every eligible player, keeper or not."""
    ml_df = ml_models.build_ml_dataset(scored_df)

    assert (ml_df["position"] == "Goalkeeper").any()


def test_build_ml_dataset_drops_players_below_minutes_threshold(scored_df):
    ml_df = ml_models.build_ml_dataset(scored_df)

    assert "Attacker Three" not in ml_df["player_name"].values


def test_find_similar_players_excludes_the_query_player(scored_df):
    ml_df = ml_models.build_ml_dataset(scored_df)

    result = ml_models.find_similar_players(ml_df, "Midfielder One", role="overall", top_n=5)

    assert "Midfielder One" not in result["player_name"].values
    assert len(result) == min(5, len(ml_df) - 1)
    assert (result["similarity"] <= 1.0001).all()


def test_find_similar_players_unknown_role_raises(scored_df):
    ml_df = ml_models.build_ml_dataset(scored_df)

    try:
        ml_models.find_similar_players(ml_df, "Midfielder One", role="not_a_real_role")
        assert False, "expected a ValueError for an unknown role"
    except ValueError:
        pass


def test_find_similar_players_unknown_player_raises(scored_df):
    ml_df = ml_models.build_ml_dataset(scored_df)

    try:
        ml_models.find_similar_players(ml_df, "Nobody At All", role="overall")
        assert False, "expected a ValueError for a player not in the dataset"
    except ValueError:
        pass


# --- Stage B3 similarity filters --------------------------------------------

def test_same_position_only_restricts_candidates_to_query_players_position(scored_df):
    """Attacker One (Team A) has one other eligible attacker (Attacker Two)
    and several eligible non-attackers - same_position_only=True should
    keep only Attacker Two."""
    ml_df = ml_models.build_ml_dataset(scored_df)

    result = ml_models.find_similar_players(
        ml_df, "Attacker One", role="overall", same_position_only=True,
    )

    assert set(result["player_name"]) == {"Attacker Two"}
    assert (result["position"] == "Attacker").all()


def test_same_team_exclude_drops_players_from_the_same_team(scored_df):
    """Attacker One and Defender One both play for Team A - excluding
    same-team candidates should drop Defender One from Attacker One's
    results."""
    ml_df = ml_models.build_ml_dataset(scored_df)

    result = ml_models.find_similar_players(
        ml_df, "Attacker One", role="overall", same_team_exclude=True,
    )

    assert "Defender One" not in result["player_name"].values
    assert "Team A" not in result["team_name"].values


def test_min_minutes_filters_out_low_minute_candidates(scored_df):
    """min_minutes is a stricter reliability filter than the base
    eligibility bar - raising it to 1000 should drop the eligible-but-lower
    minute candidates (Attacker Two: 900, Defender Two: 600)."""
    ml_df = ml_models.build_ml_dataset(scored_df)

    result = ml_models.find_similar_players(
        ml_df, "Midfielder One", role="overall", min_minutes=1000,
    )

    assert "Attacker Two" not in result["player_name"].values
    assert "Defender Two" not in result["player_name"].values


def test_max_age_filters_out_older_candidates(scored_df):
    """Only Defender Two (age 21) is <= 21 among Midfielder One's
    candidates (ages 27, 22, 30, 28, 21, 29, 34) - max_age=21 should leave
    just that one match."""
    ml_df = ml_models.build_ml_dataset(scored_df)

    result = ml_models.find_similar_players(
        ml_df, "Midfielder One", role="overall", max_age=21,
    )

    assert set(result["player_name"]) == {"Defender Two"}


def test_goalkeeper_role_with_same_position_only(scored_df):
    """The 'goalkeeper' role only makes sense compared to other
    goalkeepers - with 2 eligible keepers in the fixture, searching from
    one (with same_position_only) should return exactly the other one."""
    ml_df = ml_models.build_ml_dataset(scored_df)

    result = ml_models.find_similar_players(
        ml_df, "Goalkeeper One", role="goalkeeper", same_position_only=True,
    )

    assert set(result["player_name"]) == {"Goalkeeper Two"}
