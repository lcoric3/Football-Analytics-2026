"""
Streamlit dashboard for the HNL scouting project (season set by
src/season_config.py, defaults to 2025/2026).

Read-only view over files the pipeline (`python main.py`) already produced -
this file never calls the SportMonks API and never writes or recomputes any
data file. It only reads CSVs from data/processed/ and data/output/, charts
from reports/figures_<season>/, and the Markdown reports in reports/.

Run with:
    streamlit run app.py
"""
import os

import pandas as pd
import streamlit as st

from src import ml_models
from src import replacement_scouting
from src import season_config
from src.scouting_scores import MIN_MINUTES_FOR_SCORES

st.set_page_config(page_title=f"HNL {season_config.SEASON_NAME} Scouting Dashboard", layout="wide")

SCORED_CSV = season_config.processed_path("hnl_player_scored")
ML_FEATURES_CSV = season_config.processed_path("hnl_ml_features")
TOP_PLAYERS_CSV = season_config.output_path("top_players_hnl")
SPECIALIST_CSV = season_config.output_path("specialist_rankings_hnl")
CLUSTERS_CSV = season_config.output_path("player_clusters")
FIGURES_DIR = season_config.figures_dir()
REPORT_MD = season_config.scouting_report_path()
CLUSTER_PROFILES_MD = season_config.cluster_profiles_report_path()

# Rankings page: dashboard label -> (source CSV, category value in that CSV).
RANKING_CATEGORIES = {
    "Top overall outfield players": (TOP_PLAYERS_CSV, "best_overall"),
    "Best U23 / young talents": (TOP_PLAYERS_CSV, "best_young_talents"),
    "Best attackers": (TOP_PLAYERS_CSV, "best_attackers"),
    "Best creators": (SPECIALIST_CSV, "best_creators"),
    "Best defenders": (TOP_PLAYERS_CSV, "best_defenders"),
    "Best dribblers": (SPECIALIST_CSV, "best_dribblers"),
    "Best passers": (SPECIALIST_CSV, "best_passers"),
    "Best progressive midfielders": (SPECIALIST_CSV, "best_progressive_midfielders"),
    "Best passer defenders": (SPECIALIST_CSV, "best_passer_defenders"),
    "Best goalkeepers": (TOP_PLAYERS_CSV, "best_goalkeepers"),
}

# Player profile page: example similarity chart saved for a handful of
# players by visualization.py - shown as a bonus if the searched player
# happens to be one of them.
EXAMPLE_SIMILARITY_CHARTS = {
    "Dion Beljo": "player_similarity_attacker_example.png",
    "Ismaël Bennacer": "player_similarity_midfielder_example.png",
    "Sergi Domínguez": "player_similarity_defender_example.png",
}


@st.cache_data
def load_csv(path):
    """Reads a CSV if it exists, otherwise returns None so callers can show
    a friendly error instead of a stack trace."""
    if not os.path.exists(path):
        return None
    return pd.read_csv(path)


def missing_file_error(path):
    st.error(
        f"**Missing file:** `{path}`\n\n"
        "Run the pipeline first to generate it:\n\n"
        "```powershell\npython main.py\n```"
    )


def render_overview():
    st.title(f"HNL {season_config.SEASON_NAME} Scouting Dashboard")
    st.markdown(
        "A read-only view over the Football-Analytics-2026 scouting pipeline: "
        "`SportMonks API -> raw data -> cleaned data -> feature engineering -> "
        "scouting scores -> rankings -> visualizations -> ML dataset`. "
        "This dashboard never calls the SportMonks API and never writes or "
        "recomputes any data - it only reads the CSVs, charts, and reports "
        "the pipeline already produced."
    )

    scored_df = load_csv(SCORED_CSV)
    if scored_df is None:
        missing_file_error(SCORED_CSV)
        return

    eligible = scored_df[scored_df["minutes"] >= MIN_MINUTES_FOR_SCORES]

    col1, col2, col3 = st.columns(3)
    col1.metric("Players", len(scored_df))
    col2.metric("Teams", scored_df["team_name"].nunique())
    col3.metric(f"Eligible players (>={MIN_MINUTES_FOR_SCORES} min)", len(eligible))

    st.subheader("Full scouting report")
    if os.path.exists(REPORT_MD):
        with st.expander("Open the full Markdown scouting report"):
            with open(REPORT_MD, encoding="utf-8") as f:
                st.markdown(f.read())
    else:
        missing_file_error(REPORT_MD)


