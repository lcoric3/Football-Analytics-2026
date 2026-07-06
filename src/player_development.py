"""
Stage 4: multi-season player development - compares the same players'
scouting scores across HNL 2024/2025 and HNL 2025/2026 (matched by
`player_id`, never `player_name` - see build_development_dataset) to surface
who improved, who declined, who broke through as a young talent, and who
kept improving after a transfer.

This module never calls the SportMonks API and never touches raw data - it
only reads the per-season CSVs the pipeline already produced
(data/processed/hnl_player_scored_<season>.csv and
data/output/top_players_hnl_<season>.csv) and writes one comparison CSV plus
one Markdown report.

Football data science logic:
A player's scouting scores (attacking_score, overall_score, ...) are
season-relative percentile ranks (see scouting_scores.py) - "how this
player compared to the 2024/2025 pool" or "... to the 2025/2026 pool", not
an absolute rating. Two different seasons can have a different player
pool, different team-strength distribution, and even different
STAT_TYPE_MAP coverage (see clean_data.py) if SportMonks exposes a
different set of stat types for a given season. So a positive
`overall_score_change` here means "improved relative to their own season's
peers", not "objectively became a better footballer" - see the report's
Limitations section for the full caveat list.
"""
import logging
import os
from datetime import date

import pandas as pd

from src import season_config

logger = logging.getLogger(__name__)

BASE_SEASON_SUFFIX = "2024_2025"
TARGET_SEASON_SUFFIX = "2025_2026"
BASE_SEASON_NAME = "2024/2025"
TARGET_SEASON_NAME = "2025/2026"

DEVELOPMENT_OUTPUT_CSV_PATH = (
    f"{season_config.OUTPUT_DIR}/player_development_"
    f"{BASE_SEASON_SUFFIX}_to_{TARGET_SEASON_SUFFIX}.csv"
)
DEVELOPMENT_REPORT_PATH = f"{season_config.REPORTS_DIR}/hnl_multi_season_development_report.md"

# Same U23 cutoff used throughout the rest of the project (visualization.py,
# analysis.py, scouting_scores.py).
U23_AGE_LIMIT = 23

# Context columns compared across seasons - mapped to the output column
# name used in the saved CSV (team_name -> "team", not "team_name").
CONTEXT_COLUMN_OUTPUT_NAMES = {
    "team_name": "team", "position": "position", "age": "age", "minutes": "minutes",
}

SCORE_COLUMNS = [
    "overall_score", "age_potential_score", "attacking_score", "creative_score",
    "defensive_score", "dribbling_score", "passing_score", "duel_defending_score",
    "progressive_midfielder_score", "passer_defender_score", "underrated_score",
]
SPECIALIST_SCORE_COLUMNS = [
    "dribbling_score", "passing_score", "duel_defending_score",
    "progressive_midfielder_score", "passer_defender_score",
]
SPECIALIST_CHANGE_COLUMNS = [f"{c}_change" for c in SPECIALIST_SCORE_COLUMNS]

TOP_N = 10


def _scored_path(suffix):
    return f"{season_config.PROCESSED_DIR}/hnl_player_scored_{suffix}.csv"


def _top_players_path(suffix):
    return f"{season_config.OUTPUT_DIR}/top_players_hnl_{suffix}.csv"


def load_scored(suffix):
    path = _scored_path(suffix)
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"{path} not found. Run the pipeline for that season first "
            f"(HNL_OUTPUT_SUFFIX={suffix})."
        )
    return pd.read_csv(path)


def load_hidden_gem_ids(suffix):
    """player_id set for category=="hidden_gems" in that season's
    top_players_hnl CSV - used by rank_hidden_gems_who_improved. Returns an
    empty set (with a warning) if the file or category isn't there, so a
    missing ranking file never breaks the whole comparison."""
    path = _top_players_path(suffix)
    if not os.path.exists(path):
        logger.warning("%s not found - hidden_gems_who_improved will be empty.", path)
        return set()
    top_players_df = pd.read_csv(path)
    if "category" not in top_players_df.columns:
        return set()
    hidden_gems = top_players_df[top_players_df["category"] == "hidden_gems"]
    return set(hidden_gems["player_id"])


def _available_columns(df, columns, season_label):
    """Subset of `columns` that actually exist in df - SportMonks stat
    availability (clean_data.py's STAT_TYPE_MAP) or a score computed only
    above a minutes floor (scouting_scores.py) can differ between seasons,
    so a comparison column is silently skipped (not a crash) if either
    season is missing it."""
    missing = [c for c in columns if c not in df.columns]
    if missing:
        logger.warning("%s scored data is missing columns (skipping): %s", season_label, missing)
    return [c for c in columns if c in df.columns]


