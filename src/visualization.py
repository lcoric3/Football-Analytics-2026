"""
Stage 6: charts for the scouting rankings.

Football data science logic:
Horizontal bar charts, longest bar first, are used for "top N by metric X"
leaderboards - they're the clearest way to present a ranking because
player names stay readable on the y-axis regardless of name length,
unlike a vertical bar chart with rotated labels. Scatter plots are used
wherever the point is a *relationship between two stats* (volume vs.
efficiency, age vs. score, minutes vs. score) that a single ranked list
can't show - e.g. two dribblers can have the same dribbling_score for
completely different reasons (one tries a lot and lands half, the other
tries rarely but never fails), and only a scatter plot makes that visible.

Charts based on per-90 rates/scores only include players who cleared
MIN_MINUTES_FOR_SCORES (the same 450-minute floor used in
scouting_scores.py), so a one-substitute-appearance outlier can't take
the top spot or skew an axis.

Color follows a single fixed palette throughout (see COLORS below) so the
same idea always reads the same way across every chart in the report:
one hue per score/series, never reused for something unrelated, and never
picked to "match the team" or otherwise encode something not in the data.
"""
import logging
import os

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.scouting_scores import MIN_MINUTES_FOR_SCORES

logger = logging.getLogger(__name__)

SCORED_CSV_PATH = "data/processed/hnl_player_scored_2025_2026.csv"
SPECIALIST_CSV_PATH = "data/output/specialist_rankings_hnl_2025_2026.csv"
SIMILARITY_CSV_PATH = "data/output/player_similarity_results.csv"
FIGURES_DIR = "reports/figures"
TOP_N = 10
U23_AGE_LIMIT = 23

# Fixed-order categorical palette (never cycled/reassigned) plus chart
# chrome colors, so a metric/series always gets the same color everywhere.
BLUE, AQUA, YELLOW, GREEN, VIOLET, RED, MAGENTA, ORANGE = (
    "#2a78d6", "#1baf7a", "#eda100", "#008300",
    "#4a3aa7", "#e34948", "#e87ba4", "#eb6834",
)
CATEGORICAL = [BLUE, AQUA, YELLOW, GREEN, VIOLET, RED, MAGENTA, ORANGE]

INK_PRIMARY = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
GRIDLINE = "#e1e0d9"
SURFACE = "#fcfcfb"

POSITION_COLORS = {
    "Defender": BLUE, "Midfielder": AQUA, "Attacker": YELLOW, "Goalkeeper": GREEN,
}


def _outfield_only(df):
    """overall_score is built from outfield actions and is close to
    meaningless for goalkeepers (see scouting_scores.py) - every chart that
    ranks/plots overall_score excludes them, same as best_overall/best_u23
    in analysis.py. Goalkeepers keep their own goalkeeper_score and
    best_goalkeepers ranking; they're never dropped from the underlying
    data, just from these outfield-scoped charts."""
    return df[df["position"].astype(str).str.lower() != "goalkeeper"]

METRIC_LABELS = {
    "attacking_score": "Attacking", "creative_score": "Creative",
    "defensive_score": "Defensive", "discipline_score": "Discipline",
    "dribbling_score": "Dribbling", "passing_score": "Passing",
    "duel_defending_score": "Duel Defending",
    "progressive_midfielder_score": "Progressive MF",
    "passer_defender_score": "Passer/Ball-Playing",
}


def _apply_style():
    """One shared look for every chart in this module - flat design,
    muted gridlines, no seaborn."""
    plt.rcParams.update({
        "figure.facecolor": SURFACE,
        "axes.facecolor": SURFACE,
        "savefig.facecolor": SURFACE,
        "axes.edgecolor": GRIDLINE,
        "axes.labelcolor": INK_SECONDARY,
        "text.color": INK_PRIMARY,
        "xtick.color": INK_MUTED,
        "ytick.color": INK_MUTED,
        "axes.grid": True,
        "grid.color": GRIDLINE,
        "grid.linewidth": 0.7,
        "font.family": "sans-serif",
        "font.size": 10,
        "axes.titlesize": 13,
        "axes.titleweight": "bold",
        "axes.spines.top": False,
        "axes.spines.right": False,
        "legend.frameon": False,
    })


