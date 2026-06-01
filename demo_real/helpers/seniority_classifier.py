"""
ai/classifier.py — AI-powered seniority classification for job postings.

Sends a batch of jobs to the LLM in a single call; the model reads title,
skills, description, and occupational group to decide Senior / Mid / Junior.

Falls back to a lightweight keyword heuristic if the API call fails.
"""
import json
import logging
import re

from openai import OpenAI
import config

logger = logging.getLogger(__name__)

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=config.OPENAI_API_KEY)
    return _client


_SYSTEM = """\
You are a recruitment expert. Classify each job posting as exactly one of:
  "senior"  — requires 5+ years experience, leadership, architecture, or expert-level ownership
  "mid"     — standard professional role (2–5 years), no explicit seniority marker
  "junior"  — entry-level, trainee, apprentice, intern, student worker, or 0–2 years experience

Use ALL available signals: title keywords, required skills, years of experience in the
description, scope of responsibilities, and occupational group.

Respond with ONLY a valid JSON array — no prose, no markdown fences.
Each element: {"i": <index>, "level": "<senior|mid|junior>"}
"""


def classify_seniority(jobs: list[dict]) -> list[dict]:
    """
    Classify seniority for every job in-place (adds/overwrites the 'seniority' key).

    Parameters
    ----------
    jobs : list of job dicts (must contain at least 'title')

    Returns
    -------
    Same list, each job now has a 'seniority' field: "senior" | "mid" | "junior"
    """
    if not jobs:
        return jobs

    if not config.OPENAI_API_KEY:
        return _fallback(jobs)

    # Build compact per-job summaries to keep the prompt small
    lines = []
    for i, j in enumerate(jobs):
        parts = [f"[{i}] Title: {j.get('title') or '—'}"]
        if j.get("occ_group"):
            parts.append(f"Category: {j['occ_group']}")
        skills = j.get("skills_en") or j.get("skills")
        if skills:
            parts.append(f"Skills: {str(skills)[:250]}")
        desc = j.get("description") or j.get("description_snippet") or j.get("summary")
        if desc:
            parts.append(f"Description: {str(desc)[:350]}")
        lines.append(" | ".join(parts))

    user_input = "Classify these job postings:\n\n" + "\n".join(lines)

    try:
        client = _get_client()
        response = client.responses.create(
            model=config.CLASSIFIER_MODEL,
            instructions=_SYSTEM,
            input=user_input,
        )
        raw = (response.output_text or "").strip()

        # Strip accidental markdown fences
        raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.MULTILINE).strip()
        results = json.loads(raw)

        if not isinstance(results, list):
            raise ValueError("Expected a JSON array")

        # Apply classifications back to jobs
        for item in results:
            idx   = item.get("i")
            level = item.get("level", "").lower()
            if idx is not None and 0 <= int(idx) < len(jobs) and level in ("senior", "mid", "junior"):
                jobs[int(idx)]["seniority"] = level

        # Any job the model missed → fallback keyword guess
        for j in jobs:
            if not j.get("seniority"):
                j["seniority"] = _keyword_guess(j.get("title", ""))

    except Exception as exc:
        logger.warning("AI seniority classification failed (%s) — using keyword fallback", exc)
        return _fallback(jobs)

    return jobs


# ── Keyword fallback (no API key, or API error) ───────────────────────────────

_SENIOR_RE = re.compile(
    r"\b(senior|sr\.?|lead|principal|head\s+of|chief|staff|architect|"
    r"leitend|expert\w*|teamleiter|teamlead|director|manager|consultant)\b",
    re.IGNORECASE,
)
_JUNIOR_RE = re.compile(
    r"\b(junior|jr\.?|trainee|intern|praktikant\w*|werkstudent\w*|"
    r"berufseinsteiger\w*|absolvent\w*|nachwuchs\w*|apprentice|azubi|"
    r"lehrling|auszubildend\w*|entry[\s\-]?level|einstieg\w*)\b",
    re.IGNORECASE,
)


def _keyword_guess(title: str) -> str:
    if _SENIOR_RE.search(title or ""):
        return "senior"
    if _JUNIOR_RE.search(title or ""):
        return "junior"
    return "mid"


def _fallback(jobs: list[dict]) -> list[dict]:
    for j in jobs:
        if not j.get("seniority"):
            j["seniority"] = _keyword_guess(j.get("title", ""))
    return jobs
