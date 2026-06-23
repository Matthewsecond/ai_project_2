"""
enrichment/observation.py — the HR profile-override conversation (Saved tab).

Two LLM calls relocated from the saved blueprint and converted to Structured Outputs in
rework 2.4:
  - extract_profile_overrides(profile, message) → the profile fields an HR observation implies
    (ObservationOverrides; only the mentioned fields survive).
  - phrase_observation_reply(message, overrides, impact_text) → a 1-2 sentence acknowledgement
    (ObservationReply, single prose field).

The blueprint keeps the orchestration in between (recompute Match Insights old vs new, diff the
pipeline impact, persist the new profile) — these helpers only own the two model calls. The
extract call returns {} on no API key and raises on a model error (the bp maps that to a 500);
the reply call always degrades to a safe fallback string (the reply is a flourish).
"""
import json
import logging

from jobs_intelligence_ai import config
from jobs_intelligence_ai.shared.llm import get_client
from .config import (
    OBSERVATION_MODEL,
    OVERRIDE_EXTRACT_PROMPT, ObservationOverrides,
    OBSERVATION_REPLY_PROMPT, ObservationReply,
)

logger = logging.getLogger(__name__)

_REPLY_FALLBACK = "Profile updated."


def extract_profile_overrides(profile: dict, message: str) -> dict:
    """Extract the profile overrides an HR observation implies (Structured Outputs).

    Returns only the fields the note actually changed (null/empty fields are dropped). Returns
    {} when there is no API key; raises on a model error so the blueprint surfaces it as a 500."""
    if not config.OPENAI_API_KEY:
        return {}

    instructions = OVERRIDE_EXTRACT_PROMPT.format(
        profile=json.dumps(profile or {}, ensure_ascii=False))
    resp = get_client().responses.parse(
        model=OBSERVATION_MODEL,
        instructions=instructions,
        input=message,
        text_format=ObservationOverrides,
    )
    parsed = resp.output_parsed
    if parsed is None:
        return {}
    return {k: v for k, v in parsed.model_dump().items() if v not in (None, "", [])}


def phrase_observation_reply(message: str, overrides: dict, impact_text: str) -> str:
    """Phrase a 1-2 sentence acknowledgement of an HR observation (Structured Outputs).

    The reply is a flourish, so this returns a safe fallback ("Profile updated.") on no API key
    or any error rather than raising."""
    if not config.OPENAI_API_KEY:
        return _REPLY_FALLBACK

    instructions = OBSERVATION_REPLY_PROMPT.format(
        message=message,
        overrides=json.dumps(overrides or {}, ensure_ascii=False),
        impact=impact_text,
    )
    try:
        resp = get_client().responses.parse(
            model=OBSERVATION_MODEL,
            instructions=instructions,
            input=message,
            text_format=ObservationReply,
        )
        if resp.output_parsed is None:
            return _REPLY_FALLBACK
        return (resp.output_parsed.reply or "").strip() or _REPLY_FALLBACK
    except Exception as exc:
        logger.warning("Observation reply phrasing failed (%s)", exc)
        return _REPLY_FALLBACK