def _save(fig, filename):
    fig.tight_layout()
    os.makedirs(FIGURES_DIR, exist_ok=True)
    path = os.path.join(FIGURES_DIR, filename)
    fig.savefig(path, dpi=160)
    plt.close(fig)
    logger.info("Saved chart: %s", path)


def _barh_chart(labels, values, title, xlabel, filename, color=BLUE, value_fmt="{:.2f}"):
    """Horizontal bar chart, longest bar on top. `labels`/`values` must
    already be in rank order (best first)."""
    n = len(labels)
    fig, ax = plt.subplots(figsize=(9.5, max(3.0, 0.45 * n + 1.6)))
    y_pos = np.arange(n)
    bars = ax.barh(y_pos, values, color=color, height=0.65, zorder=3)
    ax.set_yticks(y_pos)
    ax.set_yticklabels(labels)
    ax.invert_yaxis()  # rank 1 on top
    ax.set_xlabel(xlabel)
    ax.set_title(title, pad=12)
    ax.grid(axis="y", visible=False)
    ax.set_xlim(0, max(values) * 1.15 if len(values) else 1)

    for bar, value in zip(bars, values):
        ax.text(
            bar.get_width() + max(values) * 0.015, bar.get_y() + bar.get_height() / 2,
            value_fmt.format(value), va="center", fontsize=9, color=INK_SECONDARY,
        )

    _save(fig, filename)


def _scatter_with_labels(x, y, labels, highlight_mask, title, xlabel, ylabel, filename):
    """Scatter plot where every point shares one color (the entity being
    plotted doesn't change), and a handful of `highlight_mask` points get a
    bigger marker plus a name label - selective direct labeling instead of
    labeling every single dot, which would be unreadable.

    Highlighted points are often bunched close together (the top 8 by some
    score tend to have similar stats, that's why they're the top 8), so
    labels are sorted left-to-right and alternated above/below the point -
    a simple heuristic that avoids most overlap without pulling in a
    dedicated label-placement dependency."""
    fig, ax = plt.subplots(figsize=(9.5, 7))
    ax.scatter(x[~highlight_mask], y[~highlight_mask], color=BLUE, alpha=0.30, s=26, linewidths=0, zorder=2)
    ax.scatter(
        x[highlight_mask], y[highlight_mask], color=BLUE, alpha=0.95, s=60,
        edgecolors=INK_PRIMARY, linewidths=0.7, zorder=3,
    )

    highlighted = pd.DataFrame({"x": x[highlight_mask], "y": y[highlight_mask], "label": labels[highlight_mask]})
    highlighted = highlighted.sort_values("x").reset_index(drop=True)
    for i, row in highlighted.iterrows():
        dy = 12 if i % 2 == 0 else -22
        ax.annotate(
            row["label"], (row["x"], row["y"]), textcoords="offset points", xytext=(9, dy),
            fontsize=8.5, color=INK_SECONDARY, va="center",
            arrowprops=dict(arrowstyle="-", color=INK_MUTED, linewidth=0.6, shrinkA=0, shrinkB=4),
        )

    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.set_title(title, pad=12)
    _save(fig, filename)


def _radar_chart(metric_labels, series_dict, title, filename):
    """Radar/spider chart: one axis per metric, one polygon per player.
    Good for "compare a few players across several dimensions at once" -
    a grouped bar chart says the same thing but a radar makes each
    player's *shape* (well-rounded vs. spiky/specialist) easier to see
    at a glance."""
    n = len(metric_labels)
    angles = np.linspace(0, 2 * np.pi, n, endpoint=False).tolist()
    angles += angles[:1]

    fig, ax = plt.subplots(figsize=(7.5, 7.5), subplot_kw=dict(polar=True))
    ax.set_facecolor(SURFACE)
    ax.set_theta_offset(np.pi / 2)
    ax.set_theta_direction(-1)
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(metric_labels, color=INK_SECONDARY, fontsize=10)
    ax.set_ylim(0, 100)
    ax.set_yticks([25, 50, 75, 100])
    ax.set_yticklabels(["25", "50", "75", "100"], color=INK_MUTED, fontsize=8)
    ax.grid(color=GRIDLINE)
    ax.spines["polar"].set_color(GRIDLINE)

    for (name, values), color in zip(series_dict.items(), CATEGORICAL):
        vals = values + values[:1]
        ax.plot(angles, vals, color=color, linewidth=2, label=name, zorder=3)
        ax.fill(angles, vals, color=color, alpha=0.10, zorder=2)

    ax.set_title(title, pad=28)
    ax.legend(loc="upper right", bbox_to_anchor=(1.35, 1.08), fontsize=9)
    _save(fig, filename)


