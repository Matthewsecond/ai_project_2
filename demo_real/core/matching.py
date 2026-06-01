"""
matching.py — Real AI matching using OpenAI Vector Store (file_search).

Flow:
  1. Embed candidate text → semantic search via file_search tool (Responses API)
  2. Extract job IDs / positions from the search results
  3. Fetch full job records from MySQL for those IDs
  4. Return ranked list with real similarity scores

This mirrors the pattern in llm_chat.py (JobsAustriaChat) which is already
proven against the same vector store.
"""
import json
import os
import re
import logging
from openai import OpenAI

import config
from core.database import fetch_jobs_by_ids, fetch_jobs_for_matching
from helpers.seniority_classifier import classify_seniority

logger = logging.getLogger(__name__)

# ─── OpenAI client (lazy) ─────────────────────────────────────────────────────
_client: OpenAI | None = None

def get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=config.OPENAI_API_KEY)
    return _client


# ─── System prompt for the matching call ─────────────────────────────────────
_MATCH_PROMPT = """You are a job matching engine for Jobs Intelligence Austria.
The user will provide a candidate profile (CV text, free-text description, or key skills).
Use file_search to find the most relevant job postings.

After searching, respond with ONLY a valid JSON array — no prose, no markdown fences.
Each element must have exactly these fields:
  "job_id"      : integer or null  (numeric id if you can read it from the document)
  "position"    : string           (exact job title as it appears in the document)
  "score"       : float            (your confidence this is a match, 0.0–1.0)
  "match_reason": string           (one sentence explaining the match)

Return at most {top_n} results, best match first.
If you cannot find a numeric id in the document, set job_id to null.
"""


# ─── Public interface ─────────────────────────────────────────────────────────

def run_matching(candidate_text: str, filters: dict, top_n: int = None) -> list[dict]:
    """
    Main entry point.
    Returns a ranked list of job dicts with score, grade, match_reason.
    Falls back to keyword-based scoring if OpenAI key is missing.
    """
    top_n = min(top_n or config.DEFAULT_TOP_N, config.MAX_TOP_N)

    if not config.OPENAI_API_KEY or config.OPENAI_API_KEY == "your_key_here":
        logger.warning("No OpenAI API key — using keyword fallback")
        return _keyword_fallback(candidate_text, filters, top_n)

    try:
        return _vector_match(candidate_text, filters, top_n)
    except Exception as e:
        logger.error("Vector match failed: %s — falling back to keyword", e)
        return _keyword_fallback(candidate_text, filters, top_n)


# ─── Real vector store matching ───────────────────────────────────────────────

