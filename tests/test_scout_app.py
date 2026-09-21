"""
UI smoke/behaviour tests for scout_app.py (the PRIVATE scouting app), driven
through Streamlit's headless AppTest harness.

Hermetic by construction:
  * player data is the synthetic conftest fixture written to a temp folder
    (season_config.PROCESSED_DIR is redirected) - the real data/ is untouched
  * the database is tests/fake_supabase.py - no Supabase, no network
  * dotenv.load_dotenv is disabled, so a real local .env is never read
  * SUPABASE_* variables are cleared unless a test sets fake ones
  * the app is behind its password gate: tests log in with a FAKE password
    (open_page does it), and the gate itself is tested at the bottom
"""
import ast
import logging
import subprocess
import sys
from pathlib import Path

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from src import scout_players, scout_ratings, scouting_database, season_config
from tests.fake_supabase import FakeAPIError, FakeSupabaseClient

APP_PATH = str(Path(__file__).resolve().parent.parent / "scout_app.py")
FAKE_KEY = "sb_secret_FAKE_TEST_KEY_1234567890"
FAKE_URL = "https://example-project.supabase.co"
TEST_PASSWORD = "fake-test-password-Zx9!-not-a-real-secret"
WRONG_PASSWORD = "fake-wrong-password-4711"

PAGES = [
    "Početna", "Pretraživanje igrača", "Skautska procjena",
    "Shortliste", "Usporedba igrača", "Postavke veze",
]


# --- fixtures ------------------------------------------------------------------

@pytest.fixture
def app_env(tmp_path, monkeypatch, scored_df):
    """Synthetic player data, no .env, no Supabase configuration - but the
    (fake) login password IS set, so the gate can be passed."""
    monkeypatch.setattr(season_config, "PROCESSED_DIR", str(tmp_path))
    scored_df.to_csv(tmp_path / "hnl_player_scored_2025_2026.csv", index=False)
    scored_df.head(6).to_csv(tmp_path / "hnl_player_scored_2024_2025.csv", index=False)
    monkeypatch.setattr("dotenv.load_dotenv", lambda *args, **kwargs: False)
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SECRET_KEY", raising=False)
    monkeypatch.setenv("SCOUT_APP_PASSWORD", TEST_PASSWORD)
    st.cache_data.clear()
    st.cache_resource.clear()
    yield
    st.cache_data.clear()
    st.cache_resource.clear()


@pytest.fixture
def fake_db(app_env, monkeypatch):
    """A configured app whose Supabase client is the in-memory fake."""
    client = FakeSupabaseClient()
    monkeypatch.setenv("SUPABASE_URL", FAKE_URL)
    monkeypatch.setenv("SUPABASE_SECRET_KEY", FAKE_KEY)
    monkeypatch.setattr(scouting_database, "create_client", lambda config: client)
    return client


# --- helpers -------------------------------------------------------------------

def press(at, label):
    """Click the (single) button with this label, then rerun."""
    buttons = [b for b in at.button if b.label == label]
    assert len(buttons) == 1, f"expected exactly one {label!r} button, found {len(buttons)}"
    buttons[0].click().run()


def new_session():
    """A fresh browser session showing the lock screen."""
    return AppTest.from_file(APP_PATH, default_timeout=60).run()


def login(at, password=TEST_PASSWORD):
    """Type a password into the lock screen and press 'Prijava'."""
    at.text_input[0].set_value(password)
    press(at, "Prijava")
    return at


def open_page(page):
    """A logged-in session on the given page."""
    at = login(new_session())
    assert at.sidebar.radio, "login did not unlock the app"
    at.sidebar.radio[0].set_value(page).run()
    return at


def has_button(at, label):
    return any(b.label == label for b in at.button)


def visible_text(at):
    parts = []
    for group in (at.markdown, at.error, at.warning, at.info, at.success, at.caption, at.metric):
        parts += [str(getattr(el, "value", "")) for el in group]
    parts += [str(df.value) for df in at.dataframe]
    return "\n".join(parts)


def metric_values(at):
    return {m.label: m.value for m in at.metric}


def save_report_for(at, player_name, **slider_overrides):
    """On the 'Skautska procjena' page: search a player and save a report."""
    at.text_input(key="assess_query").set_value(player_name).run()
    for key, value in slider_overrides.items():
        at.slider(key=key).set_value(value)
    press(at, "Spremi izvještaj")


