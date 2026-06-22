"""
Lightweight fakes for unit-testing JIA's sync SQLAlchemy code without a database.

JIA runs SQL through the pattern:

    with get_engine().connect() as conn:
        result = conn.execute(text(sql), params)
        rows = [dict(r._mapping) for r in result]

These fakes record every executed statement (whitespace-normalised) and return
canned rows for the SELECTs a test programs, so a unit test can assert exactly which
SQL a code path emits and feed it deterministic results — no live MySQL needed.

Usage:
    eng = FakeEngine({"FROM View_Jobs": [{"job_id": 1, "title": "Engineer"}]})
    monkeypatch.setattr(database, "get_engine", lambda: eng)
    ...
    assert eng.calls  # inspect emitted SQL
"""
from __future__ import annotations

import re


def _norm(sql: str) -> str:
    """Whitespace-normalise SQL so substring matching is robust to formatting."""
    return re.sub(r"\s+", " ", str(sql)).strip()


class FakeRow:
    """Stand-in for a SQLAlchemy Row: supports `dict(row._mapping)` and `row.col`."""

    def __init__(self, mapping: dict):
        self._mapping = dict(mapping)

    def __getattr__(self, name):
        try:
            return self._mapping[name]
        except KeyError as e:
            raise AttributeError(name) from e

    def __getitem__(self, key):
        return self._mapping[key]


class FakeResult:
    """Stand-in for a SQLAlchemy CursorResult — iterable, with fetchall/rowcount."""

    def __init__(self, rows=(), lastrowid=None, rowcount=0):
        self._rows = [r if isinstance(r, FakeRow) else FakeRow(r) for r in rows]
        self.lastrowid = lastrowid
        self.rowcount = rowcount if rowcount else len(self._rows)

    def __iter__(self):
        return iter(self._rows)

    def fetchall(self):
        return list(self._rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None


class FakeConn:
    """Records every execute(); returns canned results for matching SELECTs.

    `responses` maps a substring of the normalised SQL to either a list of row
    dicts, a FakeResult, or a list of FakeResults consumed in call order. A
    statement matching nothing returns an empty result with an auto-incrementing
    lastrowid (so inserts get distinct ids).
    """

    def __init__(self, responses: dict | None = None, calls: list | None = None):
        self._responses = responses or {}
        self.calls = calls if calls is not None else []
        self._auto_id = 1000

    def execute(self, statement, params=None):
        sql = _norm(statement)
        self.calls.append((sql, params))
        for needle, canned in self._responses.items():
            if _norm(needle) in sql:
                if isinstance(canned, list) and canned and isinstance(canned[0], FakeResult):
                    return canned.pop(0)
                if isinstance(canned, FakeResult):
                    return canned
                return FakeResult(rows=canned)
        self._auto_id += 1
        return FakeResult(lastrowid=self._auto_id)

    # context-manager protocol: `with get_engine().connect() as conn:`
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def close(self):
        pass


class FakeEngine:
    """Stand-in for a SQLAlchemy Engine — `.connect()` yields a FakeConn."""

    def __init__(self, responses: dict | None = None):
        self.responses = responses or {}
        self.calls: list = []   # shared across connections, in call order

    def connect(self):
        return FakeConn(self.responses, self.calls)
