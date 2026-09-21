"""Tests for src/scout_validation.py - form validation - plus a parity check
that keeps its value lists in sync with supabase/schema.sql."""
import re
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from src import scout_validation as sv

TODAY = date(2026, 9, 21)
SCHEMA_SQL = (Path(__file__).resolve().parent.parent / "supabase" / "schema.sql").read_text(
    encoding="utf-8"
)


def valid_form(**overrides):
    form = {
        "league_code": "hnl", "player_id": 42, "season_suffix": "2025_2026",
        "observation_date": date(2026, 9, 1), "opponent": "Hajduk",
        "observed_position": "Midfielder",
        "technical_rating": 7, "tactical_rating": 6, "physical_rating": 8,
        "mental_rating": 5, "potential_rating": 9,
        "strengths": "Passing range", "weaknesses": "Pace", "notes": "Watched live",
        "recommendation": "Nastaviti pratiti",
    }
    form.update(overrides)
    return form


# --- report: happy path -------------------------------------------------------

def test_valid_report_passes_and_is_database_ready():
    result = sv.validate_report(valid_form(), today=TODAY)
    assert result.ok and result.errors == []
    assert result.data["observation_date"] == "2026-09-01"     # JSON-serialisable
    assert result.data["player_id"] == 42
    assert result.data["technical_rating"] == 7


def test_optional_fields_can_be_empty_and_become_none():
    form = valid_form(opponent="  ", strengths="", weaknesses=None, notes="   ")
    result = sv.validate_report(form, today=TODAY)
    assert result.ok
    assert result.data["opponent"] is None
    assert result.data["strengths"] is None
    assert result.data["weaknesses"] is None
    assert result.data["notes"] is None


def test_text_is_trimmed():
    result = sv.validate_report(valid_form(opponent="  Rijeka  "), today=TODAY)
    assert result.data["opponent"] == "Rijeka"


def test_ratings_accept_integral_floats_and_digit_strings():
    form = valid_form(technical_rating=7.0, tactical_rating="6")
    assert sv.validate_report(form, today=TODAY).ok


# --- report: ratings ----------------------------------------------------------

@pytest.mark.parametrize("field", list(sv.RATING_FIELDS))
@pytest.mark.parametrize("bad", [0, 11, -1, 5.5, "abc", None, True, float("nan")])
def test_invalid_rating_is_rejected_with_a_message(field, bad):
    result = sv.validate_report(valid_form(**{field: bad}), today=TODAY)
    assert not result.ok
    assert any(sv.RATING_FIELDS[field] in e for e in result.errors)
    assert result.data == {}


@pytest.mark.parametrize("edge", [1, 10])
def test_rating_boundaries_are_accepted(edge):
    assert sv.validate_report(valid_form(technical_rating=edge), today=TODAY).ok


# --- report: required fields --------------------------------------------------

@pytest.mark.parametrize("field", ["observed_position", "recommendation", "observation_date",
                                   "player_id", "season_suffix", "league_code"])
def test_missing_required_field_is_rejected(field):
    for empty in (None, "", "   "):
        result = sv.validate_report(valid_form(**{field: empty}), today=TODAY)
        assert not result.ok, f"{field}={empty!r} should be rejected"


def test_all_errors_are_reported_at_once():
    result = sv.validate_report(
        valid_form(observed_position="", technical_rating=0, recommendation="?"), today=TODAY
    )
    assert len(result.errors) == 3


def test_unknown_recommendation_is_rejected():
    assert not sv.validate_report(valid_form(recommendation="Kupiti odmah"), today=TODAY).ok


@pytest.mark.parametrize("recommendation", sv.RECOMMENDATIONS)
def test_every_listed_recommendation_is_accepted(recommendation):
    assert sv.validate_report(valid_form(recommendation=recommendation), today=TODAY).ok


# --- report: dates ------------------------------------------------------------

def test_future_date_is_rejected_but_today_is_fine():
    assert sv.validate_report(valid_form(observation_date=TODAY), today=TODAY).ok
    future = sv.validate_report(valid_form(observation_date=TODAY + timedelta(days=1)), today=TODAY)
    assert not future.ok and "budućnosti" in future.errors[0]


def test_date_accepts_iso_strings_and_datetimes():
    assert sv.validate_report(valid_form(observation_date="2026-09-01"), today=TODAY).ok
    assert sv.validate_report(valid_form(observation_date=datetime(2026, 9, 1, 18, 30)), today=TODAY).ok


def test_garbage_date_is_rejected():
    assert not sv.validate_report(valid_form(observation_date="01.09.2026x"), today=TODAY).ok


# --- report: text lengths -----------------------------------------------------

@pytest.mark.parametrize("field, limit", [
    ("opponent", sv.MAX_OPPONENT_LEN),
    ("observed_position", sv.MAX_POSITION_LEN),
    ("strengths", sv.MAX_STRENGTHS_LEN),
    ("weaknesses", sv.MAX_WEAKNESSES_LEN),
    ("notes", sv.MAX_NOTES_LEN),
])
def test_text_length_limit_is_enforced(field, limit):
    assert sv.validate_report(valid_form(**{field: "x" * limit}), today=TODAY).ok
    too_long = sv.validate_report(valid_form(**{field: "x" * (limit + 1)}), today=TODAY)
    assert not too_long.ok
    assert str(limit) in too_long.errors[0]


# --- report: identity fields --------------------------------------------------

