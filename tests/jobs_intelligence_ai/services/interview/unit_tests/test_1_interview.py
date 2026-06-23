"""
Offline unit tests for the Structured-Outputs InterviewHelper (2.3 #3).

No network: an injected fake client makes `responses.parse` return a canned Pydantic
schema object (mimicking `output_parsed`), or raise. Asserts the post-processing rules
the schema can't express — score clamping, the `final` override, follow-up exhaustion,
status/impact normalisation — plus the input guards and the no-key / API-failure fallbacks.
"""
import pytest

import jobs_intelligence_ai.services.interview.orchestrator as orch_mod
from jobs_intelligence_ai.services.interview import InterviewHelper
from jobs_intelligence_ai.services.interview import config as ic


class _FakeResponses:
    """`.parse()` returns a canned schema object (as `output_parsed`), or raises."""
    def __init__(self, parsed=None, exc=None):
        self._parsed, self._exc = parsed, exc

    def parse(self, **kwargs):
        if self._exc:
            raise self._exc
        return type("Resp", (), {"output_parsed": self._parsed})()


class _FakeClient:
    def __init__(self, parsed=None, exc=None):
        self.responses = _FakeResponses(parsed, exc)


@pytest.fixture
def helper_for(monkeypatch):
    """Factory → an InterviewHelper whose model call returns `parsed` (or raises `exc`),
    with a non-empty API key so the call isn't short-circuited."""
    def _make(parsed=None, exc=None):
        monkeypatch.setattr(orch_mod.config, "OPENAI_API_KEY", "test-key")
        return InterviewHelper(client=_FakeClient(parsed, exc))
    return _make


_JOB = {"title": "Backend Engineer", "company": "ACME", "description": "Build APIs."}
_CV = "10 years of Python and distributed systems."


# ── input guards (no model call) ───────────────────────────────────────────────
def test_generate_questions_requires_job_and_cv():
    """Missing job.title or cv_text short-circuits before any model call."""
    h = InterviewHelper(client=_FakeClient())
    assert h.generate_questions({"title": ""}, _CV)["ok"] is False
    assert h.generate_questions(_JOB, "")["ok"] is False


def test_parse_questions_requires_text():
    """Empty document text returns an error without calling the model."""
    h = InterviewHelper(client=_FakeClient())
    assert h.parse_questions("   ")["ok"] is False


def test_analyze_answer_requires_question_and_answer():
    """Both question and answer must be non-empty."""
    h = InterviewHelper(client=_FakeClient())
    assert h.analyze_answer("", "ans", _JOB, _CV)["ok"] is False
    assert h.analyze_answer("q", "", _JOB, _CV)["ok"] is False


# ── happy paths + coercion ─────────────────────────────────────────────────────
def test_generate_questions_shapes_and_renumbers(helper_for):
    """Questions are returned with int ids; blank-text entries are dropped."""
    parsed = ic.QuestionList(questions=[
        ic._Question(id=1, question="Tell me about X", note="depth gap"),
        ic._Question(id=2, question="   ", note="blank → dropped"),
    ])
    out = helper_for(parsed).generate_questions(_JOB, _CV)
    assert out["ok"] is True
    assert out["questions"] == [{"id": 1, "question": "Tell me about X", "note": "depth gap"}]


def test_parse_questions_orders_and_renumbers(helper_for):
    """Parsed pairs are renumbered from 1 in order; blanks dropped."""
    parsed = ic.ParsedQAList(questions=[
        ic._ParsedQA(id=7, question="Why us?", answer="I admire the mission."),
        ic._ParsedQA(id=9, question="Next?", answer=""),
    ])
    out = helper_for(parsed).parse_questions("some prepared doc")
    assert [q["id"] for q in out["questions"]] == [1, 2]
    assert out["questions"][1]["answer"] == ""


def test_analyze_complete_answer_scores(helper_for):
    """A complete answer keeps its (clamped) score and surfaces the lists."""
    parsed = ic.AnswerAnalysis(
        complete=True, status="answer", needs="", score=150, verdict="Strong",
        strengths=["concrete metrics"], concerns=[], signals=["ownership"])
    out = helper_for(parsed).analyze_answer("q", "a detailed reply", _JOB, _CV)
    assert out["ok"] is True and out["complete"] is True
    assert out["score"] == 100          # clamped from 150
    assert out["signals"] == ["ownership"]


def test_analyze_incomplete_answer_withholds_score(helper_for):
    """A clarifying / in-progress exchange reports complete=False and no score."""
    parsed = ic.AnswerAnalysis(
        complete=False, status="clarifying", needs="ask what dataset", score=None,
        verdict="", strengths=[], concerns=[], signals=[])
    out = helper_for(parsed).analyze_answer("q", "which data?", _JOB, _CV)
    assert out["complete"] is False
    assert out["score"] is None
    assert out["status"] == "clarifying"


