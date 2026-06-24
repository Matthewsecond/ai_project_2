"""
Integration tests for the blueprint routes thinned in rework 2.4 (Flask test_client).

Services are mocked at the blueprint boundary, so these assert the wiring the conversions left in
place — input validation (400), the service result jsonified (200), and a service error mapped to
the 500 envelope — without touching OpenAI or the DB. Uses an authenticated client so requests
clear the login gate. Patch targets are the names imported INTO each blueprint module.
"""
_JD = "jobs_intelligence_ai.frontend.blueprints.job_detail"
_SEARCH = "jobs_intelligence_ai.frontend.blueprints.search"


# ── job_detail (prose tool) ─────────────────────────────────────────────────────
def test_desc_translate_ok(auth_client, monkeypatch):
    """desc_translate returns the service's text as { ok, text }."""
    monkeypatch.setattr(f"{_JD}.translate_description", lambda desc: "Translated.")
    resp = auth_client.post("/api/desc_translate", json={"description": "Stellenbeschreibung"})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True and body["text"] == "Translated."


def test_desc_translate_requires_description(auth_client):
    """Missing description → 400 before any service call."""
    resp = auth_client.post("/api/desc_translate", json={})
    assert resp.status_code == 400
    assert resp.get_json()["ok"] is False


def test_desc_translate_service_error_is_500(auth_client, monkeypatch):
    """A service exception is mapped to the 500 envelope."""
    def boom(desc):
        raise RuntimeError("model down")
    monkeypatch.setattr(f"{_JD}.translate_description", boom)
    resp = auth_client.post("/api/desc_translate", json={"description": "x"})
    assert resp.status_code == 500
    assert resp.get_json()["ok"] is False


# ── job_detail (the one real-JSON tool) ─────────────────────────────────────────
def test_candidate_strength_ok(auth_client, monkeypatch):
    """candidate_strength spreads the service's dict into the response body."""
    monkeypatch.setattr(
        f"{_JD}.score_candidate_strength",
        lambda job, cv, lang="de": {"axes": ["Skills Match"], "scores": [8],
                                    "reasons": ["ok"], "overall": "Good."})
    resp = auth_client.post("/api/candidate_strength",
                            json={"job": {"title": "Dev"}, "cv_text": "Senior dev"})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True and body["scores"] == [8] and body["overall"] == "Good."


def test_candidate_strength_requires_inputs(auth_client):
    """Missing job.title / cv_text → 400."""
    resp = auth_client.post("/api/candidate_strength", json={"job": {}, "cv_text": ""})
    assert resp.status_code == 400


# ── search match-analysis ───────────────────────────────────────────────────────
def test_match_analyze_ok(auth_client, monkeypatch):
    """match/analyze returns the service's prose as { ok, text }."""
    monkeypatch.setattr(f"{_SEARCH}.analyze_candidate_match",
                        lambda cv, jobs: "Strong fit overall.")
    resp = auth_client.post("/api/match/analyze",
                            json={"candidate_text": "Dev", "jobs": [{"title": "X"}]})
    assert resp.status_code == 200
    assert resp.get_json()["text"] == "Strong fit overall."


def test_match_analyze_requires_jobs(auth_client):
    """match/analyze with no jobs → 400."""
    resp = auth_client.post("/api/match/analyze", json={"candidate_text": "Dev"})
    assert resp.status_code == 400
    assert resp.get_json()["ok"] is False
