"""
chat.py — Conversational job search assistant using OpenAI Responses API.
Multi-turn memory via previous_response_id; same vector store as matching.py.
"""
import json
import re
import logging
from jobs_intelligence_ai import config
from jobs_intelligence_ai.shared.llm import get_client

logger = logging.getLogger(__name__)

# The OpenAI client now lives in shared/llm.py (single app-wide singleton).
# `_get_client` is kept as a local alias so this module's internals are unchanged;
# `get_client` is re-exported for the job-detail blueprint and the core facade.
# Stage 2.1a shim — direct callers should migrate to `shared.llm.get_client`.
_get_client = get_client


_SYSTEM_TEMPLATE = """You are an AI recruitment assistant for Jobs Intelligence {label}.
You help recruiters find job openings for their candidates in the {label} job market.

You have file_search access to a live database of {label} job postings.
Use file_search whenever the user asks to find jobs, search for positions, or asks about job availability.

CRITICAL OUTPUT FORMAT RULES — you must follow these exactly:
1. {lang_instruction}
2. Be concise and professional.
3. NEVER use markdown lists, bullet points, numbered lists, or ** bold ** to describe jobs.
4. When you find jobs via file_search:
   - Write 1-2 plain sentences summarising what you found.
   - Then output EXACTLY this JSON block as the LAST thing in your response.
     Wrap it in ```json ... ``` code fences. No text after the closing fence.
   ```json
   {{"jobs":[{{
     "job_id":"<numeric id from document>",
     "title":"<exact job title>",
     "company":"<company name>",
     "city":"<city>",
     "state":"<region / state>",
     "salary":"<salary amount>",
     "portal":"<portal name>",
     "occ_group":"<occupational group>",
     "url":"<job url>",
     "description_snippet":"<one sentence: key requirements or role details>",
     "score":0.85
   }},…]}}
   ```
   Include up to 10 jobs. score = your match confidence 0.0–1.0.
   job_id = the numeric id from the document — always include it.
   Fill every field from the document. Use null only if genuinely absent.
5. If no relevant jobs were found, omit the JSON block entirely and say so in plain text.
"""

# session_id → last response_id for conversation continuity
_sessions: dict[str, str] = {}

# ── Job-specific chat ─────────────────────────────────────────────────────────

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

    client = _get_client()
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


# ── Segment chat (multi-CV clustering) ────────────────────────────────────────

_SEGMENT_SYSTEM = """You are an assistant explaining a TALENT SEGMENT that was produced by clustering candidate CVs by similarity (embeddings). Answer the recruiter's questions about this segment — why these candidates were grouped together, their shared profile, how individuals differ, and how they fit the matched roles. Refer to candidates by name.

SEGMENT: {title}
SUMMARY: {summary}
PERSONA (synthetic profile representing the segment):
{persona}

CANDIDATES IN THIS SEGMENT:
{members}

MATCHED ROLES (the A/B grade reflects the segment's fit):
{jobs}

Rules:
1. Stay focused on THIS segment, its candidates, and its roles.
2. Be concise — 2–4 sentences unless asked for more detail.
3. {{LANG_INSTRUCTION}}
4. The grouping is by overall CV similarity; if asked why someone is included, explain via their shared skills/role/seniority, and note honestly if they look like a weaker fit for the cluster.
"""

_segment_sessions: dict[str, str] = {}


def send_segment_message(session_id: str, user_message: str, segment: dict, lang: str = "en") -> dict:
    """Chat about one talent segment: the system prompt carries the segment's
    persona, member CVs, and matched roles. No file_search."""
    if not config.OPENAI_API_KEY:
        return {"text": "Segment chat requires an OpenAI API key — add OPENAI_API_KEY to your .env file."}

    client = _get_client()
    previous_id = _segment_sessions.get(session_id)

    members = "\n".join(f"- {m.get('name', '')}: {(m.get('text') or '')[:500]}"
                        for m in (segment.get("members") or [])[:12]) or "(none)"
    jobs = "\n".join(f"- [{j.get('grade', '?')}] {j.get('title', '')}"
                     for j in (segment.get("jobs") or [])[:15]) or "(not matched yet)"
    lang_instruction = _LANG_INSTRUCTIONS.get(lang, _LANG_INSTRUCTIONS["en"])
    system = _SEGMENT_SYSTEM.replace("{{LANG_INSTRUCTION}}", lang_instruction).format(
        title=(segment.get("title") or "")[:120],
        summary=(segment.get("summary") or "")[:400],
        persona=(segment.get("persona_text") or "")[:1500],
        members=members,
        jobs=jobs,
    )

    kwargs: dict = dict(model=config.CHAT_MODEL, instructions=system, input=user_message)
    if previous_id:
        kwargs["previous_response_id"] = previous_id
    try:
        response = client.responses.create(**kwargs)
        _segment_sessions[session_id] = response.id
        return {"text": response.output_text or ""}
    except Exception as e:
        logger.error("Segment chat error (session=%s): %s", session_id, e)
        return {"text": f"Sorry, something went wrong: {e}"}


