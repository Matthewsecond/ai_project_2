"""
persona.py — Synthesize a "persona" (synthetic candidate) for one talent segment.

After segmenting (see segmenting.py), each segment is a group of similar CVs. This turns
that group into a single synthetic candidate: a short title, a one-line summary, and a
`persona_text` written like a CV summary so it can be fed straight into the existing matching
engine (Orchestrator.run) as a candidate_text.

The model call uses Structured Outputs (responses.parse → validated PersonaResult); on any
failure it falls back to a member profile as the persona_text so a flaky call never breaks
the clustering view.
"""
import logging

from jobs_intelligence_ai.shared.llm import get_client
from .config import CHAT_MODEL, PERSONA_PROMPT, PersonaResult

logger = logging.getLogger(__name__)


def synthesize_persona(member_texts: list[str]) -> dict:
    """LLM → {title, summary, persona_text} for one cluster of candidate profiles.
    Falls back to a member profile as the persona_text if the call fails."""
    joined = "\n\n---\n\n".join((t or "")[:1500] for t in member_texts[:12])
    parsed = None
    try:
        resp = get_client().responses.parse(
            model=CHAT_MODEL,
            instructions=PERSONA_PROMPT,
            input="CANDIDATE PROFILES IN THIS SEGMENT:\n\n" + joined,
            text_format=PersonaResult,
        )
        parsed = resp.output_parsed
    except Exception as e:
        logger.warning("persona synthesis failed (%s) — using fallback", e)

    fallback_text = (member_texts[0] if member_texts else "").strip()
    return {
        "title":        (parsed.title if parsed else "").strip() or "Candidate segment",
        "summary":      (parsed.summary if parsed else "").strip(),
        "persona_text": (parsed.persona_text if parsed else "").strip() or fallback_text,
    }
