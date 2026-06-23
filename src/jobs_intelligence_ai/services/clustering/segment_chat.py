"""
segment_chat.py — Chat about one talent segment (multi-CV clustering view).

A conversational surface over ONE clustering segment: the system prompt carries the
segment's persona, member CVs, and matched roles, and the assistant explains why the
candidates were grouped, how they differ, and how they fit the roles. No file_search;
text-only reply with multi-turn memory via previous_response_id.

Lives in `clustering/` because it operates on a clustering segment — its domain — rather
than being a generic "chat" feature (rework 2.3 #6; relocated from the old top-level chat.py).
"""
import logging

from jobs_intelligence_ai import config
from jobs_intelligence_ai.shared.llm import get_client
from .config import CHAT_MODEL, SEGMENT_SYSTEM, LANG_INSTRUCTIONS

logger = logging.getLogger(__name__)

_segment_sessions: dict[str, str] = {}


def send_segment_message(session_id: str, user_message: str, segment: dict, lang: str = "en") -> dict:
    """Chat about one talent segment: the system prompt carries the segment's
    persona, member CVs, and matched roles. No file_search."""
    if not config.OPENAI_API_KEY:
        return {"text": "Segment chat requires an OpenAI API key — add OPENAI_API_KEY to your .env file."}

    client = get_client()
    previous_id = _segment_sessions.get(session_id)

    members = "\n".join(f"- {m.get('name', '')}: {(m.get('text') or '')[:500]}"
                        for m in (segment.get("members") or [])[:12]) or "(none)"
    jobs = "\n".join(f"- [{j.get('grade', '?')}] {j.get('title', '')}"
                     for j in (segment.get("jobs") or [])[:15]) or "(not matched yet)"
    lang_instruction = LANG_INSTRUCTIONS.get(lang, LANG_INSTRUCTIONS["en"])
    system = SEGMENT_SYSTEM.replace("{{LANG_INSTRUCTION}}", lang_instruction).format(
        title=(segment.get("title") or "")[:120],
        summary=(segment.get("summary") or "")[:400],
        persona=(segment.get("persona_text") or "")[:1500],
        members=members,
        jobs=jobs,
    )

    kwargs: dict = dict(model=CHAT_MODEL, instructions=system, input=user_message)
    if previous_id:
        kwargs["previous_response_id"] = previous_id
    try:
        response = client.responses.create(**kwargs)
        _segment_sessions[session_id] = response.id
        return {"text": response.output_text or ""}
    except Exception as e:
        logger.error("Segment chat error (session=%s): %s", session_id, e)
        return {"text": f"Sorry, something went wrong: {e}"}


def clear_segment_session(session_id: str) -> None:
    _segment_sessions.pop(session_id, None)
