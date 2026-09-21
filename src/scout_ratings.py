"""
Scout rating maths for the private scouting app (scout_app.py).

Football data science logic:
The analytical pipeline (scouting_scores.py) turns *statistics* into an
`overall_score` (0-100, a percentile-based score). A human scout sees things
statistics cannot - body language, decision speed, how a player copes with
pressure - and records them as 1-10 ratings in a scouting report. This
module puts those two views on the SAME 0-100 scale and blends them:

    1. Each report's four ratings (technical, tactical, physical, mental) are
       converted from 1-10 to 0-100 and combined with fixed weights into one
       per-report scout score.
    2. If a player has several reports for a season, their scout scores are
       averaged - every observation counts equally.
    3. combined_score = 0.65 * analytical_score + 0.35 * scout_score. The
       analytical part carries more weight because it is measured over a full
       season of minutes, while a scout sees only a handful of matches.

The combined score only exists when BOTH inputs exist. A player nobody has
scouted yet shows their analytical score alone - never an invented blend.

This module is pure calculation: no database, no files, no Streamlit. It does
not touch scouting_scores.py or any existing analytical formula; it only
*reads* the analytical `overall_score` as an input.

Rounding: everything is rounded to ONE decimal, but only at the very end.
combined_score is computed from the un-rounded scout score, so a value shown
in the app can differ by 0.1 from a hand calculation done on the rounded
numbers on screen.
"""
import math
from numbers import Real

import pandas as pd

# --- Weights (named constants, covered by tests) ---------------------------

# How the four report ratings combine into one scout score. They must sum to
# 1.0 - a test enforces that.
TECHNICAL_WEIGHT = 0.30
TACTICAL_WEIGHT = 0.30
PHYSICAL_WEIGHT = 0.20
MENTAL_WEIGHT = 0.20

# Report column -> weight. Potential is deliberately NOT part of the scout
# score: it is a judgement about the future, not about what the scout saw,
# so it is shown separately (see summarize_reports).
SCOUT_RATING_WEIGHTS = {
    "technical_rating": TECHNICAL_WEIGHT,
    "tactical_rating": TACTICAL_WEIGHT,
    "physical_rating": PHYSICAL_WEIGHT,
    "mental_rating": MENTAL_WEIGHT,
}

# How the analytical and scout scores blend into the combined score. They
# must sum to 1.0 - a test enforces that.
ANALYTICAL_WEIGHT = 0.65
SCOUT_WEIGHT = 0.35

# Report ratings are whole numbers on this scale.
RATING_MIN = 1
RATING_MAX = 10

DECIMALS = 1


def _is_missing(value):
    """True for None / NaN / pandas NA - i.e. "there is no number here"."""
    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def rating_to_100(rating):
    """Converts a 1-10 rating to the 0-100 scale: (rating - 1) / 9 * 100.

    1 maps to 0, 10 maps to 100, and everything in between is linear (so 5.5
    - the midpoint of the scale - maps to exactly 50). Raises ValueError for
    anything that is not a number between 1 and 10, so a bad value can never
    silently produce a score."""
    if isinstance(rating, bool) or not isinstance(rating, Real) or _is_missing(rating):
        raise ValueError(f"Rating must be a number, got {rating!r}.")
    if not RATING_MIN <= rating <= RATING_MAX:
        raise ValueError(f"Rating must be between {RATING_MIN} and {RATING_MAX}, got {rating}.")
    return (rating - RATING_MIN) / (RATING_MAX - RATING_MIN) * 100


def report_scout_score(report):
    """One report's scout score on the 0-100 scale (NOT rounded).

    weighted sum of the four ratings, each converted with rating_to_100:
        0.30 * technical + 0.30 * tactical + 0.20 * physical + 0.20 * mental"""
    return sum(
        weight * rating_to_100(report[column])
        for column, weight in SCOUT_RATING_WEIGHTS.items()
    )


def _mean_scout_score(reports):
    """Un-rounded average of per-report scout scores, or None with no reports.
    Averaging the per-report scores is the same as scoring the averaged
    ratings (the formula is linear), so there is only one definition."""
    reports = list(reports)
    if not reports:
        return None
    return sum(report_scout_score(r) for r in reports) / len(reports)


