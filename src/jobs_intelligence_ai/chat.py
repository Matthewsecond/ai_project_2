"""
chat.py — Candidate assistant chat (awaiting its domain home).

Holding module for the candidate assistant — a search-tab chat that discusses ONE loaded
candidate and edits their CV/profile. It moves to services/candidate/ in step 2.3 #7. The
other surfaces that used to share this file have left: the job-search chat was DELETED
(superseded; #5), single-job chat → services/search/job_chat.py (#5), and segment chat →
services/clustering/segment_chat.py (#6).

Multi-turn memory via previous_response_id; the OpenAI client is shared/llm.get_client.
"""
import json
import re
import logging
from jobs_intelligence_ai import config
from jobs_intelligence_ai.shared.llm import get_client

logger = logging.getLogger(__name__)

# The OpenAI client lives in shared/llm.py; `_get_client` is a local alias so this module's
# internals read unchanged.
_get_client = get_client

_LANG_INSTRUCTIONS = {
    "en":   "Always respond in English, regardless of the job description language or what language the user writes in.",
    "de":   "Antworte immer auf Deutsch, unabhängig von der Sprache der Stellenbeschreibung oder der Nutzernachricht.",
    "sk":   "Vždy odpovedaj po slovensky, bez ohľadu na jazyk inzerátu alebo správy používateľa.",
    "auto": "Respond in the same language the user writes in.",
}


# ── Candidate assistant (main-page chat) — moves to services/candidate/ in 2.3 #7 ──
# A chat docked on the search tab that works with ONE loaded candidate: it can
# (a) discuss the candidate and the job offers currently matched for them, and
# (b) edit the candidate's CV/profile when the recruiter asks. Profile edits come
# back as a structured JSON block the front-end merges into the profile card.

_CANDIDATE_SYSTEM = """You are an AI recruitment assistant helping a recruiter work with ONE specific candidate \
for the {label} job market.

You can do two things:
1. DISCUSS — answer the recruiter's questions about this candidate, their profile, and the job offers that have been \
matched for them (fit, comparisons, which to prioritise, skill gaps, salary, location, next steps, etc.).
2. EDIT THE CV — when the recruiter asks to add, change or remove a detail about the candidate (a skill, language, \
certification/licence, availability, salary expectation, location, job title, seniority, or a summary point), update \
the candidate's profile accordingly.

{lang_instruction}

Current candidate profile (JSON):
{profile}

Job offers currently matched for this candidate (top results on screen):
{jobs}

OUTPUT RULES — follow exactly:
- Write a short, natural reply to the recruiter (1–4 sentences). No markdown headings or bullet lists.
- ONLY if this message asks you to change the candidate's CV/profile, append EXACTLY ONE JSON block as the LAST thing \
in your reply, wrapped in ```json ... ``` fences, with no text after the closing fence:
  ```json
  {{"profile_updates": {{ ...only the fields that change... }}, "cv_note": "<one concise CV-style sentence describing the change>"}}
  ```
  Scalar fields (give the FULL new value — it replaces the old one):
    title, seniority, location, languages, salary_expectation, availability, industry, role_category, summary
  Array fields (list ONLY the new items to ADD — the app appends them and de-duplicates):
    skills, top_skills, strengths, certifications
  Set "cv_note" to a concise statement of what was added/changed, phrased so it can be appended to the candidate's CV \
  text for re-matching (e.g. "Holds a valid forklift licence." or "Available from July 2026.").
- If the message is only a question or discussion and changes nothing about the candidate, do NOT output any JSON block.
"""

_candidate_sessions: dict[str, str] = {}


def _format_jobs_for_prompt(jobs: list[dict]) -> str:
    """Compact, readable list of the matched offers for the system prompt."""
    if not jobs:
        return "(no jobs matched yet — the recruiter has not run matching, or there were no results)"
    lines = []
    for i, j in enumerate(jobs[:15], 1):
        loc   = ", ".join(filter(None, [j.get("city"), j.get("state")])) or "—"
        sal   = j.get("salary") or "—"
        grade = j.get("grade") or ""
        score = j.get("score_pct") or (f"{round(j['score'] * 100)}%" if isinstance(j.get("score"), (int, float)) else "")
        head  = f"{i}. {j.get('title') or 'Untitled'} — {j.get('company') or 'Unknown company'} ({loc})"
        meta  = f"salary {sal}; fit {score} {('grade ' + grade) if grade else ''}".strip()
        line  = f"{head}; {meta}"
        if j.get("match_reason"):
            line += f"; why: {j['match_reason']}"
        lines.append(line)
    return "\n".join(lines)


def send_candidate_message(session_id: str, user_message: str, profile: dict | None,
                           jobs: list[dict] | None, lang: str = "en") -> dict:
    """Candidate-centric chat. Returns {text, profile_updates, cv_note}.

    `profile` is the current candidate-profile dict shown on the card; `jobs` is the
    list of offers currently matched on screen. Both are passed each turn so the
    assistant always reasons over the latest state even across re-matches.
    """
    if not config.OPENAI_API_KEY:
        return {"text": "The candidate assistant requires an OpenAI API key — add OPENAI_API_KEY to your .env file.",
                "profile_updates": {}, "cv_note": ""}

    client = _get_client()
    previous_id = _candidate_sessions.get(session_id)

    # Keep the profile blob small but useful — drop bulky/raw fields.
    prof = profile or {}
    slim = {k: v for k, v in prof.items()
            if k not in ("experiences", "current_company", "raw", "_lat", "_lon") and v not in (None, "", [])}

    lang_instruction = _LANG_INSTRUCTIONS.get(lang, _LANG_INSTRUCTIONS["en"])
    system = _CANDIDATE_SYSTEM.format(
        label=config.COUNTRY_LABEL,
        lang_instruction=lang_instruction,
        profile=json.dumps(slim, ensure_ascii=False) if slim else "(no candidate loaded yet)",
        jobs=_format_jobs_for_prompt(jobs or []),
    )

    kwargs: dict = dict(
        model=config.CHAT_MODEL,
        instructions=system,
        input=user_message,
    )
    if previous_id:
        kwargs["previous_response_id"] = previous_id

    try:
        response = client.responses.create(**kwargs)
        _candidate_sessions[session_id] = response.id
        return _parse_candidate(response.output_text or "")
    except Exception as e:
        logger.error("Candidate chat error (session=%s): %s", session_id, e)
        return {"text": f"Sorry, something went wrong: {e}", "profile_updates": {}, "cv_note": ""}


def clear_candidate_session(session_id: str) -> None:
    _candidate_sessions.pop(session_id, None)


def _parse_candidate(raw: str) -> dict:
    """Split prose from an optional trailing ```json {"profile_updates":..} ``` block."""
    s = raw.strip()
    out = {"text": s, "profile_updates": {}, "cv_note": ""}

    m = re.search(r'```(?:json)?\s*(\{.*\})\s*```\s*$', s, re.DOTALL)
    if not m:
        # Tolerate a bare trailing JSON object with no fences.
        m = re.search(r'(\{\s*"profile_updates".*\})\s*$', s, re.DOTALL)
    if m:
        try:
            data = json.loads(m.group(1))
            if isinstance(data, dict) and ("profile_updates" in data or "cv_note" in data):
                out["text"]            = s[:m.start()].strip()
                out["profile_updates"] = data.get("profile_updates") or {}
                out["cv_note"]         = (data.get("cv_note") or "").strip()
        except Exception:
            pass   # malformed block → just return the whole thing as prose
    return out
