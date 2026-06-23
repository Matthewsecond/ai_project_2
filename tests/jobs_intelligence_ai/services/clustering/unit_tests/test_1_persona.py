"""
Offline unit tests for the Structured-Outputs persona synthesis (2.3 #6).

No network: patch the module's `get_client` so `responses.parse` returns a canned
`PersonaResult`, or raises. Asserts the parsed fields flow through, and that any failure
(or empty fields) falls back to the first member profile as the persona_text.
"""
import jobs_intelligence_ai.services.clustering.persona as persona_mod
from jobs_intelligence_ai.services.clustering import synthesize_persona
from jobs_intelligence_ai.services.clustering.config import PersonaResult


class _FakeResponses:
    """`.parse()` returns a canned PersonaResult (as output_parsed), or raises."""
    def __init__(self, parsed=None, exc=None):
        self._parsed, self._exc = parsed, exc

    def parse(self, **kwargs):
        if self._exc:
            raise self._exc
        return type("Resp", (), {"output_parsed": self._parsed})()


def _patch(monkeypatch, parsed=None, exc=None):
    client = type("C", (), {"responses": _FakeResponses(parsed, exc)})()
    monkeypatch.setattr(persona_mod, "get_client", lambda *a, **k: client)


def test_returns_parsed_persona(monkeypatch):
    """A successful structured call maps straight to {title, summary, persona_text}."""
    _patch(monkeypatch, PersonaResult(
        title="Senior B2B SaaS sellers", summary="Experienced enterprise AEs.",
        persona_text="10y closing six-figure SaaS deals; SDR→AE; SQL, Salesforce."))
    out = synthesize_persona(["AE with 10y SaaS", "Enterprise seller"])
    assert out["title"] == "Senior B2B SaaS sellers"
    assert out["persona_text"].startswith("10y closing")


def test_failure_falls_back_to_first_member(monkeypatch):
    """If the call raises, persona_text falls back to the first member profile."""
    _patch(monkeypatch, exc=RuntimeError("boom"))
    out = synthesize_persona(["First member CV text", "second"])
    assert out["persona_text"] == "First member CV text"
    assert out["title"] == "Candidate segment"      # default label


def test_empty_parsed_fields_use_fallback_and_default(monkeypatch):
    """Blank model fields degrade to the default title and the member fallback text."""
    _patch(monkeypatch, PersonaResult(title="  ", summary="", persona_text="  "))
    out = synthesize_persona(["Member CV"])
    assert out["title"] == "Candidate segment"
    assert out["persona_text"] == "Member CV"