@pytest.mark.parametrize("field, bad", [
    ("player_id", 0), ("player_id", -5), ("player_id", "abc"), ("player_id", 1.5),
    ("season_suffix", "2025/2026"), ("season_suffix", "25_26"),
    ("league_code", "HNL"), ("league_code", "hnl; drop table"),
])
def test_malformed_identity_fields_are_rejected(field, bad):
    assert not sv.validate_report(valid_form(**{field: bad}), today=TODAY).ok


# --- shortlist ----------------------------------------------------------------

def test_shortlist_requires_a_name():
    for empty in (None, "", "   "):
        assert not sv.validate_shortlist(empty, "opis").ok


def test_shortlist_valid_and_trimmed():
    result = sv.validate_shortlist("  U23 krila ", "  opis ")
    assert result.ok
    assert result.data == {"name": "U23 krila", "description": "opis"}
    assert sv.validate_shortlist("Ime", "").data["description"] is None


def test_shortlist_length_limits():
    assert sv.validate_shortlist("x" * sv.MAX_SHORTLIST_NAME_LEN, None).ok
    assert not sv.validate_shortlist("x" * (sv.MAX_SHORTLIST_NAME_LEN + 1), None).ok
    assert not sv.validate_shortlist("Ime", "x" * (sv.MAX_SHORTLIST_DESCRIPTION_LEN + 1)).ok


# --- shortlist entry ----------------------------------------------------------

def test_entry_valid():
    result = sv.validate_shortlist_entry("Prioritet", 1, " brz ")
    assert result.ok
    assert result.data == {"status": "Prioritet", "priority": 1, "note": "brz"}


@pytest.mark.parametrize("status", sv.STATUSES)
def test_every_listed_status_is_accepted(status):
    assert sv.validate_shortlist_entry(status, 3, None).ok


@pytest.mark.parametrize("status", ["Kupljen", "", None, "prioritet"])
def test_unknown_status_is_rejected(status):
    assert not sv.validate_shortlist_entry(status, 3, None).ok


@pytest.mark.parametrize("priority", [0, 6, -1, 2.5, "x", None])
def test_invalid_priority_is_rejected(priority):
    assert not sv.validate_shortlist_entry("Praćenje", priority, None).ok


def test_entry_note_length():
    assert sv.validate_shortlist_entry("Praćenje", 3, "x" * sv.MAX_SHORTLIST_NOTE_LEN).ok
    assert not sv.validate_shortlist_entry("Praćenje", 3, "x" * (sv.MAX_SHORTLIST_NOTE_LEN + 1)).ok


# --- parity with supabase/schema.sql -----------------------------------------

def _sql_string_list(constraint_name):
    """The quoted values inside `constraint <name> check (col in ( ... ))`."""
    match = re.search(rf"constraint {constraint_name}\s+check \(.*?\bin \((.*?)\)\)", SCHEMA_SQL, re.S)
    assert match, f"constraint {constraint_name} not found in schema.sql"
    return re.findall(r"'([^']+)'", match.group(1))


def test_recommendations_match_the_sql_constraint():
    assert _sql_string_list("scouting_reports_recommendation_values") == list(sv.RECOMMENDATIONS)


def test_statuses_match_the_sql_constraint():
    assert _sql_string_list("shortlist_players_status_values") == list(sv.STATUSES)


def test_default_status_and_priority_match_sql_defaults():
    assert f"default '{sv.DEFAULT_STATUS}'" in SCHEMA_SQL
    assert f"default {sv.DEFAULT_PRIORITY}" in SCHEMA_SQL


def test_priority_range_matches_sql():
    assert f"check (priority between {sv.PRIORITY_MIN} and {sv.PRIORITY_MAX})" in SCHEMA_SQL


@pytest.mark.parametrize("column", ["technical", "tactical", "physical", "mental", "potential"])
def test_rating_range_matches_sql(column):
    assert f"check ({column}_rating between {sv.RATING_MIN} and {sv.RATING_MAX})" in SCHEMA_SQL


@pytest.mark.parametrize("fragment", [
    f"char_length(observed_position) between 1 and {sv.MAX_POSITION_LEN}",
    f"opponent is null or char_length(opponent) between 1 and {sv.MAX_OPPONENT_LEN}",
    f"strengths is null or char_length(strengths) <= {sv.MAX_STRENGTHS_LEN}",
    f"weaknesses is null or char_length(weaknesses) <= {sv.MAX_WEAKNESSES_LEN}",
    f"notes is null or char_length(notes) <= {sv.MAX_NOTES_LEN}",
    f"char_length(name) between 1 and {sv.MAX_SHORTLIST_NAME_LEN}",
    f"description is null or char_length(description) <= {sv.MAX_SHORTLIST_DESCRIPTION_LEN}",
    f"note is null or char_length(note) <= {sv.MAX_SHORTLIST_NOTE_LEN}",
])
def test_length_limits_match_sql(fragment):
    assert fragment in SCHEMA_SQL


def test_schema_enables_rls_on_every_table_and_defines_no_policy():
    for table in ("scouting_reports", "shortlists", "shortlist_players"):
        assert f"alter table public.{table}" in SCHEMA_SQL
        assert re.search(rf"alter table public\.{table}\s+enable row level security", SCHEMA_SQL)
    assert "create policy" not in SCHEMA_SQL.lower()


def test_schema_has_the_unique_player_per_shortlist_constraint():
    assert re.search(r"unique \(shortlist_id, player_id\)", SCHEMA_SQL)
