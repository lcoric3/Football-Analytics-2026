"""Tests for src/scouting_database.py.

The repository runs against tests/fake_supabase.py (in memory) - these tests
never call a real Supabase, never need SUPABASE_* variables and never open a
network connection.
"""
import logging

import pytest

from src import scouting_database as db
from tests.fake_supabase import FakeAPIError, FakeSupabaseClient

FAKE_KEY = "sb_secret_THIS_IS_A_FAKE_TEST_KEY_1234567890"
FAKE_URL = "https://example-project.supabase.co"


@pytest.fixture
def client():
    return FakeSupabaseClient()


@pytest.fixture
def repo(client):
    return db.ScoutingRepository(client)


def report_data(**overrides):
    data = {
        "league_code": "hnl", "player_id": 42, "season_suffix": "2025_2026",
        "observation_date": "2026-09-01", "opponent": "Hajduk",
        "observed_position": "Midfielder",
        "technical_rating": 7, "tactical_rating": 6, "physical_rating": 8,
        "mental_rating": 5, "potential_rating": 9,
        "strengths": "Passing", "weaknesses": "Pace", "notes": None,
        "recommendation": "Nastaviti pratiti",
    }
    data.update(overrides)
    return data


# =============================================================================
# Configuration
# =============================================================================

def test_config_prefers_secrets_over_environment():
    secrets = {"SUPABASE_URL": "https://fake-from-secrets.supabase.co", "SUPABASE_SECRET_KEY": "fake-secret-key"}
    environ = {"SUPABASE_URL": "https://fake-from-env.supabase.co", "SUPABASE_SECRET_KEY": "fake-env-key"}
    config = db.load_config(secrets, environ)
    assert config.url == "https://fake-from-secrets.supabase.co"
    assert config.secret_key == "fake-secret-key"


def test_config_falls_back_to_environment():
    environ = {"SUPABASE_URL": FAKE_URL, "SUPABASE_SECRET_KEY": FAKE_KEY}
    config = db.load_config(secrets={}, environ=environ)
    assert config.url == FAKE_URL
    assert config.secret_key == FAKE_KEY


def test_config_can_mix_sources_per_variable():
    secrets = {"SUPABASE_URL": FAKE_URL}
    environ = {"SUPABASE_SECRET_KEY": FAKE_KEY}
    config = db.load_config(secrets, environ)
    assert (config.url, config.secret_key) == (FAKE_URL, FAKE_KEY)
    assert db.config_status(secrets, environ) == {
        "SUPABASE_URL": "st.secrets", "SUPABASE_SECRET_KEY": "environment",
    }


def test_missing_configuration_raises_a_clear_error_naming_the_variables():
    with pytest.raises(db.ConfigError) as excinfo:
        db.load_config(secrets={}, environ={})
    message = str(excinfo.value)
    assert "SUPABASE_URL" in message and "SUPABASE_SECRET_KEY" in message


def test_partially_missing_configuration_names_only_the_missing_variable():
    with pytest.raises(db.ConfigError) as excinfo:
        db.load_config(secrets={}, environ={"SUPABASE_URL": FAKE_URL})
    assert "SUPABASE_SECRET_KEY" in str(excinfo.value)
    assert "SUPABASE_URL" not in str(excinfo.value)


@pytest.mark.parametrize("blank", ["", "   ", None, 123])
def test_blank_values_count_as_missing(blank):
    environ = {"SUPABASE_URL": blank, "SUPABASE_SECRET_KEY": blank}
    with pytest.raises(db.ConfigError):
        db.load_config(secrets={}, environ=environ)


def test_url_must_be_https():
    environ = {"SUPABASE_URL": "http://evil.example.com", "SUPABASE_SECRET_KEY": FAKE_KEY}
    with pytest.raises(db.ConfigError, match="https"):
        db.load_config(secrets={}, environ=environ)
    # ...except a local Supabase instance used for development.
    environ["SUPABASE_URL"] = "http://localhost:54321"
    assert db.load_config(secrets={}, environ=environ).url == "http://localhost:54321"


def test_trailing_slash_is_removed_from_the_url():
    environ = {"SUPABASE_URL": FAKE_URL + "/", "SUPABASE_SECRET_KEY": FAKE_KEY}
    assert db.load_config(secrets={}, environ=environ).url == FAKE_URL


def test_a_broken_secrets_object_is_treated_as_no_secrets():
    class ExplodingSecrets:
        def __getitem__(self, key):
            raise FileNotFoundError("no secrets.toml")   # what Streamlit does without a file

    environ = {"SUPABASE_URL": FAKE_URL, "SUPABASE_SECRET_KEY": FAKE_KEY}
    assert db.load_config(ExplodingSecrets(), environ).url == FAKE_URL


