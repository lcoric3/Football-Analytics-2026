"""
Shared pytest fixtures for the test suite.

Every fixture here is built from small, synthetic, in-memory data - no test
reads data/, calls the SportMonks API, or needs SPORTMONKS_API_TOKEN/.env.
That keeps `pytest` runnable in any environment (including CI) without
credentials.
"""
import os
import sys

import pandas as pd
import pytest

# tests/ has no __init__.py, so make sure the project root (which contains
# the `src` package) is importable regardless of the directory pytest is
# invoked from.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import feature_engineering, scouting_scores  # noqa: E402

# Nine synthetic players spanning every position, with a spread of playing
# time that deliberately straddles scouting_scores.MIN_MINUTES_FOR_SCORES
# (450) so eligible/ineligible behavior can be tested. Values are made up
# but internally consistent (e.g. duels_won <= duels).
RAW_PLAYER_ROWS = [
    {
        "player_id": 1, "player_name": "Attacker One", "team_name": "Team A",
        "position": "Attacker", "age": 27, "nationality": "Croatia",
        "appearances": 20, "minutes": 1800, "goals": 15, "assists": 5,
        "shots": 60, "shots_on_target": 35, "passes": 400, "pass_accuracy": 78,
        "tackles": 5, "interceptions": 3, "duels": 80, "duels_won": 40,
        "yellow_cards": 2, "red_cards": 0, "rating": 7.2,
        "dribble_attempts": 40, "successful_dribbles": 20, "dribbled_past": 10,
        "fouls_drawn": 15, "crosses": 10, "accurate_crosses": 4,
        "long_balls": 5, "accurate_long_balls": 2, "key_passes": 10,
        "aerials_won": 20, "clearances": 2, "saves": 0, "saves_inside_box": 0,
        "goals_conceded": 0, "clean_sheets": 0, "penalties_saved": 0,
    },
    {
        "player_id": 2, "player_name": "Attacker Two", "team_name": "Team B",
        "position": "Attacker", "age": 22, "nationality": "Croatia",
        "appearances": 15, "minutes": 900, "goals": 6, "assists": 2,
        "shots": 30, "shots_on_target": 15, "passes": 200, "pass_accuracy": 72,
        "tackles": 3, "interceptions": 2, "duels": 40, "duels_won": 18,
        "yellow_cards": 1, "red_cards": 0, "rating": 6.8,
        "dribble_attempts": 25, "successful_dribbles": 10, "dribbled_past": 8,
        "fouls_drawn": 8, "crosses": 5, "accurate_crosses": 2,
        "long_balls": 2, "accurate_long_balls": 1, "key_passes": 5,
        "aerials_won": 10, "clearances": 1, "saves": 0, "saves_inside_box": 0,
        "goals_conceded": 0, "clean_sheets": 0, "penalties_saved": 0,
    },
    {
        # Below the 450-minute eligibility bar - used to test that scores
        # come back NaN instead of a noisy/misleading value.
        "player_id": 3, "player_name": "Attacker Three", "team_name": "Team A",
        "position": "Attacker", "age": 19, "nationality": "Croatia",
        "appearances": 4, "minutes": 300, "goals": 2, "assists": 0,
        "shots": 8, "shots_on_target": 4, "passes": 50, "pass_accuracy": 70,
        "tackles": 1, "interceptions": 0, "duels": 10, "duels_won": 4,
        "yellow_cards": 0, "red_cards": 0, "rating": 6.5,
        "dribble_attempts": 6, "successful_dribbles": 2, "dribbled_past": 3,
        "fouls_drawn": 2, "crosses": 1, "accurate_crosses": 0,
        "long_balls": 0, "accurate_long_balls": 0, "key_passes": 1,
        "aerials_won": 2, "clearances": 0, "saves": 0, "saves_inside_box": 0,
        "goals_conceded": 0, "clean_sheets": 0, "penalties_saved": 0,
    },
    {
        "player_id": 4, "player_name": "Midfielder One", "team_name": "Team C",
        "position": "Midfielder", "age": 26, "nationality": "Croatia",
        "appearances": 22, "minutes": 2000, "goals": 4, "assists": 10,
        "shots": 20, "shots_on_target": 8, "passes": 1200, "pass_accuracy": 88,
        "tackles": 40, "interceptions": 25, "duels": 100, "duels_won": 55,
        "yellow_cards": 4, "red_cards": 0, "rating": 7.5,
        "dribble_attempts": 30, "successful_dribbles": 15, "dribbled_past": 12,
        "fouls_drawn": 10, "crosses": 15, "accurate_crosses": 6,
        "long_balls": 40, "accurate_long_balls": 25, "key_passes": 35,
        "aerials_won": 15, "clearances": 10, "saves": 0, "saves_inside_box": 0,
        "goals_conceded": 0, "clean_sheets": 0, "penalties_saved": 0,
    },
    {
        "player_id": 5, "player_name": "Midfielder Two", "team_name": "Team D",
        "position": "Midfielder", "age": 30, "nationality": "Croatia",
        "appearances": 18, "minutes": 1000, "goals": 1, "assists": 4,
        "shots": 10, "shots_on_target": 3, "passes": 600, "pass_accuracy": 82,
        "tackles": 20, "interceptions": 12, "duels": 50, "duels_won": 25,
        "yellow_cards": 3, "red_cards": 0, "rating": 6.9,
        "dribble_attempts": 15, "successful_dribbles": 6, "dribbled_past": 6,
        "fouls_drawn": 5, "crosses": 8, "accurate_crosses": 3,
        "long_balls": 20, "accurate_long_balls": 12, "key_passes": 15,
        "aerials_won": 8, "clearances": 5, "saves": 0, "saves_inside_box": 0,
        "goals_conceded": 0, "clean_sheets": 0, "penalties_saved": 0,
    },
    {
        "player_id": 6, "player_name": "Defender One", "team_name": "Team A",
        "position": "Defender", "age": 28, "nationality": "Croatia",
        "appearances": 24, "minutes": 1500, "goals": 1, "assists": 1,
        "shots": 5, "shots_on_target": 1, "passes": 800, "pass_accuracy": 85,
        "tackles": 50, "interceptions": 40, "duels": 120, "duels_won": 80,
        "yellow_cards": 5, "red_cards": 0, "rating": 7.0,
        "dribble_attempts": 5, "successful_dribbles": 1, "dribbled_past": 10,
        "fouls_drawn": 3, "crosses": 2, "accurate_crosses": 1,
        "long_balls": 30, "accurate_long_balls": 20, "key_passes": 3,
        "aerials_won": 40, "clearances": 60, "saves": 0, "saves_inside_box": 0,
        "goals_conceded": 0, "clean_sheets": 0, "penalties_saved": 0,
    },
    {
        "player_id": 7, "player_name": "Defender Two", "team_name": "Team B",
        "position": "Defender", "age": 21, "nationality": "Croatia",
        "appearances": 10, "minutes": 600, "goals": 0, "assists": 0,
        "shots": 2, "shots_on_target": 0, "passes": 300, "pass_accuracy": 80,
        "tackles": 20, "interceptions": 15, "duels": 40, "duels_won": 22,
        "yellow_cards": 2, "red_cards": 0, "rating": 6.6,
        "dribble_attempts": 2, "successful_dribbles": 0, "dribbled_past": 5,
        "fouls_drawn": 1, "crosses": 1, "accurate_crosses": 0,
        "long_balls": 10, "accurate_long_balls": 6, "key_passes": 1,
        "aerials_won": 15, "clearances": 20, "saves": 0, "saves_inside_box": 0,
        "goals_conceded": 0, "clean_sheets": 0, "penalties_saved": 0,
    },
    {
        "player_id": 8, "player_name": "Goalkeeper One", "team_name": "Team C",
        "position": "Goalkeeper", "age": 29, "nationality": "Croatia",
        "appearances": 22, "minutes": 1700, "goals": 0, "assists": 0,
        "shots": 0, "shots_on_target": 0, "passes": 500, "pass_accuracy": 75,
        "tackles": 0, "interceptions": 0, "duels": 5, "duels_won": 2,
        "yellow_cards": 1, "red_cards": 0, "rating": 7.1,
        "dribble_attempts": 0, "successful_dribbles": 0, "dribbled_past": 0,
        "fouls_drawn": 0, "crosses": 0, "accurate_crosses": 0,
        "long_balls": 20, "accurate_long_balls": 10, "key_passes": 0,
        "aerials_won": 2, "clearances": 5, "saves": 60, "saves_inside_box": 45,
        "goals_conceded": 20, "clean_sheets": 8, "penalties_saved": 2,
    },
    {
        "player_id": 9, "player_name": "Goalkeeper Two", "team_name": "Team D",
        "position": "Goalkeeper", "age": 34, "nationality": "Croatia",
        "appearances": 8, "minutes": 500, "goals": 0, "assists": 0,
        "shots": 0, "shots_on_target": 0, "passes": 150, "pass_accuracy": 70,
        "tackles": 0, "interceptions": 0, "duels": 2, "duels_won": 1,
        "yellow_cards": 0, "red_cards": 0, "rating": 6.4,
        "dribble_attempts": 0, "successful_dribbles": 0, "dribbled_past": 0,
        "fouls_drawn": 0, "crosses": 0, "accurate_crosses": 0,
        "long_balls": 5, "accurate_long_balls": 2, "key_passes": 0,
        "aerials_won": 1, "clearances": 1, "saves": 20, "saves_inside_box": 15,
        "goals_conceded": 10, "clean_sheets": 2, "penalties_saved": 0,
    },
]


@pytest.fixture
def raw_df():
    """A clean-stage DataFrame (post clean_data.py schema), fully synthetic."""
    return pd.DataFrame(RAW_PLAYER_ROWS)


@pytest.fixture
def features_df(raw_df):
    """raw_df with feature_engineering.py's per-90/ratio columns added."""
    return feature_engineering.add_features(raw_df)


@pytest.fixture
def scored_df(features_df):
    """features_df with scouting_scores.py's percentile-based scores added."""
    return scouting_scores.add_scores(features_df)
