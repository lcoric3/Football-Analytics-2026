"""Tests for src/scout_auth.py - password lookup, comparison and attempt
throttling. Pure logic: no Streamlit, no Supabase, no network, and the
passwords used here are obviously fake."""
import logging
import threading

import pytest

from src import scout_auth as auth

PASSWORD = "fake-test-password-Zx9!-not-a-real-secret"
OTHER = "another-fake-password-0000"


# --- load_password --------------------------------------------------------------

def test_password_comes_from_secrets_first_then_environment():
    assert auth.load_password({"SCOUT_APP_PASSWORD": PASSWORD}, {"SCOUT_APP_PASSWORD": OTHER}) == PASSWORD
    assert auth.load_password({}, {"SCOUT_APP_PASSWORD": OTHER}) == OTHER


def test_the_variable_name_is_the_documented_one():
    assert auth.PASSWORD_VARIABLE == "SCOUT_APP_PASSWORD"


@pytest.mark.parametrize("blank", [None, "", "   ", 12345])
def test_missing_or_blank_password_means_none(blank):
    assert auth.load_password({"SCOUT_APP_PASSWORD": blank}, {"SCOUT_APP_PASSWORD": blank}) is None
    assert auth.load_password({}, {}) is None


def test_a_broken_secrets_object_falls_back_to_the_environment():
    class Exploding:
        def __getitem__(self, key):
            raise FileNotFoundError("no secrets.toml")

    assert auth.load_password(Exploding(), {"SCOUT_APP_PASSWORD": PASSWORD}) == PASSWORD
    assert auth.load_password(Exploding(), {}) is None


# --- verify_password ------------------------------------------------------------

def test_correct_password_is_accepted():
    assert auth.verify_password(PASSWORD, PASSWORD) is True


@pytest.mark.parametrize("wrong", [
    "", " ", OTHER, PASSWORD.upper(), PASSWORD[:-1], PASSWORD + "x", "x" + PASSWORD, None, 123, b"bytes",
])
def test_wrong_passwords_are_rejected(wrong):
    assert auth.verify_password(wrong, PASSWORD) is False


@pytest.mark.parametrize("expected", [None, "", "   "])
def test_nothing_matches_when_no_password_is_configured(expected):
    assert auth.verify_password("", expected) is False
    assert auth.verify_password(PASSWORD, expected) is False
    assert auth.verify_password(None, expected) is False


def test_surrounding_whitespace_of_the_input_is_ignored():
    assert auth.verify_password(f"  {PASSWORD}\n", PASSWORD) is True


def test_non_ascii_passwords_work():
    croatian = "šđčćž-Zaporka-ŠĐČĆŽ-2026"
    assert auth.verify_password(croatian, croatian) is True
    assert auth.verify_password("sdccz-Zaporka-SDCCZ-2026", croatian) is False


def test_comparison_uses_hmac_compare_digest_on_equal_length_digests(monkeypatch):
    seen = []
    real = auth.hmac.compare_digest

    def spy(a, b):
        seen.append((len(a), len(b)))
        return real(a, b)

    monkeypatch.setattr(auth.hmac, "compare_digest", spy)
    assert auth.verify_password("short", PASSWORD) is False
    assert auth.verify_password(PASSWORD, PASSWORD) is True
    # Both sides are SHA-256 digests (32 bytes), whatever the password length -
    # so the comparison leaks neither content nor length.
    assert seen == [(32, 32), (32, 32)]


def test_verifying_never_logs_the_passwords(caplog):
    with caplog.at_level(logging.DEBUG):
        auth.verify_password(OTHER, PASSWORD)
        auth.verify_password(PASSWORD, PASSWORD)
    assert PASSWORD not in caplog.text and OTHER not in caplog.text


# --- AttemptLimiter --------------------------------------------------------------

class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def limiter(clock):
    return auth.AttemptLimiter(clock=clock)


def fail(limiter, times):
    for _ in range(times):
        limiter.record_failure()


def test_defaults_are_sensible():
    assert auth.MAX_FAILURES_BEFORE_LOCKOUT == 5
    assert auth.WARN_AFTER_FAILURES < auth.MAX_FAILURES_BEFORE_LOCKOUT
    assert auth.BASE_LOCKOUT_SECONDS < auth.MAX_LOCKOUT_SECONDS


