"""
Input validation for the private scouting app's forms.

Every rule here mirrors a CHECK constraint in supabase/schema.sql (the
database is the last line of defence; this module exists so the user gets a
clear message in plain language instead of a raw database error). A test
compares the value lists below with the SQL file so the two cannot silently
drift apart.

Each validate_* function returns a ValidationResult: `data` holds the cleaned,
database-ready dict when the input is valid, `errors` holds human-readable
(Croatian) messages when it is not. Nothing here raises for bad user input and
nothing here touches the network.
"""
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from numbers import Integral, Real

from src.scout_ratings import RATING_MAX, RATING_MIN

# --- Allowed values (mirrored in supabase/schema.sql) -----------------------

RECOMMENDATIONS = (
    "Preporučeno",
    "Nastaviti pratiti",
    "Potrebno ponovno gledati",
    "Ne preporučuje se",
)

STATUSES = (
    "Praćenje",
    "Potrebno skautirati",
    "Prioritet",
    "Odbijen",
)
DEFAULT_STATUS = STATUSES[0]

# 1 = highest priority ... 5 = lowest.
PRIORITY_MIN = 1
PRIORITY_MAX = 5
DEFAULT_PRIORITY = 3

# --- Length limits (mirrored in supabase/schema.sql) ------------------------

MAX_OPPONENT_LEN = 100
MAX_POSITION_LEN = 50
MAX_STRENGTHS_LEN = 2000
MAX_WEAKNESSES_LEN = 2000
MAX_NOTES_LEN = 5000
MAX_SHORTLIST_NAME_LEN = 100
MAX_SHORTLIST_DESCRIPTION_LEN = 1000
MAX_SHORTLIST_NOTE_LEN = 1000

RATING_FIELDS = {
    "technical_rating": "Tehnička ocjena",
    "tactical_rating": "Taktička ocjena",
    "physical_rating": "Fizička ocjena",
    "mental_rating": "Mentalna ocjena",
    "potential_rating": "Ocjena potencijala",
}

_LEAGUE_CODE_RE = re.compile(r"^[a-z0-9_]{1,32}$")
_SEASON_SUFFIX_RE = re.compile(r"^[0-9]{4}_[0-9]{4}$")


@dataclass
class ValidationResult:
    data: dict = field(default_factory=dict)
    errors: list = field(default_factory=list)

    @property
    def ok(self):
        return not self.errors


# --- Small helpers ----------------------------------------------------------

def _to_int(value):
    """Whole-number value or None. Accepts ints, integral floats (7.0) and
    digit strings; rejects bool, NaN, fractions and everything else."""
    if isinstance(value, bool):
        return None
    if isinstance(value, Integral):
        return int(value)
    if isinstance(value, Real):
        return int(value) if float(value).is_integer() else None
    if isinstance(value, str) and re.fullmatch(r"\s*-?\d+\s*", value):
        return int(value)
    return None


def _clean_text(value, label, max_len, errors, required=False):
    """Trimmed text, or None when empty. Records an error when a required
    field is empty or a field is longer than the database allows."""
    text = "" if value is None else str(value).strip()
    if not text:
        if required:
            errors.append(f"{label} je obavezno polje.")
        return None
    if len(text) > max_len:
        errors.append(f"{label} može imati najviše {max_len} znakova (uneseno: {len(text)}).")
        return None
    return text


def _clean_date(value, errors, today):
    if isinstance(value, datetime):
        value = value.date()
    elif isinstance(value, str):
        try:
            value = date.fromisoformat(value.strip())
        except ValueError:
            errors.append("Datum promatranja nije ispravan (očekivani oblik: GGGG-MM-DD).")
            return None
    if not isinstance(value, date):
        errors.append("Datum promatranja je obavezno polje.")
        return None
    if value > today:
        errors.append("Datum promatranja ne može biti u budućnosti.")
        return None
    return value


def _clean_rating(value, label, errors):
    rating = _to_int(value)
    if rating is None or not RATING_MIN <= rating <= RATING_MAX:
        errors.append(f"{label} mora biti cijeli broj od {RATING_MIN} do {RATING_MAX}.")
        return None
    return rating


# --- Public validators ------------------------------------------------------

def validate_report(form, today=None):
    """Validates a scouting-report form (a dict of raw widget values).

    Required: player, season, league, observation date (not in the future),
    observed position, the five 1-10 ratings and a recommendation. Optional:
    opponent, strengths, weaknesses, notes."""
    today = today or date.today()
    errors = []
    data = {}

    league_code = str(form.get("league_code") or "").strip()
    if not _LEAGUE_CODE_RE.match(league_code):
        errors.append("Liga nije ispravna.")
    data["league_code"] = league_code

    player_id = _to_int(form.get("player_id"))
    if player_id is None or player_id <= 0:
        errors.append("Igrač nije odabran.")
    data["player_id"] = player_id

    season_suffix = str(form.get("season_suffix") or "").strip()
    if not _SEASON_SUFFIX_RE.match(season_suffix):
        errors.append("Sezona nije ispravna.")
    data["season_suffix"] = season_suffix

    data["observation_date"] = _clean_date(form.get("observation_date"), errors, today)
    data["opponent"] = _clean_text(form.get("opponent"), "Protivnik", MAX_OPPONENT_LEN, errors)
    data["observed_position"] = _clean_text(
        form.get("observed_position"), "Promatrana pozicija", MAX_POSITION_LEN, errors, required=True
    )

    for column, label in RATING_FIELDS.items():
        data[column] = _clean_rating(form.get(column), label, errors)

    data["strengths"] = _clean_text(form.get("strengths"), "Snage", MAX_STRENGTHS_LEN, errors)
    data["weaknesses"] = _clean_text(form.get("weaknesses"), "Slabosti", MAX_WEAKNESSES_LEN, errors)
    data["notes"] = _clean_text(form.get("notes"), "Opće bilješke", MAX_NOTES_LEN, errors)

    recommendation = form.get("recommendation")
    if recommendation not in RECOMMENDATIONS:
        errors.append("Preporuka mora biti jedna od ponuđenih vrijednosti.")
    data["recommendation"] = recommendation

    if errors:
        return ValidationResult(errors=errors)
    # ISO string so the payload is JSON-serialisable for the API client.
    data["observation_date"] = data["observation_date"].isoformat()
    return ValidationResult(data=data)


def validate_shortlist(name, description):
    """Validates a shortlist name (required) and description (optional)."""
    errors = []
    data = {
        "name": _clean_text(name, "Naziv shortliste", MAX_SHORTLIST_NAME_LEN, errors, required=True),
        "description": _clean_text(
            description, "Opis shortliste", MAX_SHORTLIST_DESCRIPTION_LEN, errors
        ),
    }
    return ValidationResult(errors=errors) if errors else ValidationResult(data=data)


def validate_shortlist_entry(status, priority, note):
    """Validates the editable fields of a player on a shortlist."""
    errors = []
    if status not in STATUSES:
        errors.append("Status mora biti jedna od ponuđenih vrijednosti.")
    priority_value = _to_int(priority)
    if priority_value is None or not PRIORITY_MIN <= priority_value <= PRIORITY_MAX:
        errors.append(f"Prioritet mora biti cijeli broj od {PRIORITY_MIN} do {PRIORITY_MAX}.")
    cleaned_note = _clean_text(note, "Bilješka", MAX_SHORTLIST_NOTE_LEN, errors)
    if errors:
        return ValidationResult(errors=errors)
    return ValidationResult(data={"status": status, "priority": priority_value, "note": cleaned_note})
