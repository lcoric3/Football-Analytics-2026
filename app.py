"""
Streamlit dashboard for the HNL scouting project - supports HNL 2025/2026,
HNL 2024/2025, and the 2024/2025 -> 2025/2026 multi-season player
development comparison, switchable at runtime via the sidebar "Season"
selector (see main()).

Read-only view over files the pipeline (`python main.py`, run once per
season) and `src/player_development.py` already produced - this file never
calls the SportMonks API and never writes or recomputes any data file. It
only reads CSVs from data/processed/ and data/output/, charts from
reports/figures_<season>/, and the Markdown reports in reports/.

Because the season selector switches seasons at runtime (not via the
HNL_OUTPUT_SUFFIX environment variable, which is fixed for the lifetime of
this process), every path below is built by passing an explicit `suffix`
to season_config's helpers rather than relying on their env-derived
defaults.

Run with:
    streamlit run app.py
"""
import os

import pandas as pd
import plotly.express as px
import streamlit as st

from src import ml_models
from src import player_development
from src import replacement_scouting
from src import season_config
from src.scouting_scores import MIN_MINUTES_FOR_SCORES

st.set_page_config(page_title="HNL Scouting Dashboard", layout="wide")

# suffix -> display label, in the order shown in the season selector.
SEASON_LABELS = {"2025_2026": "2025/2026", "2024_2025": "2024/2025"}
SUFFIX_BY_LABEL = {label: suffix for suffix, label in SEASON_LABELS.items()}
MULTI_SEASON_LABEL = "Multi-season development"

# Player profile page: example similarity chart saved for a handful of
# players by visualization.py - shown as a bonus if the searched player
# happens to be one of them. Keyed by the season-agnostic example_slot
# (see ml_models.EXAMPLE_SIMILARITY_QUERIES) - the *player* filling each
# slot can differ between seasons, so this is resolved per-season from the
# similarity CSV in _example_chart_for_player rather than a fixed
# name -> filename mapping.
SIMILARITY_EXAMPLE_SLOTS = {
    "midfielder_example": "player_similarity_midfielder_example.png",
    "attacker_example": "player_similarity_attacker_example.png",
    "defender_example": "player_similarity_defender_example.png",
}


@st.cache_data
def load_csv(path):
    """Reads a CSV if it exists, otherwise returns None so callers can show
    a friendly error instead of a stack trace."""
    if not os.path.exists(path):
        return None
    return pd.read_csv(path)


def _ranked_bar_chart(df, value_col, title, label_col="player_name", color_col=None):
    """Horizontal bar chart for an already-ranked (best/most-extreme-first)
    dataframe. Plotly draws horizontal bars bottom-up, so the input needs
    reversing first - otherwise rank #1 would render at the bottom."""
    if df.empty:
        return
    chart_df = df.iloc[::-1]
    fig = px.bar(
        chart_df, x=value_col, y=label_col, orientation="h",
        color=color_col, title=title,
    )
    fig.update_layout(yaxis_title="", xaxis_title=value_col)
    st.plotly_chart(fig, width="stretch")


def missing_file_error(path):
    st.error(
        f"**Missing file:** `{path}`\n\n"
        "Run the pipeline first to generate it:\n\n"
        "```powershell\npython main.py\n```"
    )


def ranking_categories(suffix):
    """Rankings page: dashboard label -> (source CSV, category value in
    that CSV) - rebuilt per season since the CSV paths are season-suffixed."""
    top_players_csv = season_config.output_path("top_players_hnl", suffix=suffix)
    specialist_csv = season_config.output_path("specialist_rankings_hnl", suffix=suffix)
    return {
        "Top overall outfield players": (top_players_csv, "best_overall"),
        "Best U23 / young talents": (top_players_csv, "best_young_talents"),
        "Best attackers": (top_players_csv, "best_attackers"),
        "Best creators": (specialist_csv, "best_creators"),
        "Best defenders": (top_players_csv, "best_defenders"),
        "Best dribblers": (specialist_csv, "best_dribblers"),
        "Best passers": (specialist_csv, "best_passers"),
        "Best progressive midfielders": (specialist_csv, "best_progressive_midfielders"),
        "Best passer defenders": (specialist_csv, "best_passer_defenders"),
        "Best goalkeepers": (top_players_csv, "best_goalkeepers"),
    }


