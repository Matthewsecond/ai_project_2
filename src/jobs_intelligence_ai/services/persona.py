"""
persona.py — Synthesize a "persona" (synthetic candidate) for one talent segment.

After clustering (see clustering.py), each segment is a group of similar CVs. This
turns that group into a single synthetic candidate: a short title, a one-line
summary, and a `persona_text` written like a CV summary so it can be fed straight
into the existing matching engine (Orchestrator.run) as a candidate_text.
"""
import json
import logging
import re

from jobs_intelligence_ai import config
from jobs_intelligence_ai.chat import get_client

logger = logging.getLogger(__name__)

_PERSONA_INSTRUCTIONS = (
    "You are a recruitment analyst. You are given several candidate profiles that were "
    "grouped into ONE talent segment. Describe the SEGMENT as a whole, not each person. "
    "Return ONLY valid JSON (no prose, no markdown fences) with exactly these keys:\n"
    '  "title": a 3-5 word label for the segment (e.g. "Senior B2B SaaS sellers")\n'
    '  "summary": one sentence describing the shared role focus and seniority\n'
    '  "persona_text": a synthetic candidate profile of 5-8 lines capturing the segment\'s '
    "common role focus, seniority, core skills, tools, and languages — written like a concise "
    "CV summary so it can be matched against job postings.\n"
    "Respond in English."
)


def synthesize_persona(member_texts: list[str]) -> dict:
    """LLM → {title, summary, persona_text} for one cluster of candidate profiles.
    Falls back to a member profile as the persona_text if the call/parse fails."""
    client = get_client()
    joined = "\n\n---\n\n".join((t or "")[:1500] for t in member_texts[:12])
    data = {}
    try:
        resp = client.responses.create(
            model=config.CHAT_MODEL,
            instructions=_PERSONA_INSTRUCTIONS,
            input="CANDIDATE PROFILES IN THIS SEGMENT:\n\n" + joined,
        )
        data = _parse_json_obj(resp.output_text or "")
    except Exception as e:
        logger.warning("persona synthesis failed (%s) — using fallback", e)

    fallback_text = (member_texts[0] if member_texts else "").strip()
    return {
        "title":        (data.get("title") or "Candidate segment").strip(),
        "summary":      (data.get("summary") or "").strip(),
        "persona_text": (data.get("persona_text") or fallback_text).strip(),
    }


def _parse_json_obj(text: str) -> dict:
    text = re.sub(r"```(?:json)?", "", text or "").strip().rstrip("`").strip()
    try:
        d = json.loads(text)
        if isinstance(d, dict):
            return d
    except Exception:
        pass
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            d = json.loads(m.group())
            return d if isinstance(d, dict) else {}
        except Exception:
            return {}
    return {}
