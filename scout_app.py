"""
PRIVATE scouting app - reports, shortlists and player comparison on top of
the analytics pipeline's existing scored data.

*** THIS APP MUST STAY PRIVATE. ***
It talks to Supabase with a SECRET key (sb_secret_...), which bypasses Row
Level Security: anyone who can open the running app can read, edit and delete
every scouting note. Never deploy it as a public Streamlit app - see
SCOUTING_SETUP.md ("Kako aplikacija ostaje privatna"). The separate public
dashboard is app.py, which never touches this database and does not know any
of these secrets.

Two independent protections, both required:
    1. Streamlit's "Only specific people can view this app" (Community Cloud)
    2. A password gate (SCOUT_APP_PASSWORD, see src/scout_auth.py). The gate
       runs FIRST in main(): before any player data is loaded and before the
       Supabase client is created. Without a configured password the app
       stays locked.

Data flow:
    data/processed/hnl_player_scored_<season>.csv   (read-only, from the pipeline)
  + Supabase: scouting_reports / shortlists / shortlist_players
  -> src/scout_ratings.py computes scout_score and combined_score
  -> this file only draws the UI.

This app never calls the SportMonks API and never writes any local file:
scouting notes live in Supabase only.

Run locally with:
    streamlit run scout_app.py
"""
from dataclasses import dataclass
from datetime import date

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from dotenv import load_dotenv

from src import scout_auth, scout_players, scout_ratings, scout_validation, scouting_database

# Local development: pick up SUPABASE_URL / SUPABASE_SECRET_KEY /
# SCOUT_APP_PASSWORD from a git-ignored .env. On Streamlit Cloud the values
# come from st.secrets.
load_dotenv()

st.set_page_config(page_title="Skautski sustav (privatno)", layout="wide")

PAGES = [
    "Početna",
    "Pretraživanje igrača",
    "Skautska procjena",
    "Shortliste",
    "Usporedba igrača",
    "Postavke veze",
]

# Never build a selectbox with thousands of entries.
MAX_PICKER_OPTIONS = 500

COLUMN_LABELS = {
    "player_name": "Igrač", "team_name": "Klub", "position": "Pozicija", "age": "Dob",
    "minutes": "Minute", "overall_score": "Analitička ocjena", "scout_score": "Skautska ocjena",
    "combined_score": "Kombinirana ocjena", "scout_report_count": "Izvještaja",
}

RADAR_METRICS = {
    "attacking_score": "Napad", "creative_score": "Kreacija", "defensive_score": "Obrana",
    "discipline_score": "Disciplina", "dribbling_score": "Dribling", "passing_score": "Dodavanje",
    "duel_defending_score": "Dvoboji", "scout_score": "Skautska ocjena",
}

GOALKEEPER_NOTE = (
    "Napomena: `overall_score` se računa iz akcija igrača u polju (napad, kreacija, obrana), "
    "pa za golmane nije smislena mjera. Za golmane pogledajte `goalkeeper_score`."
)


# =============================================================================
# Login gate - runs BEFORE any data is shown or any Supabase client exists
# =============================================================================

# The ONLY thing kept in st.session_state for authentication: a boolean. The
# password itself is never stored (the login field is cleared on submit and
# the value only lives in a local variable for the comparison), and the
# failed-attempt counter lives on the server (see _login_limiter).
AUTH_FLAG = "scout_authenticated"


@st.cache_resource(show_spinner=False)
def _login_limiter():
    """One AttemptLimiter shared by every session of this server process, so
    opening a new browser tab cannot reset the failed-attempt counter."""
    return scout_auth.AttemptLimiter()


def is_logged_in():
    return st.session_state.get(AUTH_FLAG) is True


def logout():
    """Removes the login flag and drops the cached Supabase client, so the
    next login starts from a locked state."""
    st.session_state.pop(AUTH_FLAG, None)
    st.session_state.pop("_flash", None)
    _cached_repository.clear()


def render_login(expected_password):
    """The lock screen. On the right password it sets the login flag and
    reruns; every message is generic - nothing about the configuration or the
    password is revealed."""
    st.title("Skautski sustav (privatno)")
    limiter = _login_limiter()
    with st.form("login", clear_on_submit=True):
        candidate = st.text_input("Zaporka", type="password")
        submitted = st.form_submit_button("Prijava")
    if submitted:
        if limiter.seconds_locked() == 0:            # never compared during a lockout
            if scout_auth.verify_password(candidate, expected_password):
                limiter.record_success()
                st.session_state[AUTH_FLAG] = True
                st.rerun()
            else:
                limiter.record_failure()
                st.error("Pogrešna zaporka.")
    remaining = limiter.seconds_locked()
    if remaining:
        st.warning(f"Previše neuspjelih pokušaja. Pokušajte ponovno za {remaining} s.")
    elif limiter.failures_since_success >= scout_auth.WARN_AFTER_FAILURES:
        st.warning(
            "Više uzastopnih neuspjelih pokušaja prijave. Nakon nekoliko pogrešaka "
            "prijava se privremeno blokira."
        )