def _example_chart_for_player(suffix, player_name):
    """If `player_name` is this season's query player for one of the three
    similarity example slots (see ml_models.EXAMPLE_SIMILARITY_QUERIES),
    returns that chart's filename - otherwise None. Data-driven per season
    (reads the similarity CSV) rather than a fixed player list, since the
    actual query player for each slot can be a data-driven fallback
    (ml_models.resolve_example_player) and therefore differ between
    seasons."""
    similarity_path = season_config.output_path("player_similarity_results", suffix=suffix)
    similarity_df = load_csv(similarity_path)
    if similarity_df is None or "example_slot" not in similarity_df.columns:
        return None
    for slot, filename in SIMILARITY_EXAMPLE_SLOTS.items():
        match = similarity_df[
            (similarity_df["example_slot"] == slot) & (similarity_df["query_player"] == player_name)
        ]
        if not match.empty:
            return filename
    return None


def render_overview(suffix):
    season_name = SEASON_LABELS[suffix]
    st.title(f"HNL {season_name} Scouting Dashboard")
    st.markdown(
        "A read-only view over the Football-Analytics-2026 scouting pipeline: "
        "`SportMonks API -> raw data -> cleaned data -> feature engineering -> "
        "scouting scores -> rankings -> visualizations -> ML dataset`. "
        "This dashboard never calls the SportMonks API and never writes or "
        "recomputes any data - it only reads the CSVs, charts, and reports "
        "the pipeline already produced."
    )

    scored_path = season_config.processed_path("hnl_player_scored", suffix=suffix)
    scored_df = load_csv(scored_path)
    if scored_df is None:
        missing_file_error(scored_path)
        return

    eligible = scored_df[scored_df["minutes"] >= MIN_MINUTES_FOR_SCORES]

    col1, col2, col3 = st.columns(3)
    col1.metric("Players", len(scored_df))
    col2.metric("Teams", scored_df["team_name"].nunique())
    col3.metric(f"Eligible players (>={MIN_MINUTES_FOR_SCORES} min)", len(eligible))

    st.subheader("Score distribution by position")
    if not eligible.empty:
        fig_box = px.box(
            eligible, x="position", y="overall_score", points="outliers",
            title=f"overall_score distribution by position ({MIN_MINUTES_FOR_SCORES}+ minutes)",
        )
        fig_box.update_layout(xaxis_title="", yaxis_title="overall_score")
        st.plotly_chart(fig_box, width="stretch")

    st.subheader("Full scouting report")
    report_path = season_config.scouting_report_path(suffix=suffix)
    if os.path.exists(report_path):
        with st.expander("Open the full Markdown scouting report"):
            with open(report_path, encoding="utf-8") as f:
                st.markdown(f.read())
    else:
        missing_file_error(report_path)


def render_rankings(suffix):
    st.title("Player Rankings")
    categories = ranking_categories(suffix)
    label = st.selectbox("Category", list(categories))
    path, category = categories[label]

    df = load_csv(path)
    if df is None:
        missing_file_error(path)
        return

    subset = df[df["category"] == category].sort_values("rank")
    if subset.empty:
        st.warning(f"No rows found for category `{category}`.")
        return
    st.dataframe(subset.drop(columns=["category"]), hide_index=True, width="stretch")


