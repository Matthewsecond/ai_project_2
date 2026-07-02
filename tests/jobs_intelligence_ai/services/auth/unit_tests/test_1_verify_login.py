"""
Offline unit tests for auth.verify_login (2.3 #9).

auth is DB-only; the security-critical bit is the password check, which we pin without a live
DB via a tiny inline fake engine (mimicking `get_engine().connect()` → `.execute().mappings()
.first()`). A correct password returns the user dict (no hash); a wrong password or unknown
user returns None. The rest (init_db/create_user/list_users) is covered by boot + the login flow.
"""
from werkzeug.security import generate_password_hash

import jobs_intelligence_ai.services.auth.accounts as acc


class _FakeMappings:
    def __init__(self, row): self._row = row
    def first(self): return self._row


class _FakeExecResult:
    def __init__(self, row): self._row = row
    def mappings(self): return _FakeMappings(self._row)


class _FakeConn:
    def __init__(self, row): self._row = row
    def __enter__(self): return self
    def __exit__(self, *exc): return False
    def execute(self, *a, **k): return _FakeExecResult(self._row)


def _patch(monkeypatch, row):
    """Make get_engine().connect() yield a conn whose SELECT returns `row` (or None)."""
    engine = type("E", (), {"connect": lambda self: _FakeConn(row)})()
    monkeypatch.setattr(acc, "get_engine", lambda: engine)


def _row(password):
    return {"id": 1, "account_company_id": 1, "username": "admin",
            "password_hash": generate_password_hash(password),
            "display_name": "Administrator", "role": "admin", "visibility": "all"}


def test_correct_password_returns_user_without_hash(monkeypatch):
    """A matching password returns the public user dict — never the hash."""
    _patch(monkeypatch, _row("admin"))
    out = acc.verify_login("admin", "admin")
    assert out == {"id": 1, "account_company_id": 1, "username": "admin",
                   "display_name": "Administrator", "role": "admin", "visibility": "all"}
    assert "password_hash" not in out


def test_wrong_password_returns_none(monkeypatch):
    """A bad password is rejected."""
    _patch(monkeypatch, _row("correct-horse"))
    assert acc.verify_login("admin", "wrong") is None


def test_unknown_user_returns_none(monkeypatch):
    """No matching row → None (no crash on the missing user)."""
    _patch(monkeypatch, None)
    assert acc.verify_login("ghost", "x") is None
