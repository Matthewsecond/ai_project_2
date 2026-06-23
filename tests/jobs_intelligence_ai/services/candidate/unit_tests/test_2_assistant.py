"""
Offline unit tests for the Structured-Outputs candidate assistant (2.3 #7).

No network: inject a fake client whose `responses.parse` returns a canned `CandidateReply`.
Asserts the reply maps to `text`, that only the changed (non-null) profile_updates fields
reach the front-end, that pure discussion yields no updates, plus session continuity and the
no-key / error fallbacks.
"""
import jobs_intelligence_ai.services.candidate.assistant as asst_mod
from jobs_intelligence_ai.services.candidate import send_candidate_message, clear_candidate_session
from jobs_intelligence_ai.services.candidate.config import CandidateReply, ProfileUpdates


class _FakeResponses:
    """`.parse()` records its kwargs and returns a canned CandidateReply with an id."""
    def __init__(self, parsed=None, exc=None):
        self._parsed, self._exc, self.calls = parsed, exc, []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        if self._exc:
            raise self._exc
        return type("Resp", (), {"id": "resp_1", "output_parsed": self._parsed})()


class _FakeClient:
    def __init__(self, parsed=None, exc=None):
        self.responses = _FakeResponses(parsed, exc)


def _patch(monkeypatch, parsed=None, exc=None):
    client = _FakeClient(parsed, exc)
    monkeypatch.setattr(asst_mod, "get_client", lambda *a, **k: client)
    monkeypatch.setattr(asst_mod.config, "OPENAI_API_KEY", "test-key")
    return client


def test_no_key_returns_message(monkeypatch):
    """With no API key, returns an explanatory message and no profile edits."""
    monkeypatch.setattr(asst_mod.config, "OPENAI_API_KEY", "")
    out = send_candidate_message("s1", "hi", {"name": "Ann"}, [])
    assert "OpenAI API key" in out["text"]
    assert out["profile_updates"] == {} and out["cv_note"] == ""


def test_edit_returns_only_changed_fields(monkeypatch):
    """A CV edit surfaces only the non-null update fields, plus the cv_note."""
    parsed = CandidateReply(
        reply="Added the forklift licence.",
        profile_updates=ProfileUpdates(certifications=["Forklift licence"]),
        cv_note="Holds a valid forklift licence.")
    _patch(monkeypatch, parsed)
    out = send_candidate_message("s1", "add forklift licence", {"name": "Ann"}, [])
    assert out["text"] == "Added the forklift licence."
    assert out["profile_updates"] == {"certifications": ["Forklift licence"]}
    assert out["cv_note"] == "Holds a valid forklift licence."


def test_pure_discussion_has_no_updates(monkeypatch):
    """When profile_updates is null (just discussion), updates is an empty dict."""
    parsed = CandidateReply(reply="They look like a strong fit for role 2.",
                            profile_updates=None, cv_note="")
    _patch(monkeypatch, parsed)
    out = send_candidate_message("s1", "which role fits best?", {"name": "Ann"}, [])
    assert out["profile_updates"] == {}
    assert out["text"].startswith("They look like")


def test_session_continuity(monkeypatch):
    """The response id is threaded as previous_response_id on the next turn."""
    clear_candidate_session("s2")
    client = _patch(monkeypatch, CandidateReply(reply="ok", profile_updates=None, cv_note=""))
    send_candidate_message("s2", "hi", {"name": "Ann"}, [])
    send_candidate_message("s2", "more", {"name": "Ann"}, [])
    assert client.responses.calls[1]["previous_response_id"] == "resp_1"


def test_error_is_caught(monkeypatch):
    """A model error degrades to a friendly message with no edits."""
    _patch(monkeypatch, exc=RuntimeError("boom"))
    out = send_candidate_message("s3", "hi", {"name": "Ann"}, [])
    assert "something went wrong" in out["text"]
    assert out["profile_updates"] == {}