def render_player_profile(suffix):
    st.title("Player Search / Profile")

    scored_path = season_config.processed_path("hnl_player_scored", suffix=suffix)
    scored_df = load_csv(scored_path)
    if scored_df is None:
        missing_file_error(scored_path)
        return

    query = st.text_input("Search player name")
    if not query:
        st.info("Type a player name to search.")
        return

    matches = scored_df[scored_df["player_name"].str.contains(query, case=False, na=False)]
    if matches.empty:
        st.warning(f"No players found matching '{query}'.")
        return

    player_name = st.selectbox("Select player", sorted(matches["player_name"].unique()))
    row = scored_df[scored_df["player_name"] == player_name].iloc[0]

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Age", f"{row['age']:.0f}" if pd.notna(row["age"]) else "n/a")
    col2.metric("Team", row["team_name"])
    col3.metric("Position", row["position"])
    col4.metric("Minutes", f"{row['minutes']:.0f}" if pd.notna(row["minutes"]) else "n/a")

    st.subheader("Scouting scores")
    score_cols = [
        "attacking_score", "creative_score", "defensive_score", "discipline_score",
        "overall_score", "dribbling_score", "passing_score", "duel_defending_score",
        "progressive_midfielder_score", "passer_defender_score", "goalkeeper_score",
        "age_potential_score", "underrated_score",
    ]
    scores = {c: row[c] for c in score_cols if pd.notna(row.get(c))}
    if scores:
        st.dataframe(pd.DataFrame([scores]), hide_index=True, width="stretch")
    else:
        st.info(
            f"No scores available - this player is likely below the "
            f"{MIN_MINUTES_FOR_SCORES}-minute eligibility threshold."
        )

    st.subheader("Key per-90 stats")
    per90_cols = [
        "goals_per90", "assists_per90", "shots_per90", "shots_on_target_per90",
        "passes_per90", "tackles_per90", "interceptions_per90", "cards_per90",
        "successful_dribbles_per90", "key_passes_per90",
    ]
    per90 = {c: row[c] for c in per90_cols if pd.notna(row.get(c))}
    if per90:
        st.dataframe(pd.DataFrame([per90]), hide_index=True, width="stretch")

    chart_file = _example_chart_for_player(suffix, player_name)
    if chart_file:
        chart_path = os.path.join(season_config.figures_dir(suffix), chart_file)
        if os.path.exists(chart_path):
            st.subheader("Similarity chart (example)")
            st.image(chart_path)


def render_similarity_search(suffix):
    st.title("Similarity Search")

    ml_features_path = season_config.processed_path("hnl_ml_features", suffix=suffix)
    ml_df = load_csv(ml_features_path)
    if ml_df is None:
        missing_file_error(ml_features_path)
        return

    player_name = st.selectbox("Player", sorted(ml_df["player_name"].unique()))
    roles = sorted(ml_models.ROLE_FEATURE_SETS)
    role = st.selectbox("Role", roles, index=roles.index("overall"))

    col1, col2 = st.columns(2)
    same_position_only = col1.checkbox("Same position only", value=False)
    same_team_exclude = col2.checkbox("Exclude same team", value=False)
    min_minutes = st.number_input("Minimum minutes", min_value=0, value=0, step=50)
    max_age = st.number_input("Maximum age", min_value=0, value=0, step=1, help="0 = no age limit")
    top_n = st.slider("Number of results", 5, 25, 10)

    try:
        results = ml_models.find_similar_players(
            ml_df, player_name, role=role, top_n=top_n,
            same_position_only=same_position_only,
            same_team_exclude=same_team_exclude,
            min_minutes=min_minutes or None,
            max_age=max_age or None,
        )
    except ValueError as exc:
        st.warning(str(exc))
        return

    if results.empty:
        st.warning("No similar players found with these filters.")
        return
    st.dataframe(results, hide_index=True, width="stretch")


