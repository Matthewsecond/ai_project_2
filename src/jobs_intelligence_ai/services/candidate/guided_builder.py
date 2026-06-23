"""
candidate/guided_builder.py — the guided "target candidate" builder chat (Guided tab).

Two LLM calls relocated from the guided blueprint and converted to Structured Outputs in
rework 2.4:
  - extract_guided_fields(message, ...) → the target-spec field updates the message implies
    (GuidedFieldUpdates; only the mentioned fields survive).
  - phrase_guided_reply(message, ...)   → the guide's reply + the single next narrowing question
    and its quick-pick chips (GuidedReply).

The blueprint keeps everything data-grounded — it owns the live DB faceting, the taxonomy
catalog, the salary benchmark and the chip-routing — and passes the grounding in pre-rendered;
these helpers only own the two model calls. Both replace the old `_gpt_json` helper (a
responses.create + json.loads round-trip behind two "Return ONLY valid JSON" prompts) that
the guided blueprint used to borrow from the saved blueprint.

extract returns {} on no API key and raises on a model error (the bp maps that to a 500);
the reply call always degrades to {} (the bp falls back to safe defaults) — the chat must
keep working even when phrasing fails.
"""
import logging

from jobs_intelligence_ai import config
from jobs_intelligence_ai.shared.llm import get_client
from .config import (
    GUIDED_MODEL,
    GUIDED_EXTRACT_PROMPT, GuidedFieldUpdates,
    GUIDED_REPLY_PROMPT, GuidedReply,
)

logger = logging.getLogger(__name__)


def extract_guided_fields(message: str, *, draft: str, locked: str, catalog: str,
                          last_field: str, offer: str, salary: str) -> dict:
    """Extract the target-spec field updates a guided message implies (Structured Outputs).

    Returns only the fields the message actually provides (null/empty dropped). Returns {}
    when there is no API key; raises on a model error so the blueprint surfaces it as a 500.
    The string args are the pre-rendered grounding the blueprint assembles: the draft JSON,
    the hand-locked fields, the sector catalog, the prev-question field, and the offer + salary
    hints that help resolve referential answers."""
    if not config.OPENAI_API_KEY:
        return {}

    instructions = GUIDED_EXTRACT_PROMPT.format(
        draft=draft, locked=locked, catalog=catalog,
        last_field=last_field or "(nothing specific yet)",
        offer=offer, salary=salary)
    resp = get_client().responses.parse(
        model=GUIDED_MODEL,
        instructions=instructions,
        input=message,
        text_format=GuidedFieldUpdates,
    )
    parsed = resp.output_parsed
    if parsed is None:
        return {}
    return {k: v for k, v in parsed.model_dump().items() if v not in (None, "", [])}


def phrase_guided_reply(message: str, *, lang: str, last_question: str, field_updates: str,
                        user_edits: str, draft: str, facets: str, salary_hint: str) -> dict:
    """Phrase the guide's reply + the next narrowing question and chips (Structured Outputs).

    Returns the GuidedReply as a dict (reply, next_question, facet, answer_field, options,
    suggestions); the blueprint validates the chips against live data and applies safe defaults.
    The phrasing is non-critical, so this degrades to {} on no API key or any error rather than
    raising — the chat keeps working. The string args are the pre-rendered grounding the
    blueprint assembles (the applied updates, the merged draft, the live facets, salary hint)."""
    if not config.OPENAI_API_KEY:
        return {}

    instructions = GUIDED_REPLY_PROMPT.format(
        lang=lang, message=message,
        last_question=last_question or "(none yet)",
        field_updates=field_updates, user_edits=user_edits,
        draft=draft, facets=facets, salary_hint=salary_hint)
    try:
        resp = get_client().responses.parse(
            model=GUIDED_MODEL,
            instructions=instructions,
            input=message,
            text_format=GuidedReply,
        )
        if resp.output_parsed is None:
            return {}
        return resp.output_parsed.model_dump()
    except Exception as exc:
        logger.warning("Guided reply phrasing failed (%s)", exc)
        return {}
