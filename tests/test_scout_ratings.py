"""Tests for src/scout_ratings.py - the scout score and combined score maths.
Pure calculation: no database, files or network."""
import math

import numpy as np
import pandas as pd
import pytest

from src import scout_ratings as sr


def report(technical=5, tactical=5, physical=5, mental=5, potential=5):
    return {
        "technical_rating": technical, "tactical_rating": tactical,
        "physical_rating": physical, "mental_rating": mental,
        "potential_rating": potential,
    }


# --- weights are named constants and add up ---------------------------------

def test_scout_weights_are_the_specified_values():
    assert sr.TECHNICAL_WEIGHT == 0.30
    assert sr.TACTICAL_WEIGHT == 0.30
    assert sr.PHYSICAL_WEIGHT == 0.20
    assert sr.MENTAL_WEIGHT == 0.20
    assert sr.SCOUT_RATING_WEIGHTS == {
        "technical_rating": 0.30, "tactical_rating": 0.30,
        "physical_rating": 0.20, "mental_rating": 0.20,
    }


def test_combined_weights_are_the_specified_values():
    assert sr.ANALYTICAL_WEIGHT == 0.65
    assert sr.SCOUT_WEIGHT == 0.35


def test_weights_sum_to_one():
    assert math.isclose(sum(sr.SCOUT_RATING_WEIGHTS.values()), 1.0)
    assert math.isclose(sr.ANALYTICAL_WEIGHT + sr.SCOUT_WEIGHT, 1.0)


def test_potential_is_not_part_of_the_scout_score():
    # Changing only the potential rating must not move the scout score.
    assert sr.scout_score([report(potential=1)]) == sr.scout_score([report(potential=10)])


# --- 1-10 -> 0-100 -----------------------------------------------------------

@pytest.mark.parametrize("rating, expected", [
    (1, 0.0),
    (10, 100.0),
    (5.5, 50.0),                 # midpoint of the scale
    (2, 100 / 9),
    (7, 6 / 9 * 100),
])
def test_rating_to_100(rating, expected):
    assert sr.rating_to_100(rating) == pytest.approx(expected)


def test_rating_to_100_is_linear_and_monotonic():
    values = [sr.rating_to_100(r) for r in range(1, 11)]
    assert values == sorted(values)
    steps = np.diff(values)
    assert np.allclose(steps, steps[0])


@pytest.mark.parametrize("bad", [0, 11, -3, 10.01, 0.99, None, float("nan"), "7", True, [5]])
def test_rating_to_100_rejects_invalid(bad):
    with pytest.raises(ValueError):
        sr.rating_to_100(bad)


def test_rating_to_100_accepts_numpy_numbers():
    assert sr.rating_to_100(np.int64(10)) == 100.0
    assert sr.rating_to_100(np.float64(1.0)) == 0.0


# --- scout score -------------------------------------------------------------

def test_all_tens_is_100_and_all_ones_is_0():
    assert sr.scout_score([report(10, 10, 10, 10)]) == 100.0
    assert sr.scout_score([report(1, 1, 1, 1)]) == 0.0


def test_scout_score_applies_the_weights():
    # technical + physical at 10, tactical + mental at 1:
    # 0.30*100 + 0.30*0 + 0.20*100 + 0.20*0 = 50
    assert sr.scout_score([report(10, 1, 10, 1)]) == 50.0
    # Only technical maxed: 0.30 * 100 = 30
    assert sr.scout_score([report(10, 1, 1, 1)]) == 30.0
    # Only physical maxed: 0.20 * 100 = 20
    assert sr.scout_score([report(1, 1, 10, 1)]) == 20.0


def test_scout_score_worked_example_rounds_to_one_decimal():
    # 8,7,6,9 -> 0.3*77.78 + 0.3*66.67 + 0.2*55.56 + 0.2*88.89 = 72.222...
    assert sr.scout_score([report(8, 7, 6, 9)]) == 72.2


def test_scout_score_averages_multiple_reports():
    assert sr.scout_score([report(10, 10, 10, 10), report(1, 1, 1, 1)]) == 50.0
    three = [report(10, 10, 10, 10), report(10, 10, 10, 10), report(1, 1, 1, 1)]
    assert sr.scout_score(three) == 66.7


def test_scout_score_is_none_without_reports():
    assert sr.scout_score([]) is None


# --- combined score ----------------------------------------------------------

def test_combined_score_formula():
    # 0.65 * 60 + 0.35 * 80 = 39 + 28 = 67
    assert sr.combined_score(60.0, 80.0) == 67.0


def test_combined_score_rounds_to_one_decimal():
    # 0.65 * 62.5 + 0.35 * 72.2 = 65.895 -> one decimal
    result = sr.combined_score(62.5, 72.2)
    assert result == round(result, 1)
    assert result == pytest.approx(65.9, abs=0.1)


@pytest.mark.parametrize("analytical, scout", [
    (None, 70.0), (60.0, None), (None, None),
    (float("nan"), 70.0), (60.0, float("nan")), (pd.NA, 70.0),
])
def test_combined_score_needs_both_inputs(analytical, scout):
    assert sr.combined_score(analytical, scout) is None


