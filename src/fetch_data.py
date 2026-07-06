"""
Stage 1: fetch HNL 2025/2026 player statistics from SportMonks.

Football data science logic:
SportMonks does not expose "all player stats for a season" as a single
bulk endpoint. Statistics live on the *player* entity, filtered by season.
So the shape of this stage is:

  1. Find the league  (Croatian HNL / 1. HNL)
  2. Find the season   (2025/2026)
  3. Find the teams playing in that season
  4. For each team, call /squads/seasons/{season_id}/teams/{team_id} to get
     its squad for that season, with each player's statistics nested in
     via `include=player.statistics.details`

Two SportMonks quirks that shaped this:
  - Multiple `include` values are joined with `;`, not `,`. A comma gets
    parsed as part of the nested path and produces a confusing 404.
  - This endpoint caps nested includes at 3 levels, so
    `player.statistics.details.type` (4 levels) is rejected. That means we
    only get `details[].type_id` (a number), not a readable name - see
    clean_data.py's STAT_TYPE_MAP, which maps those ids to column names
    using SportMonks' `/core/types` reference list.

This does more API calls than a single bulk request would (one per team
instead of one for the whole league), but it's the structure the API
actually offers, and it keeps each call small enough to avoid timeouts.

This module only fetches and saves data as-is - it does not interpret or
rename anything. That interpretation (turning SportMonks' nested
"statistic type name -> value" structure into columns like `goals` or
`tackles`) happens in clean_data.py, which is easier to fix if a stat's
exact name differs from what's assumed here.
"""
import json
import logging
import os

import pandas as pd

from src import season_config
from src.sportmonks_client import SportMonksClient

logger = logging.getLogger(__name__)

RAW_JSON_PATH = season_config.raw_json_path()
RAW_CSV_PATH = season_config.raw_csv_path()

# Defaults target the Croatian top flight. If SportMonks' search doesn't
# return an exact match (naming varies: "HNL", "1. HNL", "SuperSport HNL"),
# set HNL_LEAGUE_ID / HNL_SEASON_ID directly to skip the lookup.
DEFAULT_LEAGUE_SEARCH = "HNL"
DEFAULT_SEASON_NAME = season_config.SEASON_NAME

# Statistics detail include, chained onto each squad player. Includes are
# joined with `;` (SportMonks-specific separator - see module docstring).
# No `.type` here: that would be a 4th nesting level, which this endpoint
# rejects. clean_data.py maps the resulting numeric `type_id` to column
# names itself instead.
PLAYER_STATS_INCLUDE = "player.statistics.details;player.position;player.nationality"


def find_league_id(client, search_term=DEFAULT_LEAGUE_SEARCH):
    """Find the Croatian HNL league_id, or use HNL_LEAGUE_ID if set."""
    override = os.getenv("HNL_LEAGUE_ID")
    if override:
        return int(override)

    results = client.get(f"/leagues/search/{search_term}") or {}
    candidates = results.get("data", []) or []

    croatian = [
        c for c in candidates
        if (c.get("country_id") is not None or "country" in c)
    ]
    pool = croatian or candidates

    if not pool:
        raise RuntimeError(
            f"No leagues found searching for '{search_term}'. "
            "Set HNL_LEAGUE_ID in your environment to skip this lookup."
        )
    if len(pool) > 1:
        logger.warning(
            "Multiple leagues matched '%s': %s. Using the first result - "
            "set HNL_LEAGUE_ID explicitly if this is wrong.",
            search_term, [(c.get("id"), c.get("name")) for c in pool],
        )
    return pool[0]["id"]


def find_season_id(client, league_id, season_name=DEFAULT_SEASON_NAME):
    """Find the season_id for e.g. '2025/2026', or use HNL_SEASON_ID if set."""
    override = os.getenv("HNL_SEASON_ID")
    if override:
        return int(override)

    league = client.get(f"/leagues/{league_id}", params={"include": "seasons"}) or {}
    seasons = (league.get("data") or {}).get("seasons", []) or []

    for season in seasons:
        if season.get("name") == season_name:
            return season["id"]

    raise RuntimeError(
        f"No season named '{season_name}' found for league {league_id}. "
        f"Available seasons: {[s.get('name') for s in seasons]}. "
        "Set HNL_SEASON_ID in your environment to skip this lookup."
    )


def get_teams_for_season(client, season_id):
    """Return the list of teams competing in a given season."""
    season = client.get(f"/seasons/{season_id}", params={"include": "teams"}) or {}
    teams = (season.get("data") or {}).get("teams", []) or []
    if not teams:
        raise RuntimeError(f"No teams found for season {season_id}.")
    return teams


def fetch_player_statistics(client, season_id, teams):
    """
    For every team in the season, fetch the season squad with each
    player's statistics for this season nested in.

    Returns a flat list of squad-entry dicts (one per player per team).
    """
    all_entries = []

    for team in teams:
        team_id = team["id"]
        team_name = team.get("name", f"team_{team_id}")
        logger.info("Fetching squad + statistics for %s (team_id=%s)...", team_name, team_id)

        squad = client.get(
            f"/squads/seasons/{season_id}/teams/{team_id}",
            params={
                "include": PLAYER_STATS_INCLUDE,
                "filters": f"playerStatisticSeasons:{season_id}",
            },
        ) or {}

        entries = squad.get("data", []) or []
        for entry in entries:
            entry["team_id"] = team_id
            entry["team_name"] = team_name
        all_entries.extend(entries)

    if not all_entries:
        raise RuntimeError(
            "No player statistics were returned for any team. Check that "
            "the season/teams have squad data available on your SportMonks plan."
        )
    return all_entries


def save_raw(entries):
    """Save the raw API data as both JSON (full fidelity) and CSV (flattened)."""
    os.makedirs(os.path.dirname(RAW_JSON_PATH), exist_ok=True)

    with open(RAW_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)

    # json_normalize flattens top-level fields; nested "player.statistics"
    # stays as a Python object per row - clean_data.py parses that nested
    # structure into named per-90-ready columns.
    df = pd.json_normalize(entries)
    df.to_csv(RAW_CSV_PATH, index=False)

    logger.info("Saved %d raw squad entries to %s and %s", len(entries), RAW_JSON_PATH, RAW_CSV_PATH)
    return df


def run():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    client = SportMonksClient()

    league_id = find_league_id(client)
    logger.info("Using league_id=%s", league_id)

    season_id = find_season_id(client, league_id)
    logger.info("Using season_id=%s", season_id)

    teams = get_teams_for_season(client, season_id)
    logger.info("Found %d teams for season %s", len(teams), season_id)

    entries = fetch_player_statistics(client, season_id, teams)
    return save_raw(entries)


if __name__ == "__main__":
    run()
