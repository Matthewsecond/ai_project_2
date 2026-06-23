"""
Offline unit tests for the Structured-Outputs LinkedIn enricher (2.3 #7).

No network: patch the module's `get_client` so `responses.parse` returns a canned
`LinkedInProfile`, or raises. Asserts the AI fields merge over the mechanical base, that
empty/null AI fields don't blank out good base values, and that no key / a failure returns
the base unchanged.
"""
import jobs_intelligence_ai.services.candidate.profile_enricher as pe_mod
from jobs_intelligence_ai.services.candidate import enrich_linkedin_profile
from jobs_intelligence_ai.services.candidate.config import LinkedInProfile


class _FakeResponses:
    """`.parse()` returns a canned LinkedInProfile (as output_parsed), or raises."""
    def __init__(self, parsed=None, exc=None):
        self._parsed, self._exc = parsed, exc

    def parse(self, **kwargs):
        if self._exc:
            raise self._exc
        return type("Resp", (), {"output_parsed": self._parsed})()


def _patch(monkeypatch, parsed=None, exc=None):
    client = type("C", (), {"responses": _FakeResponses(parsed, exc)})()
    monkeypatch.setattr(pe_mod, "get_client", lambda *a, **k: client)
    monkeypatch.setattr(pe_mod.config, "OPENAI_API_KEY", "test-key")


def _profile(**over):
    """A fully-populated LinkedInProfile, with per-test overrides."""
    base = dict(
        name="Max Weber", title="Backend Developer", current_company="ACME",
        headline="Backend dev", seniority="Mid", years_experience=5,
        industry="Software", role_category="Software Engineering", education_level="BSc",
        management_experience="No", top_skills=["Python", "FastAPI"],
        specializations=["APIs"], languages="German (native), English C1", location="Vienna",
        ai_summary="Solid backend engineer.", strengths=["APIs", "Docker"],
        estimated_salary_min=3500, estimated_salary_max=4500)
    base.update(over)
    return LinkedInProfile(**base)


def test_no_key_returns_base(monkeypatch):
    """With no API key, the mechanical base is returned untouched (no model call)."""
    monkeypatch.setattr(pe_mod.config, "OPENAI_API_KEY", "")
    base = {"name": "Mechanical", "phone": "123"}
    assert enrich_linkedin_profile({"full_name": "x"}, base=base) == base


def test_ai_fields_merge_over_base(monkeypatch):
    """AI-inferred fields overwrite the base; provenance keys are stamped on."""
    _patch(monkeypatch, _profile(seniority="Senior", years_experience=8))
    out = enrich_linkedin_profile({"full_name": "Max"}, base={"phone": "123", "seniority": "Mid"})
    assert out["seniority"] == "Senior"
    assert out["years_experience"] == 8
    assert out["phone"] == "123"                 # base-only field preserved
    assert out["source"] == "imported" and out["ai_model"]


def test_empty_ai_fields_do_not_blank_base(monkeypatch):
    """Null/empty AI fields are skipped so they can't erase a good base value."""
    _patch(monkeypatch, _profile(current_company=None, top_skills=[]))
    out = enrich_linkedin_profile({"full_name": "Max"},
                                  base={"current_company": "BaseCo", "top_skills": ["SQL"]})
    assert out["current_company"] == "BaseCo"
    assert out["top_skills"] == ["SQL"]


def test_failure_returns_base(monkeypatch):
    """A model error returns the base unchanged — ingestion never breaks."""
    _patch(monkeypatch, exc=RuntimeError("boom"))
    base = {"name": "Mechanical"}
    assert enrich_linkedin_profile({"full_name": "x"}, base=base) == base