def render_rankings():
    st.title("Player Rankings")
    label = st.selectbox("Category", list(RANKING_CATEGORIES))
    path, category = RANKING_CATEGORIES[label]

    df = load_csv(path)
    if df is None:
        missing_file_error(path)
        return

    subset = df[df["category"] == category].sort_values("rank")
    if subset.empty:
        st.warning(f"No rows found for category `{category}`.")
        return
    st.dataframe(subset.drop(columns=["category"]), hide_index=True, use_container_width=True)


def render_player_profile():
    st.title("Player Search / Profile")

    scored_df = load_csv(SCORED_CSV)
    if scored_df is None:
        missing_file_error(SCORED_CSV)
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
        st.dataframe(pd.DataFrame([scores]), hide_index=True, use_container_width=True)
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
        st.dataframe(pd.DataFrame([per90]), hide_index=True, use_container_width=True)

    chart_file = EXAMPLE_SIMILARITY_CHARTS.get(player_name)
    if chart_file:
        chart_path = os.path.join(FIGURES_DIR, chart_file)
        if os.path.exists(chart_path):
            st.subheader("Similarity chart (example)")
            st.image(chart_path)


def render_similarity_search():
    st.title("Similarity Search")

    ml_df = load_csv(ML_FEATURES_CSV)
    if ml_df is None:
        missing_file_error(ML_FEATURES_CSV)
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
    st.dataframe(results, hide_index=True, use_container_width=True)


def render_replacement_scouting():
    st.title("Replacement Scouting")

    ml_df = load_csv(ML_FEATURES_CSV)
    if ml_df is None:
        missing_file_error(ML_FEATURES_CSV)
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
    st.dataframe(results, hide_index=True, use_container_width=True)


def render_hidden_gems():
    st.title("Hidden Gems")

    top_players_df = load_csv(TOP_PLAYERS_CSV)
    if top_players_df is None:
        missing_file_error(TOP_PLAYERS_CSV)
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
                st.dataframe(subset.drop(columns=["category"]), hide_index=True, use_container_width=True)


def render_clusters():
    st.title("Player Clusters")

    clusters_df = load_csv(CLUSTERS_CSV)
    if clusters_df is None:
        missing_file_error(CLUSTERS_CSV)
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
    st.dataframe(cluster_summary, hide_index=True, use_container_width=True)

    cluster_options = sorted(clusters_df["cluster_name"].dropna().unique())
    selected = st.selectbox("Show players in cluster", cluster_options)
    subset = clusters_df[clusters_df["cluster_name"] == selected].sort_values(
        "quality_score", ascending=False
    )
    st.dataframe(subset, hide_index=True, use_container_width=True)

    if os.path.exists(CLUSTER_PROFILES_MD):
        with st.expander("Full cluster profiles report (plain-English style descriptions)"):
            with open(CLUSTER_PROFILES_MD, encoding="utf-8") as f:
                st.markdown(f.read())
    else:
        st.info(f"Cluster profiles report not found at `{CLUSTER_PROFILES_MD}`.")


def render_charts_report():
    st.title("Charts & Report")

    if not os.path.isdir(FIGURES_DIR):
        st.error(f"**Missing folder:** `{FIGURES_DIR}`. Run `python main.py` to generate charts.")
    else:
        chart_files = sorted(f for f in os.listdir(FIGURES_DIR) if f.lower().endswith(".png"))
        if not chart_files:
            st.warning(f"No charts found in `{FIGURES_DIR}`.")
        else:
            cols = st.columns(2)
            for i, chart_file in enumerate(chart_files):
                with cols[i % 2]:
                    st.image(os.path.join(FIGURES_DIR, chart_file), caption=chart_file)

    st.divider()
    st.subheader("Full scouting report")
    if os.path.exists(REPORT_MD):
        with st.expander("Open the full Markdown scouting report", expanded=False):
            with open(REPORT_MD, encoding="utf-8") as f:
                st.markdown(f.read())
    else:
        missing_file_error(REPORT_MD)


PAGES = {
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
    st.sidebar.title(f"HNL {season_config.SEASON_NAME} Scouting")
    page = st.sidebar.radio("Section", list(PAGES))
    PAGES[page]()


if __name__ == "__main__":
    main()
