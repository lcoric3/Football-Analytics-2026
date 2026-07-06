"""
Stage 8: Markdown scouting report.

Football data science logic:
This module computes nothing new about players - it only reads whatever
scouting_scores.py, analysis.py, ml_models.py, replacement_scouting.py, and
visualization.py already produced (the scored/ranked/similarity/cluster/
replacement CSVs and the PNGs in reports/figures_<season>/), formats it, and
explains it in prose. That's a deliberate choice: a report that recomputes
its own numbers can drift from the data it's supposed to summarize; a
report that only reads already-saved files always matches the last
pipeline run exactly.
"""
import logging
import os
from datetime import date

import pandas as pd

from src import clean_data
from src import season_config
from src.scouting_scores import MIN_MINUTES_FOR_SCORES

logger = logging.getLogger(__name__)

CLEAN_CSV_PATH = clean_data.CLEAN_CSV_PATH
SCORED_CSV_PATH = season_config.processed_path("hnl_player_scored")
TOP_PLAYERS_CSV_PATH = season_config.output_path("top_players_hnl")
SPECIALIST_CSV_PATH = season_config.output_path("specialist_rankings_hnl")
SIMILARITY_CSV_PATH = season_config.output_path("player_similarity_results")
REPLACEMENT_CSV_PATH = season_config.output_path("replacement_targets")
CLUSTERS_CSV_PATH = season_config.output_path("player_clusters")
# Relative filename only - both reports live in the same reports/ folder,
# so the Markdown report links to this one by name, not full path.
CLUSTER_PROFILES_REPORT_FILE = os.path.basename(season_config.cluster_profiles_report_path())
REPORT_PATH = season_config.scouting_report_path()
# Folder name only (e.g. "figures_2025_2026") - this report lives directly
# in reports/, so image links are relative to that, not to the repo root.
FIGURES_DIR_NAME = season_config.figures_dir_name()

TOP_N = 10


def _fmt(value, decimals=None):
    if pd.isna(value):
        return ""
    if decimals is not None:
        return f"{value:.{decimals}f}"
    return str(value)


def _md_table(df, columns, headers=None, decimals=None):
    """Tiny Markdown-table writer - avoids adding a `tabulate` dependency
    just for this."""
    headers = headers or columns
    decimals = decimals or {}
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join([":---"] * len(headers)) + "|"]
    for _, row in df.iterrows():
        cells = [_fmt(row[c], decimals.get(c)) for c in columns]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def _category_table(rankings_df, category, columns, headers, decimals=None, top_n=TOP_N):
    subset = rankings_df[rankings_df["category"] == category].sort_values("rank").head(top_n)
    return _md_table(subset, columns, headers, decimals)


def _find_underrated(scored_df, top_n=8):
    """Players with the highest underrated_score (Stage B2) - overall_score
    plus a capped bonus for outperforming their own teammates and a capped
    bonus for playing at a squad below the league's average team (see
    scouting_scores.py for the exact formula). Replaces the project's
    earlier fixed "exclude the three big clubs" list with a computed,
    reproducible team-context signal.

    Outfield only: overall_score (and therefore underrated_score) isn't a
    meaningful measure of goalkeeping quality (Section 6), so a goalkeeper
    landing here would be an artifact, not a real "underrated" signal."""
    outfield = scored_df[scored_df["position"].astype(str).str.lower() != "goalkeeper"]
    eligible = outfield[outfield["minutes"] >= MIN_MINUTES_FOR_SCORES]
    return (
        eligible.dropna(subset=["underrated_score"])
        .sort_values("underrated_score", ascending=False)
        .head(top_n)
    )


def _similarity_section(similarity_df, example_slot, chart_file=None, top_n=TOP_N):
    """example_slot (e.g. "midfielder_example") identifies which
    demonstration example this is - not the player name or role, since two
    slots can resolve to the same fallback player in a given season (see
    ml_models.EXAMPLE_SIMILARITY_QUERIES). The query player and role shown
    below are read from the data, so this always reflects whichever player
    this season's pipeline actually searched for that slot."""
    subset = similarity_df[similarity_df["example_slot"] == example_slot].sort_values("rank").head(top_n)
    if subset.empty:
        return f"*No similarity example available for slot `{example_slot}`.*\n"
    query_player = subset["query_player"].iloc[0]
    role = subset["role"].iloc[0]
    filters = subset["filters"].iloc[0] if "filters" in subset.columns else ""
    filters_note = f" - filters: `{filters}`" if isinstance(filters, str) and filters else ""
    table = _md_table(
        subset, ["rank", "player_name", "team_name", "position", "similarity"],
        ["Rank", "Player", "Team", "Position", "Similarity"], decimals={"similarity": 2},
    )
    chart = f"\n![Players similar to {query_player}]({chart_file})\n" if chart_file else ""
    return (
        f"**{query_player} - role: `{role}`**{filters_note}\n\n"
        f"{table}\n"
        f"{chart}\n"
        f"*The chart shows cosine similarity (0-1) for each match - see "
        f"section 19 for what that number means.*\n"
    )


def _replacement_section(replacement_df, example_slot, top_n=TOP_N):
    """example_slot identifies which demonstration example this is - see
    _similarity_section's docstring for why (not player name/role)."""
    subset = replacement_df[replacement_df["example_slot"] == example_slot].sort_values("rank").head(top_n)
    if subset.empty:
        return f"*No replacement-target example available for slot `{example_slot}`.*\n"
    query_player = subset["query_player"].iloc[0]
    role = subset["role"].iloc[0]
    table = _md_table(
        subset,
        ["rank", "player_name", "team_name", "position", "age", "similarity",
         "age_potential_score", "underrated_score", "younger_bonus", "replacement_score"],
        ["Rank", "Player", "Team", "Position", "Age", "Similarity", "Potential",
         "Underrated", "Younger Bonus", "Replacement Score"],
        decimals={"similarity": 2, "age_potential_score": 1, "underrated_score": 1,
                  "younger_bonus": 1, "replacement_score": 1, "age": 0},
    )
    return f"**Replacement targets for {query_player}** (role: `{role}`)\n\n{table}\n"