def render_replacement_scouting(suffix):
    st.title("Replacement Scouting")

    ml_features_path = season_config.processed_path("hnl_ml_features", suffix=suffix)
    ml_df = load_csv(ml_features_path)
    if ml_df is None:
        missing_file_error(ml_features_path)
        return

    with st.expander("What is replacement_score?"):
        st.markdown(
            "A statistical shortlist, **not** a transfer recommendation:\n\n"
            "```\n"
            "replacement_score = 0.4 * (similarity * 100)\n"
            "                   + 0.3 * age_potential_score\n"
            "                   + 0.2 * underrated_score\n"
            "                   + 0.1 * reliability_percentile\n"
            "                   + younger_bonus (+5 if candidate is younger)\n"
            "```\n"
            "- **similarity** - is the candidate actually the same *kind* of player?\n"
            "- **age_potential_score** - good now, with runway to keep improving.\n"
            "- **underrated_score** - a nod toward value, not just quality.\n"
            "- **reliability_percentile** - minutes rank within this candidate pool only.\n\n"
            "See `src/replacement_scouting.py` for the full reasoning and caveats."
        )

    player_name = st.selectbox("Departing player", sorted(ml_df["player_name"].unique()))

    col1, col2 = st.columns(2)
    same_position_only = col1.checkbox("Same position only", value=True)
    same_team_exclude = col2.checkbox("Exclude same team", value=True)
    min_minutes = st.number_input("Minimum minutes", min_value=0, value=0, step=50, key="repl_min_minutes")
    max_age = st.number_input(
        "Maximum age", min_value=0, value=0, step=1, help="0 = no age limit", key="repl_max_age"
    )
    top_n = st.slider("Number of results", 5, 25, 10, key="repl_top_n")

    try:
        results = replacement_scouting.find_replacement_targets(
            ml_df, player_name, top_n=top_n,
            same_position_only=same_position_only,
            same_team_exclude=same_team_exclude,
            min_minutes=min_minutes or None,
            max_age=max_age or None,
        )
    except ValueError as exc:
        st.warning(str(exc))
        return

    if results.empty:
        st.warning("No replacement targets found with these filters.")
        return
    st.dataframe(results, hide_index=True, width="stretch")


def render_hidden_gems(suffix):
    st.title("Hidden Gems")

    top_players_path = season_config.output_path("top_players_hnl", suffix=suffix)
    top_players_df = load_csv(top_players_path)
    if top_players_df is None:
        missing_file_error(top_players_path)
        return

    st.markdown(
        "Team-context scoring on top of `overall_score`: **underrated players** only "
        "requires outperforming your own teammates (can still include big-club "
        "players); **hidden gems** requires both outperforming your team *and* "
        "playing for a squad below the league's average team; **small club "
        "standouts** requires only the second condition, sorted by plain "
        "`overall_score`."
    )

    tabs = st.tabs(["Underrated players", "Hidden gems", "Small club standouts"])
    categories = ["underrated_players", "hidden_gems", "small_club_standouts"]
    for tab, category in zip(tabs, categories):
        with tab:
            subset = top_players_df[top_players_df["category"] == category].sort_values("rank")
            if subset.empty:
                st.warning(f"No rows found for category `{category}`.")
            else:
                st.dataframe(subset.drop(columns=["category"]), hide_index=True, width="stretch")


