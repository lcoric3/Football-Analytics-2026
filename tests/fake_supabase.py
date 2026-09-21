"""
In-memory stand-in for the official Supabase client, used by the scouting
tests and by the scout_app smoke test. It implements just the query-builder
surface scouting_database.py uses (table/select/insert/update/delete/eq/in_/
order/range/limit/execute) and imitates the database behaviours the code
relies on:

  * UNIQUE constraints raise an error carrying PostgreSQL code "23505"
    (exactly what postgrest's APIError exposes as `.code`)
  * ON DELETE CASCADE from shortlists to shortlist_players
  * generated uuid `id`, `created_at`/`added_at` and `updated_at` (bumped on
    every update, like the schema's trigger)
  * column defaults (league_code, status, priority)

No network, no Supabase, no credentials - safe to use anywhere.
"""
import copy
import itertools
import uuid


class FakeAPIError(Exception):
    """Shaped like postgrest.exceptions.APIError (has .code and .message)."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


class FakeResult:
    def __init__(self, data):
        self.data = data


# table -> functions mapping a row to its UNIQUE key (None = not applicable)
UNIQUE_KEYS = {
    "shortlists": [lambda r: ("name", str(r["name"]).lower())],
    "shortlist_players": [lambda r: ("player", r["shortlist_id"], r["player_id"])],
}

DEFAULTS = {
    "scouting_reports": {"league_code": "hnl"},
    "shortlists": {"description": None},
    "shortlist_players": {"league_code": "hnl", "status": "Praćenje", "priority": 3, "note": None},
}

TIMESTAMP_COLUMNS = {
    "scouting_reports": ("created_at",),
    "shortlists": ("created_at",),
    "shortlist_players": ("added_at",),
}


class FakeSupabaseClient:
    def __init__(self):
        self.tables = {"scouting_reports": [], "shortlists": [], "shortlist_players": []}
        self.calls = []            # (table, operation) log for assertions
        self.fail_with = None      # set to an exception to make the next execute() raise
        self._clock = itertools.count(1)

    def table(self, name):
        return FakeQuery(self, name)

    def _now(self):
        # Monotonic fake timestamps: sortable strings that always increase.
        return f"2026-01-01T00:00:{next(self._clock):06d}+00:00"


class FakeQuery:
    def __init__(self, client, table):
        self._client = client
        self._table = table
        self._op = "select"
        self._payload = None
        self._filters = []
        self._orders = []
        self._range = None
        self._limit = None

    # -- builder -------------------------------------------------------------
    def select(self, _columns="*"):
        self._op = "select"
        return self

    def insert(self, payload):
        self._op, self._payload = "insert", payload
        return self

    def update(self, payload):
        self._op, self._payload = "update", payload
        return self

    def delete(self):
        self._op = "delete"
        return self

    def eq(self, column, value):
        self._filters.append((column, lambda v, target=value: v == target))
        return self

    def in_(self, column, values):
        self._filters.append((column, lambda v, target=tuple(values): v in target))
        return self

    def order(self, column, desc=False):
        self._orders.append((column, desc))
        return self

    def range(self, start, end):
        self._range = (start, end)
        return self

    def limit(self, count):
        self._limit = count
        return self

    # -- execution -----------------------------------------------------------
    def _matching(self):
        rows = self._client.tables[self._table]
        return [r for r in rows if all(pred(r.get(col)) for col, pred in self._filters)]

    def execute(self):
        self._client.calls.append((self._table, self._op))
        if self._client.fail_with is not None:
            error, self._client.fail_with = self._client.fail_with, None
            raise error
        return getattr(self, f"_do_{self._op}")()

    def _do_select(self):
        rows = self._matching()
        # Apply the last order() first so the FIRST order() is the primary key.
        for column, desc in reversed(self._orders):
            present = [r for r in rows if r.get(column) is not None]
            missing = [r for r in rows if r.get(column) is None]
            rows = sorted(present, key=lambda r: r[column], reverse=desc) + missing
        if self._range is not None:
            rows = rows[self._range[0]: self._range[1] + 1]
        if self._limit is not None:
            rows = rows[: self._limit]
        return FakeResult(copy.deepcopy(rows))

    def _do_insert(self):
        payloads = self._payload if isinstance(self._payload, list) else [self._payload]
        created = []
        for payload in payloads:
            row = {**DEFAULTS.get(self._table, {}), **payload}
            self._check_foreign_key(row)
            self._check_unique(row)
            now = self._client._now()
            row["id"] = str(uuid.uuid4())
            for column in TIMESTAMP_COLUMNS[self._table]:
                row[column] = now
            row["updated_at"] = now
            self._client.tables[self._table].append(row)
            created.append(copy.deepcopy(row))
        return FakeResult(created)

    def _do_update(self):
        updated = []
        for row in self._matching():
            candidate = {**row, **self._payload}
            self._check_unique(candidate, ignore=row)
            row.update(self._payload)
            row["updated_at"] = self._client._now()
            updated.append(copy.deepcopy(row))
        return FakeResult(updated)

    def _do_delete(self):
        doomed = self._matching()
        ids = {r["id"] for r in doomed}
        rows = self._client.tables[self._table]
        rows[:] = [r for r in rows if r["id"] not in ids]
        if self._table == "shortlists":  # ON DELETE CASCADE
            members = self._client.tables["shortlist_players"]
            members[:] = [m for m in members if m["shortlist_id"] not in ids]
        return FakeResult(copy.deepcopy(doomed))

    # -- constraints ---------------------------------------------------------
    def _check_unique(self, candidate, ignore=None):
        for key_fn in UNIQUE_KEYS.get(self._table, []):
            for existing in self._client.tables[self._table]:
                if existing is ignore:
                    continue
                if key_fn(existing) == key_fn(candidate):
                    raise FakeAPIError(
                        "23505",
                        f'duplicate key value violates unique constraint on "{self._table}"',
                    )

    def _check_foreign_key(self, row):
        if self._table == "shortlist_players":
            parents = {s["id"] for s in self._client.tables["shortlists"]}
            if row.get("shortlist_id") not in parents:
                raise FakeAPIError("23503", "violates foreign key constraint on shortlist_id")
