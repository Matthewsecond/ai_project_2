"""
Fixtures for the frontend integration tests.

Builds the real Flask app via `create_app()` with the auth DB init stubbed out (no MySQL), and
offers an authenticated client that has cleared the login gate. The blueprints are real and wired;
individual tests mock the *service* calls at the blueprint boundary so nothing hits OpenAI / the DB.
"""
import pytest


@pytest.fixture
def app(monkeypatch):
    """The assembled Flask app, with `auth.init_db` stubbed so create_app() touches no DB."""
    import jobs_intelligence_ai.services.auth as auth
    monkeypatch.setattr(auth, "init_db", lambda *a, **k: None)

    from jobs_intelligence_ai.frontend.app import create_app
    app = create_app()
    app.config.update(TESTING=True)
    return app


@pytest.fixture
def client(app):
    """A bare test client (no session) — for exercising the login gate."""
    return app.test_client()


@pytest.fixture
def auth_client(client):
    """A test client with a logged-in session, so requests clear the before_request gate."""
    with client.session_transaction() as sess:
        sess["user_id"]      = 1
        sess["username"]     = "tester"
        sess["display_name"] = "Tester"
        sess["role"]         = "admin"
    return client