def require_login():
    """True only when the user may see the app. Otherwise draws the lock
    screen (or the 'locked' notice when no password is configured) and
    returns False. Nothing but this check may run before it succeeds."""
    expected = scout_auth.load_password(st.secrets, None)
    if is_logged_in():
        if expected:
            return True
        logout()                       # password no longer configured -> lock again
    if not expected:
        st.title("Skautski sustav (privatno)")
        st.error(
            "**Aplikacija je zaključana.** Zaštita zaporkom nije postavljena, pa pristup nije "
            f"moguć. Upute: [SCOUTING_SETUP.md]({scouting_database.SETUP_DOC_URL})."
        )
        return False
    render_login(expected)
    return False


# =============================================================================
# Data / database context
# =============================================================================

@dataclass
class Context:
    league_code: str
    players: pd.DataFrame          # scored players (all seasons) + scout columns
    reports: list                  # scouting reports of this league (dicts)
    repo: object                   # ScoutingRepository, or None if not configured
    config_error: str              # why repo is None ("" if configured)
    db_error: str                  # why reports could not be loaded ("" if fine)


@st.cache_data(show_spinner=False)
def load_players(league_code):
    """Read-only load of the pipeline's scored CSVs (cached; never written)."""
    return scout_players.load_league_players(league_code)


@st.cache_resource(show_spinner=False)
def _cached_repository():
    """One Supabase client per server process. Held in st.cache_resource
    (server memory) - NOT in st.session_state, and never written anywhere.
    Takes no arguments so the key is not part of any cache key. Exceptions are
    not cached, so fixing the secrets and reloading just works."""
    config = scouting_database.load_config(st.secrets)
    return scouting_database.ScoutingRepository(scouting_database.create_client(config))


def get_repository():
    """(repository, error message). Never raises, never includes a secret."""
    try:
        return _cached_repository(), ""
    except scouting_database.ConfigError as exc:
        return None, str(exc)
    except ImportError:
        return None, "Nedostaje Python paket `supabase` (pip install -r requirements.txt)."
    except Exception as exc:  # e.g. malformed key rejected by the client library
        return None, f"Supabase klijent nije inicijaliziran ({type(exc).__name__})."


def build_context(league_code):
    repo, config_error = get_repository()
    reports, db_error = [], ""
    if repo is not None:
        try:
            reports = repo.list_reports(league_code=league_code)
        except scouting_database.ScoutingDatabaseError as exc:
            db_error = str(exc)
    reports_df = pd.DataFrame(reports) if reports else None
    players = scout_ratings.add_scout_columns(load_players(league_code), reports_df)
    return Context(league_code, players, reports, repo, config_error, db_error)


def require_database(ctx):
    """True when the database is usable; otherwise shows why (with a link to
    the setup guide) and returns False so the page can stop."""
    if ctx.repo is None:
        st.warning(
            f"**Baza nije povezana.** {ctx.config_error}\n\n"
            f"Kako je postaviti: [SCOUTING_SETUP.md]({scouting_database.SETUP_DOC_URL}). "
            "Pretraživanje i usporedba igrača rade i bez baze (samo s analitičkim ocjenama)."
        )
        return False
    if ctx.db_error:
        st.error(
            f"{ctx.db_error}\n\nProvjerite je li `supabase/schema.sql` pokrenut u SQL Editoru "
            f"([SCOUTING_SETUP.md]({scouting_database.SETUP_DOC_URL}), korak 2) i "
            "na stranici *Postavke veze* pokrenite test veze."
        )
        return False
    return True


def flash(message):
    """Show a success message after the next rerun (st.rerun would drop it)."""
    st.session_state["_flash"] = message


def show_flash():
    message = st.session_state.pop("_flash", None)
    if message:
        st.success(message)


def show_errors(errors):
    st.error("Provjerite unos:\n\n" + "\n".join(f"- {e}" for e in errors))


# =============================================================================
# Small UI helpers
# =============================================================================

def fmt_score(value):
    """One decimal, or an em dash when there is no value."""
    return "—" if value is None or pd.isna(value) else f"{value:.1f}"


def fmt_int(value):
    return "—" if value is None or pd.isna(value) else f"{value:.0f}"


def season_selector(ctx, key):
    """(season_suffix, season_players) for the league's available seasons."""
    seasons = scout_players.available_seasons(ctx.league_code)
    if not seasons:
        st.error("Nema učitanih podataka o igračima (`data/processed/`). Prvo pokrenite pipeline.")
        return None, None
    suffix = st.selectbox("Sezona", list(seasons), format_func=seasons.get, key=key)
    return suffix, ctx.players[ctx.players["season_suffix"] == suffix]


def player_picker(season_players, key, label="Igrač"):
    """Name search + selectbox. Returns the chosen player's row, or None."""
    query = st.text_input("Pretraži po imenu", key=f"{key}_query")
    matches = scout_players.filter_players(season_players, name_query=query).sort_values("player_name")
    if matches.empty:
        st.info("Nema igrača koji odgovaraju pretrazi.")
        return None
    if len(matches) > MAX_PICKER_OPTIONS:
        st.caption(f"Prikazano prvih {MAX_PICKER_OPTIONS} od {len(matches)} - suzite pretragu.")
        matches = matches.head(MAX_PICKER_OPTIONS)
    labels = {int(r.player_id): scout_players.player_label(r) for _, r in matches.iterrows()}
    player_id = st.selectbox(label, list(labels), format_func=labels.get, key=f"{key}_player")
    return matches[matches["player_id"] == player_id].iloc[0]


