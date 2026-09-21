"""Tests for src/scout_players.py - player filters and read-only loading.
Uses synthetic frames/CSVs only; it never reads the real data/ folder."""
import pandas as pd
import pytest

from src import scout_players as sp
from src import season_config


@pytest.fixture
def players():
    return pd.DataFrame({
        "league_code": "hnl",
        "season_suffix": ["2025_2026"] * 6 + ["2024_2025"] * 2,
        "player_id": [1, 2, 3, 4, 5, 6, 1, 7],
        "player_name": ["Luka Ćorić", "Ivan Perišić", "Đuro Bašić", "Marko Kovač",
                        "Ante Šarić", "Pero Horvat", "Luka Ćorić", "Stari Igrač"],
        "team_name": ["Dinamo", "Hajduk", "Rijeka", "Dinamo", "Osijek", "Hajduk", "Hajduk", "Rijeka"],
        "position": ["Midfielder", "Attacker", "Defender", "Goalkeeper",
                     "Defender", "Midfielder", "Midfielder", "Defender"],
        "age": [21.0, 33.0, 19.0, 28.0, float("nan"), 24.0, 20.0, 30.0],
        "minutes": [1800.0, 900.0, 300.0, 2000.0, 1200.0, 450.0, 1500.0, 800.0],
        "overall_score": [70.0, 55.0, float("nan"), 40.0, 62.0, 48.0, 65.0, 50.0],
    })


def ids(frame):
    return sorted(frame["player_id"].tolist())


# --- individual filters -------------------------------------------------------

def test_no_filters_returns_everything(players):
    assert len(sp.filter_players(players)) == len(players)


def test_season_filter(players):
    assert ids(sp.filter_players(players, season_suffix="2025_2026")) == [1, 2, 3, 4, 5, 6]
    assert ids(sp.filter_players(players, season_suffix="2024_2025")) == [1, 7]


def test_team_filter_accepts_several_clubs(players):
    result = sp.filter_players(players, season_suffix="2025_2026", teams=["Dinamo", "Osijek"])
    assert ids(result) == [1, 4, 5]


def test_position_filter(players):
    result = sp.filter_players(players, season_suffix="2025_2026", positions=["Defender"])
    assert ids(result) == [3, 5]


def test_min_age_is_inclusive(players):
    result = sp.filter_players(players, season_suffix="2025_2026", min_age=24)
    assert ids(result) == [2, 4, 6]


def test_max_age_is_inclusive(players):
    result = sp.filter_players(players, season_suffix="2025_2026", max_age=21)
    assert ids(result) == [1, 3]


def test_age_range(players):
    result = sp.filter_players(players, season_suffix="2025_2026", min_age=20, max_age=28)
    assert ids(result) == [1, 4, 6]


def test_players_with_unknown_age_are_excluded_only_when_an_age_bound_is_set(players):
    assert 5 in ids(sp.filter_players(players, season_suffix="2025_2026"))
    assert 5 not in ids(sp.filter_players(players, season_suffix="2025_2026", min_age=0))
    assert 5 not in ids(sp.filter_players(players, season_suffix="2025_2026", max_age=99))


def test_min_minutes_is_inclusive(players):
    result = sp.filter_players(players, season_suffix="2025_2026", min_minutes=900)
    assert ids(result) == [1, 2, 4, 5]
    assert 6 not in ids(result)     # 450 minutes < 900


# --- name search ---------------------------------------------------------------

def test_name_search_is_case_insensitive(players):
    assert ids(sp.filter_players(players, season_suffix="2025_2026", name_query="MARKO")) == [4]


def test_name_search_ignores_accents(players):
    assert ids(sp.filter_players(players, season_suffix="2025_2026", name_query="coric")) == [1]
    assert ids(sp.filter_players(players, season_suffix="2025_2026", name_query="sari")) == [5]
    assert ids(sp.filter_players(players, season_suffix="2025_2026", name_query="peris")) == [2]


def test_name_search_handles_d_with_stroke(players):
    assert ids(sp.filter_players(players, season_suffix="2025_2026", name_query="duro")) == [3]


def test_name_search_matches_a_fragment(players):
    assert ids(sp.filter_players(players, season_suffix="2025_2026", name_query="ho")) == [6]


def test_blank_name_search_means_no_restriction(players):
    assert len(sp.filter_players(players, season_suffix="2025_2026", name_query="   ")) == 6


