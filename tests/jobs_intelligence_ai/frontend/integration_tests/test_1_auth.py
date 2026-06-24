"""
Integration tests for the app-level auth gate (Flask test_client).

The `before_request` login gate lives on the app, not in any blueprint, so it only appears once
the app is assembled. Asserts: unauthenticated API calls get a JSON 401, unauthenticated page
loads redirect to /login, and /login itself is public.
"""


def test_api_requires_login(client):
    """An unauthenticated /api/ request is rejected with a JSON 401."""
    resp = client.get("/api/filters")
    assert resp.status_code == 401
    assert resp.get_json()["ok"] is False


def test_page_redirects_to_login(client):
    """An unauthenticated page load redirects to the login screen."""
    resp = client.get("/")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_login_page_is_public(client):
    """The login page is reachable without a session."""
    resp = client.get("/login")
    assert resp.status_code == 200


def test_authenticated_request_passes_gate(auth_client, monkeypatch):
    """With a session, the gate lets the request through to the route (here a mocked service)."""
    monkeypatch.setattr(
        "jobs_intelligence_ai.frontend.blueprints.job_detail.translate_description",
        lambda desc: "ok")
    resp = auth_client.post("/api/desc_translate", json={"description": "x"})
    assert resp.status_code == 200