def clear_segment_session(session_id: str) -> None:
    _segment_sessions.pop(session_id, None)


# ── Candidate assistant (main-page chat) ────────────────────────────────────────
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


def _build_filter_context(filters: dict) -> str:
    """Turn active filter dict into a natural-language constraint block appended to the user message."""
    if not filters:
        return ""
    lines = []
    if filters.get("portal"):
        lines.append(f"- Only include jobs from portal/source: {filters['portal']}")
    if filters.get("state"):
        lines.append(f"- Only include jobs located in state: {filters['state']}")
    sal_min = filters.get("salary_min")
    sal_max = filters.get("salary_max")
    if sal_min and sal_max:
        lines.append(f"- Salary must be between €{sal_min} and €{sal_max} per month")
    elif sal_min:
        lines.append(f"- Salary must be at least €{sal_min} per month")
    elif sal_max:
        lines.append(f"- Salary must be at most €{sal_max} per month")
    if not lines:
        return ""
    return "\n\nFilter requirements (strictly apply these):\n" + "\n".join(lines)


def send_message(session_id: str, user_message: str, lang: str = "auto",
                 filters: dict | None = None, max_results: int | None = None) -> dict:
    """
    Process one chat turn.
    Returns {"text": str, "jobs": list[dict]}.
    """
    if not config.OPENAI_API_KEY:
        return {
            "text": "Chat requires an OpenAI API key — add OPENAI_API_KEY to your .env file.",
            "jobs": [],
        }

    client = _get_client()
    previous_id = _sessions.get(session_id)

    system = _SYSTEM_TEMPLATE.format(
        label=config.COUNTRY_LABEL,
        lang_instruction=_LANG_INSTRUCTIONS.get(lang, _LANG_INSTRUCTIONS["auto"]),
    )

    # Inject filter constraints into the user message so the model can apply them during retrieval
    augmented_input = user_message + _build_filter_context(filters or {})

    # Boost retrieval window when the user wants more results
    n_retrieve = min(max(max_results or 20, 20), 50)

    kwargs: dict = dict(
        model=config.CHAT_MODEL,
        instructions=system,
        input=augmented_input,
        tools=[{
            "type": "file_search",
            "vector_store_ids": [config.VECTOR_STORE_ID],
            "max_num_results": n_retrieve,
        }],
    )
    if previous_id:
        kwargs["previous_response_id"] = previous_id

    try:
        response = client.responses.create(**kwargs)
        _sessions[session_id] = response.id
        return _parse(response.output_text or "")
    except Exception as e:
        logger.error("Chat error (session=%s): %s", session_id, e)
        return {"text": f"Sorry, something went wrong: {e}", "jobs": []}


def clear_session(session_id: str) -> None:
    _sessions.pop(session_id, None)


