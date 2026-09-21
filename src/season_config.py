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
from pathlib import Path

# The SportMonks season name to search for (see fetch_data.find_season_id).
SEASON_NAME = os.getenv("HNL_SEASON_NAME", "2025/2026")

# The suffix appended to every generated file name for this season, e.g.
# "2025_2026" -> hnl_player_stats_clean_2025_2026.csv.
OUTPUT_SUFFIX = os.getenv("HNL_OUTPUT_SUFFIX", "2025_2026")

# The repository root, derived from this file's own location
# (<repo root>/src/season_config.py) rather than from the current working
# directory. Every data/report path below is built from it, so the pipeline
# and the dashboard find the same files no matter where the process was
# started from - a `python main.py` run from another folder, an IDE "run"
# button, or Streamlit Community Cloud. Paths are joined with os.path.join
# so they stay correct on both Windows and Linux.
PROJECT_ROOT = Path(__file__).resolve().parent.parent

RAW_DIR = str(PROJECT_ROOT / "data" / "raw")
PROCESSED_DIR = str(PROJECT_ROOT / "data" / "processed")
OUTPUT_DIR = str(PROJECT_ROOT / "data" / "output")
REPORTS_DIR = str(PROJECT_ROOT / "reports")


def raw_json_path(suffix=None):
    return os.path.join(RAW_DIR, f"hnl_player_stats_raw_{suffix or OUTPUT_SUFFIX}.json")


def raw_csv_path(suffix=None):
    return os.path.join(RAW_DIR, f"hnl_player_stats_raw_{suffix or OUTPUT_SUFFIX}.csv")


def processed_path(base_name, suffix=None):
    """e.g. processed_path("hnl_player_stats_clean")
    -> "data/processed/hnl_player_stats_clean_2025_2026.csv"

    `suffix` overrides the current-process season (OUTPUT_SUFFIX, set once
    from HNL_OUTPUT_SUFFIX at import time) - the dashboard's season
    selector needs this, since it switches seasons at runtime within one
    process rather than via an environment variable."""
    return os.path.join(PROCESSED_DIR, f"{base_name}_{suffix or OUTPUT_SUFFIX}.csv")


def output_path(base_name, suffix=None):
    """e.g. output_path("top_players_hnl")
    -> "data/output/top_players_hnl_2025_2026.csv" - see processed_path's
    docstring for what `suffix` is for."""
    return os.path.join(OUTPUT_DIR, f"{base_name}_{suffix or OUTPUT_SUFFIX}.csv")


def cluster_profiles_report_path(suffix=None):
    return os.path.join(REPORTS_DIR, f"player_cluster_profiles_{suffix or OUTPUT_SUFFIX}.md")


def scouting_report_path(suffix=None):
    return os.path.join(REPORTS_DIR, f"hnl_{suffix or OUTPUT_SUFFIX}_scouting_report.md")


def figures_dir_name(suffix=None):
    """e.g. "figures_2025_2026" - just the folder name, for building
    relative Markdown image links (the report lives in REPORTS_DIR itself,
    so links are relative to that, not to the repo root)."""
    return f"figures_{suffix or OUTPUT_SUFFIX}"


def figures_dir(suffix=None):
    """e.g. "reports/figures_2025_2026" - one folder per season, so
    regenerating one season's charts never overwrites another's."""
    return os.path.join(REPORTS_DIR, figures_dir_name(suffix))