def render_clusters(suffix):
    st.title("Player Clusters")

    clusters_path = season_config.output_path("player_clusters", suffix=suffix)
    clusters_df = load_csv(clusters_path)
    if clusters_df is None:
        missing_file_error(clusters_path)
        return

    st.markdown(
        "KMeans groups players by *statistical shape*, not quality - a cluster "
        "describes a playing style, not a tier. An elite and a modest player can "
        "share a cluster if their per-90 rates have a similar shape."
    )

    cluster_summary = (
        clusters_df.groupby(["cluster_id", "cluster_name"])
        .size()
        .reset_index(name="players")
        .sort_values("cluster_id")
    )
    st.dataframe(cluster_summary, hide_index=True, width="stretch")

    cluster_options = sorted(clusters_df["cluster_name"].dropna().unique())
    selected = st.selectbox("Show players in cluster", cluster_options)
    subset = clusters_df[clusters_df["cluster_name"] == selected].sort_values(
        "quality_score", ascending=False
    )
    st.dataframe(subset, hide_index=True, width="stretch")

    cluster_profiles_path = season_config.cluster_profiles_report_path(suffix=suffix)
    if os.path.exists(cluster_profiles_path):
        with st.expander("Full cluster profiles report (plain-English style descriptions)"):
            with open(cluster_profiles_path, encoding="utf-8") as f:
                st.markdown(f.read())
    else:
        st.info(f"Cluster profiles report not found at `{cluster_profiles_path}`.")


def render_charts_report(suffix):
    st.title("Charts & Report")

    figures_dir = season_config.figures_dir(suffix)
    if not os.path.isdir(figures_dir):
        st.error(f"**Missing folder:** `{figures_dir}`. Run `python main.py` to generate charts.")
    else:
        chart_files = sorted(f for f in os.listdir(figures_dir) if f.lower().endswith(".png"))
        if not chart_files:
            st.warning(f"No charts found in `{figures_dir}`.")
        else:
            cols = st.columns(2)
            for i, chart_file in enumerate(chart_files):
                with cols[i % 2]:
                    st.image(os.path.join(figures_dir, chart_file), caption=chart_file)

    st.divider()
    st.subheader("Full scouting report")
    report_path = season_config.scouting_report_path(suffix=suffix)
    if os.path.exists(report_path):
        with st.expander("Open the full Markdown scouting report", expanded=False):
            with open(report_path, encoding="utf-8") as f:
                st.markdown(f.read())
    else:
        missing_file_error(report_path)


def _development_metric(row, column, decimals=None):
    value = row.get(column)
    if pd.isna(value):
        return "n/a"
    return f"{value:.{decimals}f}" if decimals is not None else str(value)