def test_combined_score_is_computed_from_the_unrounded_scout_score():
    # Ratings 1,1,1,3 -> raw scout 4.444..., displayed 4.4. With analytical 40:
    #   from raw    : 0.65*40 + 0.35*4.4444 = 27.5556 -> 27.6
    #   from rounded: 0.65*40 + 0.35*4.4    = 27.54   -> 27.5
    summary = sr.summarize_reports([report(1, 1, 1, 3)], analytical_score=40.0)
    assert summary["scout_score"] == 4.4
    assert summary["combined_score"] == 27.6


# --- summary -----------------------------------------------------------------

def test_summary_without_reports_has_no_invented_values():
    summary = sr.summarize_reports([], analytical_score=55.0)
    assert summary["report_count"] == 0
    assert summary["scout_score"] is None
    assert summary["combined_score"] is None          # never a fake blend
    assert summary["technical_avg"] is None
    assert summary["potential_avg"] is None
    assert summary["analytical_score"] == 55.0        # the analytical score is still shown


def test_summary_with_reports_but_no_analytical_score():
    summary = sr.summarize_reports([report(8, 7, 6, 9)], analytical_score=None)
    assert summary["scout_score"] == 72.2
    assert summary["analytical_score"] is None
    assert summary["combined_score"] is None


def test_summary_with_both_scores():
    summary = sr.summarize_reports([report(10, 10, 10, 10, potential=8)], analytical_score=60.0)
    assert summary["report_count"] == 1
    assert summary["scout_score"] == 100.0
    assert summary["combined_score"] == round(0.65 * 60 + 0.35 * 100, 1) == 74.0


def test_summary_reports_dimension_averages_and_report_count():
    reports = [report(8, 6, 4, 2, potential=9), report(6, 6, 6, 6, potential=7)]
    summary = sr.summarize_reports(reports, analytical_score=50.0)
    assert summary["report_count"] == 2
    assert summary["technical_avg"] == 7.0
    assert summary["tactical_avg"] == 6.0
    assert summary["physical_avg"] == 5.0
    assert summary["mental_avg"] == 4.0
    assert summary["potential_avg"] == 8.0


def test_summary_accepts_numpy_analytical_score():
    summary = sr.summarize_reports([report(10, 10, 10, 10)], analytical_score=np.float64(60.0))
    assert summary["combined_score"] == 74.0


# --- DataFrame helper --------------------------------------------------------

def players(overall_scores):
    return pd.DataFrame({
        "league_code": "hnl",
        "season_suffix": "2025_2026",
        "player_id": list(range(1, len(overall_scores) + 1)),
        "overall_score": overall_scores,
    })


def reports_frame(rows):
    return pd.DataFrame(rows)


def test_add_scout_columns_matches_the_scalar_functions():
    reports = reports_frame([
        {"league_code": "hnl", "season_suffix": "2025_2026", "player_id": 1, **report(8, 7, 6, 9, 7)},
        {"league_code": "hnl", "season_suffix": "2025_2026", "player_id": 1, **report(10, 10, 10, 10, 9)},
    ])
    result = sr.add_scout_columns(players([60.0, 70.0]), reports)

    expected = sr.summarize_reports(
        [report(8, 7, 6, 9, 7), report(10, 10, 10, 10, 9)], analytical_score=60.0
    )
    first = result.iloc[0]
    assert first["scout_report_count"] == 2
    assert first["scout_score"] == expected["scout_score"]
    assert first["combined_score"] == expected["combined_score"]
    assert first["scout_potential_avg"] == expected["potential_avg"]


def test_add_scout_columns_leaves_unscouted_players_without_scores():
    reports = reports_frame([
        {"league_code": "hnl", "season_suffix": "2025_2026", "player_id": 1, **report()},
    ])
    result = sr.add_scout_columns(players([60.0, 70.0]), reports)
    unscouted = result.iloc[1]
    assert unscouted["scout_report_count"] == 0
    assert math.isnan(unscouted["scout_score"])
    assert math.isnan(unscouted["combined_score"])       # not invented
    assert unscouted["overall_score"] == 70.0            # analytical score untouched


def test_add_scout_columns_without_any_reports():
    for empty in (None, pd.DataFrame()):
        result = sr.add_scout_columns(players([60.0]), empty)
        assert result["scout_report_count"].tolist() == [0]
        assert result["combined_score"].isna().all()


def test_add_scout_columns_matches_on_season_not_just_player():
    reports = reports_frame([
        {"league_code": "hnl", "season_suffix": "2024_2025", "player_id": 1, **report(10, 10, 10, 10)},
    ])
    result = sr.add_scout_columns(players([60.0]), reports)   # a 2025_2026 player
    assert result.iloc[0]["scout_report_count"] == 0


def test_add_scout_columns_without_analytical_score_keeps_scout_only():
    reports = reports_frame([
        {"league_code": "hnl", "season_suffix": "2025_2026", "player_id": 1, **report(10, 10, 10, 10)},
    ])
    result = sr.add_scout_columns(players([float("nan")]), reports)
    assert result.iloc[0]["scout_score"] == 100.0
    assert math.isnan(result.iloc[0]["combined_score"])


def test_add_scout_columns_does_not_modify_its_input():
    frame = players([60.0])
    before = frame.copy()
    sr.add_scout_columns(frame, None)
    pd.testing.assert_frame_equal(frame, before)
