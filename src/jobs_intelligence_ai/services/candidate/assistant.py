"""
assistant.py — Candidate assistant chat (search-tab, one loaded candidate).

A chat docked on the search tab that works with ONE loaded candidate: it can (a) discuss the
candidate and the job offers currently matched for them, and (b) edit the candidate's
CV/profile when the recruiter asks. The model call uses Structured Outputs
(responses.parse → CandidateReply): a natural `reply`, an optional `profile_updates` object
(only the changed fields), and a `cv_note` — which the front-end merges into the profile
card (scalars replace, arrays append+dedupe). Multi-turn memory via previous_response_id.

Relocated from the old top-level chat.py in rework 2.3 #7 (the last surface to leave it).
"""
import json
import logging

from jobs_intelligence_ai import config
from jobs_intelligence_ai.shared.llm import get_client
from .config import CHAT_MODEL, ASSISTANT_PROMPT, LANG_INSTRUCTIONS, CandidateReply

logger = logging.getLogger(__name__)

_candidate_sessions: dict[str, str] = {}


def _format_jobs_for_prompt(jobs: list[dict]) -> str:
    """Compact, readable list of the matched offers for the system prompt."""
    if not jobs:
        return "(no jobs matched yet — the recruiter has not run matching, or there were no results)"
    lines = []
    for i, j in enumerate(jobs[:15], 1):
        loc   = ", ".join(filter(None, [j.get("city"), j.get("state")])) or "—"
        sal   = j.get("salary") or "—"
        grade = j.get("grade") or ""
        score = j.get("score_pct") or (f"{round(j['score'] * 100)}%" if isinstance(j.get("score"), (int, float)) else "")
        head  = f"{i}. {j.get('title') or 'Untitled'} — {j.get('company') or 'Unknown company'} ({loc})"
        meta  = f"salary {sal}; fit {score} {('grade ' + grade) if grade else ''}".strip()
        line  = f"{head}; {meta}"
        if j.get("match_reason"):
            line += f"; why: {j['match_reason']}"
        lines.append(line)
    return "\n".join(lines)


def send_candidate_message(session_id: str, user_message: str, profile: dict | None,
                           jobs: list[dict] | None, lang: str = "en") -> dict:
    """Candidate-centric chat. Returns {text, profile_updates, cv_note}.

    `profile` is the current candidate-profile dict shown on the card; `jobs` is the list of
    offers currently matched on screen. Both are passed each turn so the assistant always
    reasons over the latest state even across re-matches. Uses Structured Outputs; on any
    failure it returns an error message with no profile edits."""
    if not config.OPENAI_API_KEY:
        return {"text": "The candidate assistant requires an OpenAI API key — add OPENAI_API_KEY to your .env file.",
                "profile_updates": {}, "cv_note": "", "search_suggestion": ""}

    previous_id = _candidate_sessions.get(session_id)

    # Keep the profile blob small but useful — drop bulky/raw fields.
    prof = profile or {}
    slim = {k: v for k, v in prof.items()
            if k not in ("experiences", "current_company", "raw", "_lat", "_lon") and v not in (None, "", [])}

    lang_instruction = LANG_INSTRUCTIONS.get(lang, LANG_INSTRUCTIONS["en"])
    system = ASSISTANT_PROMPT.format(
        label=config.COUNTRY_LABEL,
        lang_instruction=lang_instruction,
        profile=json.dumps(slim, ensure_ascii=False) if slim else "(no candidate loaded yet)",
        jobs=_format_jobs_for_prompt(jobs or []),
    )

    kwargs: dict = dict(
        model=CHAT_MODEL,
        instructions=system,
        input=user_message,
        text_format=CandidateReply,
    )
    if previous_id:
        kwargs["previous_response_id"] = previous_id

    try:
        response = get_client().responses.parse(**kwargs)
        _candidate_sessions[session_id] = response.id
        return _shape_reply(response.output_parsed)
    except Exception as e:
        logger.error("Candidate chat error (session=%s): %s", session_id, e)
        return {"text": f"Sorry, something went wrong: {e}", "profile_updates": {}, "cv_note": "",
                "search_suggestion": ""}


def _shape_reply(parsed) -> dict:
    """CandidateReply → {text, profile_updates, cv_note, search_suggestion}, dropping unset
    (null/blank) update fields so only the fields the recruiter actually changed reach the front-end."""
    if parsed is None:
        return {"text": "", "profile_updates": {}, "cv_note": "", "search_suggestion": ""}
    updates = {}
    if parsed.profile_updates is not None:
        updates = {k: v for k, v in parsed.profile_updates.model_dump().items()
                   if v not in (None, "", [])}
    return {
        "text":              (parsed.reply or "").strip(),
        "profile_updates":   updates,
        "cv_note":           (parsed.cv_note or "").strip(),
        "search_suggestion": (parsed.search_suggestion or "").strip(),
    }


def clear_candidate_session(session_id: str) -> None:
    _candidate_sessions.pop(session_id, None)
