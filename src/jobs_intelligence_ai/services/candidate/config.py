"""
config.py — settings for the `candidate` service (flat constants, per rework §5).

Home for this module's two LLM calls' prompts + Structured-Outputs schemas (both converted
in rework 2.3 #7): the LinkedIn profile enricher and the candidate assistant chat. The DB
store and the example-CV PDF builders have no model call, so nothing about them lives here.
"""
from typing import Literal, Optional

from pydantic import BaseModel

from jobs_intelligence_ai import config

CHAT_MODEL = config.CHAT_MODEL


# ── profile_enricher.enrich_linkedin_profile ───────────────────────────────────
ENRICH_PROMPT = """You are a senior recruiter analyzing a candidate's LinkedIn profile for the Austrian job market.
Read the raw profile JSON and produce a normalized, recruiter-ready structured record.
INFER where reasonable (seniority, total years of experience, industry, salary) from the
work history, titles, skills and dates — do not merely copy fields. Be conservative: never
invent specific employers, credentials or facts not supported by the data.

Salaries in this market are AUSTRIAN MONTHLY GROSS in euros (~14 salaries/year). Estimate a
realistic monthly-gross range for this candidate's role, seniority and location. This is an
ESTIMATE derived from the role — LinkedIn does not provide it.

For fields you genuinely cannot determine, use null (or an empty list). For seniority pick
exactly one of: Junior, Mid, Senior, Lead, Executive. years_experience and the salary
estimates are integers (monthly gross EUR for salary)."""

# AI-inferred keys merged over the mechanical base, in order.
AI_KEYS = (
    "name", "title", "current_company", "headline", "seniority", "years_experience",
    "industry", "role_category", "education_level", "management_experience",
    "top_skills", "specializations", "languages", "location", "ai_summary",
    "strengths", "estimated_salary_min", "estimated_salary_max",
)


class LinkedInProfile(BaseModel):
    """Normalized recruiter-ready profile inferred from a raw LinkedIn scrape."""
    name: str
    title: str
    current_company: Optional[str]
    headline: str
    seniority: Literal["Junior", "Mid", "Senior", "Lead", "Executive"]
    years_experience: Optional[int]
    industry: str
    role_category: str
    education_level: Optional[str]
    management_experience: str
    top_skills: list[str]
    specializations: list[str]
    languages: str
    location: str
    ai_summary: str
    strengths: list[str]
    estimated_salary_min: Optional[int]
    estimated_salary_max: Optional[int]


# ── assistant.send_candidate_message ───────────────────────────────────────────
ASSISTANT_PROMPT = """You are an AI recruitment assistant helping a recruiter work with ONE specific candidate \
for the {label} job market.

You can do two things:
1. DISCUSS — answer the recruiter's questions about this candidate, their profile, and the job offers that have been \
matched for them (fit, comparisons, which to prioritise, skill gaps, salary, location, next steps, etc.).
2. EDIT THE CV — when the recruiter asks to add, change or remove a detail about the candidate (a skill, language, \
certification/licence, availability, salary expectation, location, job title, seniority, or a summary point).

{lang_instruction}

Current candidate profile (JSON):
{profile}

Job offers currently matched for this candidate (top results on screen):
{jobs}

OUTPUT RULES:
- "reply": a short, natural reply to the recruiter (1–4 sentences). No markdown headings or bullet lists.
- "profile_updates": fill this ONLY when the recruiter asks to change the candidate's CV/profile; otherwise leave it null.
  Set ONLY the fields that change, leaving the rest null.
    Scalar fields (give the FULL new value — it replaces the old one):
      title, seniority, location, languages, salary_expectation, availability, industry, role_category, summary
    Array fields (list ONLY the new items to ADD — the app appends them and de-duplicates):
      skills, top_skills, strengths, certifications
- "cv_note": when profile_updates is set, a concise statement of what was added/changed, phrased so it can be appended \
to the candidate's CV text for re-matching (e.g. "Holds a valid forklift licence." or "Available from July 2026."). \
Otherwise an empty string."""

LANG_INSTRUCTIONS = {
    "en":   "Always respond in English, regardless of the job description language or what language the user writes in.",
    "de":   "Antworte immer auf Deutsch, unabhängig von der Sprache der Stellenbeschreibung oder der Nutzernachricht.",
    "sk":   "Vždy odpovedaj po slovensky, bez ohľadu na jazyk inzerátu alebo správy používateľa.",
    "auto": "Respond in the same language the user writes in.",
}


class ProfileUpdates(BaseModel):
    """The candidate-profile fields the recruiter asked to change (others stay null).
    Scalars replace the old value; arrays list only the new items to append+dedupe."""
    title: Optional[str] = None
    seniority: Optional[str] = None
    location: Optional[str] = None
    languages: Optional[str] = None
    salary_expectation: Optional[str] = None
    availability: Optional[str] = None
    industry: Optional[str] = None
    role_category: Optional[str] = None
    summary: Optional[str] = None
    skills: Optional[list[str]] = None
    top_skills: Optional[list[str]] = None
    strengths: Optional[list[str]] = None
    certifications: Optional[list[str]] = None


class CandidateReply(BaseModel):
    """The assistant's reply, plus optional CV edits when the recruiter asked for them."""
    reply: str
    profile_updates: Optional[ProfileUpdates] = None
    cv_note: str = ""