def render_player_development():
    base_suffix = player_development.BASE_SEASON_SUFFIX
    target_suffix = player_development.TARGET_SEASON_SUFFIX
    base_label = player_development.BASE_SEASON_NAME
    target_label = player_development.TARGET_SEASON_NAME

    st.title(f"Player Development ({base_label} -> {target_label})")
    st.markdown(
        "Players matched by `player_id` across both seasons - scores are "
        "**season-relative, not an absolute rating** (see the full report "
        "below for methodology and limitations)."
    )

    dev_df = load_csv(player_development.DEVELOPMENT_OUTPUT_CSV_PATH)
    if dev_df is None:
        missing_file_error(player_development.DEVELOPMENT_OUTPUT_CSV_PATH)
        return

    matched = len(dev_df)
    team_changes = int(dev_df["changed_team"].sum()) if "changed_team" in dev_df.columns else 0
    improved = int(dev_df["improved_overall"].sum()) if "improved_overall" in dev_df.columns else 0
    declined = (
        int((dev_df["overall_score_change"] < 0).sum())
        if "overall_score_change" in dev_df.columns else 0
    )

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Players matched", matched)
    col2.metric("Changed team", team_changes)
    col3.metric(f"Improved in {target_label}", improved)
    col4.metric(f"Declined in {target_label}", declined)

    tabs = st.tabs([
        "Biggest improvers", "Biggest decliners", "Young improvers",
        "Changed-team improvers", "Hidden gems who improved", "Player search",
    ])

    with tabs[0]:
        biggest_improvers = player_development.rank_biggest_improvers(dev_df, top_n=20)
        _ranked_bar_chart(
            biggest_improvers, "overall_score_change",
            f"Biggest improvers: overall_score change ({base_label} -> {target_label})",
        )
        st.dataframe(biggest_improvers, hide_index=True, width="stretch")

    with tabs[1]:
        biggest_decliners = player_development.rank_biggest_decliners(dev_df, top_n=20)
        _ranked_bar_chart(
            biggest_decliners, "overall_score_change",
            f"Biggest decliners: overall_score change ({base_label} -> {target_label})",
        )
        st.dataframe(biggest_decliners, hide_index=True, width="stretch")

    with tabs[2]:
        young_improvers = player_development.rank_young_improvers(dev_df, top_n=20)
        if young_improvers.empty:
            st.warning("No young improvers found.")
        else:
            _ranked_bar_chart(
                young_improvers, "overall_score_change",
                f"Young improvers (age <= {player_development.U23_AGE_LIMIT}): overall_score change",
            )
            st.dataframe(young_improvers, hide_index=True, width="stretch")

    with tabs[3]:
        changed_team_improvers = player_development.rank_changed_team_improvers(dev_df, top_n=20)
        if changed_team_improvers.empty:
            st.warning("No changed-team improvers found.")
        else:
            _ranked_bar_chart(
                changed_team_improvers, "overall_score_change",
                "Improved after changing team: overall_score change",
            )
            st.dataframe(changed_team_improvers, hide_index=True, width="stretch")

    with tabs[4]:
        hidden_gem_ids = player_development.load_hidden_gem_ids(base_suffix)
        hidden_gems_improved = player_development.rank_hidden_gems_who_improved(
            dev_df, hidden_gem_ids, top_n=20,
        )
        if hidden_gems_improved.empty:
            st.warning("No hidden gems from last season also improved this season.")
        else:
            st.dataframe(hidden_gems_improved, hide_index=True, width="stretch")

    with tabs[5]:
        query = st.text_input("Search player name", key="dev_query")
        if not query:
            st.info("Type a player name to search.")
        else:
            matches = dev_df[dev_df["player_name"].str.contains(query, case=False, na=False)]
            if matches.empty:
                st.warning(f"No players found matching '{query}'.")
            else:
                player_name = st.selectbox("Select player", sorted(matches["player_name"].unique()))
                row = dev_df[dev_df["player_name"] == player_name].iloc[0]

                col_a, col_b = st.columns(2)
                with col_a:
                    st.markdown(f"**HNL {base_label}**")
                    st.metric("Team", _development_metric(row, f"team_{base_suffix}"))
                    st.metric("Position", _development_metric(row, f"position_{base_suffix}"))
                    st.metric("Age", _development_metric(row, f"age_{base_suffix}", decimals=0))
                    st.metric("Minutes", _development_metric(row, f"minutes_{base_suffix}", decimals=0))
                    st.metric("Overall score", _development_metric(row, f"overall_score_{base_suffix}", decimals=1))
                with col_b:
                    st.markdown(f"**HNL {target_label}**")
                    st.metric("Team", _development_metric(row, f"team_{target_suffix}"))
                    st.metric("Position", _development_metric(row, f"position_{target_suffix}"))
                    st.metric("Age", _development_metric(row, f"age_{target_suffix}", decimals=0))
                    st.metric("Minutes", _development_metric(row, f"minutes_{target_suffix}", decimals=0))
                    st.metric("Overall score", _development_metric(row, f"overall_score_{target_suffix}", decimals=1))

                overall_base_col = f"overall_score_{base_suffix}"
                overall_target_col = f"overall_score_{target_suffix}"
                if pd.notna(row.get(overall_base_col)) and pd.notna(row.get(overall_target_col)):
                    st.subheader("Overall score: season comparison")
                    overall_compare = pd.DataFrame({
                        "season": [base_label, target_label],
                        "overall_score": [row[overall_base_col], row[overall_target_col]],
                    })
                    fig_overall = px.bar(
                        overall_compare, x="season", y="overall_score",
                        title=f"{player_name}: overall_score by season",
                    )
                    fig_overall.update_layout(xaxis_title="")
                    st.plotly_chart(fig_overall, width="stretch")

                st.subheader("Score changes")
                change_cols = [c for c in dev_df.columns if c.endswith("_change")]
                changes = {c: row[c] for c in change_cols if pd.notna(row.get(c))}
                if changes:
                    st.dataframe(pd.DataFrame([changes]), hide_index=True, width="stretch")

                score_change_cols = [c for c in change_cols if c.endswith("_score_change")]
                score_changes = {c: row[c] for c in score_change_cols if pd.notna(row.get(c))}
                if score_changes:
                    change_chart_df = pd.DataFrame({
                        "metric": [c[: -len("_score_change")].replace("_", " ") for c in score_changes],
                        "change": list(score_changes.values()),
                    }).sort_values("change")
                    fig_changes = px.bar(
                        change_chart_df, x="change", y="metric", orientation="h",
                        color="change", color_continuous_scale="RdYlGn",
                        title=f"{player_name}: score changes by category ({base_label} -> {target_label})",
                    )
                    fig_changes.update_layout(yaxis_title="", coloraxis_showscale=False)
                    st.plotly_chart(fig_changes, width="stretch")

                st.subheader("Flags")
                flag_cols = [
                    "changed_team", "same_position", "minutes_increased",
                    "young_player", "improved_overall", "improved_specialist_score",
                ]
                flags = {c: row[c] for c in flag_cols if c in dev_df.columns}
                if flags:
                    st.dataframe(pd.DataFrame([flags]), hide_index=True, width="stretch")

    st.divider()
    st.subheader("Trends across all matched players")
    age_col = f"age_{target_suffix}"
    hover_cols = [c for c in [f"team_{target_suffix}", f"position_{target_suffix}"] if c in dev_df.columns]
    trend_col1, trend_col2 = st.columns(2)
    with trend_col1:
        if age_col in dev_df.columns and "overall_score_change" in dev_df.columns:
            fig_age = px.scatter(
                dev_df, x=age_col, y="overall_score_change", hover_data=["player_name"] + hover_cols,
                title=f"Age ({target_label}) vs overall_score change",
            )
            st.plotly_chart(fig_age, width="stretch")
    with trend_col2:
        if "minutes_change" in dev_df.columns and "overall_score_change" in dev_df.columns:
            fig_minutes = px.scatter(
                dev_df, x="minutes_change", y="overall_score_change", hover_data=["player_name"] + hover_cols,
                title="Minutes change vs overall_score change",
            )
            st.plotly_chart(fig_minutes, width="stretch")

    st.divider()
    st.subheader("Full multi-season development report")
    if os.path.exists(player_development.DEVELOPMENT_REPORT_PATH):
        with st.expander("Open the full report"):
            with open(player_development.DEVELOPMENT_REPORT_PATH, encoding="utf-8") as f:
                st.markdown(f.read())
    else:
        missing_file_error(player_development.DEVELOPMENT_REPORT_PATH)


SINGLE_SEASON_PAGES = {
    "Overview": render_overview,
    "Player rankings": render_rankings,
    "Player search / profile": render_player_profile,
    "Similarity search": render_similarity_search,
    "Replacement scouting": render_replacement_scouting,
    "Hidden gems": render_hidden_gems,
    "Clusters": render_clusters,
    "Charts / report": render_charts_report,
}


def main():
    st.sidebar.title("HNL Scouting Dashboard")
    season_choice = st.sidebar.selectbox(
        "Season", list(SEASON_LABELS.values()) + [MULTI_SEASON_LABEL],
    )

    if season_choice == MULTI_SEASON_LABEL:
        render_player_development()
        return

    suffix = SUFFIX_BY_LABEL[season_choice]
    st.sidebar.caption(f"Showing HNL {season_choice} data")

    page = st.sidebar.radio("Section", list(SINGLE_SEASON_PAGES))
    SINGLE_SEASON_PAGES[page](suffix)


if __name__ == "__main__":
    main()
