"""
Tests for src/clean_data.py - flattening raw SportMonks squad entries and
de-duplicating players who appear under two clubs in the same season.
"""
from src import clean_data


def _entry(player_id, name, team_name, position, minutes, appearances=10, season_id=1):
    """Build one minimal SportMonks-shaped squad entry - just enough for
    clean_data.py to parse (type_id 119 = minutes, 321 = appearances)."""
    return {
        "team_name": team_name,
        "player": {
            "id": player_id,
            "display_name": name,
            "position": {"name": position},
            "date_of_birth": "1998-05-01",
            "nationality": {"name": "Croatia"},
            "statistics": [
                {
                    "season_id": season_id,
                    "details": [
                        {"type_id": 119, "value": {"total": minutes}},
                        {"type_id": 321, "value": {"total": appearances}},
                    ],
                }
            ],
        },
    }


def test_duplicate_player_across_two_teams_is_deduped_to_one_row():
    """A mid-season transfer/loan can list the same player_id under two
    clubs with identical season totals (statistics.details isn't split per
    spell) - clean() must keep exactly one row per player_id, not double it."""
    entries = [
        _entry(100, "Transferred Player", "Team X", "Midfielder", minutes=1500),
        _entry(100, "Transferred Player", "Team Y", "Midfielder", minutes=1500),
    ]

    df = clean_data.clean(entries)

    assert len(df) == 1
    assert df.iloc[0]["player_id"] == 100


def test_zero_minutes_players_are_filtered_out():
    """Players with 0 (or missing) minutes never took the field this season
    - they shouldn't appear in the cleaned dataset at all."""
    entries = [
        _entry(200, "Unused Squad Player", "Team Z", "Attacker", minutes=0),
    ]

    df = clean_data.clean(entries)

    assert df.empty


def test_goalkeepers_are_kept_in_the_clean_dataset():
    """clean_data.py has no notion of "outfield only" - that filtering
    happens later, in analysis.py. Goalkeepers must survive cleaning."""
    entries = [
        _entry(300, "Keeper Player", "Team W", "Goalkeeper", minutes=900),
    ]

    df = clean_data.clean(entries)

    assert (df["position"] == "Goalkeeper").any()