def enrich_jobs_from_db(jobs: list[dict]) -> list[dict]:
    """
    Fill in full description, URL, skills and other DB fields for chat jobs.
    1. Try to look up by numeric job_id.
    2. For any jobs whose ID wasn't found, fall back to title + company LIKE search.
    """
    if not jobs:
        return jobs

    from jobs_intelligence_ai import config
    from jobs_intelligence_ai.infra.database import fetch_jobs_by_ids, fetch_jobs_by_title_company
    from jobs_intelligence_ai.services.seniority_classifier import classify_seniority

    c = config.COL

    def _s(v):
        s = str(v).strip() if v is not None else None
        return s if s else None

    def _apply_row(e: dict, row: dict) -> None:
        """Overwrite job dict fields with authoritative DB values."""
        db_id = _s(row.get(c["job_id"]))
        if db_id:
            e["job_id"]  = db_id
        e["title"]                   = _s(row.get(c["title"]))                   or e.get("title")
        e["company"]                 = _s(row.get(c["company"]))                 or e.get("company")
        e["state"]                   = _s(row.get(c["state"]))                   or e.get("state")
        e["city"]                    = _s(row.get(c["city"]))                    or e.get("city")
        e["municipality"]            = _s(row.get(c.get("municipality", "municipality")))
        e["zipcode"]                 = _s(row.get(c.get("zipcode", "zipcode")))
        e["detailed_location"]       = _s(row.get(c.get("detailed_location", "detailed_location")))
        e["salary"]                  = _s(row.get(c["salary"]))                  or e.get("salary")
        e["salary_type"]             = _s(row.get(c.get("salary_type", "salary_type")))
        e["original_salary"]         = _s(row.get(c.get("original_salary", "original_salary")))
        e["work_time"]               = _s(row.get(c.get("work_time", "work_time")))
        e["employment_relationship"] = _s(row.get(c.get("employment_relationship", "employment_relationship")))
        e["education"]               = _s(row.get(c.get("education", "education")))
        e["portal"]                  = _s(row.get(c["portal"]))                  or e.get("portal")
        e["occ_group"]               = _s(row.get(c["occ_group"]))               or e.get("occ_group")
        e["url"]                     = _s(row.get(c["url"]))                     or e.get("url")
        e["order_number"]            = _s(row.get(c.get("order_number", "order_number")))
        e["posted"]                  = _s(row.get(c["date_posted"]))
        e["application_deadline"]    = _s(row.get(c.get("application_deadline", "application_deadline")))
        e["start_timeline"]          = _s(row.get(c.get("start_timeline", "start_timeline")))
        e["description"]             = _s(row.get(c["description"]))
        e["summary"]                 = _s(row.get(c.get("summary", "summary")))
        e["skills"]                  = _s(row.get(c.get("skills", "skills")))
        e["skills_en"]               = _s(row.get(c.get("skills_en", "skills_english")))
        e["contacts"]                = _s(row.get(c.get("contacts", "contacts")))
        e["lat"]                     = row.get("_lat")
        e["lon"]                     = row.get("_lon")

    enriched = [dict(j) for j in jobs]
    for j in enriched:
        j["_verified"] = False   # will be set True only by a confirmed DB id match

    # ── Pass 1: look up by numeric job_id ────────────────────────────────────
    id_map: dict[str, int] = {}   # str(id) → index in enriched list
    raw_ids = []
    for i, j in enumerate(enriched):
        jid = j.get("job_id")
        if jid and str(jid).isdigit():
            raw_ids.append(int(jid))
            id_map[str(jid)] = i

    resolved: set[int] = set()   # indices that were enriched via ID lookup

    if raw_ids:
        try:
            rows = fetch_jobs_by_ids(raw_ids)
            for row in rows:
                jid = str(row.get(c["job_id"]) or "")
                if jid in id_map:
                    idx = id_map[jid]
                    _apply_row(enriched[idx], row)
                    enriched[idx]["_verified"] = True
                    resolved.add(idx)
        except Exception:
            pass

    unverified_ids = [enriched[i].get("job_id") for i in range(len(enriched)) if i not in resolved]
    if unverified_ids:
        logger.warning(
            "enrich_jobs_from_db: %d/%d job IDs not found in DB (likely hallucinated): %s",
            len(unverified_ids), len(enriched), unverified_ids[:10],
        )

    # ── Pass 2: title + company fallback for unresolved jobs ─────────────────
    # Runs to fill in fields where possible but does NOT set _verified=True —
    # these jobs matched by title similarity, not by the ID GPT returned.
    unresolved_indices = [i for i in range(len(enriched)) if i not in resolved]
    if unresolved_indices:
        candidates = [
            {"idx": i, "title": enriched[i].get("title"), "company": enriched[i].get("company")}
            for i in unresolved_indices
            if enriched[i].get("title")
        ]
        if candidates:
            try:
                fallback_rows = fetch_jobs_by_title_company(candidates)
                # Map each fallback row back by matched title
                title_to_idx = {c_["title"].lower(): c_["idx"] for c_ in candidates if c_.get("title")}
                for row in fallback_rows:
                    matched = (row.get("_matched_title") or "").lower()
                    idx = title_to_idx.get(matched)
                    if idx is not None:
                        _apply_row(enriched[idx], row)
            except Exception as exc:
                logger.warning("Title/company fallback failed: %s", exc)

    # Classify all jobs in one batch AI call (uses title + skills + description)
    classify_seniority(enriched)

    return enriched


def _parse(raw: str) -> dict:
    """
    Extract prose text and jobs list from the AI response.
    Handles multiple formats gpt-4o may return:
      1. prose + ```json {"jobs":[...]} ``` at the end  (expected)
      2. prose + raw {"jobs":[...]} at the end
      3. just raw {"jobs":[...]} with no prose
      4. {"jobs":[...]} embedded anywhere in the text
    """
    s = raw.strip()

    # 1. Code-fenced block at end  (expected format)
    m = re.search(r'```(?:json)?\s*(\{.*?\})\s*```\s*$', s, re.DOTALL)
    if m:
        text = s[:m.start()].strip()
        try:
            data = json.loads(m.group(1))
            if isinstance(data, dict) and "jobs" in data:
                return {"text": text, "jobs": data["jobs"]}
        except Exception:
            pass

    # 2. Entire response is a raw JSON object containing "jobs"
    if s.startswith('{'):
        try:
            data = json.loads(s)
            if isinstance(data, dict) and "jobs" in data:
                return {"text": "", "jobs": data["jobs"]}
        except Exception:
            pass

    # 3. JSON object with "jobs" key embedded somewhere in the text
    m = re.search(r'(\{"jobs"\s*:\s*\[)', s, re.DOTALL)
    if m:
        candidate = s[m.start():]
        # strip any trailing code fence or prose
        candidate = re.sub(r'```[\s\S]*$', '', candidate).strip()
        try:
            data = json.loads(candidate)
            if isinstance(data, dict) and "jobs" in data:
                prose = s[:m.start()].strip()
                return {"text": prose, "jobs": data["jobs"]}
        except Exception:
            pass

    return {"text": s, "jobs": []}