def test_analyze_final_override_forces_score(helper_for):
    """`final=True` scores the exchange even when the model judged it incomplete."""
    parsed = ic.AnswerAnalysis(
        complete=False, status="partial", needs="more detail", score=55,
        verdict="Brief but on point", strengths=[], concerns=[], signals=[])
    out = helper_for(parsed).analyze_answer("q", "short reply", _JOB, _CV, final=True)
    assert out["complete"] is True
    assert out["score"] == 55


def test_summarize_clamps_score(helper_for):
    """The overall fit score is clamped into 0–100."""
    parsed = ic.InterviewSummary(score=120, recommendation="Advance", summary="Strong fit.")
    out = helper_for(parsed).summarize(
        [{"question": "q", "answer": "a", "score": 80}], _JOB, _CV)
    assert out["ok"] is True
    assert out["score"] == 100
    assert out["recommendation"] == "Advance"


def test_summarize_requires_answered_records(helper_for):
    """Nothing answered → error, no model call."""
    assert helper_for().summarize([{"question": "q", "answer": ""}], _JOB, _CV)["ok"] is False


def test_followup_empty_question_is_exhausted(helper_for):
    """An empty proposed question is treated as exhausted even if the flag says otherwise."""
    parsed = ic.Followup(exhausted=False, question="   ", note="", reason="covered")
    thread = [{"question": "q", "answer": "a thorough answer"}]
    out = helper_for(parsed).suggest_followup(thread, _JOB, _CV)
    assert out["exhausted"] is True
    assert out["question"] == ""


def test_followup_requires_an_answer(helper_for):
    """A thread with questions but no answers can't be followed up."""
    out = helper_for().suggest_followup([{"question": "q", "answer": ""}], _JOB, _CV)
    assert out["ok"] is False


def test_model_answer_shapes_payload(helper_for):
    """model_answer returns trimmed guidance and a capped covers list."""
    parsed = ic.ModelAnswer(model_answer="Cover scope, evidence, outcomes.",
                            covers=["named projects", "quantified impact"])
    out = helper_for(parsed).model_answer("How did you scale X?", _JOB, _CV)
    assert out["ok"] is True
    assert out["model_answer"].startswith("Cover scope")
    assert out["covers"] == ["named projects", "quantified impact"]


def test_opportunities_normalises_impact_and_caps(helper_for):
    """An out-of-range impact defaults to 'medium'; the list is capped at 6."""
    opps = [ic._Opportunity(title=f"Op {i}", rationale="r", action="a", impact="high")
            for i in range(8)]
    parsed = ic.OpportunityList(opportunities=opps, summary="You're close.")
    out = helper_for(parsed).improvement_opportunities(
        [{"question": "q", "answer": "a"}], _JOB, _CV)
    assert len(out["opportunities"]) == 6
    assert all(o["impact"] in ("high", "medium", "low") for o in out["opportunities"])


def test_assess_candidate_shapes_aspects(helper_for):
    """Aspects keep valid statuses and clamped scores; summary passes through."""
    parsed = ic.AspectAssessment(aspects=[
        ic._Aspect(aspect="Python depth", score=95, status="strong", note="10y"),
        ic._Aspect(aspect="Leadership", score=40, status="weak", note="no evidence"),
    ], summary="Strong technically.")
    out = helper_for(parsed).assess_candidate(_JOB, _CV, None, records=[])
    assert out["ok"] is True
    assert {a["aspect"] for a in out["aspects"]} == {"Python depth", "Leadership"}
    assert out["aspects"][0]["status"] == "strong"


# ── failure fallbacks ──────────────────────────────────────────────────────────
def test_api_failure_returns_error_dict(helper_for):
    """A raising model call degrades to {"ok": False, "error": ...} — never raises."""
    out = helper_for(exc=RuntimeError("boom")).generate_questions(_JOB, _CV)
    assert out["ok"] is False
    assert "boom" in out["error"]


def test_no_api_key_short_circuits(monkeypatch):
    """With no API key, every call returns an explanatory error without touching the client."""
    monkeypatch.setattr(orch_mod.config, "OPENAI_API_KEY", "")
    h = InterviewHelper(client=_FakeClient(exc=AssertionError("must not call the model")))
    out = h.generate_questions(_JOB, _CV)
    assert out["ok"] is False
    assert "OPENAI_API_KEY" in out["error"]


def test_none_output_parsed_is_an_error(helper_for):
    """A None `output_parsed` (e.g. a refusal) is surfaced as an error, not a crash."""
    out = helper_for(parsed=None).generate_questions(_JOB, _CV)
    assert out["ok"] is False