def scout_score(reports):
    """Scout score (0-100, rounded to one decimal) for a player's reports in
    one season - the average of the per-report scores. None if there are no
    reports."""
    raw = _mean_scout_score(reports)
    return None if raw is None else round(raw, DECIMALS)


def combined_score(analytical_score, scout_score_value):
    """0.65 * analytical_score + 0.35 * scout_score, rounded to one decimal.

    Returns None unless BOTH inputs exist - the app must then show only the
    analytical score, never a blend with an invented scout score."""
    if _is_missing(analytical_score) or _is_missing(scout_score_value):
        return None
    blended = ANALYTICAL_WEIGHT * analytical_score + SCOUT_WEIGHT * scout_score_value
    return round(blended, DECIMALS)


def summarize_reports(reports, analytical_score=None):
    """Everything the app shows about a player's scouting for ONE season.

    `reports` is a list of dicts with the five *_rating keys. Returns:
        report_count       how many reports were averaged
        scout_score        0-100, or None with no reports
        technical_avg ...  average 1-10 rating per dimension (one decimal)
        potential_avg      average potential rating (1-10) - shown separately,
                           not part of scout_score
        analytical_score   the analytical overall_score, rounded (or None)
        combined_score     0-100, only when both scores exist, else None

    This is the single place scores are derived, so the search table, the
    profile and the comparison can never disagree."""
    reports = list(reports)
    raw_scout = _mean_scout_score(reports)

    summary = {"report_count": len(reports)}
    for column in (*SCOUT_RATING_WEIGHTS, "potential_rating"):
        key = column.replace("_rating", "_avg")
        summary[key] = (
            round(sum(r[column] for r in reports) / len(reports), DECIMALS) if reports else None
        )
    summary["scout_score"] = None if raw_scout is None else round(raw_scout, DECIMALS)
    summary["analytical_score"] = (
        None if _is_missing(analytical_score) else round(float(analytical_score), DECIMALS)
    )
    # Blend from the un-rounded scout score (see module docstring).
    summary["combined_score"] = combined_score(analytical_score, raw_scout)
    return summary


def add_scout_columns(players_df, reports_df):
    """Adds scout_report_count, scout_score, scout_potential_avg and
    combined_score to a players DataFrame.

    Players and reports are matched on (league_code, player_id, season_suffix)
    - never on name. `players_df` needs those three columns plus the
    analytical `overall_score`. Players with no reports get a count of 0 and
    NaN scores (so combined_score stays NaN rather than being invented).
    `reports_df` may be None or empty."""
    result = players_df.copy()
    result["scout_report_count"] = 0
    result["scout_score"] = float("nan")
    result["scout_potential_avg"] = float("nan")
    result["combined_score"] = float("nan")

    if reports_df is None or reports_df.empty or result.empty:
        return result

    keys = ["league_code", "player_id", "season_suffix"]
    reports = reports_df.copy()
    reports["player_id"] = reports["player_id"].astype("int64")

    # Index the reports once per key, then look each player up - a few
    # hundred players and a handful of reports, so clarity beats vectorising.
    reports_by_key = {
        key: group.to_dict("records") for key, group in reports.groupby(keys, sort=False)
    }
    for idx, row in result.iterrows():
        group = reports_by_key.get((row["league_code"], int(row["player_id"]), row["season_suffix"]))
        if not group:
            continue
        summary = summarize_reports(group, row.get("overall_score"))
        result.at[idx, "scout_report_count"] = summary["report_count"]
        result.at[idx, "scout_score"] = summary["scout_score"]
        result.at[idx, "scout_potential_avg"] = summary["potential_avg"]
        if summary["combined_score"] is not None:
            result.at[idx, "combined_score"] = summary["combined_score"]
    result["scout_report_count"] = result["scout_report_count"].astype(int)
    return result


# Sanity guard at import time: a typo in a weight should fail loudly here,
# not silently skew every score.
assert math.isclose(sum(SCOUT_RATING_WEIGHTS.values()), 1.0), "scout rating weights must sum to 1"
assert math.isclose(ANALYTICAL_WEIGHT + SCOUT_WEIGHT, 1.0), "combined score weights must sum to 1"