def test_a_fresh_limiter_is_not_locked(limiter):
    assert limiter.seconds_locked() == 0
    assert limiter.failures_since_success == 0


def test_no_lockout_before_the_limit(limiter):
    fail(limiter, auth.MAX_FAILURES_BEFORE_LOCKOUT - 1)
    assert limiter.seconds_locked() == 0
    assert limiter.failures_since_success == auth.MAX_FAILURES_BEFORE_LOCKOUT - 1


def test_lockout_starts_at_the_limit_and_lasts_the_base_duration(limiter, clock):
    fail(limiter, auth.MAX_FAILURES_BEFORE_LOCKOUT)
    assert limiter.seconds_locked() == auth.BASE_LOCKOUT_SECONDS
    clock.advance(10)
    assert limiter.seconds_locked() == auth.BASE_LOCKOUT_SECONDS - 10
    clock.advance(auth.BASE_LOCKOUT_SECONDS)
    assert limiter.seconds_locked() == 0


def test_remaining_seconds_round_up(limiter, clock):
    fail(limiter, auth.MAX_FAILURES_BEFORE_LOCKOUT)
    clock.advance(auth.BASE_LOCKOUT_SECONDS - 0.2)
    assert limiter.seconds_locked() == 1                          # never shows 0 while still locked


def test_each_further_lockout_doubles_up_to_the_cap(limiter, clock):
    durations = []
    for _ in range(8):
        fail(limiter, auth.MAX_FAILURES_BEFORE_LOCKOUT)
        durations.append(limiter.seconds_locked())
        clock.advance(auth.MAX_LOCKOUT_SECONDS + 1)               # wait it out
    expected = [min(auth.BASE_LOCKOUT_SECONDS * 2 ** i, auth.MAX_LOCKOUT_SECONDS) for i in range(8)]
    assert durations == expected
    assert durations[-1] == auth.MAX_LOCKOUT_SECONDS


def test_the_failure_window_restarts_after_a_lockout(limiter, clock):
    fail(limiter, auth.MAX_FAILURES_BEFORE_LOCKOUT)
    clock.advance(auth.MAX_LOCKOUT_SECONDS + 1)
    fail(limiter, auth.MAX_FAILURES_BEFORE_LOCKOUT - 1)
    assert limiter.seconds_locked() == 0                          # needs a full new round of failures


def test_success_clears_everything(limiter, clock):
    fail(limiter, auth.MAX_FAILURES_BEFORE_LOCKOUT)
    assert limiter.seconds_locked() > 0
    limiter.record_success()
    assert limiter.seconds_locked() == 0
    assert limiter.failures_since_success == 0
    fail(limiter, auth.MAX_FAILURES_BEFORE_LOCKOUT)               # escalation also started over
    assert limiter.seconds_locked() == auth.BASE_LOCKOUT_SECONDS


def test_the_warning_counter_survives_a_lockout_but_not_a_success(limiter, clock):
    fail(limiter, auth.MAX_FAILURES_BEFORE_LOCKOUT)
    clock.advance(auth.MAX_LOCKOUT_SECONDS + 1)
    assert limiter.failures_since_success == auth.MAX_FAILURES_BEFORE_LOCKOUT
    limiter.record_success()
    assert limiter.failures_since_success == 0


def test_custom_thresholds(clock):
    custom = auth.AttemptLimiter(max_failures=2, base_lockout=5, max_lockout=7, clock=clock)
    fail(custom, 2)
    assert custom.seconds_locked() == 5
    clock.advance(6)
    fail(custom, 2)
    assert custom.seconds_locked() == 7                           # 10 capped to 7


def test_limiter_is_thread_safe(limiter):
    threads = [threading.Thread(target=fail, args=(limiter, 25)) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert limiter.failures_since_success == 200


def test_failures_are_logged_without_any_password(limiter, caplog):
    with caplog.at_level(logging.DEBUG):
        fail(limiter, auth.MAX_FAILURES_BEFORE_LOCKOUT)
    assert "Failed login attempt" in caplog.text
    assert "locked" in caplog.text.lower()
    assert PASSWORD not in caplog.text