def build_development_dataset(
    base_df, target_df,
    base_suffix=BASE_SEASON_SUFFIX, target_suffix=TARGET_SEASON_SUFFIX,
):
    """Inner-joins `base_df` and `target_df` on `player_id` (never
    `player_name` - SportMonks IDs are stable per player, while name
    strings can differ in accents/transliteration between API pulls, or
    collide between two different players who share a name) and computes
    season-over-season changes for every score column present in *both*
    seasons. A player who only appears in one season (didn't play, wasn't
    in the league, transferred away/in) is dropped - this dataset is
    specifically "players seen in both seasons".

    Any score column missing from either season is skipped rather than
    raising - see _available_columns."""
    context_cols = list(CONTEXT_COLUMN_OUTPUT_NAMES)
    base_context = _available_columns(base_df, context_cols, base_suffix)
    target_context = _available_columns(target_df, context_cols, target_suffix)
    base_scores = _available_columns(base_df, SCORE_COLUMNS, base_suffix)
    target_scores = _available_columns(target_df, SCORE_COLUMNS, target_suffix)

    base_rename = {c: f"{CONTEXT_COLUMN_OUTPUT_NAMES[c]}_{base_suffix}" for c in base_context}
    base_rename.update({c: f"{c}_{base_suffix}" for c in base_scores})
    base_subset = base_df[["player_id", "player_name"] + base_context + base_scores].rename(
        columns=base_rename
    )

    target_rename = {c: f"{CONTEXT_COLUMN_OUTPUT_NAMES[c]}_{target_suffix}" for c in target_context}
    target_rename.update({c: f"{c}_{target_suffix}" for c in target_scores})
    target_subset = target_df[["player_id", "player_name"] + target_context + target_scores].rename(
        columns=target_rename
    )
    # player_name is kept from the base season only - a player's name isn't
    # expected to change between seasons, so there's no need for two copies.
    target_subset = target_subset.drop(columns=["player_name"])

    merged = base_subset.merge(target_subset, on="player_id", how="inner")

    minutes_base_col, minutes_target_col = f"minutes_{base_suffix}", f"minutes_{target_suffix}"
    if minutes_base_col in merged.columns and minutes_target_col in merged.columns:
        merged["minutes_change"] = merged[minutes_target_col] - merged[minutes_base_col]

    common_scores = [c for c in base_scores if c in target_scores]
    for col in common_scores:
        merged[f"{col}_change"] = merged[f"{col}_{target_suffix}"] - merged[f"{col}_{base_suffix}"]

    team_base_col, team_target_col = f"team_{base_suffix}", f"team_{target_suffix}"
    merged["changed_team"] = False
    if team_base_col in merged.columns and team_target_col in merged.columns:
        merged["changed_team"] = merged[team_base_col] != merged[team_target_col]

    position_base_col, position_target_col = f"position_{base_suffix}", f"position_{target_suffix}"
    merged["same_position"] = pd.NA
    if position_base_col in merged.columns and position_target_col in merged.columns:
        merged["same_position"] = merged[position_base_col] == merged[position_target_col]

    merged["minutes_increased"] = False
    if "minutes_change" in merged.columns:
        merged["minutes_increased"] = merged["minutes_change"] > 0

    age_target_col = f"age_{target_suffix}"
    merged["young_player"] = False
    if age_target_col in merged.columns:
        merged["young_player"] = merged[age_target_col] <= U23_AGE_LIMIT

    merged["improved_overall"] = False
    if "overall_score_change" in merged.columns:
        merged["improved_overall"] = merged["overall_score_change"] > 0

    specialist_change_cols = [c for c in SPECIALIST_CHANGE_COLUMNS if c in merged.columns]
    merged["improved_specialist_score"] = False
    if specialist_change_cols:
        merged["improved_specialist_score"] = (merged[specialist_change_cols] > 0).any(axis=1)

    return merged