# =============================================================================
# Without configuration: never crashes, explains what to do
# =============================================================================

@pytest.mark.parametrize("page", PAGES)
def test_every_page_renders_without_configuration_and_without_traceback(app_env, page):
    at = open_page(page)
    assert not at.exception, [e.message for e in at.exception]


@pytest.mark.parametrize("page", ["Početna", "Skautska procjena", "Shortliste", "Postavke veze"])
def test_pages_that_need_the_database_explain_and_link_to_the_setup_guide(app_env, page):
    at = open_page(page)
    warnings = " ".join(w.value for w in at.warning)
    assert "SCOUTING_SETUP.md" in warnings
    assert "SUPABASE_URL" in warnings and "SUPABASE_SECRET_KEY" in warnings


def test_search_works_without_a_database_using_analytical_scores_only(app_env):
    at = open_page("Pretraživanje igrača")
    assert not at.exception
    table = at.dataframe[0].value
    assert "Analitička ocjena" in table.columns
    assert table["Skautska ocjena"].isna().all()          # nothing invented
    assert table["Kombinirana ocjena"].isna().all()
    assert len(table) == 9


def test_comparison_works_without_a_database(app_env):
    at = open_page("Usporedba igrača")
    at.multiselect[0].set_value([1, 4]).run()
    assert not at.exception
    assert len(at.dataframe) >= 3


def test_settings_page_reports_missing_variables_without_values(app_env):
    at = open_page("Postavke veze")
    status = at.dataframe[0].value
    assert status["Izvor"].tolist() == ["NEDOSTAJE", "NEDOSTAJE"]