def reports_for(ctx, player_id, season_suffix):
    return [
        r for r in ctx.reports
        if int(r["player_id"]) == int(player_id) and r["season_suffix"] == season_suffix
    ]


def reports_table(reports, names=None):
    """Report list as a display DataFrame, newest observation first. With
    `names` (player_id -> name) an "Igrač" column is added in front."""
    rows = []
    for r in sorted(reports, key=lambda r: (r["observation_date"], r["created_at"]), reverse=True):
        rows.append({
            **({"Igrač": names.get(int(r["player_id"]), f"#{r['player_id']}")} if names else {}),
            "Datum": r["observation_date"], "Protivnik": r.get("opponent"),
            "Pozicija": r["observed_position"], "Tehnička": r["technical_rating"],
            "Taktička": r["tactical_rating"], "Fizička": r["physical_rating"],
            "Mentalna": r["mental_rating"], "Potencijal": r["potential_rating"],
            "Skautska ocjena": round(scout_ratings.report_scout_score(r), scout_ratings.DECIMALS),
            "Preporuka": r["recommendation"], "Snage": r.get("strengths"),
            "Slabosti": r.get("weaknesses"), "Bilješke": r.get("notes"),
        })
    return pd.DataFrame(rows)


def score_columns_config():
    fmt1 = "%.1f"
    return {
        COLUMN_LABELS["age"]: st.column_config.NumberColumn(format="%d"),
        COLUMN_LABELS["minutes"]: st.column_config.NumberColumn(format="%d"),
        COLUMN_LABELS["overall_score"]: st.column_config.NumberColumn(format=fmt1),
        COLUMN_LABELS["scout_score"]: st.column_config.NumberColumn(format=fmt1),
        COLUMN_LABELS["combined_score"]: st.column_config.NumberColumn(format=fmt1),
    }


def render_player_table(frame):
    columns = [c for c in scout_players.TABLE_COLUMNS if c in frame.columns]
    st.dataframe(
        frame[columns].rename(columns=COLUMN_LABELS),
        hide_index=True, width="stretch", column_config=score_columns_config(),
    )


def render_score_metrics(row):
    """Analytical / scout / combined score for one player row. With no scout
    report only the analytical score is shown - never an invented blend."""
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Analitička ocjena", fmt_score(row.get("overall_score")))
    col2.metric("Skautska ocjena", fmt_score(row.get("scout_score")))
    col3.metric("Kombinirana ocjena", fmt_score(row.get("combined_score")))
    col4.metric("Skautskih izvještaja", fmt_int(row.get("scout_report_count")))
    col5.metric("Prosj. potencijal (1-10)", fmt_score(row.get("scout_potential_avg")))
    if int(row.get("scout_report_count") or 0) == 0:
        st.info("Nema skautskih izvještaja za ovog igrača i sezonu - prikazana je samo analitička ocjena.")
    elif pd.isna(row.get("overall_score")):
        st.info("Igrač nema analitičku ocjenu (premalo minuta), pa kombinirana ocjena ne postoji.")
    if row.get("position") == "Goalkeeper":
        st.caption(GOALKEEPER_NOTE)


# =============================================================================
# Page: Početna
# =============================================================================

def render_home(ctx):
    st.title("Privatni skautski sustav")
    st.warning(
        "**Privatna aplikacija.** Koristi Supabase secret ključ koji zaobilazi sigurnosna "
        "pravila baze - nikada je ne objavljujte javno. Javni analitički dashboard je zasebna "
        "aplikacija (`app.py`)."
    )
    st.markdown(
        "Analitičke ocjene dolaze iz postojećeg pipelinea (samo za čitanje), a skautske "
        "izvještaje i shortliste spremate u Supabase bazu."
    )

    seasons = scout_players.available_seasons(ctx.league_code)
    if not seasons:
        st.error("Nema učitanih podataka o igračima (`data/processed/`). Prvo pokrenite pipeline.")
        return
    latest = next(iter(seasons))
    latest_players = ctx.players[ctx.players["season_suffix"] == latest]

    col1, col2, col3, col4 = st.columns(4)
    col1.metric(f"Igrača ({seasons[latest]})", len(latest_players))
    if require_database(ctx):
        try:
            shortlists = ctx.repo.list_shortlists()
        except scouting_database.ScoutingDatabaseError as exc:
            shortlists = []
            st.error(str(exc))
        col2.metric("Skautskih izvještaja", len(ctx.reports))
        col3.metric("Skautiranih igrača", len({(r["player_id"], r["season_suffix"]) for r in ctx.reports}))
        col4.metric("Shortlisti", len(shortlists))

    st.subheader(f"Najbolji igrači ({seasons[latest]})")
    scouted = latest_players[latest_players["combined_score"].notna()]
    if not scouted.empty:
        st.caption("Po kombiniranoj ocjeni - samo igrači s analitičkom i skautskom ocjenom.")
        render_player_table(scout_players.sort_by_score(scouted, "combined_score").head(10))
    else:
        st.caption("Još nema igrača s kombiniranom ocjenom - prikazana je analitička ocjena.")
        outfield = latest_players[latest_players["position"] != "Goalkeeper"]
        render_player_table(scout_players.sort_by_score(outfield, "overall_score").head(10))

    if ctx.reports:
        st.subheader("Najnoviji izvještaji")
        names = ctx.players.drop_duplicates("player_id").set_index("player_id")["player_name"].to_dict()
        table = reports_table(ctx.reports, names=names).head(5)
        st.dataframe(table[["Igrač", "Datum", "Protivnik", "Skautska ocjena", "Preporuka"]],
                     hide_index=True, width="stretch")