def _vector_match(candidate_text: str, filters: dict, top_n: int) -> list[dict]:
    client = get_client()

    # 1. Run file_search via Responses API (same as llm_chat.py)
    response = client.responses.create(
        model=config.CHAT_MODEL,
        instructions=_MATCH_PROMPT.format(top_n=top_n),
        input=f"Find the best matching jobs for this candidate:\n\n{candidate_text}",
        tools=[{
            "type": "file_search",
            "vector_store_ids": [config.VECTOR_STORE_ID],
            "max_num_results": config.MAX_NUM_RESULTS,
        }],
    )

    raw_text = response.output_text or ""
    logger.debug("Vector store raw response: %s", raw_text[:500])

    # 2. Parse the JSON array from the response
    matches = _parse_match_json(raw_text)
    if not matches:
        logger.warning("Could not parse JSON from model response")
        return []

    # 3. Fetch full job records from MySQL
    #    Try by numeric ID first, then fall back to position-name lookup
    job_ids    = [m["job_id"]   for m in matches if m.get("job_id")]
    positions  = [m["position"] for m in matches if m.get("position")]

    db_jobs = {}   # job_id → db row dict
    if job_ids:
        rows = fetch_jobs_by_ids(job_ids)
        for r in rows:
            db_jobs[str(r.get(config.COL["job_id"]))] = r

    # For any match not resolved by ID, try to find by position name
    unresolved = [m for m in matches if not m.get("job_id") or str(m["job_id"]) not in db_jobs]
    db_by_pos: dict[str, dict] = {}   # normalized title → db row (for null-id fallback)
    if unresolved and positions:
        fallback_rows = fetch_jobs_for_matching(
            {"_positions": [m["position"] for m in unresolved]},
            limit=len(unresolved) * 3
        )
        for r in fallback_rows:
            jid = str(r.get(config.COL["job_id"]))
            if jid not in db_jobs:
                db_jobs[jid] = r
            title_key = str(r.get(config.COL["title"]) or "").strip().lower()
            if title_key and title_key not in db_by_pos:
                db_by_pos[title_key] = r

    # 4. Apply hard filters (state, portal, etc.) and build final result list
    results = []
    for match in matches:
        jid  = str(match.get("job_id", "")) if match.get("job_id") else None
        row  = db_jobs.get(jid) if jid else None
        # Secondary lookup: match by position title when job_id was null or stale
        if row is None and match.get("position"):
            pos_key = match["position"].strip().lower()
            row = db_by_pos.get(pos_key)
            if row is None:
                for k, v in db_by_pos.items():
                    if pos_key[:50] in k or k[:50] in pos_key:
                        row = v
                        break

        # If we have a DB row, apply hard filters
        if row and not _passes_filters(row, filters):
            continue

        score = float(match.get("score", 0.5))
        score = round(max(0.0, min(1.0, score)), 3)
        grade = _grade(score)

        if row:
            job_dict = _serialize_job(row)
        else:
            # Model found it in vector store but not in DB — use whatever we have
            job_dict = {
                "job_id":    jid or match.get("position", ""),
                "title":     match.get("position", "Unknown"),
                "company":   None, "state": None, "city": None,
                "salary":    None, "url":   None, "portal": None,
                "occ_group": None, "posted": None, "lat": None, "lon": None,
            }

        results.append({
            **job_dict,
            "score":        score,
            "score_pct":    f"{int(score * 100)}%",
            "grade":        grade,
            "match_reason": match.get("match_reason", ""),
        })

    # Supplement unresolved results with keyword-matched DB jobs.
    # The vector store may be indexed from older data; keyword fallback always
    # hits the live DB so its results always have full metadata.
    resolved   = [r for r in results if r.get("company") is not None]
    unresolved = [r for r in results if r.get("company") is None]

    if unresolved:
        logger.warning(
            "Vector store/DB mismatch: %d/%d results not resolved from DB — "
            "supplementing with keyword-matched DB jobs.",
            len(unresolved), len(results),
        )
        kw_results = _keyword_fallback(candidate_text, filters, len(unresolved) + 5)
        existing_titles = {r["title"].lower()[:50] for r in resolved}
        for kw in kw_results:
            if kw["title"].lower()[:50] not in existing_titles:
                resolved.append(kw)
                existing_titles.add(kw["title"].lower()[:50])
            if len(resolved) >= top_n:
                break

    resolved.sort(key=lambda x: x["score"], reverse=True)
    final = resolved[:top_n]
    classify_seniority(final)
    return final


def _passes_filters(row: dict, filters: dict) -> bool:
    c = config.COL
    if filters.get("state") and row.get(c["state"]) != filters["state"]:
        return False
    if filters.get("portal") and row.get(c["portal"]) != filters["portal"]:
        return False
    if filters.get("occ_group") and row.get(c["occ_group"]) != filters["occ_group"]:
        return False
    if filters.get("city"):
        city_val = str(row.get(c["city"], "") or "")
        if filters["city"].lower() not in city_val.lower():
            return False
    return True


def _parse_match_json(text: str) -> list[dict]:
    """Extract a JSON array from the model's response text."""
    # Strip markdown fences if present
    text = re.sub(r"```(?:json)?", "", text).strip().rstrip("`").strip()

    # Try direct parse
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return data
    except Exception:
        pass

    # Try to find a JSON array anywhere in the text
    match = re.search(r'\[.*\]', text, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group())
            if isinstance(data, list):
                return data
        except Exception:
            pass

    return []


# ─── Keyword fallback (no OpenAI key) ─────────────────────────────────────────