def test_the_key_never_appears_in_repr_or_str_of_the_config():
    config = db.load_config(secrets={}, environ={"SUPABASE_URL": FAKE_URL, "SUPABASE_SECRET_KEY": FAKE_KEY})
    assert FAKE_KEY not in repr(config)
    assert FAKE_KEY not in str(config)


def test_config_status_reports_sources_but_never_values():
    status = db.config_status({"SUPABASE_URL": FAKE_URL}, {"SUPABASE_SECRET_KEY": FAKE_KEY})
    assert FAKE_KEY not in str(status) and FAKE_URL not in str(status)
    assert db.config_status({}, {}) == {"SUPABASE_URL": None, "SUPABASE_SECRET_KEY": None}


# =============================================================================
# Error handling / secret safety
# =============================================================================

def test_unexpected_errors_become_safe_database_errors(repo, client):
    client.fail_with = RuntimeError(f"connection failed for {FAKE_URL} with key {FAKE_KEY}")
    with pytest.raises(db.ScoutingDatabaseError) as excinfo:
        repo.list_reports()
    message = str(excinfo.value)
    assert "RuntimeError" in message
    assert FAKE_KEY not in message and FAKE_URL not in message      # raw text is dropped
    assert excinfo.value.__cause__ is None                           # and not chained


def test_postgrest_style_errors_keep_their_code_and_message(repo, client):
    client.fail_with = FakeAPIError("42501", "permission denied for table scouting_reports")
    with pytest.raises(db.ScoutingDatabaseError) as excinfo:
        repo.list_reports()
    assert "42501" in str(excinfo.value)
    assert "permission denied" in str(excinfo.value)


def test_errors_are_logged_without_secrets(repo, client, caplog):
    client.fail_with = RuntimeError(f"boom {FAKE_KEY}")
    with caplog.at_level(logging.DEBUG):
        with pytest.raises(db.ScoutingDatabaseError):
            repo.list_reports()
    assert FAKE_KEY not in caplog.text


# =============================================================================
# Connection check
# =============================================================================

def test_check_connection_ok(repo):
    assert repo.check_connection() == {
        "scouting_reports": None, "shortlists": None, "shortlist_players": None,
    }


def test_check_connection_reports_the_failing_table(repo, client):
    client.fail_with = FakeAPIError("42P01", 'relation "public.scouting_reports" does not exist')
    result = repo.check_connection()
    assert "42P01" in result["scouting_reports"]
    assert result["shortlists"] is None and result["shortlist_players"] is None


# =============================================================================
# Scouting reports: create / read / update / delete
# =============================================================================

def test_create_and_read_back_a_report(repo):
    created = repo.create_report(report_data())
    assert created["id"] and created["player_id"] == 42
    fetched = repo.list_reports(player_id=42, season_suffix="2025_2026")
    assert [r["id"] for r in fetched] == [created["id"]]
    assert fetched[0]["recommendation"] == "Nastaviti pratiti"


def test_create_ignores_unknown_fields(repo):
    created = repo.create_report(report_data(id="hacked", created_at="1999", sneaky="x"))
    assert created["id"] != "hacked"
    assert "sneaky" not in created


def test_list_reports_filters_by_player_and_season(repo):
    repo.create_report(report_data(player_id=1))
    repo.create_report(report_data(player_id=2))
    repo.create_report(report_data(player_id=1, season_suffix="2024_2025"))
    assert len(repo.list_reports()) == 3
    assert len(repo.list_reports(player_id=1)) == 2
    assert len(repo.list_reports(player_id=1, season_suffix="2025_2026")) == 1
    assert repo.list_reports(player_id=999) == []
    assert len(repo.list_reports(league_code="hnl")) == 3
    assert repo.list_reports(league_code="premier") == []


def test_list_reports_is_newest_observation_first(repo):
    repo.create_report(report_data(observation_date="2026-03-01"))
    repo.create_report(report_data(observation_date="2026-09-01"))
    repo.create_report(report_data(observation_date="2026-06-01"))
    dates = [r["observation_date"] for r in repo.list_reports()]
    assert dates == ["2026-09-01", "2026-06-01", "2026-03-01"]


def test_update_a_report_changes_only_the_given_fields_and_bumps_updated_at(repo):
    created = repo.create_report(report_data())
    updated = repo.update_report(created["id"], {"technical_rating": 9, "notes": "Second viewing"})
    assert updated["technical_rating"] == 9
    assert updated["notes"] == "Second viewing"
    assert updated["tactical_rating"] == 6                     # untouched
    assert updated["updated_at"] > created["updated_at"]       # trigger imitation


def test_update_a_missing_report_is_a_clear_error(repo):
    with pytest.raises(db.ScoutingDatabaseError, match="nije pronađen"):
        repo.update_report("00000000-0000-0000-0000-000000000000", {"notes": "x"})