def select_final_columns(merged_df, base_suffix=BASE_SEASON_SUFFIX, target_suffix=TARGET_SEASON_SUFFIX):
    """The exact column set/order this project's development CSV should
    have. Any column not actually present in `merged_df` (e.g. a score that
    was missing from one season - see _available_columns) is skipped
    rather than raising a KeyError, so a season with incomplete stat
    coverage still produces a usable, if smaller, comparison."""
    ordered = [
        "player_id", "player_name",
        f"age_{base_suffix}", f"age_{target_suffix}",
        f"team_{base_suffix}", f"team_{target_suffix}",
        f"position_{base_suffix}", f"position_{target_suffix}",
        f"minutes_{base_suffix}", f"minutes_{target_suffix}", "minutes_change",
        f"overall_score_{base_suffix}", f"overall_score_{target_suffix}", "overall_score_change",
        "age_potential_score_change",
        "attacking_score_change",
        "creative_score_change",
        "defensive_score_change",
        "dribbling_score_change",
        "passing_score_change",
        "duel_defending_score_change",
        "progressive_midfielder_score_change",
        "passer_defender_score_change",
        "underrated_score_change",
        "changed_team", "same_position", "minutes_increased", "young_player",
        "improved_overall", "improved_specialist_score",
    ]
    available = [c for c in ordered if c in merged_df.columns]
    missing = [c for c in ordered if c not in merged_df.columns]
    if missing:
        logger.warning("Development dataset is missing expected columns (skipped): %s", missing)
    return merged_df[available].copy()


# --- Rankings ---------------------------------------------------------------

def rank_biggest_improvers(dev_df, top_n=TOP_N):
    if "overall_score_change" not in dev_df.columns:
        return dev_df.iloc[0:0]
    return dev_df.dropna(subset=["overall_score_change"]).sort_values(
        "overall_score_change", ascending=False
    ).head(top_n)


def rank_biggest_decliners(dev_df, top_n=TOP_N):
    if "overall_score_change" not in dev_df.columns:
        return dev_df.iloc[0:0]
    return dev_df.dropna(subset=["overall_score_change"]).sort_values(
        "overall_score_change", ascending=True
    ).head(top_n)


def rank_young_improvers(dev_df, top_n=TOP_N):
    if "young_player" not in dev_df.columns or "improved_overall" not in dev_df.columns:
        return dev_df.iloc[0:0]
    pool = dev_df[dev_df["young_player"] & dev_df["improved_overall"]]
    return pool.sort_values("overall_score_change", ascending=False).head(top_n)


def rank_increased_minutes(dev_df, top_n=TOP_N):
    if "minutes_change" not in dev_df.columns:
        return dev_df.iloc[0:0]
    return dev_df.dropna(subset=["minutes_change"]).sort_values(
        "minutes_change", ascending=False
    ).head(top_n)


def rank_changed_team_improvers(dev_df, top_n=TOP_N):
    if "changed_team" not in dev_df.columns or "improved_overall" not in dev_df.columns:
        return dev_df.iloc[0:0]
    pool = dev_df[dev_df["changed_team"] & dev_df["improved_overall"]]
    return pool.sort_values("overall_score_change", ascending=False).head(top_n)


def rank_specialist_improvers(dev_df, top_n=TOP_N):
    """Ranked by each player's single best specialist-score improvement
    (dribbling/passing/duel_defending/progressive_midfielder/
    passer_defender) - a player can be a below-average all-rounder but a
    big riser in one specific skill, which overall_score_change alone
    would hide. `best_specialist_metric`/`best_specialist_score_change` are
    computed here for ranking/reporting only - they aren't part of the
    saved development CSV schema."""
    available = [c for c in SPECIALIST_CHANGE_COLUMNS if c in dev_df.columns]
    if not available or "improved_specialist_score" not in dev_df.columns:
        return dev_df.iloc[0:0]
    pool = dev_df[dev_df["improved_specialist_score"]].copy()
    if pool.empty:
        return pool
    pool["best_specialist_score_change"] = pool[available].max(axis=1)
    pool["best_specialist_metric"] = pool[available].idxmax(axis=1).str.replace("_change", "", regex=False)
    return pool.sort_values("best_specialist_score_change", ascending=False).head(top_n)


def rank_hidden_gems_who_improved(dev_df, hidden_gem_ids, top_n=TOP_N):
    if "improved_overall" not in dev_df.columns or not hidden_gem_ids:
        return dev_df.iloc[0:0]
    pool = dev_df[dev_df["player_id"].isin(hidden_gem_ids) & dev_df["improved_overall"]]
    return pool.sort_values("overall_score_change", ascending=False).head(top_n)


# --- Report -------------------------------------------------------------