# =============================================================================
# Page: Pretraživanje igrača (+ profil)
# =============================================================================

def render_search(ctx):
    st.title("Pretraživanje igrača")
    suffix, season_players = season_selector(ctx, "search_season")
    if suffix is None:
        return
    if not ctx.repo:
        st.info("Baza nije povezana - skautske i kombinirane ocjene su prazne. Vidi *Postavke veze*.")

    col1, col2 = st.columns(2)
    teams = col1.multiselect("Klub", sorted(season_players["team_name"].dropna().unique()))
    positions = col2.multiselect("Pozicija", sorted(season_players["position"].dropna().unique()))
    col3, col4, col5, col6 = st.columns(4)
    min_age = col3.number_input("Minimalna dob", min_value=0, value=0, step=1, help="0 = bez ograničenja")
    max_age = col4.number_input("Maksimalna dob", min_value=0, value=0, step=1, help="0 = bez ograničenja")
    min_minutes = col5.number_input("Minimalno minuta", min_value=0, value=0, step=100)
    query = col6.text_input("Ime igrača")

    filtered = scout_players.filter_players(
        season_players, teams=teams, positions=positions,
        min_age=min_age or None, max_age=max_age or None,
        min_minutes=min_minutes or None, name_query=query,
    )

    sort_label = st.selectbox("Sortiraj prema", list(scout_players.SORT_OPTIONS), index=2)
    filtered = scout_players.sort_by_score(filtered, scout_players.SORT_OPTIONS[sort_label])
    st.caption(f"{len(filtered)} igrača")
    render_player_table(filtered)

    st.divider()
    st.subheader("Profil igrača")
    if filtered.empty:
        st.info("Nema igrača za prikaz profila - promijenite filtre.")
        return
    shown = filtered.head(MAX_PICKER_OPTIONS)
    labels = {int(r.player_id): scout_players.player_label(r) for _, r in shown.iterrows()}
    player_id = st.selectbox("Odaberite igrača", list(labels), format_func=labels.get)
    render_profile(ctx, shown[shown["player_id"] == player_id].iloc[0])


def render_profile(ctx, row):
    st.markdown(f"### {row['player_name']}")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Klub", row["team_name"])
    col2.metric("Pozicija", row["position"])
    col3.metric("Dob", fmt_int(row.get("age")))
    col4.metric("Minute", fmt_int(row.get("minutes")))

    render_score_metrics(row)

    scores = {c: round(row[c], 1) for c in scout_players.ANALYTICAL_SCORE_COLUMNS
              if c in row.index and pd.notna(row[c])}
    if scores:
        st.markdown("**Analitičke ocjene** (iz postojećeg pipelinea)")
        st.dataframe(pd.DataFrame([scores]), hide_index=True, width="stretch")
    per90 = {c: round(row[c], 2) for c in scout_players.KEY_PER90_COLUMNS
             if c in row.index and pd.notna(row[c])}
    if per90:
        st.markdown("**Ključne statistike po 90 minuta**")
        st.dataframe(pd.DataFrame([per90]), hide_index=True, width="stretch")

    player_reports = reports_for(ctx, row["player_id"], row["season_suffix"])
    if player_reports:
        st.markdown("**Skautski izvještaji**")
        st.dataframe(reports_table(player_reports), hide_index=True, width="stretch")


# =============================================================================
# Page: Skautska procjena
# =============================================================================

