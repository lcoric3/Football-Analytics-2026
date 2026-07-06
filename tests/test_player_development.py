"""
Tests for src/player_development.py - multi-season player comparison.

All fixtures here are small, synthetic, in-memory DataFrames shaped like
the real hnl_player_scored_<season>.csv files - no test reads data/, calls
the SportMonks API, or needs SPORTMONKS_API_TOKEN/.env.
"""
import pandas as pd

from src import player_development


def _row(player_id, name, team, position, age, minutes, overall_score, **extra_scores):
    row = {
        "player_id": player_id, "player_name": name, "team_name": team,
        "position": position, "age": age, "minutes": minutes,
        "overall_score": overall_score,
    }
    row.update(extra_scores)
    return row


def base_and_target_dfs():
    """Three players who appear in both seasons (ids 1-3, covering an
    improver with the same team, an improver who also changed team and is
    young, and a decliner), plus one player only in the base season (id 4,
    e.g. left the league) and one only in the target season (id 5, e.g. a
    new signing) - both of which must be excluded from the matched output."""
    base_df = pd.DataFrame([
        _row(1, "Player A", "Team X", "Midfielder", 25, 1800, 50.0, dribbling_score=30.0),
        _row(2, "Player B", "Team Y", "Attacker", 20, 1200, 40.0, dribbling_score=20.0),
        _row(3, "Player C", "Team Z", "Defender", 30, 2000, 70.0, dribbling_score=10.0),
        _row(4, "Player D", "Team Y", "Midfielder", 27, 1500, 55.0, dribbling_score=25.0),
    ])
    target_df = pd.DataFrame([
        _row(1, "Player A", "Team X", "Midfielder", 26, 2000, 65.0, dribbling_score=45.0),
        _row(2, "Player B", "Team W", "Attacker", 21, 1400, 58.0, dribbling_score=20.0),
        _row(3, "Player C", "Team Z", "Defender", 31, 1000, 60.0, dribbling_score=10.0),
        _row(5, "Player E", "Team W", "Attacker", 22, 900, 45.0, dribbling_score=15.0),
    ])
    return base_df, target_df


def test_matching_is_by_player_id_not_name():
    """A player renamed between seasons (encoding/transliteration) must
    still match on player_id, and a name shared by two different
    player_ids must not be conflated."""
    base_df, target_df = base_and_target_dfs()
    # Simulate a transliteration change for player 1 - same id, different
    # spelling of the name.
    target_df = target_df.copy()
    target_df.loc[target_df["player_id"] == 1, "player_name"] = "Player A (renamed)"

    dev_df = player_development.build_development_dataset(base_df, target_df)

    assert set(dev_df["player_id"]) == {1, 2, 3}
    assert 4 not in dev_df["player_id"].values
    assert 5 not in dev_df["player_id"].values
    # player_name comes from the base season, unaffected by the target
    # season's differently-spelled name for the same player_id.
    assert dev_df.loc[dev_df["player_id"] == 1, "player_name"].iloc[0] == "Player A"


def test_change_columns_exist():
    base_df, target_df = base_and_target_dfs()
    dev_df = player_development.select_final_columns(
        player_development.build_development_dataset(base_df, target_df)
    )

    for col in [
        "minutes_change", "overall_score_change", "dribbling_score_change",
        "changed_team", "same_position", "minutes_increased", "young_player",
        "improved_overall", "improved_specialist_score",
    ]:
        assert col in dev_df.columns

    player_1 = dev_df[dev_df["player_id"] == 1].iloc[0]
    assert player_1["overall_score_change"] == 15.0
    assert player_1["minutes_change"] == 200


def test_changed_team_flag():
    base_df, target_df = base_and_target_dfs()
    dev_df = player_development.build_development_dataset(base_df, target_df)

    changed = dev_df.set_index("player_id")["changed_team"]
    assert changed.loc[2] == True  # noqa: E712 - Team Y -> Team W
    assert changed.loc[1] == False  # noqa: E712 - stayed at Team X
    assert changed.loc[3] == False  # noqa: E712 - stayed at Team Z


def test_biggest_improvers_sorted_descending():
    base_df, target_df = base_and_target_dfs()
    dev_df = player_development.build_development_dataset(base_df, target_df)

    improvers = player_development.rank_biggest_improvers(dev_df, top_n=10)
    changes = list(improvers["overall_score_change"])

    assert changes == sorted(changes, reverse=True)
    # Player B (+18) improved more than Player A (+15); Player C (-10,
    # a decline) is still included since top_n exceeds the pool size, but
    # correctly sorted last.
    assert list(improvers["player_id"]) == [2, 1, 3]


def test_young_improvers_requires_young_and_improved():
    base_df, target_df = base_and_target_dfs()
    dev_df = player_development.build_development_dataset(base_df, target_df)

    young_improvers = player_development.rank_young_improvers(dev_df)

    # Only Player B is age <= 23 in the target season AND improved.
    assert list(young_improvers["player_id"]) == [2]


def test_output_handles_missing_score_columns_safely():
    """If a score column (e.g. passer_defender_score) is entirely absent
    from one season's scored data - a real scenario if SportMonks didn't
    expose that stat type for a given season - the comparison must not
    raise, and the missing column's *_change should simply be absent
    rather than crashing the whole pipeline."""
    base_df, target_df = base_and_target_dfs()
    base_df = base_df.copy()
    base_df["passer_defender_score"] = [10.0, 20.0, 30.0, 40.0]
    # target_df deliberately does NOT have passer_defender_score at all.

    merged = player_development.build_development_dataset(base_df, target_df)
    dev_df = player_development.select_final_columns(merged)

    assert "passer_defender_score_change" not in dev_df.columns
    # Other change columns computed from data present in both seasons are
    # unaffected.
    assert "overall_score_change" in dev_df.columns
    assert "dribbling_score_change" in dev_df.columns
    assert len(dev_df) == 3


def test_hidden_gems_who_improved_filters_by_id_and_improvement():
    base_df, target_df = base_and_target_dfs()
    dev_df = player_development.build_development_dataset(base_df, target_df)

    # Player 3 is a "hidden gem" but declined - should be excluded even
    # though they're in the hidden_gem_ids set.
    result = player_development.rank_hidden_gems_who_improved(dev_df, hidden_gem_ids={2, 3})

    assert list(result["player_id"]) == [2]


def test_report_builds_without_raising():
    base_df, target_df = base_and_target_dfs()
    dev_df = player_development.select_final_columns(
        player_development.build_development_dataset(base_df, target_df)
    )

    report_text = player_development.build_report(
        dev_df, base_player_count=len(base_df), target_player_count=len(target_df),
        hidden_gem_ids={2},
    )

    assert "# HNL Multi-Season Player Development Report" in report_text
    assert "Player B" in report_text
