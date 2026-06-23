"""
search/job_chat.py — Single-job chat ("ask about this job") for the job-detail modal.

A conversational surface over ONE job result: the system prompt carries the full job
context (and, when the recruiter has a candidate loaded, their profile so fit can be
judged). No file_search — it never leaves the one job. Text-only reply; multi-turn memory
via previous_response_id.

Lives under `search/` because it operates on a job result — the search domain — rather
than being a generic "chat" feature (rework 2.3 #5; relocated from the old top-level chat.py).
"""
import logging

from jobs_intelligence_ai import config
from jobs_intelligence_ai.shared.llm import get_client

logger = logging.getLogger(__name__)

_JOB_SYSTEM = """You are a recruitment assistant analysing one specific job posting.
The full job details are provided below. Answer questions about this job concisely and professionally.

Job details:
  Title:       {title}
  Company:     {company}
  Location:    {location}
  Salary:      {salary}
  Category:    {occ_group}
  Skills:      {skills}
  Description: {description}

Rules:
1. Stay focused on this job. Do not search for other jobs.
2. Be concise — 2–4 sentences unless asked for more detail.
3. {{LANG_INSTRUCTION}}
4. If a candidate profile is provided below, use it to assess THIS candidate's fit for
   this job when asked — do not ask the user to supply a CV. If no candidate profile
   is provided, assess fit generically from the skills and seniority the job implies.
"""

# Appended to the job system prompt only when the recruiter has a candidate loaded,
# so the assistant can judge fit for that specific person instead of asking for a CV.
_JOB_CANDIDATE_BLOCK = """

Candidate profile (the recruiter's current candidate — assess fit for THIS job against it):
{candidate_text}"""

_LANG_INSTRUCTIONS = {
    "en":   "Always respond in English, regardless of the job description language or what language the user writes in.",
    "de":   "Antworte immer auf Deutsch, unabhängig von der Sprache der Stellenbeschreibung oder der Nutzernachricht.",
    "sk":   "Vždy odpovedaj po slovensky, bez ohľadu na jazyk inzerátu alebo správy používateľa.",
    "auto": "Respond in the same language the user writes in.",
}

_job_sessions: dict[str, str] = {}


def send_job_message(session_id: str, user_message: str, job: dict, lang: str = "en",
                     candidate_text: str = "") -> dict:
    """Single-job chat: system prompt contains full job context (and the recruiter's
    candidate profile, when supplied, so fit can be judged), no file_search."""
    if not config.OPENAI_API_KEY:
        return {"text": "Job chat requires an OpenAI API key — add OPENAI_API_KEY to your .env file."}

    client = get_client()
    previous_id = _job_sessions.get(session_id)

    lang_instruction = _LANG_INSTRUCTIONS.get(lang, _LANG_INSTRUCTIONS["en"])
    system = _JOB_SYSTEM.replace("{{LANG_INSTRUCTION}}", lang_instruction).format(
        title=job.get("title") or "—",
        company=job.get("company") or "—",
        location=", ".join(filter(None, [job.get("city"), job.get("state")])) or "—",
        salary=f"€{job.get('salary')}/month" if job.get("salary") else "Not specified",
        occ_group=job.get("occ_group") or "—",
        skills=job.get("skills_en") or job.get("skills") or "Not specified",
        description=(job.get("description") or job.get("description_snippet") or "Not available")[:1200],
    )
    candidate_text = (candidate_text or "").strip()
    if candidate_text:
        system += _JOB_CANDIDATE_BLOCK.format(candidate_text=candidate_text[:2500])

    kwargs: dict = dict(
        model=config.CHAT_MODEL,
        instructions=system,
        input=user_message,
    )
    if previous_id:
        kwargs["previous_response_id"] = previous_id

    try:
        response = client.responses.create(**kwargs)
        _job_sessions[session_id] = response.id
        return {"text": response.output_text or ""}
    except Exception as e:
        logger.error("Job chat error (session=%s): %s", session_id, e)
        return {"text": f"Sorry, something went wrong: {e}"}


def clear_job_session(session_id: str) -> None:
    _job_sessions.pop(session_id, None)