def _cluster_summary_table(clusters_df):
    rows = []
    for cluster_id, group in clusters_df.groupby("cluster_id"):
        top_player = group.sort_values("quality_score", ascending=False).iloc[0]
        rows.append({
            "cluster_id": int(cluster_id),
            "cluster_name": group["cluster_name"].iloc[0],
            "players": len(group),
            "avg_age": group["age"].mean(),
            "top_player": f"{top_player['player_name']} ({top_player['team_name']})",
        })
    summary_df = pd.DataFrame(rows).sort_values("cluster_id")
    return _md_table(
        summary_df, ["cluster_id", "cluster_name", "players", "avg_age", "top_player"],
        ["Cluster", "Name", "Players", "Avg Age", "Top Player (by quality_score)"],
        decimals={"avg_age": 1},
    )


def build_report(
    scored_df, top_players_df, specialist_df, similarity_df, replacement_df, clusters_df,
    raw_rows, deduped_rows,
):
    eligible_count = int((scored_df["minutes"] >= MIN_MINUTES_FOR_SCORES).sum())
    duplicates_removed = raw_rows - deduped_rows
    today = date.today().isoformat()

    L = []
    L.append(f"# HNL {season_config.SEASON_NAME} Scouting Report")
    L.append(f"\n*Generated {today} by `src/report.py`, from the current contents of `data/` and `reports/{FIGURES_DIR_NAME}/`.*\n")

    # 1. Project summary --------------------------------------------------
    L.append("## 1. Project Summary\n")
    L.append(
        "This project turns raw SportMonks player statistics for the Croatian "
        f"1. HNL {season_config.SEASON_NAME} season into a full scouting data pipeline: cleaned "
        "data, per-90 features, explainable scouting scores, age-aware "
        "potential scoring, team-context/underrated scoring, position- and "
        "role-specific rankings, a filterable player-similarity search, "
        "statistical replacement-target shortlists, and named player "
        "clusters. Every number in this report is read directly from the "
        "CSVs the pipeline produces (`data/processed/`, `data/output/`) - "
        "nothing here is hand-picked.\n"
    )

    # 2. Data source --------------------------------------------------------
    L.append("## 2. Data Source\n")
    L.append(
        "All player statistics come from the "
        "[SportMonks](https://www.sportmonks.com/) Football API, scoped to "
        f"the Croatian HNL / 1. HNL, {season_config.SEASON_NAME} season. `fetch_data.py` finds "
        "the league/season IDs, paginates through every team's squad "
        "statistics, and saves the raw JSON response before anything is "
        "cleaned or transformed - so the raw response is always available "
        "to re-process if the cleaning logic changes (as it did in Stage 1, "
        "below).\n"
    )

    # 3. Dataset summary ------------------------------------------------
    L.append("## 3. Dataset Summary\n")
    L.append(_md_table(
        pd.DataFrame([
            {"metric": "Raw player rows (minutes > 0, before de-duplication)", "value": raw_rows},
            {"metric": "Rows after de-duplication", "value": deduped_rows},
            {"metric": "Duplicate player rows removed", "value": duplicates_removed},
            {"metric": "Players eligible for scoring (>= 450 minutes)", "value": eligible_count},
        ]),
        ["metric", "value"], ["Metric", "Count"],
    ))
    L.append(
        "\nThe raw SportMonks response actually contains far more than the "
        "original pipeline used: of 55 distinct statistic types present in "
        "the JSON, only 15 were mapped to columns before Stage 1. Dribbles, "
        "key passes, crosses, long balls, aerials won, clearances, and "
        "fouls drawn were sitting in the data unused - Stage 1 mapped 11 of "
        "them (see Section 5 and Sections 12-16).\n"
    )

    # 4. Why per-90 ----------------------------------------------------------
    L.append("## 4. Why Per-90 Stats?\n")
    L.append(
        "Raw totals (goals, tackles, passes...) aren't comparable between "
        "players directly, because playing time varies enormously - a squad "
        "player with 5 goals in 900 minutes is doing far better than a "
        "regular starter with 5 goals in 2700 minutes. Dividing every "
        "counting stat by minutes played and scaling to a full match "
        "(`per90 = count / minutes * 90`) puts every player on the same "
        "footing regardless of how often their team picked them. All "
        "scouting scores in this project are built from per-90 rates and "
        "ratios, never raw totals (the two counting-stat exceptions - "
        "`top_scorers` and `top_assists` - are deliberately traditional "
        "Golden-Boot-style leaderboards, not scouting tools).\n"
    )

    # 5. Deduplication --------------------------------------------------
    L.append("## 5. Deduplication Fix (Stage 1)\n")
    L.append(
        f"Some players' SportMonks records list squad membership at two "
        f"clubs in the same season (typically a mid-season transfer or "
        f"loan). That duplicated their row in the cleaned data - but "
        f"`statistics.details` isn't split per club spell, so **both rows "
        f"carried the exact same full-season totals**. Left alone, that "
        f"would double-count those players in every per-90 rate and every "
        f"ranking they appear in.\n\n"
        f"**The fix:** keep exactly one row per `player_id` - the row with "
        f"the most minutes played. If the two rows disagreed on team name, "
        f"that's logged as a warning during the pipeline run so it's "
        f"visible, not silently dropped. This took the dataset from "
        f"**{raw_rows} rows to {deduped_rows} rows** "
        f"({duplicates_removed} duplicate rows removed).\n"
    )

    # 6. Top 10 overall ----------------------------------------------------
    L.append("## 6. Top 10 Overall Players\n")
    L.append(
        "**Goalkeepers are excluded from general outfield rankings because "
        "they require a separate goalkeeper-specific model.** "
        "`overall_score` is built entirely from outfield actions - goals, "
        "assists, tackles, passes - that goalkeepers essentially never "
        "record, so it isn't a meaningful measure of goalkeeping quality "
        "(see \"Best Goalkeepers\" right after Section 7 for the dedicated "
        "`goalkeeper_score` ranking, built on stats that actually apply to "
        "keepers).\n"
    )
    L.append(_category_table(
        top_players_df, "best_overall",
        ["rank", "player_name", "team_name", "position", "age", "overall_score"],
        ["Rank", "Player", "Team", "Position", "Age", "Overall"],
        decimals={"overall_score": 1, "age": 0},
    ))
    L.append(
        f"\n![Top 15 overall players]({FIGURES_DIR_NAME}/top_overall_players.png)\n\n"
        "`overall_score` blends attacking, creative, and defensive "
        "contribution (each judged against same-position peers) plus a "
        "small discipline factor. Because each ingredient is now "
        "position-aware (Section 22 explains why), this list is no longer "
        "structurally tilted toward all-round midfielders - a specialist "
        "can top it by excelling relative to their own role's peers.\n"
    )

    # 7. Best U23 ------------------------------------------------------------
    L.append("## 7. Best U23 Players\n")
    L.append(_category_table(
        top_players_df, "best_u23",
        ["rank", "player_name", "team_name", "position", "age", "overall_score"],
        ["Rank", "Player", "Team", "Position", "Age", "Overall"],
        decimals={"overall_score": 1, "age": 0},
    ))
    L.append(
        f"\n![Top 15 U23 players]({FIGURES_DIR_NAME}/top_u23_players.png)\n\n"
        "Same `overall_score` ranking, filtered to age 23 and under. Useful "
        "for spotting resale/development value rather than just current "
        "output - see Section 8 for a lens that also weighs age and "
        "playing-time reliability, not just current output.\n"
    )

    L.append(
        "### Best Goalkeepers (Separate Model)\n\n"
        "Goalkeeping requires different inputs than outfield play, so "
        "`goalkeeper_score` is built from stats mapped specifically for "
        "this fix: saves per 90, clean sheet rate, goals conceded per 90 "
        "(inverted - fewer is better), penalties saved, and pass accuracy "
        "as a simple distribution-quality proxy. It's computed only among "
        "goalkeepers and never mixed with `overall_score`.\n\n"
    )
    L.append(_category_table(
        top_players_df, "best_goalkeepers",
        ["rank", "player_name", "team_name", "age", "goalkeeper_score"],
        ["Rank", "Player", "Team", "Age", "Goalkeeper Score"],
        decimals={"goalkeeper_score": 1, "age": 0},
    ))
    L.append(
        "\n**Caveat:** this is a simple, explainable model over a small "
        "population (17-23 eligible goalkeepers) - it is not equivalent to "
        "a specialized goalkeeping model (e.g. post-shot expected goals / "
        "shot-stopping value above expected), which would need shot "
        "placement and quality data this API doesn't expose here.\n"
    )

    # 8. Best young talents & age-aware potential (Stage B1) ---------------
    L.append("## 8. Best Young Talents & Age-Aware Potential\n")
    L.append(
        "`overall_score` answers \"who's producing well right now\" - it "
        "says nothing about whether a player is young enough to still be "
        "improving, or whether their output is backed by real, proven "
        "playing time. `age_potential_score` (Stage B1) adds that lens on "
        "top, as a simple, fully additive formula (every point is "
        "traceable to one of three ingredients, not an opaque blend):\n\n"
        "```\n"
        "age_potential_score = overall_score + age_bonus + reliability_bonus\n"
        "```\n\n"
        "- **`age_bonus`**: +2.0 points for every year younger than 23 "
        "(this project's U23 cutoff), capped at 6 years below it - so a "
        "17-year-old and a 15-year-old both get the same capped maximum "
        "of +12, rather than an ever-larger reward the younger a player "
        "gets.\n"
        "- **`reliability_bonus`**: a percentile rank of minutes played "
        "(0-100) among scoring-eligible players, scaled down to at most "
        "+8 points - rewards a young player who's already earning real "
        "first-team minutes, not just a promising cameo.\n\n"
        "Like `overall_score`, this is an **outfield-only** lens - "
        "goalkeepers are excluded from every ranking below for the same "
        "reason they're excluded from Section 6.\n"
    )
    L.append("### Best Young Talents (age <= 23)\n")
    L.append(_category_table(
        top_players_df, "best_young_talents",
        ["rank", "player_name", "team_name", "position", "age", "overall_score",
         "age_bonus", "reliability_bonus", "age_potential_score"],
        ["Rank", "Player", "Team", "Position", "Age", "Overall", "Age Bonus", "Reliability", "Potential"],
        decimals={"overall_score": 1, "age_bonus": 1, "reliability_bonus": 1,
                  "age_potential_score": 1, "age": 0},
    ))
    L.append(
        "\n**`best_u23_players_by_potential`** (saved alongside "
        f"`best_young_talents` in `{TOP_PLAYERS_CSV_PATH}`) "
        "is the exact same U23 pool and sort order as the table above - it's "
        "kept as a second category label specifically so it sits next to "
        "`best_u23` (Section 7) in the output, making the \"current output\" "
        "vs. \"potential-adjusted\" comparison for the same age bracket "
        "explicit.\n"
    )
    L.append("\n### Best U21 Players (age <= 21, by potential)\n")
    L.append(_category_table(
        top_players_df, "best_u21_players",
        ["rank", "player_name", "team_name", "position", "age", "overall_score", "age_potential_score"],
        ["Rank", "Player", "Team", "Position", "Age", "Overall", "Potential"],
        decimals={"overall_score": 1, "age_potential_score": 1, "age": 0},
    ))
    L.append(
        "\nA stricter age bracket than U23 - useful for identifying "
        "development-squad-eligible talent specifically, not just "
        "\"young by transfer-market standards\".\n"
    )

    # 9. Best attackers -------------------------------------------------
    L.append("## 9. Best Attackers\n")
    L.append(_category_table(
        top_players_df, "best_attackers",
        ["rank", "player_name", "team_name", "position", "age", "attacking_score"],
        ["Rank", "Player", "Team", "Position", "Age", "Attacking"],
        decimals={"attacking_score": 1, "age": 0},
    ))
    L.append(
        f"\n![Top 10 goals per 90]({FIGURES_DIR_NAME}/top10_goals_per90.png)\n\n"
        "`attacking_score` is goal output, shots on target, and finishing "
        "quality, judged against other attackers - not raw goal totals, so "
        "a striker who has played fewer minutes but finishes efficiently "
        "isn't buried under a regular starter with more minutes.\n"
    )

    # 10. Best creators -------------------------------------------------------
    L.append("## 10. Best Creators\n")
    L.append(_category_table(
        specialist_df, "best_creators",
        ["rank", "player_name", "team_name", "position", "age", "creative_score"],
        ["Rank", "Player", "Team", "Position", "Age", "Creative"],
        decimals={"creative_score": 1, "age": 0},
    ))
    L.append(
        f"\n![Top 10 assists per 90]({FIGURES_DIR_NAME}/top10_assists_per90.png)\n\n"
        "Unlike `best_midfield_creators` (position-filtered), `best_creators` "
        "is open to every position - it's a league-wide leaderboard of "
        "`creative_score` (assists, passing volume, passing quality), so a "
        "creative attacker or full-back can appear here too.\n"
    )

    # 11. Best defenders --------------------------------------------------
    L.append("## 11. Best Defenders\n")
    L.append(_category_table(
        top_players_df, "best_defenders",
        ["rank", "player_name", "team_name", "position", "age", "defensive_score"],
        ["Rank", "Player", "Team", "Position", "Age", "Defensive"],
        decimals={"defensive_score": 1, "age": 0},
    ))
    L.append(
        "\n`defensive_score` (tackles, interceptions, duel success) is "
        "judged against other defenders, so it measures 'best defender "
        "relative to defenders', not 'most tackles in the league' - see "
        "`best_duel_defenders` (Section 14) for the raw, pool-wide version "
        "of ball-winning ability.\n"
    )

    # 12. Best dribblers ---------------------------------------------------
    L.append("## 12. Best Dribblers\n")
    L.append(_category_table(
        specialist_df, "best_dribblers",
        ["rank", "player_name", "team_name", "position", "successful_dribbles_per90", "dribble_success_rate"],
        ["Rank", "Player", "Team", "Position", "Dribbles/90", "Success %"],
        decimals={"successful_dribbles_per90": 2, "dribble_success_rate": 1},
    ))
    L.append(
        f"\n![Dribbling volume vs efficiency]({FIGURES_DIR_NAME}/dribblers_scatter.png)\n\n"
        "`dribbling_score` combines volume (successful dribbles per 90) with "
        "quality (% of attempts that succeed), so a player who tries 10 to "
        "land 2 doesn't outrank one who tries 3 to land 2. The scatter above "
        "makes that trade-off visible: top-right is the rare combination of "
        "trying often *and* succeeding often.\n"
    )

    # 13. Best passers --------------------------------------------------
    L.append("## 13. Best Passers\n")
    L.append(_category_table(
        specialist_df, "best_passers",
        ["rank", "player_name", "team_name", "position", "passes_per90", "key_passes_per90", "pass_accuracy"],
        ["Rank", "Player", "Team", "Position", "Passes/90", "Key Passes/90", "Accuracy %"],
        decimals={"passes_per90": 1, "key_passes_per90": 2, "pass_accuracy": 1},
    ))
    L.append(
        f"\n![Passing: safe vs creative]({FIGURES_DIR_NAME}/passers_scatter.png)\n\n"
        "`passing_score` deliberately treats pass accuracy as only one of "
        "five equally-weighted ingredients - a centre-back playing safe "
        "five-yard passes all game can hit 95% accuracy without creating "
        "anything. The scatter separates 'safe' passers (bottom-right: high "
        "accuracy, few key passes) from genuinely creative ones (top area: "
        "passes that actually lead to a shot).\n"
    )

    # 14. Best duel defenders -----------------------------------------------
    L.append("## 14. Best Duel Defenders\n")
    L.append(_category_table(
        specialist_df, "best_duel_defenders",
        ["rank", "player_name", "team_name", "position", "tackles_per90", "interceptions_per90", "aerials_won_per90"],
        ["Rank", "Player", "Team", "Position", "Tackles/90", "Interceptions/90", "Aerials Won/90"],
        decimals={"tackles_per90": 2, "interceptions_per90": 2, "aerials_won_per90": 2},
    ))
    L.append(
        f"\n![Duel defending profile]({FIGURES_DIR_NAME}/defender_profile_scatter.png)\n\n"
        "`duel_defending_score` is pure ball-winning ability (tackles, "
        "interceptions, aerials, duel success), judged league-wide rather "
        "than only against other defenders - so a defensively strong "
        "midfielder can also show up here, which `best_defenders` "
        "(position-filtered) would miss.\n"
    )

    # 15. Best progressive midfielders --------------------------------------
    L.append("## 15. Best Progressive Midfielders\n")
    L.append(_category_table(
        specialist_df, "best_progressive_midfielders",
        ["rank", "player_name", "team_name", "age", "progressive_midfielder_score", "key_passes_per90"],
        ["Rank", "Player", "Team", "Age", "Progressive MF", "Key Passes/90"],
        decimals={"progressive_midfielder_score": 1, "key_passes_per90": 2, "age": 0},
    ))
    L.append(
        "\n**Important caveat:** SportMonks doesn't expose true 'progressive "
        "passes' or 'progressive carries into the final third' on this "
        "plan, so `progressive_midfielder_score` is a **proxy** built from "
        "what is available - key passes, long balls, successful dribbles, "
        "and assists. It's a reasonable stand-in, not the real metric elite "
        "scouting platforms use, and should be read as 'forward-thinking "
        "involvement', not literal progressive-pass counts.\n"
    )

    # 16. Best passer/ball-playing defenders --------------------------------
    L.append("## 16. Best Passer Defenders / Ball-Playing Defenders\n")
    L.append(_category_table(
        specialist_df, "best_passer_defenders",
        ["rank", "player_name", "team_name", "age", "passer_defender_score", "passes_per90", "pass_accuracy"],
        ["Rank", "Player", "Team", "Age", "Passer Defender", "Passes/90", "Accuracy %"],
        decimals={"passer_defender_score": 1, "passes_per90": 1, "pass_accuracy": 1, "age": 0},
    ))
    L.append(
        f"\n![Passer defender profile]({FIGURES_DIR_NAME}/passer_defender_scatter.png)\n\n"
        "`best_passer_defenders` and `best_ball_playing_defenders` are "
        "**the same ranking** - both are sorted by one shared "
        "`passer_defender_score` (50% within-position passing quality, 50% "
        "`defensive_score`) rather than two separate formulas, by design "
        "decision during Stage 1/2.\n\n"
        "**Position caveat:** SportMonks only exposes coarse positions here "
        "- `Defender`, `Midfielder`, `Attacker`, `Goalkeeper` - with no "
        "centre-back/full-back/wing-back split. So this ranking can say "
        "'this defender passes and defends well' but cannot separate a "
        "ball-playing centre-back from an overlapping full-back the way a "
        "platform with detailed positions could.\n"
    )

    L.append(
        "### Comparing the specialists\n\n"
        f"![Specialist score comparison]({FIGURES_DIR_NAME}/specialist_score_comparison.png)\n\n"
        "A snapshot of the five specialist scores (Sections 12-16) "
        "side by side for a handful of players pulled from the top of each "
        "category. Notice how uneven each player's bars are - that's the "
        "point of having five separate scores instead of one: a player can "
        "be a 90+ dribbler and a below-average passer at the same time, and "
        "a single blended score would hide that.\n"
    )

    # 17. Underrated players, hidden gems & small-club standouts (Stage B2) --
    L.append("## 17. Underrated Players, Hidden Gems & Small-Club Standouts\n")
    L.append(
        "Stage B2 adds team context on top of `overall_score`: "
        "`team_average_score` (a team's own mean `overall_score` among its "
        "eligible outfield players, goalkeepers excluded) and "
        "`score_above_team_average` (`overall_score - team_average_score` - "
        "a literal gap, positive means outperforming your own teammates). "
        "`underrated_score` then blends two capped bonuses onto "
        "`overall_score`:\n\n"
        "```\n"
        "underrated_score = overall_score + standout_bonus + weak_team_bonus\n"
        "```\n\n"
        "- **`standout_bonus`**: only the *positive* part of "
        "`score_above_team_average` counts (underperforming your own team "
        "isn't 'underrated'), capped before a 0.5 weight.\n"
        "- **`weak_team_bonus`**: `league_average_team_score - "
        "team_average_score`, clipped to >= 0 and capped before a 0.5 "
        "weight - `league_average_team_score` is the mean of every team's "
        "own average (one vote per team, not per player, so one big squad "
        "can't skew the baseline). This is the computed, reproducible "
        "replacement for this project's earlier fixed 'exclude the three "
        "big clubs' list.\n\n"
    )
    L.append("### Underrated Players\n")
    underrated = _find_underrated(scored_df)
    L.append(_md_table(
        underrated,
        ["player_name", "team_name", "position", "age", "overall_score",
         "standout_bonus", "weak_team_bonus", "underrated_score"],
        ["Player", "Team", "Position", "Age", "Overall", "Standout", "Weak-Team", "Underrated"],
        decimals={"overall_score": 1, "age": 0, "standout_bonus": 1,
                  "weak_team_bonus": 1, "underrated_score": 1},
    ))
    L.append(
        "\n**Important: this table can still include big-club players.** "
        "`underrated_players` only requires outperforming your *own* "
        "teammates, regardless of how strong the squad around you is - so "
        "a Dinamo Zagreb or Hajduk Split player who clearly outshines their "
        "(already strong) teammates can legitimately appear here (note "
        "several do, below). It is **not** a small-club-only list - for "
        "that, see the two stricter views below.\n"
    )
    L.append("\n### Hidden Gems\n")
    L.append(
        "Requires *both* signals at once: outperforms their own team "
        "(`standout_bonus > 0`) **and** plays for a squad below the "
        "league's average team (`weak_team_bonus > 0`). This is the "
        "stricter, small-club-focused view.\n\n"
    )
    L.append(_category_table(
        top_players_df, "hidden_gems",
        ["rank", "player_name", "team_name", "position", "age", "overall_score",
         "standout_bonus", "weak_team_bonus", "underrated_score"],
        ["Rank", "Player", "Team", "Position", "Age", "Overall", "Standout", "Weak-Team", "Underrated"],
        decimals={"overall_score": 1, "standout_bonus": 1, "weak_team_bonus": 1,
                  "underrated_score": 1, "age": 0},
        top_n=8,
    ))
    L.append("\n### Small-Club Standouts\n")
    L.append(
        "Requires only the team-context signal (`weak_team_bonus > 0`), "
        "sorted by plain `overall_score` rather than the blended score - "
        "\"who's the best individual performer at a smaller club\", "
        "regardless of the gap to their own teammates.\n\n"
    )
    L.append(_category_table(
        top_players_df, "small_club_standouts",
        ["rank", "player_name", "team_name", "position", "age", "overall_score", "weak_team_bonus"],
        ["Rank", "Player", "Team", "Position", "Age", "Overall", "Weak-Team Bonus"],
        decimals={"overall_score": 1, "weak_team_bonus": 1, "age": 0},
        top_n=8,
    ))
    L.append(
        "\nNone of these three views are a market-value or 'true team "
        "strength' model - they're reproducible statistical proxies for "
        "visibility, not scouting verdicts (see Section 24).\n"
    )

    # 18. Similarity examples (Stage B3: filters) ---------------------------
    L.append("## 18. Player Similarity Examples\n")
    L.append(
        "Stage B3 added optional filters to the similarity search - applied "
        "to *candidates* only, after cosine similarity is computed against "
        "the full eligible pool: `same_position_only` (exact position "
        "match), `same_team_exclude` (drop the query player's own club), "
        "`min_minutes` (a stricter reliability floor), and `max_age` (e.g. "
        "for 'similar young players'). The examples below show a mix of "
        "filtered and unfiltered searches.\n\n"
    )
    L.append(_similarity_section(
        similarity_df, "midfielder_example",
        f"{FIGURES_DIR_NAME}/player_similarity_midfielder_example.png",
    ))
    L.append(_similarity_section(
        similarity_df, "defender_example",
        f"{FIGURES_DIR_NAME}/player_similarity_defender_example.png",
    ))
    L.append(_similarity_section(
        similarity_df, "attacker_example",
        f"{FIGURES_DIR_NAME}/player_similarity_attacker_example.png",
    ))
    L.append(_similarity_section(similarity_df, "young_talent_example"))

    # Radar caption: names the same three players used for the similarity
    # example charts above (whichever this season's data resolved them to -
    # see ml_models.EXAMPLE_SIMILARITY_QUERIES), not a fixed prose claim
    # about which one "spikes" on which metric - that was true for the
    # original 2025/2026 examples but isn't guaranteed for a fallback pick.
    radar_slots = ["midfielder_example", "attacker_example", "defender_example"]
    radar_players = [
        similarity_df.loc[similarity_df["example_slot"] == slot, "query_player"].iloc[0]
        for slot in radar_slots
        if (similarity_df["example_slot"] == slot).any()
    ]
    L.append(
        f"![Profile comparison: {', '.join(radar_players)}]({FIGURES_DIR_NAME}/role_radar_examples.png)\n\n"
        f"The radar chart puts {len(radar_players)} query players "
        "(the same midfielder/attacker/defender examples used above) on "
        "the same five axes (attacking/creative/defensive/dribbling/"
        "passing scores). It makes each player's *shape* obvious at a "
        "glance - a specialist spikes hard on one or two axes and barely "
        "registers elsewhere, while an all-rounder stays more balanced "
        "across several dimensions - which is exactly why role-based "
        "similarity search (Section 19) matters more than a single "
        "'overall' comparison.\n"
    )

    # 19. Cosine similarity explanation --------------------------------
    L.append("## 19. How Cosine Similarity Works (in Scouting Terms)\n")
    L.append(
        "Picture each player as a list of numbers - their per-90 rates and "
        "ratios for a chosen role (e.g. for `attacker`: "
        "`[goals_per90, shots_per90, shot_accuracy, ...]`). That list is a "
        "*vector*, a point in space with one axis per stat.\n\n"
        "**Cosine similarity measures the angle between two players' "
        "vectors, not the distance.** That distinction matters: a bench "
        "player with 500 minutes and a nailed-on starter with 2500 minutes "
        "can have nearly identical *rates* (goals per 90, pass accuracy...) "
        "even though their raw totals are worlds apart. Cosine similarity "
        "says 'these two play the same way'; a raw-numbers comparison would "
        "wrongly say 'these two have nothing in common' just because one "
        "has played far more matches. A score of 1.0 means an identical "
        "statistical shape; 0 means no relationship. Every stat is "
        "standardized first (rescaled to the same spread) so a big-number "
        "stat like `passes_per90` doesn't automatically drown out a "
        "small-number stat like `goals_per90`.\n\n"
        "**Why role-based, not one universal comparison:** comparing a "
        "striker to a centre-back on `shots_per90` is meaningless - the "
        "centre-back will always look like an outlier on stats that aren't "
        "part of their job. Each role (`attacker`, `passer`, "
        "`duel_defender`, `goalkeeper`, ...) restricts the comparison to "
        "only the stats relevant to that role, so 'similar' means 'plays a "
        "similar game', not 'happens to share a few numbers by "
        "coincidence'.\n"
    )

    # 20. Replacement scouting (Stage B4) -----------------------------------
    L.append("## 20. Replacement Scouting\n")
    L.append(
        "**This is a statistical shortlist, not a final transfer "
        "recommendation.** `src/replacement_scouting.py` builds on the "
        "similarity search above: given a departing player, it re-ranks "
        "the filtered candidate pool by `replacement_score`, a weighted "
        "sum of four signals plus one small tie-breaker:\n\n"
        "```\n"
        "replacement_score = 0.4 * (similarity * 100)\n"
        "                   + 0.3 * age_potential_score\n"
        "                   + 0.2 * underrated_score\n"
        "                   + 0.1 * reliability_percentile\n"
        "                   + younger_bonus (+5 if candidate is younger than the departing player)\n"
        "```\n\n"
        "- **similarity** (highest weight) - is the candidate actually the "
        "same *kind* of player? A statistically dissimilar candidate isn't "
        "a real replacement no matter how good their other numbers are.\n"
        "- **`age_potential_score`** (Section 8) - good now, with runway to "
        "keep improving.\n"
        "- **`underrated_score`** (Section 17) - a nod toward value, not "
        "just quality.\n"
        "- **`reliability_percentile`** - minutes rank *within this "
        "specific candidate pool* (not the whole league) - the smallest "
        "weight, used only as a tie-breaker.\n\n"
        "By default, `same_position_only=True` and `same_team_exclude=True` "
        "(a replacement is normally sought at the same position, outside "
        "the player's own squad), and the role defaults to whatever "
        "matches the departing player's own position.\n\n"
        "**It says nothing about video-scouted technique, tactical fit, "
        "injury history, character, or transfer feasibility** (fee, "
        "release clause, wages, contract length) - treat it as a "
        "reproducible first-pass shortlist for a human scout to start "
        "from, not a conclusion.\n"
    )
    L.append(_replacement_section(replacement_df, "attacker_example"))
    L.append(_replacement_section(replacement_df, "midfielder_example"))
    L.append(_replacement_section(replacement_df, "defender_example"))
    L.append(_replacement_section(replacement_df, "young_talent_example"))

    # 21. Player cluster profiles (Stage B5) --------------------------------
    L.append("## 21. Player Cluster Profiles\n")
    L.append(
        "**Clustering groups players by statistical profile, not by "
        "absolute quality.** KMeans has no notion of 'good' or 'bad' - it "
        "only finds players whose per-90 rates sit close together in "
        "feature space, the same underlying idea as the cosine-similarity "
        "search (Section 19) but grouping many players instead of "
        "comparing two. An elite player and a modest one can land in the "
        "same cluster if their rates have a similar *shape* - a cluster "
        "describes a **playing style**, not a tier.\n\n"
        "Goalkeepers are clustered separately from outfield players (their "
        "near-zero outfield stats would otherwise just form one arbitrary "
        "'goalkeeper' cluster): 8 clusters for outfield players, 2 for "
        "goalkeepers. Each cluster is named by comparing its own average "
        "stats against the population average (a z-score per feature), "
        "then matching that profile against a set of predefined archetype "
        "signatures - if no archetype clears a confidence bar, the cluster "
        "keeps a neutral `balanced profile` label instead of a forced one. "
        "**Cluster names describe playing style, not literal position** - "
        "clustering never looks at the `position` column, so an archetype "
        "like 'ball-playing defenders' only keeps that name if the cluster "
        "is actually made up mostly of defenders; otherwise it falls back "
        "to a neutral statistical name (e.g. 'defensive distributors') "
        "instead of a forced position claim.\n\n"
        f"**Full per-cluster profiles** (player count, average age/minutes, "
        f"a plain-English playing-style description, and top players) are "
        f"in [`{CLUSTER_PROFILES_REPORT_FILE}`]({CLUSTER_PROFILES_REPORT_FILE}) - "
        f"summary below:\n"
    )
    L.append(_cluster_summary_table(clusters_df))
    L.append("")

    # 22. Additional charts ------------------------------------------------
    L.append("## 22. Additional Charts\n")
    L.append(
        f"![Age vs overall score]({FIGURES_DIR_NAME}/age_vs_overall_score.png)\n\n"
        "Every eligible **outfield** player's age against their "
        "`overall_score` (goalkeepers excluded, per Section 6), with U23 "
        "players highlighted and the top 5 labeled. Useful for spotting "
        "whether a young player's output is part of a broader pattern of "
        "emerging talent or a standalone outlier.\n"
    )
    L.append(
        f"![Minutes vs overall score]({FIGURES_DIR_NAME}/minutes_vs_overall_score.png)\n\n"
        "`overall_score` against minutes played, with the 450-minute "
        "eligibility floor marked. All points clear that floor by "
        "definition (lower-minute players are excluded from scoring "
        "entirely, per Section 4), but the spread still shows that scores "
        "near the floor are based on a much smaller sample than scores from "
        "players who played most of the season - worth weighing when "
        "comparing two similar scores.\n"
    )
    L.append(
        f"![Overall score distribution by position]({FIGURES_DIR_NAME}/position_score_distribution.png)\n\n"
        "This is the chart that explains *why* position-aware scoring "
        "(Section 6) was worth adding, and why goalkeepers were removed "
        "from outfield rankings entirely: before Stage 1, `attacking_score` "
        "/ `creative_score` / `defensive_score` were percentile ranks "
        "against the *whole* player pool, so a position with a naturally "
        "different stat profile would cluster at one extreme regardless of "
        "who the best player at that position actually was. Ranking within "
        "each position group fixed that for outfielders - but goalkeepers "
        "still show an oddly narrow, high-floor `overall_score` spread here "
        "even with position-aware scoring, because the underlying stats "
        "(goals, tackles, passing volume) barely apply to their job. That's "
        "the concrete evidence behind excluding them into their own "
        "`goalkeeper_score` model instead.\n"
    )
    L.append(
        f"![Team talent map]({FIGURES_DIR_NAME}/team_talent_map.png)\n\n"
        "Average `overall_score` among eligible **outfield** players "
        "(450+ minutes, goalkeepers excluded) per "
        "club, with the eligible squad size shown in parentheses. This is a "
        "rough proxy for squad strength/depth, not a form table - it says "
        "nothing about results, only about individual statistical output. "
        "It's also the same data `team_average_score` (Section 17) is "
        "built from, per club.\n"
    )

    # 23. Methodology summary ------------------------------------------------
    L.append("## 23. Methodology Summary\n")
    L.append(
        "A quick-reference recap of every formula introduced since the "
        "original pipeline - each is explained in full where it's first "
        "used above; this section just collects them in one place.\n\n"
        "**Percentile scores (original pipeline)** - `attacking_score`, "
        "`creative_score`, `defensive_score`, `dribbling_score`, "
        "`passing_score`, `duel_defending_score`, "
        "`progressive_midfielder_score`, `passer_defender_score`, "
        "`goalkeeper_score`: each is an average of percentile ranks (0-100) "
        "on a handful of per-90/ratio stats, so raw scales never distort "
        "the blend. `overall_score = 0.3*attacking + 0.3*creative + "
        "0.3*defensive + 0.1*discipline` (Section 6).\n\n"
        "**`age_potential_score` (Section 8)** - "
        "`overall_score + age_bonus + reliability_bonus`. `age_bonus` = "
        "+2.0/year younger than 23, capped at +12 (6 years). "
        "`reliability_bonus` = percentile rank of minutes, capped at +8.\n\n"
        "**`underrated_score` (Section 17)** - "
        "`overall_score + standout_bonus + weak_team_bonus`. "
        "`standout_bonus` = the positive part of `overall_score - "
        "team_average_score`, capped, at 0.5 weight. `weak_team_bonus` = "
        "the positive part of `league_average_team_score - "
        "team_average_score`, capped, at 0.5 weight. `hidden_gems` "
        "requires both bonuses > 0; `small_club_standouts` requires only "
        "`weak_team_bonus` > 0 and sorts by raw `overall_score`.\n\n"
        "**Similarity search filters (Section 18)** - `same_position_only`, "
        "`same_team_exclude`, `min_minutes`, `max_age`: applied to "
        "candidates only, *after* cosine similarity is computed against "
        "the full pool, so filtering never changes what 'similar' means "
        "for the players who qualify.\n\n"
        "**`replacement_score` (Section 20)** - "
        "`0.4*(similarity*100) + 0.3*age_potential_score + "
        "0.2*underrated_score + 0.1*reliability_percentile + "
        "younger_bonus`. `reliability_percentile` is computed *within the "
        "candidate pool for that specific search*, not the whole league. "
        "`younger_bonus` is a flat +5, not a percentage weight.\n\n"
        "**Player clustering (Section 21)** - KMeans on per-90/ratio "
        "features (outfield and goalkeepers clustered separately). Cluster "
        "names come from comparing each cluster's own feature averages "
        "against the population average (a z-score per feature), matched "
        "against predefined archetype signatures; unmatched clusters "
        "(below a 0.5 confidence bar) get a neutral `balanced profile` "
        "label, and position-implying names are demoted to a neutral "
        "alternative unless that position is an outright majority of the "
        "cluster.\n"
    )

    # 24. Limitations -----------------------------------------------------
    L.append("## 24. Limitations\n")
    L.append(
        "- **Goalkeepers are excluded from general outfield rankings "
        "because they require a separate goalkeeper-specific model.** "
        "`goalkeeper_score` (Section 7) covers saves, clean sheets, goals "
        "conceded, and penalties saved, but it's a simple percentile model "
        "over a small population (17-23 keepers) - not a substitute for a "
        "dedicated shot-stopping model (e.g. post-shot xG).\n"
        "- **Coarse positions only.** SportMonks exposes just `Defender` / "
        "`Midfielder` / `Attacker` / `Goalkeeper` here, with no detailed "
        "sub-position (centre-back vs. full-back vs. wing-back). Anywhere "
        "this report says 'defender', it means all of those at once.\n"
        "- **No true progressive passes/carries or expected assists (xA).** "
        "`progressive_midfielder_score` is a proxy built from key passes, "
        "long balls, dribbles, and assists - useful, but not the same "
        "metric a platform with tracking data would compute.\n"
        "- **`overall_score` can still favor all-rounders over pure "
        "specialists**, even after making its three ingredients "
        "position-aware, because it averages across attacking/creative/"
        "defensive contribution. A player who is elite at exactly one thing "
        "and does nothing else will usually rank higher on a role-specific "
        "score (Sections 9-16) than on `overall_score`.\n"
        "- **`age_potential_score`, `underrated_score`, and "
        "`replacement_score` are explainable proxies, not ground truth.** "
        "They combine already-approximate scores with simple, capped "
        "bonuses - useful for a reproducible first-pass shortlist, not a "
        "substitute for scouting judgment on potential, morale, injury "
        "history, or genuine market value.\n"
        "- **`underrated_score`/`hidden_gems`/`small_club_standouts` are "
        "team-context proxies, not a market-value or true-team-strength "
        "model.** `team_average_score` only reflects this season's "
        "statistical output of a team's *eligible outfield* players - it "
        "says nothing about squad budget, wage bill, or league position.\n"
        "- **Similarity search and replacement scouting do not replace "
        "video scouting.** They surface statistically comparable players "
        "as a first-pass shortlist; a human scout still has to watch the "
        "games. `replacement_score` in particular says nothing about "
        "transfer feasibility (fee, release clause, wages, contract "
        "length).\n"
        "- **Player clusters describe playing style, not quality or "
        "literal position.** An elite and a modest player can share a "
        "cluster if their per-90 rates have a similar shape; a cluster's "
        "archetype name is demoted to a neutral one if the cluster's "
        "actual position makeup doesn't back up a position-specific claim "
        "(Section 21).\n"
        "- **Role-specific rankings are better for scouting than one "
        "global ranking.** `best_overall`/`best_u23` are a reasonable "
        "'who's good in general' view, but the specialist rankings "
        "(dribblers, passers, duel defenders, progressive midfielders, "
        "passer/ball-playing defenders, creators, ball winners, and their "
        "U23 versions) answer much more specific scouting questions and "
        "should usually be preferred over the single overall list.\n"
        "- **This model ranks and compares statistical output - it does "
        "not evaluate talent, tactical fit, or injury/character risk.** "
        "It's a strong first-pass scouting/shortlisting tool, not a "
        "replacement for video scouting or human judgment.\n"
        "- **A `�` character in a player's name (e.g. in a terminal) is a "
        "Windows console display quirk, not a data bug** - the underlying "
        "CSVs are correctly UTF-8 encoded (verified at the byte level); "
        "names like `Varaždin` and `Mejía` are stored correctly.\n"
    )

    # 25. Next improvements -------------------------------------------------
    L.append("## 25. Next Improvements\n")
    L.append(
        "- **Better position groups if SportMonks exposes detailed "
        "positions** for this competition/plan - would let "
        "`best_passer_defenders` distinguish centre-backs from full-backs, "
        "and would sharpen every position-aware score and cluster archetype.\n"
        "- **Add real market value** as an extra lens alongside "
        "`underrated_score`, so 'underrated relative to teammates' can be "
        "checked against 'underrated relative to actual transfer value'.\n"
        "- **Improve formulas with more seasons of history** - a single "
        "HNL season limits how much the scores and the optional rating/"
        "goals prediction models can be trusted; multiple seasons would "
        "support more robust percentile baselines, more stable cluster "
        "archetypes, and a meaningful supervised model.\n"
        "- **Compare HNL players against other leagues** - all scores here "
        "are relative to the HNL player pool only, so a HNL-wide top score "
        "says nothing about how that player would rank in a stronger "
        "league; cross-league benchmarking would need a shared statistical "
        "baseline across competitions.\n"
        "- **Refine cluster archetype signatures with feedback** - the "
        "z-score signature thresholds (Section 21) are a first pass; "
        "reviewing a season's worth of cluster assignments against known "
        "player profiles would help tune which features best separate "
        "each archetype.\n"
        "- **A Streamlit dashboard** (planned, not yet built) - filters by "
        "team/age/position/minutes, a player profile view, specialist "
        "rankings, similarity search, replacement scouting, cluster "
        "profiles, charts, and an in-app report viewer.\n"
    )

    return "\n".join(L) + "\n"


