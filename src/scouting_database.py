"""
Supabase / PostgreSQL access for the private scouting app (scout_app.py).

What it stores: scouting reports, shortlists and shortlist membership (see
supabase/schema.sql). Player statistics stay in the read-only CSVs.

Security model (single-user private version):
    * The app connects SERVER-SIDE with a Supabase SECRET key (`sb_secret_...`).
      That key bypasses Row Level Security, so it must only ever live in
      Streamlit Secrets or a local .env - never in client-side code, never in
      Git. Legacy `service_role` JWT keys are deliberately not supported.
    * Configuration is read from `st.secrets` first, then from environment
      variables (SUPABASE_URL, SUPABASE_SECRET_KEY). This module never
      logs, prints, returns or puts the key into an error message: errors are
      reduced to a short, safe description (operation + error type/code).
    * The client is only built by `create_client`, which scout_app.py calls
      strictly AFTER the login gate (src/scout_auth.py) has passed.
    * Every query goes through the official supabase client's query builder,
      which sends values as parameters - no SQL is ever built from strings.

This module has no Streamlit import and never touches the network on import;
`create_client` imports the supabase package lazily. Tests exercise the
repository with an in-memory fake client, so no test needs a real Supabase.
"""
import logging
import os
from dataclasses import dataclass, field

from src.scout_validation import DEFAULT_PRIORITY, DEFAULT_STATUS

logger = logging.getLogger(__name__)

URL_VARIABLE = "SUPABASE_URL"
KEY_VARIABLE = "SUPABASE_SECRET_KEY"
REQUIRED_VARIABLES = (URL_VARIABLE, KEY_VARIABLE)

SETUP_DOC_URL = "https://github.com/lcoric3/Football-Analytics-2026/blob/main/SCOUTING_SETUP.md"

TABLE_REPORTS = "scouting_reports"
TABLE_SHORTLISTS = "shortlists"
TABLE_SHORTLIST_PLAYERS = "shortlist_players"

# Supabase returns at most this many rows per request, so lists are fetched
# page by page.
PAGE_SIZE = 1000

# PostgreSQL error code for a UNIQUE constraint violation.
UNIQUE_VIOLATION = "23505"

# Columns a caller may write (id, created_at and updated_at belong to the DB).
REPORT_FIELDS = (
    "league_code", "player_id", "season_suffix", "observation_date", "opponent",
    "observed_position", "technical_rating", "tactical_rating", "physical_rating",
    "mental_rating", "potential_rating", "strengths", "weaknesses", "notes",
    "recommendation",
)


# --- Errors (messages are safe to show to the user) --------------------------

class ConfigError(Exception):
    """Supabase configuration is missing or malformed. The message names the
    variables involved, never their values."""


class ScoutingDatabaseError(Exception):
    """A database operation failed. The message is safe to display."""


class DuplicatePlayerError(ScoutingDatabaseError):
    """The player is already on that shortlist."""


class DuplicateShortlistError(ScoutingDatabaseError):
    """A shortlist with that name already exists."""


class ConfirmationRequired(ScoutingDatabaseError):
    """A destructive operation was called without confirmed=True."""


# --- Configuration -----------------------------------------------------------

@dataclass(frozen=True)
class SupabaseConfig:
    url: str
    # repr=False: even printing/logging the config object cannot leak the key.
    secret_key: str = field(repr=False)


def read_setting(name, secrets, environ):
    """Value of `name` from secrets first, then the environment, as
    (value, source). Any failure reading secrets (no secrets.toml, wrong
    type, ...) just means "not in secrets". Shared with src/scout_auth.py so
    every scouting setting follows the same lookup order."""
    if secrets is not None:
        try:
            value = secrets[name]
        except Exception:
            value = None
        if isinstance(value, str) and value.strip():
            return value.strip(), "st.secrets"
    value = (environ if environ is not None else os.environ).get(name)
    if isinstance(value, str) and value.strip():
        return value.strip(), "environment"
    return None, None


def config_status(secrets=None, environ=None):
    """{variable: source or None} - which required settings are present and
    where they came from. Never returns a value."""
    return {name: read_setting(name, secrets, environ)[1] for name in REQUIRED_VARIABLES}