# --- Existing leaderboard charts (kept, restyled to the shared palette) ---

def plot_top_goals_per90(df):
    eligible = df[df["minutes"] >= MIN_MINUTES_FOR_SCORES]
    ranked = eligible.sort_values("goals_per90", ascending=False).head(TOP_N)
    labels = [f"{r.player_name} ({r.team_name})" for r in ranked.itertuples()]
    _barh_chart(labels, ranked["goals_per90"].values, "Top 10 - Goals per 90", "Goals per 90", "top10_goals_per90.png")


def plot_top_assists_per90(df):
    eligible = df[df["minutes"] >= MIN_MINUTES_FOR_SCORES]
    ranked = eligible.sort_values("assists_per90", ascending=False).head(TOP_N)
    labels = [f"{r.player_name} ({r.team_name})" for r in ranked.itertuples()]
    _barh_chart(labels, ranked["assists_per90"].values, "Top 10 - Assists per 90", "Assists per 90", "top10_assists_per90.png")


def plot_top_overall_score(df):
    ranked = _outfield_only(df).dropna(subset=["overall_score"]).sort_values("overall_score", ascending=False).head(TOP_N)
    labels = [f"{r.player_name} ({r.team_name})" for r in ranked.itertuples()]
    _barh_chart(labels, ranked["overall_score"].values, "Top 10 - Overall Scouting Score (Outfield)", "Overall score", "top10_overall_score.png", value_fmt="{:.1f}")


def plot_best_u23(df):
    u23 = _outfield_only(df)
    u23 = u23[(u23["age"] <= U23_AGE_LIMIT) & u23["overall_score"].notna()]
    ranked = u23.sort_values("overall_score", ascending=False).head(TOP_N)
    labels = [f"{r.player_name} ({r.team_name})" for r in ranked.itertuples()]
    _barh_chart(labels, ranked["overall_score"].values, "Best U23 Players (Overall Score, Outfield)", "Overall score", "best_u23_players.png", value_fmt="{:.1f}")


# --- New charts: Stage 4 --------------------------------------------------

def plot_top_overall_players(df):
    ranked = _outfield_only(df).dropna(subset=["overall_score"]).sort_values("overall_score", ascending=False).head(15)
    labels = [f"{r.player_name} ({r.team_name})" for r in ranked.itertuples()]
    _barh_chart(
        labels, ranked["overall_score"].values,
        "Top 15 Overall Scouting Score (Outfield Players)", "Overall score (position-aware percentile blend)",
        "top_overall_players.png", value_fmt="{:.1f}",
    )


def plot_top_u23_players(df):
    u23 = _outfield_only(df)
    u23 = u23[(u23["age"] <= U23_AGE_LIMIT) & u23["overall_score"].notna()]
    ranked = u23.sort_values("overall_score", ascending=False).head(15)
    labels = [f"{r.player_name} ({r.team_name}, {r.age:.0f}y)" for r in ranked.itertuples()]
    _barh_chart(
        labels, ranked["overall_score"].values,
        "Top 15 U23 Players (Overall Score, Outfield)", "Overall score",
        "top_u23_players.png", color=AQUA, value_fmt="{:.1f}",
    )