def run():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    required = {
        "scored": SCORED_CSV_PATH,
        "top players": TOP_PLAYERS_CSV_PATH,
        "specialist rankings": SPECIALIST_CSV_PATH,
        "similarity results": SIMILARITY_CSV_PATH,
        "replacement targets": REPLACEMENT_CSV_PATH,
        "player clusters": CLUSTERS_CSV_PATH,
    }
    for label, path in required.items():
        if not os.path.exists(path):
            raise FileNotFoundError(f"{path} ({label}) not found. Run the earlier pipeline stages first.")

    scored_df = pd.read_csv(SCORED_CSV_PATH)
    top_players_df = pd.read_csv(TOP_PLAYERS_CSV_PATH)
    specialist_df = pd.read_csv(SPECIALIST_CSV_PATH)
    similarity_df = pd.read_csv(SIMILARITY_CSV_PATH)
    replacement_df = pd.read_csv(REPLACEMENT_CSV_PATH)
    clusters_df = pd.read_csv(CLUSTERS_CSV_PATH)

    raw_rows = clean_data.get_raw_row_count()
    deduped_rows = len(pd.read_csv(CLEAN_CSV_PATH))

    report = build_report(
        scored_df, top_players_df, specialist_df, similarity_df, replacement_df, clusters_df,
        raw_rows, deduped_rows,
    )

    os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write(report)
    logger.info("Saved scouting report to %s", REPORT_PATH)
    return report


if __name__ == "__main__":
    run()
