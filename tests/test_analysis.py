"""
Tests for src/analysis.py - ranking tables built on scouting scores.
"""
import pandas as pd

from src import analysis


def test_best_overall_excludes_goalkeepers(scored_df):
    """overall_score is built from outfield actions goalkeepers barely
    record, so best_overall (and best_u23) must never include one."""
    rankings = analysis.build_rankings(scored_df)

    best_overall = rankings[rankings["category"] == "best_overall"]

    assert not best_overall.empty
    assert (best_overall["position"] != "Goalkeeper").all()


def test_best_goalkeepers_contains_only_goalkeepers(scored_df):
    rankings = analysis.build_rankings(scored_df)

    best_goalkeepers = rankings[rankings["category"] == "best_goalkeepers"]

    assert not best_goalkeepers.empty
    assert (best_goalkeepers["position"] == "Goalkeeper").all()


def test_young_talent_rankings_respect_their_age_cutoffs(scored_df):
    """best_young_talents / best_u23_players_by_potential (age <= 23) and
    best_u21_players (age <= 21) should be sorted by age_potential_score
    and never include a player above their respective age cutoff."""
    rankings = analysis.build_rankings(scored_df)

    for category, age_limit in [
        ("best_young_talents", analysis.U23_AGE_LIMIT),
        ("best_u23_players_by_potential", analysis.U23_AGE_LIMIT),
        ("best_u21_players", analysis.U21_AGE_LIMIT),
    ]:
        subset = rankings[rankings["category"] == category]
        assert not subset.empty, f"{category} produced no rows"
        assert (subset["age"] <= age_limit).all()
        assert (subset["position"] != "Goalkeeper").all()

        # Sorted descending by age_potential_score. A player under the
        # U23_AGE_LIMIT/U21_AGE_LIMIT age cutoff can still be below the
        # MIN_MINUTES_FOR_SCORES eligibility bar (age and playing-time
        # eligibility are independent filters), which gives a NaN score -
        # pandas' sort_values(na_position="last") always pushes those to
        # the bottom, so: non-NaN scores must be strictly non-increasing,
        # and once a NaN appears every row after it must also be NaN.
        scores = list(subset["age_potential_score"])
        non_null = [s for s in scores if not pd.isna(s)]
        assert non_null == sorted(non_null, reverse=True)
        seen_nan = False
        for value in scores:
            if pd.isna(value):
                seen_nan = True
            else:
                assert not seen_nan, "a non-NaN score appeared after a NaN score"


# --- team-context rankings (Stage B2) ---------------------------------------

def test_underrated_players_excludes_goalkeepers_and_sorts_by_underrated_score(scored_df):
    rankings = analysis.build_rankings(scored_df)
    subset = rankings[rankings["category"] == "underrated_players"]

    assert not subset.empty
    assert (subset["position"] != "Goalkeeper").all()

    scores = list(subset["underrated_score"])
    non_null = [s for s in scores if not pd.isna(s)]
    assert non_null == sorted(non_null, reverse=True)


def test_hidden_gems_requires_both_standout_and_weak_team_bonus(scored_df):
    """hidden_gems is the intersection of "outperforms their own team" and
    "plays for a below-average team" - every row must satisfy both, not
    just one."""
    rankings = analysis.build_rankings(scored_df)
    subset = rankings[rankings["category"] == "hidden_gems"]

    if not subset.empty:
        assert (subset["standout_bonus"] > 0).all()
        assert (subset["weak_team_bonus"] > 0).all()


def test_small_club_standouts_requires_weak_team_bonus_only(scored_df):
    """small_club_standouts only requires "plays for a below-average team" -
    unlike hidden_gems it doesn't also require outperforming teammates."""
    rankings = analysis.build_rankings(scored_df)
    subset = rankings[rankings["category"] == "small_club_standouts"]

    if not subset.empty:
        assert (subset["weak_team_bonus"] > 0).all()