def test_name_search_treats_regex_characters_literally(players):
    assert sp.filter_players(players, name_query=".*").empty


def test_no_match_returns_an_empty_frame(players):
    assert sp.filter_players(players, name_query="zzzz").empty


# --- combined filters ----------------------------------------------------------

def test_filters_combine_with_and(players):
    result = sp.filter_players(
        players, season_suffix="2025_2026", teams=["Hajduk"], positions=["Midfielder"],
        min_age=20, max_age=30, min_minutes=400, name_query="pero",
    )
    assert ids(result) == [6]


def test_filtering_does_not_modify_the_input(players):
    before = players.copy()
    sp.filter_players(players, season_suffix="2025_2026", min_age=25)
    pd.testing.assert_frame_equal(players, before)


# --- sorting -------------------------------------------------------------------

def test_sort_puts_best_first_and_missing_scores_last(players):
    result = sp.sort_by_score(players[players["season_suffix"] == "2025_2026"], "overall_score")
    assert result["player_id"].tolist() == [1, 5, 2, 6, 4, 3]     # player 3 has no score -> last


def test_sort_rejects_unknown_column(players):
    with pytest.raises(ValueError):
        sp.sort_by_score(players, "nope")


def test_sort_options_point_at_real_score_columns():
    assert set(sp.SORT_OPTIONS.values()) == {"combined_score", "scout_score", "overall_score"}


# --- lookup --------------------------------------------------------------------

def test_get_player_is_season_specific(players):
    current = sp.get_player(players, "hnl", "2025_2026", 1)
    previous = sp.get_player(players, "hnl", "2024_2025", 1)
    assert current["team_name"] == "Dinamo"
    assert previous["team_name"] == "Hajduk"
    assert sp.get_player(players, "hnl", "2025_2026", 999) is None


def test_player_label(players):
    assert sp.player_label(players.iloc[1]) == "Ivan Perišić - Hajduk (Attacker)"


# --- loading (synthetic CSVs, redirected via season_config) ---------------------

@pytest.fixture
def fake_processed_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(season_config, "PROCESSED_DIR", str(tmp_path))
    return tmp_path


def _write_scored(directory, suffix, ids_):
    pd.DataFrame({
        "player_id": ids_, "player_name": [f"P{i}" for i in ids_], "team_name": "T",
        "position": "Defender", "age": 25.0, "minutes": 900.0, "overall_score": 50.0,
    }).to_csv(directory / f"hnl_player_scored_{suffix}.csv", index=False)


def test_load_league_players_adds_season_and_league_columns(fake_processed_dir):
    _write_scored(fake_processed_dir, "2025_2026", [1, 2])
    _write_scored(fake_processed_dir, "2024_2025", [1])
    loaded = sp.load_league_players("hnl")
    assert len(loaded) == 3
    assert set(loaded["league_code"]) == {"hnl"}
    assert set(loaded["season_suffix"]) == {"2025_2026", "2024_2025"}
    assert set(loaded["season_label"]) == {"2025/2026", "2024/2025"}
    assert str(loaded["player_id"].dtype) == "int64"


def test_load_league_players_skips_missing_seasons(fake_processed_dir):
    _write_scored(fake_processed_dir, "2025_2026", [1])
    loaded = sp.load_league_players("hnl")
    assert set(loaded["season_suffix"]) == {"2025_2026"}
    assert sp.available_seasons("hnl") == {"2025_2026": "2025/2026"}


def test_load_league_players_with_no_files_returns_an_empty_frame(fake_processed_dir):
    loaded = sp.load_league_players("hnl")
    assert loaded.empty
    assert {"player_id", "season_suffix", "league_code"} <= set(loaded.columns)
    assert sp.available_seasons("hnl") == {}


def test_loading_never_writes_files(fake_processed_dir):
    _write_scored(fake_processed_dir, "2025_2026", [1])
    before = sorted(p.name for p in fake_processed_dir.iterdir())
    sp.load_league_players("hnl")
    assert sorted(p.name for p in fake_processed_dir.iterdir()) == before


def test_league_registry_is_the_only_place_hnl_is_hardcoded():
    assert sp.DEFAULT_LEAGUE in sp.LEAGUES
    league = sp.LEAGUES["hnl"]
    assert league.code == "hnl" and league.seasons
