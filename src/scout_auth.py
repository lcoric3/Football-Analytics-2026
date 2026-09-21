"""
Login gate logic for the private scouting app (scout_app.py).

WHY A PASSWORD ON TOP OF STREAMLIT'S ACCESS CONTROL
scout_app.py can read, edit and delete every scouting note, because it talks
to Supabase with a secret key that bypasses Row Level Security. Streamlit's
"Only specific people can view this app" setting is the primary protection,
but it is a single switch that is easy to get wrong (a Community Cloud app
deployed from a public repository is public by default). The password gate
is a SECOND, independent layer: even if the app were public by mistake,
nobody sees data - or triggers a Supabase connection - without the password.
It does not replace the "Only specific people" setting.

What this module does (pure logic - no Streamlit, no network, no Supabase):
    * load_password: reads SCOUT_APP_PASSWORD (st.secrets first, then the
      environment - the same lookup order as the Supabase settings).
    * verify_password: constant-time comparison with hmac.compare_digest.
    * AttemptLimiter: slows down guessing after repeated failures.

Rules it is built around:
    * The password is never logged, printed, returned in an error message or
      stored anywhere. The only thing scout_app.py keeps in session state is a
      boolean "logged in" flag.
    * No password configured => the app stays LOCKED (there is no
      "open by default" mode).
"""
import hashlib
import hmac
import logging
import math
import threading
import time

from src.scouting_database import read_setting

logger = logging.getLogger(__name__)

PASSWORD_VARIABLE = "SCOUT_APP_PASSWORD"

# After this many wrong passwords in a row a temporary lockout starts...
MAX_FAILURES_BEFORE_LOCKOUT = 5
# ...lasting BASE seconds, doubling with every further lockout up to MAX.
BASE_LOCKOUT_SECONDS = 30
MAX_LOCKOUT_SECONDS = 900
# The UI shows a warning once this many wrong passwords in a row were seen.
WARN_AFTER_FAILURES = 3


def load_password(secrets=None, environ=None):
    """The configured password (secrets first, then environment), or None
    when it is missing or blank. None means: keep the app locked."""
    value, _source = read_setting(PASSWORD_VARIABLE, secrets, environ)
    return value


def verify_password(candidate, expected):
    """True only if `candidate` equals `expected`.

    Both sides are hashed with SHA-256 first and the two fixed-length digests
    are compared with hmac.compare_digest. That keeps the comparison
    constant-time AND independent of the password length (compare_digest on
    raw values of different lengths would leak the length), and it works for
    any characters, not just ASCII. A missing/blank expected password never
    matches anything."""
    if not expected or not isinstance(candidate, str):
        return False
    candidate_digest = hashlib.sha256(candidate.strip().encode("utf-8")).digest()
    expected_digest = hashlib.sha256(expected.encode("utf-8")).digest()
    return hmac.compare_digest(candidate_digest, expected_digest)


class AttemptLimiter:
    """Throttles password guessing.

    One instance is shared by every browser session of the running app (the
    app keeps it in st.cache_resource), so opening a new tab does not reset
    the counter - which a counter kept in session state would allow.
    Thread-safe; the clock is injectable for tests."""

    def __init__(
        self,
        max_failures=MAX_FAILURES_BEFORE_LOCKOUT,
        base_lockout=BASE_LOCKOUT_SECONDS,
        max_lockout=MAX_LOCKOUT_SECONDS,
        clock=time.monotonic,
    ):
        self._max_failures = max_failures
        self._base_lockout = base_lockout
        self._max_lockout = max_lockout
        self._clock = clock
        self._lock = threading.Lock()
        self._failures_since_success = 0   # drives the UI warning
        self._failures_in_window = 0       # drives the lockout
        self._lockouts = 0
        self._locked_until = 0.0

    @property
    def failures_since_success(self):
        with self._lock:
            return self._failures_since_success

    def seconds_locked(self):
        """Whole seconds left in the current lockout (0 = not locked)."""
        with self._lock:
            remaining = self._locked_until - self._clock()
            return max(0, math.ceil(remaining))

    def record_failure(self):
        """Counts a wrong password; starts a lockout after enough of them."""
        with self._lock:
            self._failures_since_success += 1
            self._failures_in_window += 1
            if self._failures_in_window >= self._max_failures:
                self._lockouts += 1
                duration = min(self._base_lockout * 2 ** (self._lockouts - 1), self._max_lockout)
                self._locked_until = self._clock() + duration
                self._failures_in_window = 0
                logger.warning("Login temporarily locked for %s s after repeated failures.", duration)
            else:
                logger.warning("Failed login attempt (%s in a row).", self._failures_since_success)

    def record_success(self):
        """A correct password clears every counter and any lockout."""
        with self._lock:
            self._failures_since_success = 0
            self._failures_in_window = 0
            self._lockouts = 0
            self._locked_until = 0.0