def report_form(prefix, defaults, position_default):
    """Renders the report input widgets; returns the raw values (a dict).
    `prefix` makes widget keys unique per form/report."""
    def key(name):
        return f"{prefix}_{name}"

    values = {}
    col1, col2, col3 = st.columns(3)
    values["observation_date"] = col1.date_input(
        "Datum promatranja *", value=defaults.get("observation_date", date.today()),
        max_value=date.today(), key=key("date"),
    )
    values["opponent"] = col2.text_input(
        "Protivnik", value=defaults.get("opponent") or "", key=key("opponent"),
        max_chars=scout_validation.MAX_OPPONENT_LEN,
    )
    values["observed_position"] = col3.text_input(
        "Promatrana pozicija *", value=defaults.get("observed_position") or position_default,
        key=key("position"), max_chars=scout_validation.MAX_POSITION_LEN,
    )

    st.markdown(f"**Ocjene ({scout_ratings.RATING_MIN}-{scout_ratings.RATING_MAX})** *")
    rating_cols = st.columns(5)
    for col, (column, label) in zip(rating_cols, scout_validation.RATING_FIELDS.items()):
        values[column] = col.slider(
            label, scout_ratings.RATING_MIN, scout_ratings.RATING_MAX,
            int(defaults.get(column, 5)), key=key(column),
        )

    values["strengths"] = st.text_area(
        "Snage", value=defaults.get("strengths") or "", key=key("strengths"),
        max_chars=scout_validation.MAX_STRENGTHS_LEN,
    )
    values["weaknesses"] = st.text_area(
        "Slabosti", value=defaults.get("weaknesses") or "", key=key("weaknesses"),
        max_chars=scout_validation.MAX_WEAKNESSES_LEN,
    )
    values["notes"] = st.text_area(
        "Opće bilješke", value=defaults.get("notes") or "", key=key("notes"),
        max_chars=scout_validation.MAX_NOTES_LEN,
    )
    recommendations = list(scout_validation.RECOMMENDATIONS)
    current = defaults.get("recommendation", recommendations[1])
    values["recommendation"] = st.selectbox(
        "Preporuka *", recommendations, index=recommendations.index(current), key=key("recommendation"),
    )
    return values


def identity_fields(row):
    return {
        "league_code": row["league_code"], "player_id": int(row["player_id"]),
        "season_suffix": row["season_suffix"],
    }


def render_assessment(ctx):
    st.title("Skautska procjena")
    if not require_database(ctx):
        return
    show_flash()

    suffix, season_players = season_selector(ctx, "assess_season")
    if suffix is None:
        return
    row = player_picker(season_players, "assess")
    if row is None:
        return
    st.markdown(f"### {row['player_name']} - {row['team_name']} ({row['position']})")
    render_score_metrics(row)

    tab_list, tab_new, tab_edit = st.tabs(["Izvještaji", "Novi izvještaj", "Uredi / obriši"])
    player_reports = reports_for(ctx, row["player_id"], suffix)
    nonce = st.session_state.get("report_form_nonce", 0)

    with tab_list:
        if player_reports:
            st.dataframe(reports_table(player_reports), hide_index=True, width="stretch")
        else:
            st.info("Još nema izvještaja za ovog igrača u odabranoj sezoni.")

    with tab_new:
        with st.form(f"new_report_{row['player_id']}_{nonce}"):
            values = report_form(f"new_{row['player_id']}_{nonce}", {}, row["position"])
            submitted = st.form_submit_button("Spremi izvještaj")
        if submitted:
            result = scout_validation.validate_report({**identity_fields(row), **values})
            if not result.ok:
                show_errors(result.errors)
            else:
                try:
                    ctx.repo.create_report(result.data)
                except scouting_database.ScoutingDatabaseError as exc:
                    st.error(str(exc))
                else:
                    st.session_state["report_form_nonce"] = nonce + 1   # fresh, empty form next time
                    flash("Izvještaj je spremljen.")
                    st.rerun()

    with tab_edit:
        render_edit_report(ctx, row, player_reports)


def render_edit_report(ctx, row, player_reports):
    if not player_reports:
        st.info("Nema izvještaja za uređivanje.")
        return
    ordered = sorted(player_reports, key=lambda r: (r["observation_date"], r["created_at"]), reverse=True)
    labels = {
        r["id"]: f"{r['observation_date']} | {r.get('opponent') or 'bez protivnika'} | "
                 f"{round(scout_ratings.report_scout_score(r), 1)}"
        for r in ordered
    }
    report_id = st.selectbox("Izvještaj", list(labels), format_func=labels.get, key=f"edit_pick_{row['player_id']}")
    report = next(r for r in ordered if r["id"] == report_id)

    defaults = {**report, "observation_date": date.fromisoformat(report["observation_date"])}
    with st.form(f"edit_report_{report_id}"):
        values = report_form(f"edit_{report_id}", defaults, row["position"])
        submitted = st.form_submit_button("Spremi izmjene")
    if submitted:
        result = scout_validation.validate_report({**identity_fields(row), **values})
        if not result.ok:
            show_errors(result.errors)
        else:
            try:
                ctx.repo.update_report(report_id, result.data)
            except scouting_database.ScoutingDatabaseError as exc:
                st.error(str(exc))
            else:
                flash("Izmjene su spremljene.")
                st.rerun()

    st.divider()
    st.markdown("**Brisanje izvještaja**")
    confirmed = st.checkbox(
        "Potvrđujem da želim trajno obrisati ovaj izvještaj", key=f"confirm_delete_report_{report_id}"
    )
    if st.button("Obriši izvještaj", disabled=not confirmed, key=f"delete_report_{report_id}"):
        try:
            ctx.repo.delete_report(report_id, confirmed=confirmed)
        except scouting_database.ScoutingDatabaseError as exc:
            st.error(str(exc))
        else:
            flash("Izvještaj je obrisan.")
            st.rerun()


# =============================================================================
# Page: Shortliste
# =============================================================================