def plot_specialist_score_comparison(scored_df, specialist_df):
    metrics = [
        "dribbling_score", "passing_score", "duel_defending_score",
        "progressive_midfielder_score", "passer_defender_score",
    ]
    colors = dict(zip(metrics, CATEGORICAL[:5]))

    # Pick 2 leaders from each of the 5 specialist categories, de-duplicated,
    # capped at 10, so the chart shows a genuinely varied cast rather than
    # e.g. the same all-rounder appearing for every metric.
    categories = [
        "best_dribblers", "best_passers", "best_duel_defenders",
        "best_progressive_midfielders", "best_passer_defenders",
    ]
    chosen_ids = []
    for category in categories:
        top = specialist_df[specialist_df["category"] == category].sort_values("rank").head(2)
        for player_id in top["player_id"]:
            if player_id not in chosen_ids:
                chosen_ids.append(player_id)
    chosen_ids = chosen_ids[:10]

    subset = scored_df[scored_df["player_id"].isin(chosen_ids)].set_index("player_id").loc[chosen_ids]
    labels = list(subset["player_name"])

    n_players, n_metrics = len(subset), len(metrics)
    x = np.arange(n_players)
    width = 0.8 / n_metrics

    fig, ax = plt.subplots(figsize=(max(11, n_players * 1.3), 6.5))
    for i, metric in enumerate(metrics):
        offset = (i - (n_metrics - 1) / 2) * width
        values = subset[metric].fillna(0).values
        ax.bar(x + offset, values, width=width, color=colors[metric], label=METRIC_LABELS[metric], zorder=3)

    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=25, ha="right")
    ax.set_ylabel("Score (0-100)")
    ax.set_title("Specialist Score Comparison - Selected Players", pad=12)
    ax.legend(loc="upper right", ncol=1, fontsize=8.5)
    _save(fig, "specialist_score_comparison.png")


def _plot_similarity_bar(similarity_df, query_player, role, filename, title):
    sub = similarity_df[
        (similarity_df["query_player"] == query_player) & (similarity_df["role"] == role)
    ].sort_values("rank")
    if sub.empty:
        logger.warning("No similarity results for %s (role=%s) - skipping %s", query_player, role, filename)
        return
    labels = [f"{r.player_name} ({r.team_name})" for r in sub.itertuples()]
    _barh_chart(labels, sub["similarity"].values, title, "Cosine similarity (0-1)", filename, color=VIOLET, value_fmt="{:.2f}")


def plot_similarity_bennacer(similarity_df):
    _plot_similarity_bar(
        similarity_df, "Ismaël Bennacer", "overall",
        "player_similarity_bennacer.png", "Players Most Similar to Ismaël Bennacer (overall)",
    )


def plot_similarity_beljo(similarity_df):
    _plot_similarity_bar(
        similarity_df, "Dion Beljo", "attacker",
        "player_similarity_beljo.png", "Players Most Similar to Dion Beljo (attacker)",
    )


def plot_similarity_dominguez(similarity_df):
    _plot_similarity_bar(
        similarity_df, "Sergi Domínguez", "passer_defender",
        "player_similarity_dominguez.png", "Players Most Similar to Sergi Domínguez (passer defender)",
    )


def plot_dribblers_scatter(df):
    eligible = df[df["minutes"] >= MIN_MINUTES_FOR_SCORES].dropna(subset=["dribbling_score"]).reset_index(drop=True)
    top8 = set(eligible.nlargest(8, "dribbling_score")["player_id"])
    mask = eligible["player_id"].isin(top8)
    _scatter_with_labels(
        eligible["dribble_success_rate"], eligible["successful_dribbles_per90"], eligible["player_name"], mask,
        "Dribbling: Volume vs. Efficiency", "Dribble success rate (%)", "Successful dribbles per 90",
        "dribblers_scatter.png",
    )


def plot_passers_scatter(df):
    eligible = df[df["minutes"] >= MIN_MINUTES_FOR_SCORES].dropna(subset=["passing_score"]).reset_index(drop=True)
    top8 = set(eligible.nlargest(8, "passing_score")["player_id"])
    mask = eligible["player_id"].isin(top8)
    _scatter_with_labels(
        eligible["pass_accuracy_ratio"], eligible["key_passes_per90"], eligible["player_name"], mask,
        "Passing: Safe vs. Creative", "Pass accuracy (ratio)", "Key passes per 90",
        "passers_scatter.png",
    )