def load_config(secrets=None, environ=None):
    """Reads SUPABASE_URL and SUPABASE_SECRET_KEY (secrets first, then
    environment). Raises ConfigError - naming only the variables, never their
    values - when something is missing or the URL is not https."""
    values = {name: read_setting(name, secrets, environ)[0] for name in REQUIRED_VARIABLES}
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise ConfigError("Nedostaje konfiguracija: " + ", ".join(missing) + ".")

    url = values[URL_VARIABLE].rstrip("/")
    is_local = url.startswith(("http://localhost", "http://127.0.0.1"))
    if not (url.startswith("https://") or is_local):
        raise ConfigError(f"{URL_VARIABLE} mora počinjati s https://.")
    return SupabaseConfig(url=url, secret_key=values[KEY_VARIABLE])


def create_client(config):
    """Builds the official Supabase client. Imported lazily so importing this
    module (and the public dashboard) never requires the supabase package."""
    from supabase import create_client as supabase_create_client

    return supabase_create_client(config.url, config.secret_key)


# --- Error handling ----------------------------------------------------------

def _safe_error_message(action, exc):
    """A short description of a failed operation that cannot contain secrets:
    the operation, the exception type and - for PostgREST errors, whose text
    is generated by the database - the error code and message."""
    detail = type(exc).__name__
    code = getattr(exc, "code", None)
    message = getattr(exc, "message", None)
    if code:
        detail += f" [{code}]"
    if code and isinstance(message, str) and message:
        detail += f": {message[:200]}"
    return f"Operacija nije uspjela ({action}): {detail}"


def _is_unique_violation(exc):
    return str(getattr(exc, "code", "")) == UNIQUE_VIOLATION