def render_shortlists(ctx):
    st.title("Shortliste")
    if not require_database(ctx):
        return
    show_flash()

    try:
        shortlists = ctx.repo.list_shortlists()
    except scouting_database.ScoutingDatabaseError as exc:
        st.error(str(exc))
        return

    with st.expander("Nova shortlista", expanded=not shortlists):
        with st.form("new_shortlist", clear_on_submit=True):
            name = st.text_input("Naziv *", max_chars=scout_validation.MAX_SHORTLIST_NAME_LEN)
            description = st.text_area("Opis", max_chars=scout_validation.MAX_SHORTLIST_DESCRIPTION_LEN)
            submitted = st.form_submit_button("Stvori shortlistu")
        if submitted:
            result = scout_validation.validate_shortlist(name, description)
            if not result.ok:
                show_errors(result.errors)
            else:
                try:
                    ctx.repo.create_shortlist(**result.data)
                except scouting_database.ScoutingDatabaseError as exc:
                    st.error(str(exc))
                else:
                    flash("Shortlista je stvorena.")
                    st.rerun()

    if not shortlists:
        st.info("Još nema shortlisti - stvorite prvu iznad.")
        return

    names = {s["id"]: s["name"] for s in shortlists}
    shortlist_id = st.selectbox("Shortlista", list(names), format_func=names.get)
    shortlist = next(s for s in shortlists if s["id"] == shortlist_id)
    if shortlist.get("description"):
        st.caption(shortlist["description"])

    render_shortlist_settings(ctx, shortlist)
    try:
        entries = ctx.repo.list_shortlist_players(shortlist_id)
    except scouting_database.ScoutingDatabaseError as exc:
        st.error(str(exc))
        return
    render_shortlist_table(ctx, entries)
    render_add_player(ctx, shortlist_id, entries)
    render_edit_entry(ctx, entries)


def render_shortlist_settings(ctx, shortlist):
    with st.expander("Promijeni naziv i opis / obriši shortlistu"):
        with st.form(f"edit_shortlist_{shortlist['id']}"):
            name = st.text_input("Naziv *", value=shortlist["name"],
                                 max_chars=scout_validation.MAX_SHORTLIST_NAME_LEN)
            description = st.text_area("Opis", value=shortlist.get("description") or "",
                                       max_chars=scout_validation.MAX_SHORTLIST_DESCRIPTION_LEN)
            submitted = st.form_submit_button("Spremi izmjene")
        if submitted:
            result = scout_validation.validate_shortlist(name, description)
            if not result.ok:
                show_errors(result.errors)
            else:
                try:
                    ctx.repo.update_shortlist(shortlist["id"], **result.data)
                except scouting_database.ScoutingDatabaseError as exc:
                    st.error(str(exc))
                else:
                    flash("Shortlista je ažurirana.")
                    st.rerun()

        st.markdown("**Brisanje shortliste** (briše i sve igrače na njoj)")
        confirmed = st.checkbox("Potvrđujem da želim trajno obrisati ovu shortlistu",
                                key=f"confirm_delete_shortlist_{shortlist['id']}")
        if st.button("Obriši shortlistu", disabled=not confirmed, key=f"delete_shortlist_{shortlist['id']}"):
            try:
                ctx.repo.delete_shortlist(shortlist["id"], confirmed=confirmed)
            except scouting_database.ScoutingDatabaseError as exc:
                st.error(str(exc))
            else:
                flash("Shortlista je obrisana.")
                st.rerun()


def shortlist_frame(ctx, entries):
    """Membership rows joined with player data and scores (matched on
    league + player_id + season, never on name)."""
    keys = ["league_code", "player_id", "season_suffix"]
    player_columns = keys + [c for c in (
        "player_name", "team_name", "position", "age", "minutes", "overall_score",
        "scout_score", "combined_score", "scout_report_count",
    ) if c in ctx.players.columns]
    frame = pd.DataFrame(entries).merge(ctx.players[player_columns], on=keys, how="left")
    frame["player_name"] = frame["player_name"].fillna(frame["player_id"].map(lambda i: f"Igrač #{i}"))
    return frame


def render_shortlist_table(ctx, entries):
    st.subheader("Igrači na shortlisti")
    if not entries:
        st.info("Shortlista je prazna.")
        return
    frame = shortlist_frame(ctx, entries)
    sort_label = st.selectbox("Sortiraj prema", list(scout_players.SORT_OPTIONS), key="shortlist_sort")
    frame = scout_players.sort_by_score(frame, scout_players.SORT_OPTIONS[sort_label])
    display = frame.rename(columns={**COLUMN_LABELS, "status": "Status", "priority": "Prioritet",
                                    "note": "Bilješka", "season_suffix": "Sezona"})
    columns = ["Igrač", "Klub", "Pozicija", "Dob", "Status", "Prioritet", "Analitička ocjena",
               "Skautska ocjena", "Kombinirana ocjena", "Izvještaja", "Sezona", "Bilješka"]
    st.dataframe(display[[c for c in columns if c in display.columns]], hide_index=True,
                 width="stretch", column_config=score_columns_config())
    st.caption("Prioritet: 1 = najviši, 5 = najniži.")


