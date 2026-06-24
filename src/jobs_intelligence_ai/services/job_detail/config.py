"""
config.py — settings for the `job_detail` service (flat constants, per rework §5).

Home for the prompts + Structured-Outputs schemas of the five Job-Detail-modal tools, all
converted in rework Stage 2.4. The four prose tools (translate, compact, cv-questions, outreach)
share the single-field `JobDetailText`; candidate-strength is the one real-JSON call and gets
its own `CandidateStrength` schema (it replaced the blueprint's "Return ONLY valid JSON" prompt).
"""
from pydantic import BaseModel

from jobs_intelligence_ai import config

JOB_DETAIL_MODEL = config.CHAT_MODEL


# ── operations.translate_description ────────────────────────────────────────────
TRANSLATE_PROMPT = (
    "You are a professional translator. "
    "Translate the following job description to English. "
    "Output only the translated text, preserving the original structure and line breaks."
)


# ── operations.compact_description ──────────────────────────────────────────────
COMPACT_PROMPT = (
    "Summarize the following job description in 3-4 sentences. "
    "Cover: the role and main responsibilities, key required skills or experience, "
    "and salary or benefits if mentioned. Be concise and informative. "
    "Output only the summary, nothing else."
)


# ── operations.generate_cv_questions ────────────────────────────────────────────
CV_QUESTIONS_PROMPT = (
    "You are a recruitment assistant. Compare the job description and the candidate CV. "
    "Identify gaps or areas where the candidate's experience may not fully match the role. "
    "Generate 5-7 targeted interview questions that probe those gaps. "
    "For each question add a brief one-line note (in parentheses) explaining the gap it addresses. "
    "Use a numbered list. Output only the questions, nothing else."
)


# ── operations.write_outreach ───────────────────────────────────────────────────
OUTREACH_PROMPT = (
    "You are a recruiter writing a brief outreach message to a candidate about a job opportunity. "
    "Write 3-4 sentences: mention the role and company, highlight one or two genuinely appealing aspects "
    "of the position, and end with a clear call to action (e.g. ask if they are open to a quick chat). "
    "If a candidate name is provided, address them by first name. "
    "If CV details are provided, personalise one sentence to their background. "
    "Keep the tone professional but warm. Output only the message text, no subject line or sign-off."
)


class JobDetailText(BaseModel):
    """A single prose output for a job-detail tool (translation / summary / questions / outreach)."""
    text: str


# ── operations.score_candidate_strength ─────────────────────────────────────────
STRENGTH_PROMPT = (
    "You are a recruitment analyst. Score the candidate against the job on exactly these "
    "5 dimensions: Skills Match, Experience Level, Education Fit, Salary Alignment, Location Fit. "
    "Score each 0-10 (10 = perfect fit). Provide a one-sentence reason for each score. "
    "Also write one overall sentence summarising the fit. Return the five dimension names in "
    "`axes` (in the order listed), the five integer `scores` and `reasons` in the same order, "
    "and the one-sentence `overall`."
)


class CandidateStrength(BaseModel):
    """The 5-dimension candidate-vs-job fit score: parallel axes/scores/reasons + an overall line."""
    axes: list[str]
    scores: list[int]
    reasons: list[str]
    overall: str
