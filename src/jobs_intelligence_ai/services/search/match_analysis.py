"""
search/match_analysis.py — overall candidate-vs-matched-jobs assessment (Search tab).

One LLM call relocated from the search blueprint and converted to Structured Outputs in rework
2.4: analyze_candidate_match(candidate_text, jobs) → a recruiter-facing prose assessment of how
the candidate stacks up across the jobs they matched (strengths, recurring gaps, what to probe in
an interview).

Lives under search/ because it operates on a candidate's live match results — the search domain —
alongside the grader and the single-job chat. Prose output, so `MatchAnalysis` is a single `text`
field; raises on no API key / model error (the blueprint maps that to a 500).
"""
import logging

from jobs_intelligence_ai import config
from jobs_intelligence_ai.shared.llm import get_client
from .config import ANALYZE_MODEL, ANALYZE_PROMPT, MatchAnalysis

logger = logging.getLogger(__name__)

_MAX_PROFILE = 2500   # candidate-profile cap (chars)
_MAX_JOBS    = 30     # matched jobs summarised into the prompt


def analyze_candidate_match(candidate_text: str, jobs: list[dict]) -> str:
    """Overall recruiter-facing assessment of a candidate vs their matched jobs (Structured Outputs).

    `jobs` is the current matched set ([{title, company, grade, score_pct, skills|skills_en,
    summary|description, city, state}]). Returns the prose assessment; raises on no API key /
    model error."""
    if not config.OPENAI_API_KEY:
        raise RuntimeError("OpenAI API key not configured")

    lines = []
    for j in jobs[:_MAX_JOBS]:
        loc    = ", ".join(filter(None, [j.get("city"), j.get("state")]))
        skills = (j.get("skills_en") or j.get("skills") or "")[:160]
        blurb  = (j.get("summary") or j.get("description") or "")[:200]
        lines.append(f"- [{j.get('grade', '?')} {j.get('score_pct', '')}] {j.get('title', '')} "
                     f"@ {j.get('company', '')}{(' · ' + loc) if loc else ''} "
                     f"| skills: {skills} | {blurb}")
    user_input = ("CANDIDATE PROFILE:\n" + candidate_text[:_MAX_PROFILE] +
                  "\n\nMATCHED JOBS (the A/B/C grade reflects current fit):\n" + "\n".join(lines))

    resp = get_client().responses.parse(
        model=ANALYZE_MODEL,
        instructions=ANALYZE_PROMPT,
        input=user_input,
        text_format=MatchAnalysis,
    )
    if resp.output_parsed is None:
        raise ValueError("Model returned no analysis")
    return resp.output_parsed.text