def render_add_player(ctx, shortlist_id, entries):
    with st.expander("Dodaj igrača"):
        suffix, season_players = season_selector(ctx, "shortlist_season")
        if suffix is None:
            return
        on_list = {int(e["player_id"]) for e in entries}
        candidates = season_players[~season_players["player_id"].isin(on_list)]
        row = player_picker(candidates, f"shortlist_add_{shortlist_id}")
        if row is None:
            return
        with st.form(f"add_to_shortlist_{shortlist_id}"):
            status = st.selectbox("Status", scout_validation.STATUSES)
            priority = st.slider("Prioritet (1 = najviši)", scout_validation.PRIORITY_MIN,
                                 scout_validation.PRIORITY_MAX, scout_validation.DEFAULT_PRIORITY)
            note = st.text_area("Bilješka", max_chars=scout_validation.MAX_SHORTLIST_NOTE_LEN)
            submitted = st.form_submit_button("Dodaj na shortlistu")
        if submitted:
            result = scout_validation.validate_shortlist_entry(status, priority, note)
            if not result.ok:
                show_errors(result.errors)
                return
            try:
                ctx.repo.add_player_to_shortlist(shortlist_id, row["league_code"], int(row["player_id"]),
                                                 row["season_suffix"], **result.data)
            except scouting_database.DuplicatePlayerError:
                st.warning("Igrač je već na ovoj shortlisti.")
            except scouting_database.ScoutingDatabaseError as exc:
                st.error(str(exc))
            else:
                flash(f"{row['player_name']} je dodan na shortlistu.")
                st.rerun()


def render_edit_entry(ctx, entries):
    if not entries:
        return
    with st.expander("Uredi ili ukloni igrača"):
        frame = shortlist_frame(ctx, entries)
        labels = {r.id: f"{r.player_name} ({r.status})" for r in frame.itertuples()}
        entry_id = st.selectbox("Igrač na shortlisti", list(labels), format_func=labels.get)
        entry = next(e for e in entries if e["id"] == entry_id)

        with st.form(f"edit_entry_{entry_id}"):
            status = st.selectbox("Status", scout_validation.STATUSES,
                                  index=scout_validation.STATUSES.index(entry["status"]),
                                  key=f"entry_status_{entry_id}")
            priority = st.slider("Prioritet (1 = najviši)", scout_validation.PRIORITY_MIN,
                                 scout_validation.PRIORITY_MAX, int(entry["priority"]),
                                 key=f"entry_priority_{entry_id}")
            note = st.text_area("Bilješka", value=entry.get("note") or "",
                                max_chars=scout_validation.MAX_SHORTLIST_NOTE_LEN,
                                key=f"entry_note_{entry_id}")
            submitted = st.form_submit_button("Spremi izmjene igrača")
        if submitted:
            result = scout_validation.validate_shortlist_entry(status, priority, note)
            if not result.ok:
                show_errors(result.errors)
            else:
                try:
                    ctx.repo.update_shortlist_player(entry_id, **result.data)
                except scouting_database.ScoutingDatabaseError as exc:
                    st.error(str(exc))
                else:
                    flash("Igrač je ažuriran.")
                    st.rerun()

        st.markdown("**Uklanjanje igrača sa shortliste**")
        confirmed = st.checkbox("Potvrđujem da želim ukloniti ovog igrača sa shortliste",
                                key=f"confirm_remove_entry_{entry_id}")
        if st.button("Ukloni igrača", disabled=not confirmed, key=f"remove_entry_{entry_id}"):
            try:
                ctx.repo.remove_shortlist_player(entry_id, confirmed=confirmed)
            except scouting_database.ScoutingDatabaseError as exc:
                st.error(str(exc))
            else:
                flash("Igrač je uklonjen sa shortliste.")
                st.rerun()


# =============================================================================
# Page: Usporedba igrača
# =============================================================================

