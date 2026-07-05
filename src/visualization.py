"""
Stage 6: charts for the scouting rankings.

Football data science logic:
Horizontal bar charts, longest bar first, are used throughout - they're
the clearest way to present "top N players by metric X" because player
names stay readable on the y-axis regardless of name length, unlike a
vertical bar chart with rotated labels.

Charts based on per-90 rates only include players who cleared the same
MIN_MINUTES_FOR_SCORES threshold used in scouting_scores.py, so a
one-substitute-appearance outlier can't take the top bar.
"""
import logging
import os

import matplotlib.pyplot as plt
import pandas as pd

from src.scouting_scores import MIN_MINUTES_FOR_SCORES

logger = logging.getLogger(__name__)

SCORED_CSV_PATH = "data/processed/hnl_player_scored_2025_2026.csv"
FIGURES_DIR = "reports/figures"
TOP_N = 10
U23_AGE_LIMIT = 23


def _barh_chart(df, value_col, title, filename, top_n=TOP_N):
    """Save a horizontal bar chart of the top_n rows in df, ranked by
    value_col (already sorted by the caller)."""
    subset = df.head(top_n).iloc[::-1]  # reverse so #1 ends up on top

    fig, ax = plt.subplots(figsize=(8, 0.5 * len(subset) + 1.5))
    ax.barh(subset["player_name"], subset[value_col], color="#2b6cb0")
    ax.set_xlabel(value_col)
    ax.set_title(title)
    fig.tight_layout()

    os.makedirs(FIGURES_DIR, exist_ok=True)
    path = os.path.join(FIGURES_DIR, filename)
    fig.savefig(path, dpi=150)
    plt.close(fig)
    logger.info("Saved chart: %s", path)


def plot_top_goals_per90(df):
    eligible = df[df["minutes"] >= MIN_MINUTES_FOR_SCORES]
    ranked = eligible.sort_values("goals_per90", ascending=False)
    _barh_chart(ranked, "goals_per90", "Top 10 - Goals per 90", "top10_goals_per90.png")


def plot_top_assists_per90(df):
    eligible = df[df["minutes"] >= MIN_MINUTES_FOR_SCORES]
    ranked = eligible.sort_values("assists_per90", ascending=False)
    _barh_chart(ranked, "assists_per90", "Top 10 - Assists per 90", "top10_assists_per90.png")


def plot_top_overall_score(df):
    ranked = df.dropna(subset=["overall_score"]).sort_values("overall_score", ascending=False)
    _barh_chart(ranked, "overall_score", "Top 10 - Overall Scouting Score", "top10_overall_score.png")


def plot_best_u23(df):
    u23 = df[(df["age"] <= U23_AGE_LIMIT) & df["overall_score"].notna()]
    ranked = u23.sort_values("overall_score", ascending=False)
    _barh_chart(ranked, "overall_score", "Best U23 Players (Overall Score)", "best_u23_players.png")


def run():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if not os.path.exists(SCORED_CSV_PATH):
        raise FileNotFoundError(f"{SCORED_CSV_PATH} not found. Run scouting_scores.run() first.")

    df = pd.read_csv(SCORED_CSV_PATH)

    plot_top_goals_per90(df)
    plot_top_assists_per90(df)
    plot_top_overall_score(df)
    plot_best_u23(df)


if __name__ == "__main__":
    run()