def _md_table(df, columns, headers=None, decimals=None):
    """Tiny Markdown-table writer - mirrors report.py's _md_table but kept
    local to avoid a cross-module import just for this (same choice
    ml_models.py's _md_cluster_table already makes)."""
    headers = headers or columns
    decimals = decimals or {}
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join([":---"] * len(headers)) + "|"]
    for _, row in df.iterrows():
        cells = []
        for c in columns:
            value = row.get(c)
            if pd.isna(value):
                cells.append("")
            elif c in decimals:
                cells.append(f"{value:.{decimals[c]}f}")
            else:
                cells.append(str(value))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def build_report(
    dev_df, base_player_count, target_player_count, hidden_gem_ids,
    base_suffix=BASE_SEASON_SUFFIX, target_suffix=TARGET_SEASON_SUFFIX,
    base_season_name=BASE_SEASON_NAME, target_season_name=TARGET_SEASON_NAME,
):
    today = date.today().isoformat()
    matched = len(dev_df)
    team_changes = int(dev_df["changed_team"].sum()) if "changed_team" in dev_df.columns else 0
    improved = int(dev_df["improved_overall"].sum()) if "improved_overall" in dev_df.columns else 0
    declined = (
        int((dev_df["overall_score_change"] < 0).sum())
        if "overall_score_change" in dev_df.columns else 0
    )

    L = []
    L.append(f"# HNL Multi-Season Player Development Report ({base_season_name} -> {target_season_name})\n")
    L.append(
        f"\n*Generated {today} by `src/player_development.py`, from the "
        f"season-suffixed CSVs already in `data/processed/` and "
        f"`data/output/` - this report never calls the SportMonks API and "
        f"never recomputes a per-season score.*\n"
    )

    # 1. Summary --------------------------------------------------------
    L.append("## 1. Summary\n")
    L.append(
        f"This report compares every player with scored, eligible-minutes "
        f"data in **both** HNL {base_season_name} and HNL {target_season_name}, "
        f"matched by `player_id` (not name - see Section 9 for why that "
        f"matters). It highlights who improved, who declined, who broke "
        f"through as a young talent, and who kept improving after a "
        f"transfer.\n"
    )
    L.append(_md_table(
        pd.DataFrame([
            {"metric": f"Scored players in {base_season_name}", "value": base_player_count},
            {"metric": f"Scored players in {target_season_name}", "value": target_player_count},
            {"metric": "Players matched in both seasons (by player_id)", "value": matched},
            {"metric": "Players who changed team between seasons", "value": team_changes},
            {"metric": f"Players with a higher overall_score in {target_season_name}", "value": improved},
            {"metric": f"Players with a lower overall_score in {target_season_name}", "value": declined},
        ]),
        ["metric", "value"], ["Metric", "Count"],
    ))

    # 2. Biggest improvers ------------------------------------------------
    L.append("\n## 2. Biggest Improvers\n")
    L.append(
        "Ranked by `overall_score_change` (this season's `overall_score` "
        "minus last season's) - the biggest gains in season-relative "
        "overall output.\n"
    )
    L.append(_md_table(
        rank_biggest_improvers(dev_df),
        ["player_name", f"team_{target_suffix}", f"position_{target_suffix}", f"age_{target_suffix}",
         f"overall_score_{base_suffix}", f"overall_score_{target_suffix}", "overall_score_change"],
        ["Player", "Team", "Position", "Age", f"Overall {base_season_name}",
         f"Overall {target_season_name}", "Change"],
        decimals={f"overall_score_{base_suffix}": 1, f"overall_score_{target_suffix}": 1,
                  "overall_score_change": 1},
    ))

    # 3. Biggest decliners ------------------------------------------------
    L.append("\n## 3. Biggest Decliners\n")
    L.append(
        "The flip side of Section 2 - the biggest drops in `overall_score`. "
        "A decline here can mean genuine regression, but see the "
        "Limitations section: fewer minutes, a tougher team context, or a "
        "role change after a transfer can all pull a season-relative score "
        "down without the player getting any worse.\n"
    )
    L.append(_md_table(
        rank_biggest_decliners(dev_df),
        ["player_name", f"team_{target_suffix}", f"position_{target_suffix}", f"age_{target_suffix}",
         f"overall_score_{base_suffix}", f"overall_score_{target_suffix}", "overall_score_change"],
        ["Player", "Team", "Position", "Age", f"Overall {base_season_name}",
         f"Overall {target_season_name}", "Change"],
        decimals={f"overall_score_{base_suffix}": 1, f"overall_score_{target_suffix}": 1,
                  "overall_score_change": 1},
    ))

    # 4. Young improvers ---------------------------------------------------
    L.append(f"\n## 4. Young Improvers (age <= {U23_AGE_LIMIT} in {target_season_name})\n")
    L.append(
        f"Players age {U23_AGE_LIMIT} or under this season who also "
        "improved their `overall_score` - the clearest \"still improving, "
        "still young\" signal this dataset can produce.\n"
    )
    L.append(_md_table(
        rank_young_improvers(dev_df),
        ["player_name", f"team_{target_suffix}", f"position_{target_suffix}", f"age_{target_suffix}",
         "overall_score_change"],
        ["Player", "Team", "Position", "Age", "Overall Change"],
        decimals={"overall_score_change": 1},
    ))

    # 5. Increased playing time -------------------------------------------
    L.append("\n## 5. Increased Playing Time\n")
    L.append(
        "Ranked by raw `minutes_change` - not a quality signal by itself, "
        "but useful alongside the other tables: a player whose scores "
        "improved *and* whose minutes grew is a much more reliable signal "
        "than one whose scores improved on a small, noisy sample (see the "
        "Limitations section).\n"
    )
    L.append(_md_table(
        rank_increased_minutes(dev_df),
        ["player_name", f"team_{target_suffix}", f"minutes_{base_suffix}", f"minutes_{target_suffix}",
         "minutes_change"],
        ["Player", "Team", f"Minutes {base_season_name}", f"Minutes {target_season_name}", "Change"],
    ))

    # 6. Improved after changing team -------------------------------------
    L.append("\n## 6. Improved After Changing Team\n")
    L.append(
        "Players who moved clubs between seasons *and* still improved "
        "their `overall_score` - a signal the improvement survived a "
        "change in teammates/system, not just one team's context (see "
        "Limitations).\n"
    )
    L.append(_md_table(
        rank_changed_team_improvers(dev_df),
        ["player_name", f"team_{base_suffix}", f"team_{target_suffix}", "overall_score_change"],
        ["Player", f"Team {base_season_name}", f"Team {target_season_name}", "Overall Change"],
        decimals={"overall_score_change": 1},
    ))

    # 7. Specialist score improvers ----------------------------------------
    L.append("\n## 7. Specialist Score Improvers\n")
    L.append(
        "Ranked by each player's single biggest specialist-score gain "
        "(`dribbling_score`, `passing_score`, `duel_defending_score`, "
        "`progressive_midfielder_score`, or `passer_defender_score` - see "
        "scouting_scores.py) - a player can be a modest all-rounder but a "
        "big riser in one specific skill, which `overall_score_change` "
        "alone would hide.\n"
    )
    specialist_improvers = rank_specialist_improvers(dev_df)
    if specialist_improvers.empty:
        L.append("*No specialist-score improvers found.*\n")
    else:
        L.append(_md_table(
            specialist_improvers,
            ["player_name", f"position_{target_suffix}", "best_specialist_metric",
             "best_specialist_score_change"],
            ["Player", "Position", "Best-Improved Metric", "Change"],
            decimals={"best_specialist_score_change": 1},
        ))

    # 8. Hidden gems who improved -------------------------------------------
    L.append("\n## 8. Hidden Gems Who Improved\n")
    L.append(
        f"Players tagged `hidden_gems` in {base_season_name} (outperforming "
        f"their own team *and* playing at a squad below the league "
        f"average - see that season's own scouting report) who then also "
        f"improved their `overall_score` in {target_season_name} - a "
        "signal that last season's under-the-radar standout kept getting "
        "better, not just a one-season blip.\n"
    )
    hidden_gems_improved = rank_hidden_gems_who_improved(dev_df, hidden_gem_ids)
    if hidden_gems_improved.empty:
        L.append("*No hidden gems from last season also improved this season.*\n")
    else:
        L.append(_md_table(
            hidden_gems_improved,
            ["player_name", f"team_{base_suffix}", f"team_{target_suffix}", "overall_score_change"],
            ["Player", f"Team {base_season_name}", f"Team {target_season_name}", "Overall Change"],
            decimals={"overall_score_change": 1},
        ))

    # 9. Methodology --------------------------------------------------------
    L.append("\n## 9. Methodology\n")
    L.append(
        "- **Matching**: players are matched by `player_id`, not "
        "`player_name` - SportMonks IDs are stable per player, while name "
        "strings can differ in accents/transliteration between API pulls, "
        "or collide between two different players who share a name. A "
        "player who didn't play in one of the two seasons (transferred out "
        f"of the league, injured all season, etc.) is not in this "
        f"comparison - only the {matched} players scored in *both* seasons "
        "are.\n"
        "- **Score changes**: every `*_score_change` column is simply "
        f"`<score>_{target_suffix} - <score>_{base_suffix}`; positive means "
        "improved relative to that season's own player pool (see "
        "Limitations).\n"
        "- **Flags**: `changed_team`/`same_position` compare the raw "
        "`team`/`position` strings between seasons; `minutes_increased`, "
        "`improved_overall`, and `improved_specialist_score` are simple "
        "`> 0` checks on the corresponding change column(s).\n"
        "- **Rankings**: `biggest_improvers`/`biggest_decliners` sort by "
        "`overall_score_change`; `young_improvers` additionally requires "
        f"age <= {U23_AGE_LIMIT} in {target_season_name}; "
        "`changed_team_improvers` requires `changed_team` and "
        "`improved_overall`; `specialist_improvers` sorts by each player's "
        "single biggest specialist-score gain; `hidden_gems_who_improved` "
        f"starts from {base_season_name}'s `hidden_gems` list and keeps "
        "only the ones who also improved.\n"
    )

    # 10. Limitations ---------------------------------------------------
    L.append("\n## 10. Limitations\n")
    L.append(
        "- **Scores are season-relative, not absolute.** Every score here "
        "(`overall_score`, `attacking_score`, ...) is a percentile rank "
        "against that season's own player pool (see scouting_scores.py). A "
        "positive `overall_score_change` means \"improved relative to "
        "their own season's peers\", not \"objectively became a better "
        "footballer\" - the league's overall talent level can shift "
        "between seasons independent of any one player.\n"
        "- **Team context changes between seasons.** `underrated_score`'s "
        "team-context bonuses (see scouting_scores.py) are relative to "
        "that season's own team-strength distribution - a team's average "
        "squad quality can rise or fall between seasons for reasons that "
        "have nothing to do with any individual player.\n"
        "- **Minutes changes affect reliability, not just opportunity.** A "
        "player with a big `overall_score_change` on a small `minutes` "
        "sample (either season) is a noisier signal than the same change "
        "on a full season's minutes - cross-check `minutes_change` and "
        "each season's raw minutes before treating a jump as a real "
        "trend.\n"
        "- **A player changing team may change role entirely.** "
        "`changed_team` only compares club names - it says nothing about "
        "whether the player's tactical role, position share, or "
        "set-piece duties changed along with the move, any of which can "
        "move scores independent of underlying skill.\n"
        "- **SportMonks stat availability may differ between seasons.** "
        "If a stat type wasn't mapped or wasn't returned for a given "
        "season (see clean_data.py's `STAT_TYPE_MAP` and its \"unmapped "
        "statistic type ids\" warning), the score(s) built from it may be "
        "missing for that season - this module skips (not crashes on) "
        "any comparison column that isn't present in both seasons, but a "
        "missing column also means that particular comparison silently "
        "isn't possible this run.\n"
        "- **This is a scouting signal, not a final evaluation.** Like "
        "every other ranking in this project, it says nothing about "
        "video-scouted technique, tactical fit, injury history, or "
        "transfer feasibility - treat it as a reproducible starting point "
        "for a human scout, not a conclusion.\n"
    )

    return "\n".join(L) + "\n"


def run():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    base_df = load_scored(BASE_SEASON_SUFFIX)
    target_df = load_scored(TARGET_SEASON_SUFFIX)

    merged = build_development_dataset(base_df, target_df)
    dev_df = select_final_columns(merged)

    os.makedirs(os.path.dirname(DEVELOPMENT_OUTPUT_CSV_PATH), exist_ok=True)
    dev_df.to_csv(DEVELOPMENT_OUTPUT_CSV_PATH, index=False)
    logger.info(
        "Saved %d matched-player development rows to %s", len(dev_df), DEVELOPMENT_OUTPUT_CSV_PATH,
    )

    hidden_gem_ids = load_hidden_gem_ids(BASE_SEASON_SUFFIX)

    report_text = build_report(dev_df, len(base_df), len(target_df), hidden_gem_ids)
    os.makedirs(os.path.dirname(DEVELOPMENT_REPORT_PATH), exist_ok=True)
    with open(DEVELOPMENT_REPORT_PATH, "w", encoding="utf-8") as f:
        f.write(report_text)
    logger.info("Saved multi-season development report to %s", DEVELOPMENT_REPORT_PATH)

    return dev_df


if __name__ == "__main__":
    run()