def plot_defender_profile_scatter(df):
    eligible = df[df["minutes"] >= MIN_MINUTES_FOR_SCORES].dropna(subset=["duel_defending_score"]).reset_index(drop=True)
    top8 = set(eligible.nlargest(8, "duel_defending_score")["player_id"])
    mask = eligible["player_id"].isin(top8)
    _scatter_with_labels(
        eligible["aerials_won_per90"], eligible["duel_defending_score"], eligible["player_name"], mask,
        "Duel Defending Profile", "Aerials won per 90", "Duel defending score",
        "defender_profile_scatter.png",
    )


def plot_passer_defender_scatter(df):
    defenders = df[
        (df["minutes"] >= MIN_MINUTES_FOR_SCORES)
        & df["position"].astype(str).str.contains("def|back", case=False, na=False)
    ].dropna(subset=["passer_defender_score"]).reset_index(drop=True)
    top8 = set(defenders.nlargest(8, "passer_defender_score")["player_id"])
    mask = defenders["player_id"].isin(top8)
    _scatter_with_labels(
        defenders["accurate_long_balls_per90"], defenders["passer_defender_score"], defenders["player_name"], mask,
        "Passer / Ball-Playing Defender Profile", "Accurate long balls per 90", "Passer defender score",
        "passer_defender_scatter.png",
    )


def plot_age_vs_overall_score(df):
    eligible = _outfield_only(df).dropna(subset=["overall_score", "age"])
    is_u23 = eligible["age"] <= U23_AGE_LIMIT

    fig, ax = plt.subplots(figsize=(9.5, 7))
    ax.scatter(eligible.loc[~is_u23, "age"], eligible.loc[~is_u23, "overall_score"], color=INK_MUTED, alpha=0.35, s=26, label="Age 24+", zorder=2)
    ax.scatter(eligible.loc[is_u23, "age"], eligible.loc[is_u23, "overall_score"], color=BLUE, alpha=0.9, s=42, label="U23 (age <= 23)", zorder=3)

    top5_u23 = eligible[is_u23].nlargest(5, "overall_score").sort_values("age")
    for i, row in enumerate(top5_u23.itertuples()):
        dy = 12 if i % 2 == 0 else -22
        ax.annotate(
            row.player_name, (row.age, row.overall_score), textcoords="offset points", xytext=(9, dy),
            fontsize=8.5, color=INK_SECONDARY, va="center",
            arrowprops=dict(arrowstyle="-", color=INK_MUTED, linewidth=0.6, shrinkA=0, shrinkB=4),
        )

    ax.set_xlabel("Age")
    ax.set_ylabel("Overall score")
    ax.set_title("Age vs. Overall Score - Spotting Young Talent (Outfield)", pad=12)
    ax.legend(loc="lower right", fontsize=9)
    _save(fig, "age_vs_overall_score.png")


def plot_minutes_vs_overall_score(df):
    eligible = df.dropna(subset=["overall_score"])
    fig, ax = plt.subplots(figsize=(9.5, 7))
    ax.scatter(eligible["minutes"], eligible["overall_score"], color=BLUE, alpha=0.4, s=26, zorder=2)
    ax.axvline(MIN_MINUTES_FOR_SCORES, color=INK_MUTED, linestyle="--", linewidth=1.2, zorder=1)
    ax.text(
        MIN_MINUTES_FOR_SCORES + 40, eligible["overall_score"].max(),
        f"{MIN_MINUTES_FOR_SCORES}-minute eligibility floor", color=INK_MUTED, fontsize=8.5, va="top",
    )
    ax.set_xlabel("Minutes played")
    ax.set_ylabel("Overall score")
    ax.set_title("Minutes vs. Overall Score - Is a High Score Reliable?", pad=12)
    _save(fig, "minutes_vs_overall_score.png")