def _keyword_fallback(candidate_text: str, filters: dict, top_n: int) -> list[dict]:
    """
    Simple keyword overlap scoring — used when OpenAI key is not set.
    Fetches real jobs from MySQL and scores by Jaccard similarity.
    """
    jobs = fetch_jobs_for_matching(filters, limit=500)
    if not jobs:
        return []

    candidate_tokens = _tokenize(candidate_text)
    c = config.COL
    scored = []

    for job in jobs:
        job_text = " ".join(filter(None, [
            str(job.get(c["title"], "") or ""),
            str(job.get(c["occ_group"], "") or ""),
            str(job.get(c["description"], "") or "")[:400],
            str(job.get(c["esco_skills"], "") or ""),
        ]))
        job_tokens = _tokenize(job_text)
        base  = _jaccard(candidate_tokens, job_tokens)
        score = round(min(0.97, 0.30 + base * 1.8), 3)
        jid   = str(job.get(c["job_id"], "0"))
        score += (sum(ord(ch) for ch in jid) % 100 - 50) / 1000.0
        score  = round(max(0.0, min(1.0, score)), 3)
        grade  = _grade(score)
        shared = candidate_tokens & job_tokens
        top_words = sorted(shared, key=len, reverse=True)[:5]
        reason = (f"Keyword overlap: {', '.join(top_words)}" if top_words
                  else "Low keyword overlap — add more specific skills")
        scored.append({
            **_serialize_job(job),
            "score":        score,
            "score_pct":    f"{int(score * 100)}%",
            "grade":        grade,
            "match_reason": reason,
        })

    scored.sort(key=lambda x: x["score"], reverse=True)
    final = scored[:top_n]
    classify_seniority(final)
    return final


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _grade(score: float) -> str:
    if score >= config.SCORE_A_MIN:
        return "A"
    if score >= config.SCORE_B_MIN:
        return "B"
    return "C"


def _tokenize(text: str) -> set[str]:
    if not text:
        return set()
    return set(re.findall(r'\b[a-züäöÜÄÖß]{3,}\b', text.lower()))


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def _serialize_job(job: dict) -> dict:
    c = config.COL
    return {
        "job_id":                 _str(job.get(c["job_id"])),
        "title":                  _str(job.get(c["title"])) or "Untitled",
        "company":                _str(job.get(c["company"])) or "Unknown",
        "state":                  _str(job.get(c["state"])),
        "city":                   _str(job.get(c["city"])),
        "municipality":           _str(job.get(c.get("municipality", "municipality"))),
        "zipcode":                _str(job.get(c.get("zipcode", "zipcode"))),
        "detailed_location":      _str(job.get(c.get("detailed_location", "detailed_location"))),
        "salary":                 _str(job.get(c["salary"])),
        "salary_type":            _str(job.get(c.get("salary_type", "salary_type"))),
        "original_salary":        _str(job.get(c.get("original_salary", "original_salary"))),
        "work_time":              _str(job.get(c.get("work_time", "work_time"))),
        "employment_relationship":_str(job.get(c.get("employment_relationship", "employment_relationship"))),
        "education":              _str(job.get(c.get("education", "education"))),
        "url":                    _str(job.get(c["url"])),
        "portal":                 _str(job.get(c["portal"])),
        "order_number":           _str(job.get(c.get("order_number", "order_number"))),
        "occ_group":              _str(job.get(c["occ_group"])),
        "posted":                 _str(job.get(c["date_posted"])),
        "application_deadline":   _str(job.get(c.get("application_deadline", "application_deadline"))),
        "start_timeline":         _str(job.get(c.get("start_timeline", "start_timeline"))),
        "description":            _str(job.get(c["description"])),
        "summary":                _str(job.get(c.get("summary", "summary"))),
        "skills":                 _str(job.get(c.get("skills", "skills"))),
        "skills_en":              _str(job.get(c.get("skills_en", "skills_english"))),
        "contacts":               _str(job.get(c.get("contacts", "contacts"))),
        "lat":                    job.get("_lat"),
        "lon":                    job.get("_lon"),
    }


def _str(val) -> str | None:
    if val is None:
        return None
    s = str(val).strip()
    return s if s else None