def test_delete_a_report_requires_confirmation(repo):
    created = repo.create_report(report_data())
    with pytest.raises(db.ConfirmationRequired):
        repo.delete_report(created["id"])
    with pytest.raises(db.ConfirmationRequired):
        repo.delete_report(created["id"], confirmed=False)
    with pytest.raises(db.ConfirmationRequired):
        repo.delete_report(created["id"], confirmed="yes")       # truthy but not True
    assert len(repo.list_reports()) == 1                          # nothing was deleted


def test_delete_a_report_after_confirmation(repo):
    keep = repo.create_report(report_data(player_id=1))
    doomed = repo.create_report(report_data(player_id=2))
    repo.delete_report(doomed["id"], confirmed=True)
    assert [r["id"] for r in repo.list_reports()] == [keep["id"]]


def test_reports_are_fetched_across_pages(repo, client, monkeypatch):
    monkeypatch.setattr(db, "PAGE_SIZE", 2)
    for player_id in range(1, 6):
        repo.create_report(report_data(player_id=player_id))
    assert len(repo.list_reports()) == 5
    selects = [c for c in client.calls if c == ("scouting_reports", "select")]
    assert len(selects) == 3                                      # 2 + 2 + 1 rows


# =============================================================================
# Shortlists
# =============================================================================

def test_create_list_and_update_a_shortlist(repo):
    created = repo.create_shortlist("U23 krila", "Brzi igrači do 23 godine")
    assert created["name"] == "U23 krila"
    assert [s["name"] for s in repo.list_shortlists()] == ["U23 krila"]

    updated = repo.update_shortlist(created["id"], "U21 krila", "Novi opis")
    assert (updated["name"], updated["description"]) == ("U21 krila", "Novi opis")
    assert updated["updated_at"] > created["updated_at"]


def test_shortlists_are_listed_by_name(repo):
    for name in ("Zadnja", "Prva", "Srednja"):
        repo.create_shortlist(name)
    assert [s["name"] for s in repo.list_shortlists()] == ["Prva", "Srednja", "Zadnja"]


def test_duplicate_shortlist_names_are_rejected_ignoring_case(repo):
    repo.create_shortlist("Napadači")
    with pytest.raises(db.DuplicateShortlistError):
        repo.create_shortlist("napadači")
    other = repo.create_shortlist("Braniči")
    with pytest.raises(db.DuplicateShortlistError):
        repo.update_shortlist(other["id"], "NAPADAČI")


def test_renaming_a_shortlist_to_its_own_name_is_allowed(repo):
    created = repo.create_shortlist("Napadači", "a")
    assert repo.update_shortlist(created["id"], "Napadači", "b")["description"] == "b"


def test_delete_a_shortlist_requires_confirmation_and_cascades(repo):
    shortlist = repo.create_shortlist("Za brisanje")
    repo.add_player_to_shortlist(shortlist["id"], "hnl", 1, "2025_2026")
    with pytest.raises(db.ConfirmationRequired):
        repo.delete_shortlist(shortlist["id"])
    assert len(repo.list_shortlists()) == 1

    repo.delete_shortlist(shortlist["id"], confirmed=True)
    assert repo.list_shortlists() == []
    assert repo.list_shortlist_players() == []                    # ON DELETE CASCADE


# =============================================================================
# Shortlist players (incl. double-add protection)
# =============================================================================

@pytest.fixture
def shortlist(repo):
    return repo.create_shortlist("Test lista")


def test_add_a_player_with_defaults(repo, shortlist):
    entry = repo.add_player_to_shortlist(shortlist["id"], "hnl", 7, "2025_2026")
    assert entry["status"] == "Praćenje"
    assert entry["priority"] == 3
    assert entry["note"] is None
    assert [e["player_id"] for e in repo.list_shortlist_players(shortlist["id"])] == [7]


def test_add_a_player_with_status_priority_and_note(repo, shortlist):
    entry = repo.add_player_to_shortlist(
        shortlist["id"], "hnl", 7, "2025_2026", status="Prioritet", priority=1, note="Brz"
    )
    assert (entry["status"], entry["priority"], entry["note"]) == ("Prioritet", 1, "Brz")


def test_the_same_player_cannot_be_added_twice_to_one_shortlist(repo, shortlist):
    repo.add_player_to_shortlist(shortlist["id"], "hnl", 7, "2025_2026")
    with pytest.raises(db.DuplicatePlayerError, match="već na ovoj shortlisti"):
        repo.add_player_to_shortlist(shortlist["id"], "hnl", 7, "2025_2026")
    assert len(repo.list_shortlist_players(shortlist["id"])) == 1


