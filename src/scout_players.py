"""
Read-only player data access and filtering for the private scouting app.

This module only READS the scored CSVs the analytics pipeline already
produced (data/processed/<file_base>_<season>.csv, located through
season_config so paths work on Linux and Windows alike). It never writes a
file, never calls the SportMonks API and never recomputes an analytical
score - `overall_score` and every other score column are used exactly as the
pipeline saved them.

League structure: HNL is the only league today, but nothing outside the
LEAGUES registry below is HNL-specific. Adding a league means adding one
entry there (and running the pipeline for it); the database tables already
carry a `league_code` column for the same reason.
"""
import logging
import os
import unicodedata
from dataclasses import dataclass

import pandas as pd

from src import season_config

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class League:
    code: str
    label: str
    # Scored-CSV base name, e.g. "hnl_player_scored" -> hnl_player_scored_2025_2026.csv
    file_base: str
    # season suffix -> display label, newest first.
    seasons: dict


LEAGUES = {
    "hnl": League(
        code="hnl",
        label="HNL",
        file_base="hnl_player_scored",
        seasons={"2025_2026": "2025/2026", "2024_2025": "2024/2025"},
    ),
}
DEFAULT_LEAGUE = "hnl"

# Columns shown in the search table, in order (missing ones are skipped).
TABLE_COLUMNS = [
    "player_name", "team_name", "position", "age", "minutes",
    "overall_score", "scout_score", "combined_score", "scout_report_count",
]

# The analytical scores from the pipeline, as saved in the scored CSV.
ANALYTICAL_SCORE_COLUMNS = [
    "overall_score", "attacking_score", "creative_score", "defensive_score",
    "discipline_score", "dribbling_score", "passing_score", "duel_defending_score",
    "progressive_midfielder_score", "passer_defender_score", "goalkeeper_score",
    "age_potential_score", "underrated_score",
]

KEY_PER90_COLUMNS = [
    "goals_per90", "assists_per90", "shots_per90", "shots_on_target_per90",
    "passes_per90", "tackles_per90", "interceptions_per90", "cards_per90",
    "successful_dribbles_per90", "key_passes_per90",
]

# What the "sort shortlist by" control offers: label -> column.
SORT_OPTIONS = {
    "Kombinirana ocjena": "combined_score",
    "Skautska ocjena": "scout_score",
    "Analitička ocjena": "overall_score",
}


def available_seasons(league_code):
    """season suffix -> label for the league's seasons whose scored CSV
    actually exists on disk (so the UI never offers a season it cannot load)."""
    league = LEAGUES[league_code]
    return {
        suffix: label
        for suffix, label in league.seasons.items()
        if os.path.exists(season_config.processed_path(league.file_base, suffix=suffix))
    }


def load_league_players(league_code):
    """All seasons of one league in a single DataFrame, read-only.

    Adds three columns the pipeline files do not have: `league_code`,
    `season_suffix` and `season_label`. They form (together with `player_id`)
    the key that ties a player to scouting reports in the database."""
    league = LEAGUES[league_code]
    frames = []
    for suffix, label in league.seasons.items():
        path = season_config.processed_path(league.file_base, suffix=suffix)
        if not os.path.exists(path):
            logger.warning("Scored CSV not found, skipping season %s: %s", suffix, path)
            continue
        frame = pd.read_csv(path)
        frame["league_code"] = league.code
        frame["season_suffix"] = suffix
        frame["season_label"] = label
        frames.append(frame)
    if not frames:
        return pd.DataFrame(
            columns=["player_id", "player_name", "team_name", "position", "age", "minutes",
                     "overall_score", "league_code", "season_suffix", "season_label"]
        )
    players = pd.concat(frames, ignore_index=True)
    players["player_id"] = players["player_id"].astype("int64")
    return players


def _fold(text):
    """Lower-cases and strips accents so "coric" matches "Ćorić". NFKD does
    not decompose đ, so it is mapped by hand."""
    text = str(text).replace("đ", "d").replace("Đ", "D")
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch)).casefold()


def filter_players(
    players_df, season_suffix=None, teams=None, positions=None,
    min_age=None, max_age=None, min_minutes=None, name_query=None,
):
    """Filters a players DataFrame. Every filter is optional (None / empty =
    no restriction).

    `teams` / `positions` are lists of exact values. Age bounds are inclusive
    and exclude players whose age is unknown when a bound is set. The name
    search is a case- and accent-insensitive "contains"."""
    result = players_df
    if season_suffix:
        result = result[result["season_suffix"] == season_suffix]
    if teams:
        result = result[result["team_name"].isin(teams)]
    if positions:
        result = result[result["position"].isin(positions)]
    if min_age is not None:
        result = result[result["age"] >= min_age]
    if max_age is not None:
        result = result[result["age"] <= max_age]
    if min_minutes is not None:
        result = result[result["minutes"] >= min_minutes]
    if name_query and name_query.strip():
        needle = _fold(name_query.strip())
        result = result[result["player_name"].map(_fold).str.contains(needle, regex=False, na=False)]
    return result


def sort_by_score(df, column):
    """Best first; players without that score go last instead of being dropped."""
    if column not in df.columns:
        raise ValueError(f"Unknown score column: {column!r}")
    return df.sort_values(column, ascending=False, na_position="last", kind="stable")


def get_player(players_df, league_code, season_suffix, player_id):
    """The single row for one player in one season, or None."""
    match = players_df[
        (players_df["league_code"] == league_code)
        & (players_df["season_suffix"] == season_suffix)
        & (players_df["player_id"] == int(player_id))
    ]
    return None if match.empty else match.iloc[0]


def player_label(row):
    """Selectbox label: 'Name - Team (Position)'."""
    return f"{row['player_name']} - {row['team_name']} ({row['position']})"