class ScoutingRepository:
    """All database operations of the scouting app, over one Supabase client."""

    def __init__(self, client):
        self._client = client

    # -- plumbing ------------------------------------------------------------

    def _run(self, action, operation):
        """Runs `operation()`; any failure becomes a ScoutingDatabaseError
        with a safe message (the original exception is not chained, so a
        traceback can never leak connection details into the UI)."""
        try:
            return operation()
        except ScoutingDatabaseError:
            raise
        except Exception as exc:
            logger.warning("Database operation failed: %s", _safe_error_message(action, exc))
            raise ScoutingDatabaseError(_safe_error_message(action, exc)) from None

    def _fetch_all(self, build_query):
        """Runs a fresh query per page and concatenates the rows.
        `build_query` must return a new query builder each call."""
        rows = []
        start = 0
        while True:
            page = build_query().range(start, start + PAGE_SIZE - 1).execute().data or []
            rows.extend(page)
            if len(page) < PAGE_SIZE:
                return rows
            start += PAGE_SIZE

    @staticmethod
    def _first(result, what):
        if not result.data:
            raise ScoutingDatabaseError(f"{what} nije pronađen.")
        return result.data[0]

    @staticmethod
    def _require_confirmation(confirmed, what):
        if confirmed is not True:
            raise ConfirmationRequired(f"Brisanje ({what}) zahtijeva potvrdu.")

    # -- connection ----------------------------------------------------------

    def check_connection(self):
        """{table: None if reachable else safe error message} - a cheap
        1-row read per table, which also proves the schema was applied."""
        results = {}
        for table in (TABLE_REPORTS, TABLE_SHORTLISTS, TABLE_SHORTLIST_PLAYERS):
            try:
                self._run(f"provjera tablice {table}",
                          lambda t=table: self._client.table(t).select("id").limit(1).execute())
                results[table] = None
            except ScoutingDatabaseError as exc:
                results[table] = str(exc)
        return results

    # -- scouting reports ----------------------------------------------------

    def create_report(self, data):
        """Inserts one report (`data` is validated by scout_validation)."""
        payload = {k: data[k] for k in REPORT_FIELDS if k in data}
        result = self._run(
            "spremanje izvještaja",
            lambda: self._client.table(TABLE_REPORTS).insert(payload).execute(),
        )
        return self._first(result, "Izvještaj")

    def list_reports(self, league_code=None, player_id=None, season_suffix=None):
        """Reports, newest observation first, optionally for one
        league/player/season."""
        def query():
            q = self._client.table(TABLE_REPORTS).select("*")
            if league_code is not None:
                q = q.eq("league_code", league_code)
            if player_id is not None:
                q = q.eq("player_id", int(player_id))
            if season_suffix is not None:
                q = q.eq("season_suffix", season_suffix)
            return q.order("observation_date", desc=True).order("id")

        return self._run("dohvat izvještaja", lambda: self._fetch_all(query))

    def update_report(self, report_id, data):
        """Updates a report's editable fields."""
        payload = {k: data[k] for k in REPORT_FIELDS if k in data}
        result = self._run(
            "izmjena izvještaja",
            lambda: self._client.table(TABLE_REPORTS).update(payload).eq("id", report_id).execute(),
        )
        return self._first(result, "Izvještaj")

    def delete_report(self, report_id, *, confirmed=False):
        """Deletes a report. Requires confirmed=True."""
        self._require_confirmation(confirmed, "izvještaj")
        self._run(
            "brisanje izvještaja",
            lambda: self._client.table(TABLE_REPORTS).delete().eq("id", report_id).execute(),
        )

    # -- shortlists ----------------------------------------------------------

    def create_shortlist(self, name, description=None):
        try:
            result = self._run(
                "stvaranje shortliste",
                lambda: self._client.table(TABLE_SHORTLISTS)
                .insert({"name": name, "description": description}).execute(),
            )
        except ScoutingDatabaseError as exc:
            self._raise_if_duplicate_name(exc)
            raise
        return self._first(result, "Shortlista")

    def list_shortlists(self):
        return self._run(
            "dohvat shortlisti",
            lambda: self._fetch_all(
                lambda: self._client.table(TABLE_SHORTLISTS).select("*").order("name").order("id")
            ),
        )

    def update_shortlist(self, shortlist_id, name, description=None):
        try:
            result = self._run(
                "izmjena shortliste",
                lambda: self._client.table(TABLE_SHORTLISTS)
                .update({"name": name, "description": description}).eq("id", shortlist_id).execute(),
            )
        except ScoutingDatabaseError as exc:
            self._raise_if_duplicate_name(exc)
            raise
        return self._first(result, "Shortlista")

    def delete_shortlist(self, shortlist_id, *, confirmed=False):
        """Deletes a shortlist and (via ON DELETE CASCADE) its players.
        Requires confirmed=True."""
        self._require_confirmation(confirmed, "shortlista")
        self._run(
            "brisanje shortliste",
            lambda: self._client.table(TABLE_SHORTLISTS).delete().eq("id", shortlist_id).execute(),
        )

    @staticmethod
    def _raise_if_duplicate_name(exc):
        if f"[{UNIQUE_VIOLATION}]" in str(exc):
            raise DuplicateShortlistError("Shortlista s tim nazivom već postoji.") from None

    # -- shortlist players ---------------------------------------------------

    def list_shortlist_players(self, shortlist_id=None):
        """Membership rows for one shortlist (or all of them), oldest first."""
        def query():
            q = self._client.table(TABLE_SHORTLIST_PLAYERS).select("*")
            if shortlist_id is not None:
                q = q.eq("shortlist_id", shortlist_id)
            return q.order("added_at").order("id")

        return self._run("dohvat igrača shortliste", lambda: self._fetch_all(query))

    def add_player_to_shortlist(
        self, shortlist_id, league_code, player_id, season_suffix,
        status=DEFAULT_STATUS, priority=DEFAULT_PRIORITY, note=None,
    ):
        """Adds a player to a shortlist. The database's UNIQUE (shortlist_id,
        player_id) constraint is the guard against adding the same player
        twice - checking there (instead of "look first, then insert") also
        holds when two requests race. Raises DuplicatePlayerError."""
        payload = {
            "shortlist_id": shortlist_id, "league_code": league_code,
            "player_id": int(player_id), "season_suffix": season_suffix,
            "status": status, "priority": priority, "note": note,
        }
        try:
            result = self._client.table(TABLE_SHORTLIST_PLAYERS).insert(payload).execute()
        except Exception as exc:
            if _is_unique_violation(exc):
                raise DuplicatePlayerError("Igrač je već na ovoj shortlisti.") from None
            logger.warning("Database operation failed: %s",
                           _safe_error_message("dodavanje igrača na shortlistu", exc))
            raise ScoutingDatabaseError(
                _safe_error_message("dodavanje igrača na shortlistu", exc)
            ) from None
        return self._first(result, "Zapis")

    def update_shortlist_player(self, entry_id, status, priority, note=None):
        result = self._run(
            "izmjena igrača na shortlisti",
            lambda: self._client.table(TABLE_SHORTLIST_PLAYERS)
            .update({"status": status, "priority": priority, "note": note})
            .eq("id", entry_id).execute(),
        )
        return self._first(result, "Zapis")

    def remove_shortlist_player(self, entry_id, *, confirmed=False):
        """Removes a player from a shortlist. Requires confirmed=True."""
        self._require_confirmation(confirmed, "igrač na shortlisti")
        self._run(
            "uklanjanje igrača sa shortliste",
            lambda: self._client.table(TABLE_SHORTLIST_PLAYERS).delete().eq("id", entry_id).execute(),
        )