def test_missing_data_folder_is_reported_not_a_crash(app_env, monkeypatch, tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.setattr(season_config, "PROCESSED_DIR", str(empty))
    st.cache_data.clear()
    for page in ("Početna", "Pretraživanje igrača", "Usporedba igrača"):
        at = open_page(page)
        assert not at.exception
        assert any("pipeline" in e.value for e in at.error)


# =============================================================================
# Player search + profile
# =============================================================================

def test_search_filters_narrow_the_table(fake_db):
    at = open_page("Pretraživanje igrača")
    at.multiselect[1].set_value(["Defender"]).run()            # Pozicija
    assert set(at.dataframe[0].value["Pozicija"]) == {"Defender"}
    at.text_input[0].set_value("Two").run()                    # Ime igrača
    assert at.dataframe[0].value["Igrač"].tolist() == ["Defender Two"]


def test_profile_shows_scores_and_the_goalkeeper_caveat(fake_db):
    at = open_page("Pretraživanje igrača")
    at.text_input[0].set_value("Goalkeeper One").run()
    assert not at.exception
    assert any("goalkeeper_score" in c.value for c in at.caption)
    assert "Analitička ocjena" in metric_values(at)


# =============================================================================
# Scouting reports: create / validate / edit / delete
# =============================================================================

def test_creating_a_report_saves_it_and_shows_the_scores(fake_db, scored_df):
    at = open_page("Skautska procjena")
    save_report_for(at, "Midfielder One")

    assert not at.exception
    stored = fake_db.tables["scouting_reports"]
    assert len(stored) == 1
    report = stored[0]
    assert (report["player_id"], report["season_suffix"], report["league_code"]) == (4, "2025_2026", "hnl")
    assert report["technical_rating"] == 5 and report["recommendation"] == "Nastaviti pratiti"
    assert any("Izvještaj je spremljen" in s.value for s in at.success)

    overall = float(scored_df.loc[scored_df["player_id"] == 4, "overall_score"].iloc[0])
    expected = scout_ratings.summarize_reports([report], overall)
    metrics = metric_values(at)
    assert metrics["Skautska ocjena"] == f"{expected['scout_score']:.1f}" == "44.4"
    assert metrics["Kombinirana ocjena"] == f"{expected['combined_score']:.1f}"
    assert metrics["Skautskih izvještaja"] == "1"


def test_the_new_report_form_is_reset_after_saving_to_avoid_double_submits(fake_db):
    at = open_page("Skautska procjena")
    save_report_for(at, "Midfielder One", **{"new_4_0_technical_rating": 9})
    assert fake_db.tables["scouting_reports"][0]["technical_rating"] == 9
    # Fresh form (new key): the slider is back at its default, not at 9.
    assert at.slider(key="new_4_1_technical_rating").value == 5


def test_invalid_input_shows_a_message_and_saves_nothing(fake_db):
    at = open_page("Skautska procjena")
    at.text_input(key="assess_query").set_value("Midfielder One").run()
    at.text_input(key="new_4_0_position").set_value("   ")
    press(at, "Spremi izvještaj")
    assert not at.exception
    assert any("Promatrana pozicija" in e.value for e in at.error)
    assert fake_db.tables["scouting_reports"] == []


def test_without_a_report_only_the_analytical_score_is_shown(fake_db):
    at = open_page("Skautska procjena")
    at.text_input(key="assess_query").set_value("Midfielder One").run()
    metrics = metric_values(at)
    assert metrics["Skautska ocjena"] == "—"
    assert metrics["Kombinirana ocjena"] == "—"                 # not a made-up blend
    assert metrics["Skautskih izvještaja"] == "0"
    assert any("samo analitička ocjena" in i.value for i in at.info)


def test_editing_a_report_updates_it(fake_db):
    at = open_page("Skautska procjena")
    save_report_for(at, "Midfielder One")
    report_id = fake_db.tables["scouting_reports"][0]["id"]

    at.slider(key=f"edit_{report_id}_technical_rating").set_value(9)
    at.text_area(key=f"edit_{report_id}_notes").set_value("Second viewing")
    press(at, "Spremi izmjene")

    assert not at.exception
    stored = fake_db.tables["scouting_reports"][0]
    assert stored["technical_rating"] == 9
    assert stored["notes"] == "Second viewing"
    assert stored["updated_at"] > stored["created_at"]
    assert any("Izmjene su spremljene" in s.value for s in at.success)


def test_deleting_a_report_requires_confirmation(fake_db):
    at = open_page("Skautska procjena")
    save_report_for(at, "Midfielder One")
    report_id = fake_db.tables["scouting_reports"][0]["id"]

    delete_button = at.button(key=f"delete_report_{report_id}")
    assert delete_button.disabled                                # locked until confirmed
    assert len(fake_db.tables["scouting_reports"]) == 1

    at.checkbox(key=f"confirm_delete_report_{report_id}").check().run()
    assert not at.button(key=f"delete_report_{report_id}").disabled
    at.button(key=f"delete_report_{report_id}").click().run()

    assert fake_db.tables["scouting_reports"] == []
    assert any("obrisan" in s.value for s in at.success)


# =============================================================================
# Shortlists
# =============================================================================

def test_create_a_shortlist_add_a_player_and_block_a_duplicate(fake_db):
    at = open_page("Shortliste")
    assert not at.exception
    [name_input] = [t for t in at.text_input if t.label == "Naziv *"]
    name_input.set_value("U23 krila").run()
    press(at, "Stvori shortlistu")
    assert [s["name"] for s in fake_db.tables["shortlists"]] == ["U23 krila"]
    shortlist_id = fake_db.tables["shortlists"][0]["id"]

    at.text_input(key=f"shortlist_add_{shortlist_id}_query").set_value("Attacker One").run()
    press(at, "Dodaj na shortlistu")
    members = fake_db.tables["shortlist_players"]
    assert [(m["player_id"], m["status"], m["priority"]) for m in members] == [(1, "Praćenje", 3)]

    # The same player is no longer offered, so it cannot be added twice from the UI...
    at.text_input(key=f"shortlist_add_{shortlist_id}_query").set_value("Attacker One").run()
    assert not has_button(at, "Dodaj na shortlistu")
    assert len(fake_db.tables["shortlist_players"]) == 1


def test_a_duplicate_reported_by_the_database_is_shown_not_crashed(fake_db, monkeypatch):
    """If two requests race, the UNIQUE constraint rejects the second one at
    insert time (repository behaviour is tested in test_scouting_database).
    Here: when the repository reports that, the UI shows a warning and adds
    nothing instead of crashing."""
    def already_there(self, *args, **kwargs):
        raise scouting_database.DuplicatePlayerError("Igrač je već na ovoj shortlisti.")

    at = open_page("Shortliste")
    [name_input] = [t for t in at.text_input if t.label == "Naziv *"]
    name_input.set_value("Lista").run()
    press(at, "Stvori shortlistu")
    shortlist_id = fake_db.tables["shortlists"][0]["id"]

    monkeypatch.setattr(scouting_database.ScoutingRepository, "add_player_to_shortlist", already_there)
    at.text_input(key=f"shortlist_add_{shortlist_id}_query").set_value("Attacker One").run()
    press(at, "Dodaj na shortlistu")
    assert not at.exception
    assert any("već na ovoj shortlisti" in w.value for w in at.warning)
    assert fake_db.tables["shortlist_players"] == []


def _shortlist_with_two_players(fake_db):
    at = open_page("Shortliste")
    [name_input] = [t for t in at.text_input if t.label == "Naziv *"]
    name_input.set_value("Lista").run()
    press(at, "Stvori shortlistu")
    shortlist_id = fake_db.tables["shortlists"][0]["id"]
    for player in ("Attacker One", "Midfielder One"):
        at.text_input(key=f"shortlist_add_{shortlist_id}_query").set_value(player).run()
        press(at, "Dodaj na shortlistu")
    assert len(fake_db.tables["shortlist_players"]) == 2
    return at


def test_shortlist_can_be_sorted_by_all_three_scores(fake_db):
    at = _shortlist_with_two_players(fake_db)
    for label in ("Kombinirana ocjena", "Skautska ocjena", "Analitička ocjena"):
        at.selectbox(key="shortlist_sort").set_value(label).run()
        assert not at.exception
    # By analytical score the better player is listed first.
    table = [d.value for d in at.dataframe if "Status" in d.value.columns][0]
    assert table["Analitička ocjena"].is_monotonic_decreasing


def test_editing_a_shortlist_player_updates_status_priority_and_note(fake_db):
    at = _shortlist_with_two_players(fake_db)
    entry = fake_db.tables["shortlist_players"][0]
    at.selectbox(key=f"entry_status_{entry['id']}").set_value("Prioritet")
    at.slider(key=f"entry_priority_{entry['id']}").set_value(1)
    at.text_area(key=f"entry_note_{entry['id']}").set_value("Brz i tehničan")
    press(at, "Spremi izmjene igrača")

    assert not at.exception
    stored = fake_db.tables["shortlist_players"][0]
    assert (stored["status"], stored["priority"], stored["note"]) == ("Prioritet", 1, "Brz i tehničan")


def test_removing_a_player_from_a_shortlist_requires_confirmation(fake_db):
    at = _shortlist_with_two_players(fake_db)
    entry = fake_db.tables["shortlist_players"][0]

    assert at.button(key=f"remove_entry_{entry['id']}").disabled
    assert len(fake_db.tables["shortlist_players"]) == 2

    at.checkbox(key=f"confirm_remove_entry_{entry['id']}").check().run()
    at.button(key=f"remove_entry_{entry['id']}").click().run()
    assert [m["id"] for m in fake_db.tables["shortlist_players"]] != [entry["id"]]
    assert len(fake_db.tables["shortlist_players"]) == 1
    assert any("uklonjen" in s.value for s in at.success)


def test_deleting_a_shortlist_requires_confirmation(fake_db):
    at = open_page("Shortliste")
    [name_input] = [t for t in at.text_input if t.label == "Naziv *"]
    name_input.set_value("Lista").run()
    press(at, "Stvori shortlistu")
    shortlist_id = fake_db.tables["shortlists"][0]["id"]

    assert at.button(key=f"delete_shortlist_{shortlist_id}").disabled
    at.checkbox(key=f"confirm_delete_shortlist_{shortlist_id}").check().run()
    at.button(key=f"delete_shortlist_{shortlist_id}").click().run()
    assert fake_db.tables["shortlists"] == []


def test_duplicate_shortlist_name_gives_a_clear_message(fake_db):
    at = open_page("Shortliste")
    [name_input] = [t for t in at.text_input if t.label == "Naziv *"]
    name_input.set_value("Lista").run()
    press(at, "Stvori shortlistu")
    [at.text_input[i] for i, t in enumerate(at.text_input) if t.label == "Naziv *"][0].set_value("lista").run()
    press(at, "Stvori shortlistu")
    assert not at.exception
    assert any("već postoji" in e.value for e in at.error)
    assert len(fake_db.tables["shortlists"]) == 1


# =============================================================================
# Comparison
# =============================================================================

def test_comparison_needs_two_players_and_shows_radar_and_bars(fake_db):
    at = open_page("Usporedba igrača")
    at.multiselect[0].set_value([1]).run()
    assert any("najmanje dva" in i.value for i in at.info)

    at.multiselect[0].set_value([1, 4, 6]).run()
    assert not at.exception
    assert len(at.get("plotly_chart")) == 1
    at.radio[0].set_value("Stupčasti").run()
    assert not at.exception and len(at.get("plotly_chart")) == 1


def test_comparison_shows_scout_and_combined_scores_when_reports_exist(fake_db):
    at = open_page("Skautska procjena")
    save_report_for(at, "Midfielder One")
    at = open_page("Usporedba igrača")
    at.multiselect[0].set_value([4, 1]).run()
    scores = [d.value for d in at.dataframe if "Skautska ocjena" in d.value.columns][0]
    by_name = scores.set_index("Igrač")
    assert by_name.loc["Midfielder One", "Skautska ocjena"] == 44.4
    assert by_name.loc["Attacker One", "Skautska ocjena"] != by_name.loc["Attacker One", "Skautska ocjena"]  # NaN


# =============================================================================
# Database problems and secrets
# =============================================================================

def test_missing_tables_show_a_readable_message_not_a_traceback(fake_db):
    at = login(new_session())
    # The fake raises once, so arm it right before the run for the page under test.
    fake_db.fail_with = FakeAPIError("42P01", 'relation "public.scouting_reports" does not exist')
    at.sidebar.radio[0].set_value("Skautska procjena").run()
    assert not at.exception
    assert any("42P01" in e.value and "schema.sql" in e.value for e in at.error)


def test_connection_test_button_reports_each_table(fake_db):
    at = open_page("Postavke veze")
    press(at, "Provjeri vezu s bazom")
    assert not at.exception
    ok = [s.value for s in at.success]
    assert len(ok) == 3 and all("OK" in s for s in ok)


def test_the_secret_key_and_url_are_never_rendered(fake_db):
    for page in PAGES:
        at = open_page(page)
        text = visible_text(at)
        assert FAKE_KEY not in text
        assert FAKE_URL not in text
    at = open_page("Postavke veze")
    press(at, "Provjeri vezu s bazom")
    assert FAKE_KEY not in visible_text(at)


def test_the_key_is_not_stored_in_session_state(fake_db):
    at = open_page("Postavke veze")
    press(at, "Provjeri vezu s bazom")
    dumped = repr(at.session_state.to_dict())
    assert FAKE_KEY not in dumped and FAKE_URL not in dumped


def test_a_failing_client_setup_is_reported_without_leaking_the_key(app_env, monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", FAKE_URL)
    monkeypatch.setenv("SUPABASE_SECRET_KEY", FAKE_KEY)

    def broken(config):
        raise ValueError(f"Invalid API key {config.secret_key}")

    monkeypatch.setattr(scouting_database, "create_client", broken)
    at = open_page("Skautska procjena")
    assert not at.exception
    text = visible_text(at)
    assert "ValueError" in text and FAKE_KEY not in text


def test_secrets_from_streamlit_secrets_are_used(app_env, monkeypatch):
    client = FakeSupabaseClient()
    monkeypatch.setattr(scouting_database, "create_client", lambda config: client)
    at = AppTest.from_file(APP_PATH, default_timeout=60)
    at.secrets["SUPABASE_URL"] = FAKE_URL
    at.secrets["SUPABASE_SECRET_KEY"] = FAKE_KEY
    at.run()
    login(at)
    at.sidebar.radio[0].set_value("Postavke veze").run()
    assert at.dataframe[0].value["Izvor"].tolist() == ["Streamlit Secrets", "Streamlit Secrets"]
    assert FAKE_KEY not in visible_text(at)


# =============================================================================
# Login gate (SCOUT_APP_PASSWORD) - second layer, on top of Streamlit's
# "Only specific people can view this app"
# =============================================================================

@pytest.fixture
def spies(fake_db, monkeypatch):
    """Counts the two things that must NOT happen before login: building the
    Supabase client and loading player data."""
    calls = {"client": 0, "players": 0}
    real_load = scout_players.load_league_players

    def counting_create_client(config):
        calls["client"] += 1
        return fake_db

    def counting_load(league_code):
        calls["players"] += 1
        return real_load(league_code)

    monkeypatch.setattr(scouting_database, "create_client", counting_create_client)
    monkeypatch.setattr(scout_players, "load_league_players", counting_load)
    return calls


NOTHING_HAPPENED = {"client": 0, "players": 0}


@pytest.mark.parametrize("blank", [None, "", "   "])
def test_without_a_password_the_app_stays_locked(spies, monkeypatch, blank):
    if blank is None:
        monkeypatch.delenv("SCOUT_APP_PASSWORD")
    else:
        monkeypatch.setenv("SCOUT_APP_PASSWORD", blank)
    at = new_session()
    assert not at.exception
    assert not at.sidebar.radio                                   # no navigation at all
    assert not at.dataframe and not at.metric                     # no data
    assert not at.text_input                                      # nothing to log in with
    text = visible_text(at)
    assert "zaključana" in text and "SCOUTING_SETUP.md" in text
    # The message is safe: it names neither the secret nor the database.
    assert "SCOUT_APP_PASSWORD" not in text and "Supabase" not in text and "SUPABASE" not in text
    assert spies == NOTHING_HAPPENED                              # even though Supabase IS configured


def test_the_lock_screen_shows_no_data_before_login(spies):
    at = new_session()
    assert not at.exception
    assert at.text_input and any(b.label == "Prijava" for b in at.button)
    assert not at.sidebar.radio and not at.dataframe and not at.metric
    assert spies == NOTHING_HAPPENED


@pytest.mark.parametrize("wrong", [
    WRONG_PASSWORD, "", TEST_PASSWORD.upper(), TEST_PASSWORD[:-1], TEST_PASSWORD + "x",
])
def test_a_wrong_password_does_not_unlock_the_app(spies, wrong):
    at = login(new_session(), wrong)
    assert not at.exception
    assert not at.sidebar.radio and not at.dataframe and not at.metric
    assert any("Pogrešna zaporka" in e.value for e in at.error)
    assert "scout_authenticated" not in at.session_state
    assert spies == NOTHING_HAPPENED


def test_the_correct_password_unlocks_the_app(spies):
    at = login(new_session())
    assert not at.exception
    assert at.sidebar.radio
    assert at.session_state["scout_authenticated"] is True
    assert not any("Pogrešna" in e.value for e in at.error)
    assert spies["client"] == 1 and spies["players"] >= 1


def test_surrounding_spaces_are_ignored_but_case_matters(spies):
    """A pasted password often carries stray spaces; case still counts."""
    assert login(new_session(), f"  {TEST_PASSWORD}  ").sidebar.radio


def test_supabase_client_is_created_only_after_a_successful_login(spies):
    at = new_session()
    assert spies["client"] == 0
    login(at, WRONG_PASSWORD)
    assert spies["client"] == 0
    login(at, TEST_PASSWORD)
    assert spies["client"] == 1


def test_logout_locks_the_app_again(spies):
    at = login(new_session())
    assert at.sidebar.radio and spies["client"] == 1

    press(at, "Odjava")
    assert not at.exception
    assert not at.sidebar.radio and not at.dataframe and not at.metric
    assert "scout_authenticated" not in at.session_state          # the flag is removed
    assert at.text_input and any(b.label == "Prijava" for b in at.button)

    # Logging back in needs the password again and builds a fresh client
    # (the cached one was dropped on logout).
    login(at, WRONG_PASSWORD)
    assert not at.sidebar.radio
    login(at, TEST_PASSWORD)
    assert at.sidebar.radio and spies["client"] == 2


def test_no_message_state_or_log_contains_a_password(spies, caplog):
    with caplog.at_level(logging.DEBUG):
        at = login(new_session(), WRONG_PASSWORD)
        login(at, TEST_PASSWORD)
        for page in PAGES:
            at.sidebar.radio[0].set_value(page).run()

    session_dump = repr(at.session_state.to_dict())
    for blob in (visible_text(at), session_dump, caplog.text):
        assert TEST_PASSWORD not in blob
        assert WRONG_PASSWORD not in blob
    assert "Failed login attempt" in caplog.text                  # it IS logged - without the value

    # The only authentication state is a boolean.
    auth_state = {k: v for k, v in at.session_state.to_dict().items() if "auth" in k.lower()}
    assert auth_state == {"scout_authenticated": True}


def test_wrong_attempts_first_warn_and_then_temporarily_lock(spies):
    at = new_session()
    for _ in range(3):
        login(at, WRONG_PASSWORD)
    assert any("Više uzastopnih" in w.value for w in at.warning)
    assert not any("Previše" in w.value for w in at.warning)

    for _ in range(2):                                            # the 5th failure starts a lockout
        login(at, WRONG_PASSWORD)
    assert any("Previše neuspjelih" in w.value for w in at.warning)

    login(at, TEST_PASSWORD)                                      # right password, but locked out
    assert not at.sidebar.radio
    assert spies == NOTHING_HAPPENED
    # Warnings stay generic: nothing about the configuration is revealed.
    text = visible_text(at)
    assert "SCOUT_APP_PASSWORD" not in text and "Supabase" not in text and TEST_PASSWORD not in text


def test_opening_a_new_session_does_not_reset_the_lockout(spies):
    at = new_session()
    for _ in range(5):
        login(at, WRONG_PASSWORD)
    other_tab = login(new_session(), TEST_PASSWORD)               # correct password, fresh session
    assert not other_tab.sidebar.radio
    assert any("Previše neuspjelih" in w.value for w in other_tab.warning)
    assert spies == NOTHING_HAPPENED


def test_a_correct_login_resets_the_failure_counter(spies):
    at = new_session()
    login(at, WRONG_PASSWORD)
    login(at, WRONG_PASSWORD)
    login(at, TEST_PASSWORD)                                      # success
    press(at, "Odjava")
    for _ in range(2):
        login(at, WRONG_PASSWORD)
    assert not any("Više uzastopnih" in w.value for w in at.warning)   # counting started over


def test_the_password_can_come_from_streamlit_secrets_and_takes_precedence(spies, monkeypatch):
    monkeypatch.setenv("SCOUT_APP_PASSWORD", WRONG_PASSWORD)      # env value loses to secrets
    at = AppTest.from_file(APP_PATH, default_timeout=60)
    at.secrets["SCOUT_APP_PASSWORD"] = TEST_PASSWORD
    at.run()
    login(at, WRONG_PASSWORD)
    assert not at.sidebar.radio
    login(at, TEST_PASSWORD)
    assert at.sidebar.radio


def test_removing_the_password_relocks_an_open_session(spies, monkeypatch):
    at = login(new_session())
    assert at.sidebar.radio
    monkeypatch.delenv("SCOUT_APP_PASSWORD")
    at.run()
    assert not at.sidebar.radio and not at.dataframe
    assert any("zaključana" in e.value for e in at.error)
    assert "scout_authenticated" not in at.session_state


# --- the public dashboard must not know about any of this ----------------------

PUBLIC_APP = Path(APP_PATH).parent / "app.py"


def test_the_public_dashboard_source_knows_nothing_about_the_scouting_secrets():
    source = PUBLIC_APP.read_text(encoding="utf-8")
    for forbidden in ("SCOUT_APP_PASSWORD", "SUPABASE", "supabase", "scout_auth",
                      "scouting_database", "scout_app", "st.secrets"):
        assert forbidden not in source, forbidden


def test_the_public_dashboard_import_chain_never_loads_scouting_or_supabase_code():
    """Imports exactly what app.py imports from src/ in a clean interpreter and
    checks that no scouting/Supabase module came along."""
    tree = ast.parse(PUBLIC_APP.read_text(encoding="utf-8"))
    statements = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.split(".")[0] == "src":
            names = ", ".join(a.name for a in node.names)
            statements.append(f"from {node.module} import {names}")
    assert statements, "app.py should import from src/"
    code = "; ".join([
        "import sys",
        f"sys.path.insert(0, {str(PUBLIC_APP.parent)!r})",
        *statements,
        "banned = {'supabase', 'src.scout_auth', 'src.scouting_database', 'src.scout_players', "
        "'src.scout_ratings', 'src.scout_validation'}",
        "loaded = sorted(banned & set(sys.modules))",
        "print(loaded)",
        "sys.exit(1 if loaded else 0)",
    ])
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
