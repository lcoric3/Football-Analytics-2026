"""
Season configuration, shared by every pipeline stage.

Football data science logic:
Each pipeline stage reads/writes a season-specific file (e.g.
hnl_player_stats_clean_2025_2026.csv). Centralizing the season name and
the output suffix here means adding a new season is one environment
variable change, not an edit to every module's hardcoded path - every
module builds its paths by calling the helpers below instead of writing
out the suffix itself.

Defaults match the 2025/2026 season this project originally shipped with,
so `python main.py` with no environment variables set behaves exactly as
before.
"""
import os

# The SportMonks season name to search for (see fetch_data.find_season_id).
SEASON_NAME = os.getenv("HNL_SEASON_NAME", "2025/2026")

# The suffix appended to every generated file name for this season, e.g.
# "2025_2026" -> hnl_player_stats_clean_2025_2026.csv.
OUTPUT_SUFFIX = os.getenv("HNL_OUTPUT_SUFFIX", "2025_2026")

RAW_DIR = "data/raw"
PROCESSED_DIR = "data/processed"
OUTPUT_DIR = "data/output"
REPORTS_DIR = "reports"


def raw_json_path(suffix=None):
    return f"{RAW_DIR}/hnl_player_stats_raw_{suffix or OUTPUT_SUFFIX}.json"


def raw_csv_path(suffix=None):
    return f"{RAW_DIR}/hnl_player_stats_raw_{suffix or OUTPUT_SUFFIX}.csv"


def processed_path(base_name, suffix=None):
    """e.g. processed_path("hnl_player_stats_clean")
    -> "data/processed/hnl_player_stats_clean_2025_2026.csv"

    `suffix` overrides the current-process season (OUTPUT_SUFFIX, set once
    from HNL_OUTPUT_SUFFIX at import time) - the dashboard's season
    selector needs this, since it switches seasons at runtime within one
    process rather than via an environment variable."""
    return f"{PROCESSED_DIR}/{base_name}_{suffix or OUTPUT_SUFFIX}.csv"


def output_path(base_name, suffix=None):
    """e.g. output_path("top_players_hnl")
    -> "data/output/top_players_hnl_2025_2026.csv" - see processed_path's
    docstring for what `suffix` is for."""
    return f"{OUTPUT_DIR}/{base_name}_{suffix or OUTPUT_SUFFIX}.csv"


def cluster_profiles_report_path(suffix=None):
    return f"{REPORTS_DIR}/player_cluster_profiles_{suffix or OUTPUT_SUFFIX}.md"


def scouting_report_path(suffix=None):
    return f"{REPORTS_DIR}/hnl_{suffix or OUTPUT_SUFFIX}_scouting_report.md"


def figures_dir_name(suffix=None):
    """e.g. "figures_2025_2026" - just the folder name, for building
    relative Markdown image links (the report lives in REPORTS_DIR itself,
    so links are relative to that, not to the repo root)."""
    return f"figures_{suffix or OUTPUT_SUFFIX}"


def figures_dir(suffix=None):
    """e.g. "reports/figures_2025_2026" - one folder per season, so
    regenerating one season's charts never overwrites another's."""
    return f"{REPORTS_DIR}/{figures_dir_name(suffix)}"
