"""
profile_parser.py — parse a structured candidate profile from raw CV text.

Backs the "paste a CV / job text → structured candidate card" path on the search tab. The
model call uses Structured Outputs (responses.parse → CandidateProfile): name, title, skills,
languages, salary expectation, contact details, a one-line summary, etc. Relocated from the
inline `chat.completions` call in the candidate blueprint and converted in rework 2.4.
"""
import logging

from jobs_intelligence_ai import config
from jobs_intelligence_ai.shared.llm import get_client
from .config import CLASSIFIER_MODEL, PROFILE_PARSE_PROMPT, CandidateProfile

logger = logging.getLogger(__name__)


def parse_candidate_profile(text: str) -> dict:
    """Extract a structured candidate profile from raw CV/pasted text.

    Returns the CandidateProfile fields as a dict (skills is always a list, the rest may be
    null). Raises if there is no API key or the model call fails — the blueprint turns that
    into a JSON error response."""
    if not config.OPENAI_API_KEY:
        raise RuntimeError("OpenAI API key not configured")

    resp = get_client().responses.parse(
        model=CLASSIFIER_MODEL,
        instructions=PROFILE_PARSE_PROMPT,
        input=text[:4000],
        text_format=CandidateProfile,
    )
    parsed = resp.output_parsed
    if parsed is None:
        raise ValueError("Model returned no structured profile")
    return parsed.model_dump()
