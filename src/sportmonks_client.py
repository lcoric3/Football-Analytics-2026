"""
Thin client for the SportMonks Football API (v3).

Football data science logic:
This module has no football logic in it - it only knows how to talk to
SportMonks reliably (auth, pagination, retries, rate limits). Keeping this
separate from fetch_data.py means the "what data do we want" logic doesn't
get tangled up with "how do we make an HTTP request work".
"""
import os
import time
import logging

import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://api.sportmonks.com/v3/football"

MAX_RETRIES = 5
INITIAL_BACKOFF_SECONDS = 2


class SportMonksError(Exception):
    """Raised for SportMonks API errors that retries can't fix."""


class SportMonksClient:
    def __init__(self, token=None):
        # Rule from CLAUDE.md: never hardcode the API token. It always
        # comes from the environment (directly, or via a .env file loaded
        # with python-dotenv before this client is created).
        self.token = token or os.getenv("SPORTMONKS_API_TOKEN")
        if not self.token:
            raise SportMonksError(
                "SPORTMONKS_API_TOKEN is not set. Set it as an environment "
                "variable or in a .env file before running the pipeline."
            )

    def _request(self, endpoint, params=None):
        """Make a single GET request, retrying on transient failures."""
        url = f"{BASE_URL}{endpoint}"
        params = dict(params or {})
        params["api_token"] = self.token

        backoff = INITIAL_BACKOFF_SECONDS
        last_error = None

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = requests.get(url, params=params, timeout=30)
            except requests.RequestException as exc:
                last_error = exc
                logger.warning(
                    "Request failed (attempt %d/%d) for %s: %s",
                    attempt, MAX_RETRIES, endpoint, exc,
                )
                time.sleep(backoff)
                backoff *= 2
                continue

            if response.status_code == 429:
                # Rate limited. Respect Retry-After if SportMonks sends it,
                # otherwise fall back to exponential backoff.
                retry_after = int(response.headers.get("Retry-After", backoff))
                logger.warning(
                    "Rate limited on %s, waiting %ds before retrying...",
                    endpoint, retry_after,
                )
                time.sleep(retry_after)
                backoff *= 2
                continue

            if response.status_code == 401:
                raise SportMonksError(
                    "SportMonks API rejected the token (401 Unauthorized). "
                    "Check that SPORTMONKS_API_TOKEN is correct and active."
                )

            if response.status_code == 404:
                logger.warning("Not found (404): %s", endpoint)
                return None

            if response.status_code >= 500:
                last_error = SportMonksError(
                    f"SportMonks server error {response.status_code} on {endpoint}"
                )
                logger.warning(
                    "Server error (attempt %d/%d) for %s: %s",
                    attempt, MAX_RETRIES, endpoint, response.status_code,
                )
                time.sleep(backoff)
                backoff *= 2
                continue

            if not response.ok:
                raise SportMonksError(
                    f"SportMonks API error {response.status_code} on {endpoint}: "
                    f"{response.text[:500]}"
                )

            data = response.json()
            if data is None:
                logger.warning("Empty response body for %s", endpoint)
                return {}
            return data

        raise SportMonksError(
            f"Failed to GET {endpoint} after {MAX_RETRIES} attempts: {last_error}"
        )

    def get(self, endpoint, params=None):
        """Single request, returns the parsed JSON body (no pagination)."""
        return self._request(endpoint, params)

    def get_all(self, endpoint, params=None):
        """
        Follow pagination and return every item under "data" as one list.

        SportMonks v3 pagination can show up in slightly different shapes
        depending on the endpoint/plan, so this handles the documented
        variants defensively:
          - meta.pagination.has_more + next_cursor  -> pass `cursor` param
          - meta.pagination.has_more + next_page URL -> GET that URL directly
          - otherwise                                -> increment `page` param
        """
        params = dict(params or {})
        items = []
        next_url = None

        while True:
            if next_url:
                # next_page was a full URL (already includes api_token/params).
                response = requests.get(next_url, timeout=30)
                response.raise_for_status()
                body = response.json()
            else:
                body = self._request(endpoint, params)

            if not body:
                break

            items.extend(body.get("data", []) or [])

            pagination = (body.get("meta") or {}).get("pagination") or body.get("pagination")
            if not pagination or not pagination.get("has_more"):
                break

            if pagination.get("next_cursor"):
                params["cursor"] = pagination["next_cursor"]
                next_url = None
            elif pagination.get("next_page"):
                next_url = pagination["next_page"]
            else:
                params["page"] = pagination.get("current_page", 1) + 1
                next_url = None

        return items