def plot_position_score_distribution(df):
    eligible = df[df["minutes"] >= MIN_MINUTES_FOR_SCORES].dropna(subset=["overall_score"])
    positions = ["Goalkeeper", "Defender", "Midfielder", "Attacker"]
    data = [eligible.loc[eligible["position"] == p, "overall_score"].values for p in positions]
    colors = [POSITION_COLORS[p] for p in positions]

    fig, ax = plt.subplots(figsize=(8.5, 6.5))
    bp = ax.boxplot(
        data, tick_labels=positions, patch_artist=True, widths=0.55,
        medianprops=dict(color=INK_PRIMARY, linewidth=1.5),
        whiskerprops=dict(color=INK_MUTED), capprops=dict(color=INK_MUTED),
        flierprops=dict(marker="o", markersize=4, markerfacecolor=INK_MUTED, markeredgecolor="none", alpha=0.6),
    )
    for patch, color in zip(bp["boxes"], colors):
        patch.set_facecolor(color)
        patch.set_alpha(0.5)
        patch.set_edgecolor(color)

    ax.set_ylabel("Overall score")
    ax.set_title("Overall Score Distribution by Position", pad=12)
    _save(fig, "position_score_distribution.png")


def plot_team_talent_map(df):
    eligible = _outfield_only(df)
    eligible = eligible[eligible["minutes"] >= MIN_MINUTES_FOR_SCORES].dropna(subset=["overall_score"])
    team_stats = (
        eligible.groupby("team_name")
        .agg(avg_score=("overall_score", "mean"), n_players=("player_id", "count"))
        .sort_values("avg_score", ascending=False)
    )
    labels = [f"{team} (n={int(row.n_players)})" for team, row in team_stats.iterrows()]
    _barh_chart(
        labels, team_stats["avg_score"].values,
        "Team Talent Map - Average Overall Score (Eligible Outfield Players)", "Average overall score",
        "team_talent_map.png", value_fmt="{:.1f}",
    )


def plot_role_radar_examples(df):
    metrics = ["attacking_score", "creative_score", "defensive_score", "dribbling_score", "passing_score"]
    metric_labels = [METRIC_LABELS[m] for m in metrics]
    players = ["Ismaël Bennacer", "Dion Beljo", "Sergi Domínguez"]

    series = {}
    for name in players:
        row = df[df["player_name"] == name]
        if row.empty:
            logger.warning("Player %s not found for role_radar_examples - skipping.", name)
            continue
        series[name] = [float(row.iloc[0][m]) if pd.notna(row.iloc[0][m]) else 0.0 for m in metrics]

    if series:
        _radar_chart(metric_labels, series, "Player Profile Comparison", "role_radar_examples.png")


def run():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    _apply_style()

    if not os.path.exists(SCORED_CSV_PATH):
        raise FileNotFoundError(f"{SCORED_CSV_PATH} not found. Run scouting_scores.run() first.")

    df = pd.read_csv(SCORED_CSV_PATH)

    plot_top_goals_per90(df)
    plot_top_assists_per90(df)
    plot_top_overall_score(df)
    plot_best_u23(df)

    plot_top_overall_players(df)
    plot_top_u23_players(df)

    if os.path.exists(SPECIALIST_CSV_PATH):
        specialist_df = pd.read_csv(SPECIALIST_CSV_PATH)
        plot_specialist_score_comparison(df, specialist_df)
    else:
        logger.warning("%s not found - skipping specialist_score_comparison.png. Run analysis.run() first.", SPECIALIST_CSV_PATH)

    if os.path.exists(SIMILARITY_CSV_PATH):
        similarity_df = pd.read_csv(SIMILARITY_CSV_PATH)
        plot_similarity_bennacer(similarity_df)
        plot_similarity_beljo(similarity_df)
        plot_similarity_dominguez(similarity_df)
    else:
        logger.warning("%s not found - skipping similarity charts. Run ml_models.run() first.", SIMILARITY_CSV_PATH)

    plot_dribblers_scatter(df)
    plot_passers_scatter(df)
    plot_defender_profile_scatter(df)
    plot_passer_defender_scatter(df)
    plot_age_vs_overall_score(df)
    plot_minutes_vs_overall_score(df)
    plot_position_score_distribution(df)
    plot_team_talent_map(df)
    plot_role_radar_examples(df)


if __name__ == "__main__":
    run()
