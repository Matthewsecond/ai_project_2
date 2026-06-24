"""
job_detail/operations.py — the AI tools behind the Job Detail modal.

Five LLM calls relocated from the job_detail blueprint and converted to Structured Outputs in
rework Stage 2.4:
  - translate_description(description)            → English translation (prose)
  - compact_description(description, lang)        → 3-4 sentence summary (prose)
  - generate_cv_questions(description, cv, lang)  → gap-based interview questions (prose)
  - write_outreach(job, name, cv, lang)          → candidate outreach message (prose)
  - score_candidate_strength(job, cv, lang)       → 5-dimension fit score (CandidateStrength, JSON)

The four prose tools share a single-field `JobDetailText`; candidate-strength is the one real-JSON
call — it replaces the blueprint's "Return ONLY valid JSON" prompt + fence-strip + json.loads (the
last such hand-parse in a blueprint). Every call goes through the shared client and raises on no
API key / model error (the blueprint maps that to a 500). Input lengths are capped to mirror the
old blueprint's slicing.
"""
import logging

from jobs_intelligence_ai import config
from jobs_intelligence_ai.shared.llm import get_client
from .config import (
    JOB_DETAIL_MODEL,
    TRANSLATE_PROMPT, COMPACT_PROMPT, CV_QUESTIONS_PROMPT, OUTREACH_PROMPT, STRENGTH_PROMPT,
    JobDetailText, CandidateStrength,
)

logger = logging.getLogger(__name__)

_MAX_DESC     = 4000   # single-description tools
_MAX_PAIR     = 3000   # description + CV sent together (cv-questions)
_MAX_STRENGTH = 1500   # description + CV for the strength scorer


def _en(lang: str, note: str) -> str:
    """Append an 'in English' instruction when the UI language is English (else stay source-language)."""
    return note if lang == "en" else ""


def _prose(instructions: str, text: str) -> str:
    """Run one Structured-Outputs prose call → the text. Raises on no API key / model error."""
    if not config.OPENAI_API_KEY:
        raise RuntimeError("OpenAI API key not configured")
    resp = get_client().responses.parse(
        model=JOB_DETAIL_MODEL,
        instructions=instructions,
        input=text,
        text_format=JobDetailText,
    )
    if resp.output_parsed is None:
        raise ValueError("Model returned no text")
    return resp.output_parsed.text


def translate_description(description: str) -> str:
    """Translate a job description to English (Structured Outputs). Raises on no key / model error."""
    return _prose(TRANSLATE_PROMPT, description[:_MAX_DESC])


def compact_description(description: str, lang: str = "de") -> str:
    """Summarise a job description in 3-4 sentences (Structured Outputs). Raises on no key / error."""
    return _prose(COMPACT_PROMPT + _en(lang, " Respond in English."), description[:_MAX_DESC])


def generate_cv_questions(description: str, cv_text: str, lang: str = "de") -> str:
    """Generate gap-based interview questions from a job + a candidate CV (Structured Outputs).

    Raises on no API key / model error."""
    prompt = f"JOB DESCRIPTION:\n{description[:_MAX_PAIR]}\n\nCANDIDATE CV:\n{cv_text[:_MAX_PAIR]}"
    return _prose(CV_QUESTIONS_PROMPT + _en(lang, " Write all questions and notes in English."), prompt)


def write_outreach(job: dict, candidate_name: str = "", cv_text: str = "", lang: str = "de") -> str:
    """Write a short candidate outreach message about a job (Structured Outputs).

    Raises on no API key / model error."""
    candidate_line = f"Candidate name: {candidate_name}" if candidate_name else "No candidate name provided."
    cv_line        = f"Candidate background (from CV):\n{cv_text}" if cv_text else "No CV provided."
    prompt = (
        f"Job title: {job.get('title', '—')}\n"
        f"Company: {job.get('company', '—')}\n"
        f"Location: {job.get('location', '—')}\n"
        f"Salary: {job.get('salary') or 'not specified'}\n"
        f"Key skills: {job.get('skills') or 'not specified'}\n"
        f"Job description excerpt: {(job.get('description') or '')[:800]}\n\n"
        f"{candidate_line}\n"
        f"{cv_line}"
    )
    return _prose(OUTREACH_PROMPT + _en(lang, " Write the message in English."), prompt)


def score_candidate_strength(job: dict, cv_text: str, lang: str = "de") -> dict:
    """Score a candidate against a job on 5 dimensions (Structured Outputs).

    Returns {axes, scores, reasons, overall} (parallel lists + an overall line). Raises on no
    API key / model error."""
    if not config.OPENAI_API_KEY:
        raise RuntimeError("OpenAI API key not configured")
    prompt = (
        f"JOB TITLE: {job.get('title', '—')}\n"
        f"COMPANY: {job.get('company', '—')}\n"
        f"REQUIRED SKILLS: {job.get('skills') or 'not specified'}\n"
        f"JOB DESCRIPTION:\n{(job.get('description') or '')[:_MAX_STRENGTH]}\n\n"
        f"CANDIDATE CV:\n{cv_text[:_MAX_STRENGTH]}"
    )
    resp = get_client().responses.parse(
        model=JOB_DETAIL_MODEL,
        instructions=STRENGTH_PROMPT + _en(lang, " Respond in English."),
        input=prompt,
        text_format=CandidateStrength,
    )
    if resp.output_parsed is None:
        raise ValueError("Model returned no score")
    return resp.output_parsed.model_dump()