def test_duplicate_is_detected_even_for_a_different_season(repo, shortlist):
    # The same person, viewed via another season, is still the same player.
    repo.add_player_to_shortlist(shortlist["id"], "hnl", 7, "2025_2026")
    with pytest.raises(db.DuplicatePlayerError):
        repo.add_player_to_shortlist(shortlist["id"], "hnl", 7, "2024_2025")


def test_the_same_player_can_be_on_different_shortlists(repo, shortlist):
    other = repo.create_shortlist("Druga lista")
    repo.add_player_to_shortlist(shortlist["id"], "hnl", 7, "2025_2026")
    repo.add_player_to_shortlist(other["id"], "hnl", 7, "2025_2026")
    assert len(repo.list_shortlist_players()) == 2


def test_duplicate_protection_relies_on_the_database_constraint(repo, shortlist, client):
    """Only ONE insert is attempted per call (no separate 'look first' read),
    so the UNIQUE constraint is what protects against a race between two
    requests."""
    repo.add_player_to_shortlist(shortlist["id"], "hnl", 7, "2025_2026")
    client.calls.clear()
    with pytest.raises(db.DuplicatePlayerError):
        repo.add_player_to_shortlist(shortlist["id"], "hnl", 7, "2025_2026")
    assert client.calls == [("shortlist_players", "insert")]


def test_duplicate_detection_works_with_the_real_postgrest_error_type(repo, shortlist, client):
    """The fake error mimics postgrest's APIError; this pins that assumption
    against the real class (offline - it only constructs the exception)."""
    postgrest_exceptions = pytest.importorskip("postgrest.exceptions")
    repo.add_player_to_shortlist(shortlist["id"], "hnl", 7, "2025_2026")
    client.fail_with = postgrest_exceptions.APIError(
        {"message": "duplicate key value violates unique constraint", "code": "23505",
         "hint": None, "details": None}
    )
    with pytest.raises(db.DuplicatePlayerError):
        repo.add_player_to_shortlist(shortlist["id"], "hnl", 7, "2025_2026")


def test_other_insert_errors_are_not_mistaken_for_duplicates(repo, shortlist, client):
    client.fail_with = FakeAPIError("23514", "violates check constraint shortlist_players_status_values")
    with pytest.raises(db.ScoutingDatabaseError) as excinfo:
        repo.add_player_to_shortlist(shortlist["id"], "hnl", 7, "2025_2026", status="Kupljen")
    assert not isinstance(excinfo.value, db.DuplicatePlayerError)
    assert "23514" in str(excinfo.value)


def test_adding_to_a_missing_shortlist_fails_cleanly(repo):
    with pytest.raises(db.ScoutingDatabaseError):
        repo.add_player_to_shortlist("00000000-0000-0000-0000-000000000000", "hnl", 7, "2025_2026")


def test_update_a_shortlist_player(repo, shortlist):
    entry = repo.add_player_to_shortlist(shortlist["id"], "hnl", 7, "2025_2026")
    updated = repo.update_shortlist_player(entry["id"], "Odbijen", 5, "Ozljeda")
    assert (updated["status"], updated["priority"], updated["note"]) == ("Odbijen", 5, "Ozljeda")
    assert updated["updated_at"] > entry["updated_at"]


def test_remove_a_shortlist_player_requires_confirmation(repo, shortlist):
    entry = repo.add_player_to_shortlist(shortlist["id"], "hnl", 7, "2025_2026")
    with pytest.raises(db.ConfirmationRequired):
        repo.remove_shortlist_player(entry["id"])
    assert len(repo.list_shortlist_players(shortlist["id"])) == 1

    repo.remove_shortlist_player(entry["id"], confirmed=True)
    assert repo.list_shortlist_players(shortlist["id"]) == []


def test_a_removed_player_can_be_added_again(repo, shortlist):
    entry = repo.add_player_to_shortlist(shortlist["id"], "hnl", 7, "2025_2026")
    repo.remove_shortlist_player(entry["id"], confirmed=True)
    repo.add_player_to_shortlist(shortlist["id"], "hnl", 7, "2025_2026")
    assert len(repo.list_shortlist_players(shortlist["id"])) == 1


def test_list_shortlist_players_is_scoped_to_one_shortlist(repo, shortlist):
    other = repo.create_shortlist("Druga")
    repo.add_player_to_shortlist(shortlist["id"], "hnl", 1, "2025_2026")
    repo.add_player_to_shortlist(other["id"], "hnl", 2, "2025_2026")
    assert [e["player_id"] for e in repo.list_shortlist_players(shortlist["id"])] == [1]
    assert [e["player_id"] for e in repo.list_shortlist_players(other["id"])] == [2]
    assert len(repo.list_shortlist_players()) == 2