def render_comparison(ctx):
    st.title("Usporedba igrača")
    suffix, season_players = season_selector(ctx, "compare_season")
    if suffix is None:
        return
    labels = {int(r.player_id): scout_players.player_label(r)
              for _, r in season_players.sort_values("player_name").iterrows()}
    chosen = st.multiselect("Igrači (2 do 4)", list(labels), format_func=labels.get, max_selections=4)
    if len(chosen) < 2:
        st.info("Odaberite najmanje dva igrača za usporedbu.")
        return

    selected = season_players[season_players["player_id"].isin(chosen)].set_index("player_id").loc[chosen]
    selected = selected.reset_index()
    names = selected["player_name"].tolist()

    st.subheader("Osnovni podaci")
    basic = selected[["player_name", "team_name", "position", "age", "minutes"]].rename(columns=COLUMN_LABELS)
    st.dataframe(basic, hide_index=True, width="stretch", column_config=score_columns_config())

    st.subheader("Ocjene")
    score_cols = [c for c in ["overall_score", "scout_score", "combined_score", "scout_report_count"]]
    scores = selected[["player_name"] + score_cols].rename(columns=COLUMN_LABELS)
    st.dataframe(scores, hide_index=True, width="stretch", column_config=score_columns_config())
    if selected["scout_report_count"].eq(0).any():
        st.caption("Igrači bez skautskog izvještaja nemaju skautsku ni kombiniranu ocjenu.")
    if (selected["position"] == "Goalkeeper").any():
        st.caption(GOALKEEPER_NOTE)

    other_scores = [c for c in scout_players.ANALYTICAL_SCORE_COLUMNS
                    if c != "overall_score" and c in selected.columns and selected[c].notna().any()]
    if other_scores:
        st.markdown("**Ostale analitičke ocjene**")
        st.dataframe(selected[["player_name"] + other_scores].round(1).rename(columns=COLUMN_LABELS),
                     hide_index=True, width="stretch")

    st.subheader("Ključne statistike po 90 minuta")
    per90 = [c for c in scout_players.KEY_PER90_COLUMNS if c in selected.columns]
    st.dataframe(selected[["player_name"] + per90].round(2).rename(columns=COLUMN_LABELS),
                 hide_index=True, width="stretch")

    st.subheader("Grafikon")
    kind = st.radio("Vrsta grafikona", ["Radar", "Stupčasti"], horizontal=True)
    metrics = {c: label for c, label in RADAR_METRICS.items()
               if c in selected.columns and selected[c].notna().any()}
    if not metrics:
        st.info("Nema ocjena za grafikon.")
        return
    if kind == "Radar":
        fig = go.Figure()
        for _, player in selected.iterrows():
            values = [None if pd.isna(player[c]) else float(player[c]) for c in metrics]
            labels_ = list(metrics.values())
            fig.add_trace(go.Scatterpolar(
                r=values + values[:1], theta=labels_ + labels_[:1], name=player["player_name"], fill="toself",
            ))
        fig.update_layout(polar={"radialaxis": {"range": [0, 100]}}, title="Ocjene (0-100)")
    else:
        long = selected.melt(id_vars="player_name", value_vars=list(metrics), var_name="metric", value_name="score")
        long["metric"] = long["metric"].map(metrics)
        fig = px.bar(long, x="metric", y="score", color="player_name", barmode="group", title="Ocjene (0-100)")
        fig.update_layout(xaxis_title="", yaxis_title="Ocjena", yaxis_range=[0, 100])
    st.plotly_chart(fig, width="stretch")
    st.caption(f"Uspoređeni igrači: {', '.join(names)}")


# =============================================================================
# Page: Postavke veze
# =============================================================================

def render_settings(ctx):
    st.title("Postavke veze")
    st.warning(
        "**Ova aplikacija mora ostati privatna.** Dok koristi secret ključ, ne smije se "
        "postaviti kao javna Streamlit aplikacija - vidi "
        f"[SCOUTING_SETUP.md]({scouting_database.SETUP_DOC_URL})."
    )

    st.subheader("Konfiguracija")
    status = scouting_database.config_status(st.secrets, None)
    source_labels = {"st.secrets": "Streamlit Secrets", "environment": "varijabla okruženja / .env", None: "NEDOSTAJE"}
    st.dataframe(
        pd.DataFrame([{"Varijabla": name, "Izvor": source_labels[source]} for name, source in status.items()]),
        hide_index=True, width="stretch",
    )
    st.caption("Vrijednosti (ni URL ni ključ) se nikada ne prikazuju.")

    st.subheader("Test veze")
    if ctx.repo is None:
        st.warning(f"{ctx.config_error}\n\nUpute: [SCOUTING_SETUP.md]({scouting_database.SETUP_DOC_URL}).")
        return
    if st.button("Provjeri vezu s bazom"):
        results = ctx.repo.check_connection()
        for table, error in results.items():
            if error is None:
                st.success(f"`{table}`: OK")
            else:
                st.error(f"`{table}`: {error}")
        if all(error is None for error in results.values()):
            st.info("Veza radi i shema je primijenjena. Možete unijeti prvi skautski izvještaj.")
        else:
            st.info("Ako tablice ne postoje, pokrenite `supabase/schema.sql` u SQL Editoru (korak 2 u uputama).")


# =============================================================================
# Main
# =============================================================================

def main():
    # The gate comes first: until it passes, no data is loaded and no
    # Supabase client is created.
    if not require_login():
        return

    st.sidebar.title("Skautski sustav")
    st.sidebar.caption("Privatna aplikacija - ne objavljivati javno")
    if st.sidebar.button("Odjava"):
        logout()
        st.rerun()
    league_code = st.sidebar.selectbox(
        "Liga", list(scout_players.LEAGUES), format_func=lambda code: scout_players.LEAGUES[code].label,
        index=list(scout_players.LEAGUES).index(scout_players.DEFAULT_LEAGUE),
    )
    page = st.sidebar.radio("Stranica", PAGES)

    ctx = build_context(league_code)
    {
        "Početna": render_home,
        "Pretraživanje igrača": render_search,
        "Skautska procjena": render_assessment,
        "Shortliste": render_shortlists,
        "Usporedba igrača": render_comparison,
        "Postavke veze": render_settings,
    }[page](ctx)


if __name__ == "__main__":
    main()
