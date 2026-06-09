"""
helpers/candidate_store.py — MySQL persistence for the saved-candidate pipeline.

Backs the Saved-Jobs / Build-a-Candidate features with the four tables in the
`Jobs_Intelligence_AI` schema, replacing the old in-memory dicts in tabs/saved.py:

    candidate            — one row per real candidate (identity + parsed profile)
    candidate_saved_job  — one row per saved job (point-in-time JSON snapshot)
    target_candidate     — guided-builder specs (NOT personal data)
    audit_log            — who viewed / edited / exported / deleted what

GDPR notes baked in here:
  * The matching code reads jobs/profile by candidate_id, never needs the name.
  * Deleting a candidate cascades to their saved jobs (ON DELETE CASCADE in DDL).
  * audit_log keeps candidate_id as a bare column (no FK) so the trail survives
    an erasure.

The public API is keyed by candidate NAME to match the existing routes/front-end;
internally we resolve each name to its surrogate candidate_id (get-or-create).
"""
import json as _json
import logging
import re

from sqlalchemy import text

from core.database import get_engine

logger = logging.getLogger(__name__)

_DB = "Jobs_Intelligence_AI"

# Profile columns on `candidate` filled by the CV parser / LinkedIn import.
# `_PROFILE_SCALARS` are plain string/number columns; `_PROFILE_JSON` are JSON
# columns serialised via _dump. LinkedIn imports add the richer fields (headline,
# work history, education, certifications, profile signals); CV uploads leave
# those null. They round-trip so a reloaded candidate keeps the full context.
_PROFILE_SCALARS = ("title", "experience_years", "location",
                    "languages", "salary_expectation", "availability", "summary",
                    "headline", "profile_pic_url", "public_identifier",
                    # AI-analysed (gpt-5.4) fields — populated for LinkedIn imports
                    "seniority", "current_company", "industry", "role_category",
                    "education_level", "management_experience", "ai_summary",
                    "ai_model", "enriched_at")
_PROFILE_INTS = ("follower_count", "years_experience",
                 "estimated_salary_min", "estimated_salary_max")
_PROFILE_JSON = ("skills", "experiences", "education", "certifications",
                 "top_skills", "specializations", "strengths", "raw_profile")

# Fields copied straight out of a saved-job dict into typed columns (for
# querying / indexing); the full job dict is also kept in job_snapshot.
_UNASSIGNED = "Unassigned"


# ── JSON helpers ──────────────────────────────────────────────────────────────
def _dump(v) -> str | None:
    """Serialise a list/dict to a JSON string for a MySQL JSON column."""
    if v is None:
        return None
    return _json.dumps(v, ensure_ascii=False, default=str)


def _load(v):
    """Parse a JSON column back to Python (PyMySQL hands these back as str)."""
    if v is None or v == "":
        return None
    if isinstance(v, (list, dict)):
        return v
    try:
        return _json.loads(v)
    except (ValueError, TypeError):
        return None


# ══════════════════════════════════════════════════════════════════════════════
#  Candidates (identity + parsed profile)
# ══════════════════════════════════════════════════════════════════════════════
def get_or_create_candidate(name: str, profile: dict | None = None,
                            created_by: str | None = None) -> int:
    """Resolve a candidate NAME to its candidate_id, creating the row if needed.

    When `profile` is supplied it is merged into the row (upsert), so saving a
    job alongside a freshly-parsed CV captures the profile in one go. `created_by`
    (the logged-in user) is recorded only when the row is first created.
    """
    name = (name or "").strip() or _UNASSIGNED
    eng = get_engine()
    with eng.begin() as conn:
        row = conn.execute(
            text(f"SELECT candidate_id FROM {_DB}.candidate WHERE full_name = :n LIMIT 1"),
            {"n": name}).first()
        if row:
            cid = int(row[0])
            if profile:
                _apply_profile(conn, cid, profile)
            return cid

        cols = {"full_name": name}
        if created_by:
            cols["created_by"] = created_by
        if profile:
            cols.update(_profile_columns(profile))
        keys = ", ".join(cols)
        vals = ", ".join(f":{k}" for k in cols)
        res = conn.execute(
            text(f"INSERT INTO {_DB}.candidate ({keys}) VALUES ({vals})"), cols)
        return int(res.lastrowid)


def _profile_columns(profile: dict) -> dict:
    """Map a parsed-profile dict to candidate column values (skills → JSON)."""
    cols: dict = {}
    for k in _PROFILE_SCALARS:
        if profile.get(k) is not None:
            cols[k] = profile[k]
    if profile.get("email"):
        cols["email"] = profile["email"]
    if profile.get("phone"):
        cols["phone"] = profile["phone"]
    if profile.get("linkedin"):
        cols["linkedin"] = profile["linkedin"]
    # `source` on a profile carries two separate concepts:
    #   • 'template' → the guided-builder KIND marker → set the is_template flag.
    #   • a real origin ('cv_upload'|'manual'|'imported', e.g. a LinkedIn import)
    #     → write the candidate.source enum column.
    for k in _PROFILE_INTS:
        if profile.get(k) is not None:
            try:
                cols[k] = int(profile[k])
            except (TypeError, ValueError):
                pass
    src = str(profile.get("source") or "").lower()
    if src == "template":
        cols["is_template"] = 1
    elif src in ("cv_upload", "manual", "imported"):
        cols["source"] = src
    for k in _PROFILE_JSON:
        if profile.get(k) is not None:
            cols[k] = _dump(profile[k])
    return cols


def _apply_profile(conn, candidate_id: int, profile: dict) -> None:
    """UPDATE the candidate row with any non-null profile fields."""
    cols = _profile_columns(profile)
    if not cols:
        return
    sets = ", ".join(f"{k} = :{k}" for k in cols)
    cols["cid"] = candidate_id
    conn.execute(text(f"UPDATE {_DB}.candidate SET {sets} WHERE candidate_id = :cid"), cols)


def upsert_profile(name: str, profile: dict, created_by: str | None = None) -> int:
    """Create-or-update a candidate's parsed profile. Returns candidate_id."""
    return get_or_create_candidate(name, profile, created_by=created_by)


def lookup_candidate(name: str) -> dict | None:
    """Quick existence check for a candidate NAME → identity + pipeline status.

    Returns {name, status, isTemplate, matches} if a candidate row exists, else
    None. Used to warn when a name being added in the search is already saved.
    """
    name = (name or "").strip()
    if not name:
        return None
    sql = (f"SELECT c.full_name, c.status, c.is_template, "
           f"  (SELECT COUNT(*) FROM {_DB}.candidate_saved_job s "
           f"   WHERE s.candidate_id = c.candidate_id) AS matches "
           f"FROM {_DB}.candidate c WHERE c.full_name = :n LIMIT 1")
    with get_engine().connect() as conn:
        row = conn.execute(text(sql), {"n": name}).mappings().first()
    if not row:
        return None
    return {
        "name":       row["full_name"],
        "status":     row["status"] or "New",
        "isTemplate": bool(row["is_template"]),
        "matches":    int(row["matches"] or 0),
    }


def _linkedin_slug(url: str) -> str:
    """Extract the stable '/in/<handle>' part of a LinkedIn URL for matching, so
    differing schemes/trailing slashes/query strings still resolve to one profile."""
    m = re.search(r"/in/([^/?#]+)", (url or "").lower())
    return m.group(1).strip() if m else ""


def lookup_by_linkedin(url: str) -> dict | None:
    """Find a saved candidate by their LinkedIn profile URL (matched on the /in/
    handle) → same shape as lookup_candidate, plus the stored URL. Lets LinkedIn
    search warn (and offer a DB reload) before paying to re-scrape a profile that
    is already on file."""
    slug = _linkedin_slug(url)
    if not slug:
        return None
    sql = (f"SELECT c.full_name, c.status, c.is_template, c.linkedin, "
           f"  (SELECT COUNT(*) FROM {_DB}.candidate_saved_job s "
           f"   WHERE s.candidate_id = c.candidate_id) AS matches "
           f"FROM {_DB}.candidate c "
           f"WHERE c.linkedin IS NOT NULL AND LOWER(c.linkedin) LIKE :pat "
           f"ORDER BY c.candidate_id DESC LIMIT 1")
    with get_engine().connect() as conn:
        row = conn.execute(text(sql), {"pat": f"%/in/{slug}%"}).mappings().first()
    if not row:
        return None
    return {
        "name":       row["full_name"],
        "status":     row["status"] or "New",
        "isTemplate": bool(row["is_template"]),
        "matches":    int(row["matches"] or 0),
        "linkedin":   row["linkedin"],
    }


def get_candidate_bundle(name: str) -> dict:
    """Profile + saved jobs for a candidate NAME, so the search tab can reload a
    previously-saved candidate from the DB instead of re-parsing a CV / re-scraping
    a LinkedIn profile. Returns {profile, jobs} (profile may be None)."""
    name = (name or "").strip()
    return {
        "profile": get_profile(name),
        "jobs":    _select_saved("WHERE c.full_name = :n", {"n": name}),
    }


def get_profile(name: str) -> dict | None:
    """Reconstruct the parsed-profile dict for a candidate, or None if no profile."""
    name = (name or "").strip()
    with get_engine().connect() as conn:
        row = conn.execute(
            text(f"SELECT full_name, email, phone, linkedin, title, experience_years, location, "
                 f"languages, skills, salary_expectation, availability, summary, "
                 f"headline, profile_pic_url, public_identifier, follower_count, "
                 f"experiences, education, certifications, "
                 f"seniority, years_experience, current_company, industry, role_category, "
                 f"education_level, management_experience, ai_summary, ai_model, enriched_at, "
                 f"top_skills, specializations, strengths, "
                 f"estimated_salary_min, estimated_salary_max "
                 f"FROM {_DB}.candidate WHERE full_name = :n LIMIT 1"),
            {"n": name}).mappings().first()
    if not row:
        return None
    profile = {
        "name":               row["full_name"],
        "title":              row["title"],
        "experience_years":   row["experience_years"],
        "location":           row["location"],
        "languages":          row["languages"],
        "skills":             _load(row["skills"]) or [],
        "salary_expectation": row["salary_expectation"],
        "availability":       row["availability"],
        "summary":            row["summary"],
        # LinkedIn-enrichment fields (null for CV/manual candidates)
        "headline":           row["headline"],
        "experiences":        _load(row["experiences"]) or [],
        "education":          _load(row["education"]) or [],
        "certifications":     _load(row["certifications"]) or [],
        # AI-analysed fields (gpt-5.4) — null for CV/manual candidates
        "seniority":            row["seniority"],
        "years_experience":     row["years_experience"],
        "current_company":      row["current_company"],
        "industry":             row["industry"],
        "role_category":        row["role_category"],
        "education_level":      row["education_level"],
        "management_experience": row["management_experience"],
        "ai_summary":           row["ai_summary"],
        "top_skills":           _load(row["top_skills"]) or [],
        "specializations":      _load(row["specializations"]) or [],
        "strengths":            _load(row["strengths"]) or [],
        "estimated_salary_min": row["estimated_salary_min"],
        "estimated_salary_max": row["estimated_salary_max"],
        "ai_model":             row["ai_model"],
        "enriched_at":          str(row["enriched_at"]) if row["enriched_at"] else None,
    }
    if row["email"]:
        profile["email"] = row["email"]
    if row["phone"]:
        profile["phone"] = row["phone"]
    if row["linkedin"]:
        profile["linkedin"] = row["linkedin"]
    if row["profile_pic_url"]:
        profile["profile_pic_url"] = row["profile_pic_url"]
    if row["public_identifier"]:
        profile["public_identifier"] = row["public_identifier"]
    if row["follower_count"] is not None:
        profile["follower_count"] = int(row["follower_count"])
    # "Has a profile" means we captured real content, not just a bare name row.
    has_content = any(profile.get(k) for k in
                      ("title", "summary", "ai_summary", "languages",
                       "salary_expectation", "headline", "seniority")) \
        or bool(profile["skills"]) or bool(profile["experiences"])
    return profile if has_content else None


# ══════════════════════════════════════════════════════════════════════════════
#  Saved jobs
# ══════════════════════════════════════════════════════════════════════════════
def _row_to_job(m) -> dict:
    """Rebuild the saved-job dict the way tabs/saved.py used to hold it in memory:
    the full job snapshot plus pipeline fields, with candidate_name re-attached."""
    job = _load(m["job_snapshot"]) or {}
    job["candidate_name"]  = m["full_name"]
    job["pipeline_status"] = m["pipeline_status"]
    job["notes"]           = m["notes"] or ""
    job["extras"]          = _load(m["extras"]) or {}
    if m["score"] is not None:
        job["score"] = float(m["score"])
    if m["grade"]:
        job["grade"] = m["grade"]
    job["job_id"] = m["job_id"]
    return job


def _select_saved(where: str = "", params: dict | None = None) -> list[dict]:
    sql = (f"SELECT s.job_id, s.job_snapshot, s.score, s.grade, s.pipeline_status, "
           f"s.notes, s.extras, c.full_name "
           f"FROM {_DB}.candidate_saved_job s "
           f"JOIN {_DB}.candidate c ON c.candidate_id = s.candidate_id "
           f"{where} ORDER BY s.saved_at ASC")
    with get_engine().connect() as conn:
        rows = conn.execute(text(sql), params or {}).mappings().all()
    return [_row_to_job(m) for m in rows]


def list_saved_jobs() -> list[dict]:
    """All saved jobs across all candidates (the old `_saved_jobs` list)."""
    return _select_saved()


def candidates_index() -> dict[str, list[dict]]:
    """Group saved jobs by candidate_name (the old _candidates_index())."""
    by_cand: dict[str, list[dict]] = {}
    for j in list_saved_jobs():
        by_cand.setdefault(j.get("candidate_name") or _UNASSIGNED, []).append(j)
    return by_cand


def list_candidates_detailed() -> list[dict]:
    """Per-candidate summary rows for the table view, straight from the DB.

    Joins the candidate row with aggregates over its saved jobs so the table can
    show who created each candidate and when, without rebuilding insights.
    """
    sql = f"""
        SELECT c.candidate_id, c.full_name, c.title, c.summary, c.status,
               c.email, c.phone, c.linkedin, c.location, c.languages, c.skills,
               c.experience_years, c.salary_expectation, c.availability,
               c.source, c.is_template, c.created_by, c.created_at,
               c.seniority, c.years_experience, c.industry, c.role_category,
               c.education_level, c.ai_summary, c.top_skills,
               c.estimated_salary_min, c.estimated_salary_max,
               COUNT(s.id)                                   AS matches,
               SUM(CASE WHEN s.grade = 'A' THEN 1 ELSE 0 END) AS grade_a,
               MAX(s.saved_at)                               AS last_saved
        FROM {_DB}.candidate c
        LEFT JOIN {_DB}.candidate_saved_job s ON s.candidate_id = c.candidate_id
        GROUP BY c.candidate_id
        ORDER BY matches DESC, c.created_at DESC
    """
    with get_engine().connect() as conn:
        rows = conn.execute(text(sql)).mappings().all()
    out = []
    for r in rows:
        name = r["full_name"]
        # Prefer the AI-ranked top skills for the table cell, else the raw skills.
        skills = _load(r["top_skills"]) or _load(r["skills"]) or []
        has_profile = bool(r["title"] or r["summary"] or r["ai_summary"] or r["languages"]
                           or r["salary_expectation"] or r["seniority"] or skills)
        lo, hi = r["estimated_salary_min"], r["estimated_salary_max"]
        est_salary = f"€{int(lo):,}–{int(hi):,}/mo" if lo and hi else ""
        out.append({
            "name":         name,
            "initials":     "".join(p[0] for p in name.split()[:2]).upper() or "?",
            "status":       r["status"] or "New",
            "title":        r["title"] or "",
            "summary":      r["summary"] or "",
            "email":        r["email"] or "",
            "phone":        r["phone"] or "",
            "linkedin":     r["linkedin"] or "",
            "location":     r["location"] or "",
            "languages":    r["languages"] or "",
            "skills":       ", ".join(str(s) for s in skills),
            "experience":   (f"{r['years_experience']} years" if r["years_experience"]
                             else (r["experience_years"] or "")),
            "salary":       r["salary_expectation"] or "",
            "availability": r["availability"] or "",
            "source":       r["source"] or "",
            # AI-analysed fields (LinkedIn imports)
            "seniority":      r["seniority"] or "",
            "industry":       r["industry"] or "",
            "roleCategory":   r["role_category"] or "",
            "educationLevel": r["education_level"] or "",
            "estSalary":      est_salary,
            "aiSummary":      r["ai_summary"] or "",
            "isTemplate":   bool(r["is_template"]),
            "matches":      int(r["matches"] or 0),
            "gradeA":       int(r["grade_a"] or 0),
            "createdBy":    r["created_by"] or "",
            "createdAt":    str(r["created_at"]) if r["created_at"] else "",
            "lastSaved":    str(r["last_saved"]) if r["last_saved"] else "",
            "hasProfile":   has_profile,
        })
    return out


# Candidate fields the UI may edit directly: pipeline status, contacts, and the
# parsed-profile columns a recruiter might tweak. `skills` is JSON, handled below.
_EDITABLE_FIELDS = ("status", "email", "phone", "linkedin", "title",
                    "experience_years", "location", "languages",
                    "salary_expectation", "availability", "summary")


def update_candidate(name: str, fields: dict, actor: str | None = None) -> bool:
    """Update editable candidate fields (status / contacts / profile). Returns True
    if a row changed. `skills` accepts a list or a comma-separated string."""
    name = (name or "").strip()
    cols = {k: fields[k] for k in _EDITABLE_FIELDS if k in fields}
    if "skills" in fields:
        sk = fields["skills"]
        if isinstance(sk, str):
            sk = [s.strip() for s in sk.split(",") if s.strip()]
        cols["skills"] = _dump(sk)
    if not cols:
        return False
    sets = ", ".join(f"{k} = :{k}" for k in cols)
    cols["n"] = name
    with get_engine().begin() as conn:
        row = conn.execute(
            text(f"SELECT candidate_id FROM {_DB}.candidate WHERE full_name = :n LIMIT 1"),
            {"n": name}).first()
        if not row:
            return False
        conn.execute(text(f"UPDATE {_DB}.candidate SET {sets} WHERE full_name = :n"), cols)
        changed = ", ".join(k for k in cols if k != "n")
        _audit(conn, "update_candidate", int(row[0]), changed, actor)
    return True


def add_saved_job(job: dict, status: str = "New", extras: dict | None = None,
                  profile: dict | None = None, actor: str | None = None) -> bool:
    """Save a job for a candidate. Returns False if it was already saved.

    The whole `job` dict is stored as a point-in-time snapshot; score/grade are
    also pulled into typed columns. A candidate row is created on first save.
    """
    name   = job.get("candidate_name") or (profile or {}).get("name") or _UNASSIGNED
    job_id = str(job.get("job_id") or "").strip()
    if not job_id:
        raise ValueError("job_id required")

    cid = get_or_create_candidate(name, profile, created_by=actor)
    score = job.get("score")
    try:
        score = float(score) if score not in (None, "") else None
    except (TypeError, ValueError):
        score = None
    grade = (job.get("grade") or "").strip().upper()[:1] or None

    with get_engine().begin() as conn:
        exists = conn.execute(
            text(f"SELECT 1 FROM {_DB}.candidate_saved_job "
                 f"WHERE candidate_id = :cid AND job_id = :jid LIMIT 1"),
            {"cid": cid, "jid": job_id}).first()
        if exists:
            return False
        conn.execute(text(
            f"INSERT INTO {_DB}.candidate_saved_job "
            f"(candidate_id, job_id, job_snapshot, score, grade, pipeline_status, notes, extras) "
            f"VALUES (:cid, :jid, :snap, :score, :grade, :status, '', :extras)"),
            {"cid": cid, "jid": job_id, "snap": _dump(job), "score": score,
             "grade": grade, "status": status, "extras": _dump(extras or {})})
        _audit(conn, "save_job", cid, f"job_id={job_id}", actor)
    return True


def update_saved_job(job_id: str, fields: dict, actor: str | None = None) -> dict | None:
    """Patch pipeline_status / notes / extras on a saved job. Returns the job, or None."""
    job_id = str(job_id or "").strip()
    sets, params = [], {"jid": job_id}
    if "pipeline_status" in fields:
        sets.append("pipeline_status = :status"); params["status"] = fields["pipeline_status"]
    if "notes" in fields:
        sets.append("notes = :notes"); params["notes"] = fields["notes"]

    with get_engine().begin() as conn:
        row = conn.execute(
            text(f"SELECT candidate_id, extras FROM {_DB}.candidate_saved_job "
                 f"WHERE job_id = :jid LIMIT 1"), {"jid": job_id}).mappings().first()
        if not row:
            return None
        # extras is merged, not replaced (matches the old PATCH behaviour).
        if "extras" in fields:
            merged = {**(_load(row["extras"]) or {}), **(fields["extras"] or {})}
            sets.append("extras = :extras"); params["extras"] = _dump(merged)
        if sets:
            conn.execute(text(f"UPDATE {_DB}.candidate_saved_job SET {', '.join(sets)} "
                              f"WHERE job_id = :jid"), params)
            _audit(conn, "update_job", int(row["candidate_id"]), f"job_id={job_id}", actor)

    found = _select_saved("WHERE s.job_id = :jid", {"jid": job_id})
    return found[0] if found else None


def delete_saved_job(job_id: str, actor: str | None = None) -> int:
    """Remove one saved job. Returns the number of rows removed (0 or 1)."""
    job_id = str(job_id or "").strip()
    with get_engine().begin() as conn:
        row = conn.execute(
            text(f"SELECT candidate_id FROM {_DB}.candidate_saved_job WHERE job_id = :jid LIMIT 1"),
            {"jid": job_id}).first()
        res = conn.execute(
            text(f"DELETE FROM {_DB}.candidate_saved_job WHERE job_id = :jid"), {"jid": job_id})
        if row:
            _audit(conn, "delete_job", int(row[0]), f"job_id={job_id}", actor)
        return res.rowcount or 0


def delete_candidate(name: str, actor: str | None = None) -> bool:
    """GDPR erasure: delete a candidate (saved jobs cascade). Returns True if removed."""
    name = (name or "").strip()
    with get_engine().begin() as conn:
        row = conn.execute(
            text(f"SELECT candidate_id FROM {_DB}.candidate WHERE full_name = :n LIMIT 1"),
            {"n": name}).first()
        if not row:
            return False
        cid = int(row[0])
        conn.execute(text(f"DELETE FROM {_DB}.candidate WHERE candidate_id = :cid"), {"cid": cid})
        # candidate_id kept in the audit detail (no FK) so the trail survives.
        _audit(conn, "erase_candidate", None, f"candidate_id={cid} name={name}", actor)
        return True


# ══════════════════════════════════════════════════════════════════════════════
#  Companies (employers from candidates' work history) — NOT personal data
#  `company` is a deduped employer catalogue; `candidate_company` links each
#  company to the candidate(s) who worked there (with role title + dates). The
#  link is personal data, so it cascades on candidate erasure; the company stays.
# ══════════════════════════════════════════════════════════════════════════════
def _get_or_create_company(conn, name: str, linkedin_url: str | None,
                           meta: dict | None = None, created_by: str | None = None) -> int:
    """Resolve an employer to a company_id (dedup by LinkedIn URL, else by name),
    creating it if needed and filling in any newly-known metadata."""
    name = (name or "").strip()
    url  = (linkedin_url or "").strip() or None
    meta = meta or {}
    if url:
        row = conn.execute(text(
            f"SELECT company_id FROM {_DB}.company WHERE linkedin_url = :u LIMIT 1"),
            {"u": url}).first()
    else:
        row = conn.execute(text(
            f"SELECT company_id FROM {_DB}.company "
            f"WHERE linkedin_url IS NULL AND name = :n LIMIT 1"), {"n": name}).first()

    extra = {k: meta[k] for k in ("industry", "company_size", "website") if meta.get(k)}
    if row:
        cid = int(row[0])
        if extra:   # backfill metadata we didn't have before
            assign = ", ".join(f"{k} = :{k}" for k in extra)
            conn.execute(text(f"UPDATE {_DB}.company SET {assign} WHERE company_id = :id"),
                         {**extra, "id": cid})
        return cid

    cols = {"name": name, "linkedin_url": url, **extra}
    if created_by:
        cols["created_by"] = created_by
    keys = ", ".join(cols)
    vals = ", ".join(f":{k}" for k in cols)
    res = conn.execute(text(f"INSERT INTO {_DB}.company ({keys}) VALUES ({vals})"), cols)
    return int(res.lastrowid)


def save_companies(candidate_id: int, companies: list[dict],
                   created_by: str | None = None) -> int:
    """Persist a candidate's employers into `company` + link them via
    `candidate_company`. Each company dict: {name, linkedin_url?, title?,
    starts_at?, ends_at?, industry?, size?/company_size?, website?}. Skips links
    that already exist (same candidate+company+title). Returns links added."""
    saved = 0
    with get_engine().begin() as conn:
        for c in companies or []:
            name = (c.get("name") or "").strip()
            if not name:
                continue
            comp_id = _get_or_create_company(conn, name, c.get("linkedin_url"), {
                "industry":     c.get("industry"),
                "company_size": c.get("size") or c.get("company_size"),
                "website":      c.get("website"),
            }, created_by=created_by)
            title = (c.get("title") or "").strip() or None
            exists = conn.execute(text(
                f"SELECT 1 FROM {_DB}.candidate_company "
                f"WHERE candidate_id = :cid AND company_id = :co "
                f"AND IFNULL(title, '') = IFNULL(:t, '') LIMIT 1"),
                {"cid": candidate_id, "co": comp_id, "t": title}).first()
            if exists:
                continue
            conn.execute(text(
                f"INSERT INTO {_DB}.candidate_company "
                f"(candidate_id, company_id, title, starts_at, ends_at) "
                f"VALUES (:cid, :co, :t, :s, :e)"),
                {"cid": candidate_id, "co": comp_id, "t": title,
                 "s": c.get("starts_at"), "e": c.get("ends_at")})
            saved += 1
        _audit(conn, "save_companies", candidate_id, f"{saved} companies", created_by)
    return saved


def list_companies() -> list[dict]:
    """All saved employers with how many of our candidates worked at each."""
    sql = (f"SELECT co.company_id, co.name, co.linkedin_url, co.industry, "
           f"       co.company_size, co.website, "
           f"       COUNT(DISTINCT cc.candidate_id) AS people "
           f"FROM {_DB}.company co "
           f"LEFT JOIN {_DB}.candidate_company cc ON cc.company_id = co.company_id "
           f"GROUP BY co.company_id ORDER BY people DESC, co.name")
    with get_engine().connect() as conn:
        rows = conn.execute(text(sql)).mappings().all()
    return [{"id": m["company_id"], "name": m["name"], "linkedin": m["linkedin_url"],
             "industry": m["industry"], "size": m["company_size"], "website": m["website"],
             "people": int(m["people"] or 0)} for m in rows]


# ══════════════════════════════════════════════════════════════════════════════
#  Target candidates (guided builder) — NOT personal data
# ══════════════════════════════════════════════════════════════════════════════
def save_target(draft: dict, label: str | None = None, created_by: str | None = None) -> int:
    """Persist a guided-builder draft spec. Returns its id."""
    label = label or (draft or {}).get("name")
    with get_engine().begin() as conn:
        res = conn.execute(text(
            f"INSERT INTO {_DB}.target_candidate (label, draft, created_by) "
            f"VALUES (:label, :draft, :by)"),
            {"label": label, "draft": _dump(draft or {}), "by": created_by})
        return int(res.lastrowid)


def list_targets() -> list[dict]:
    """List saved guided-builder specs."""
    with get_engine().connect() as conn:
        rows = conn.execute(text(
            f"SELECT id, label, draft, created_by, created_at "
            f"FROM {_DB}.target_candidate ORDER BY created_at DESC")).mappings().all()
    return [{"id": m["id"], "label": m["label"], "draft": _load(m["draft"]) or {},
             "created_by": m["created_by"], "created_at": str(m["created_at"])} for m in rows]


# ══════════════════════════════════════════════════════════════════════════════
#  Audit log
# ══════════════════════════════════════════════════════════════════════════════
def _audit(conn, action: str, candidate_id: int | None, detail: str = "",
           actor: str | None = None) -> None:
    """Write one audit row on the SAME transaction as the change it records."""
    conn.execute(text(
        f"INSERT INTO {_DB}.audit_log (actor, action, candidate_id, detail) "
        f"VALUES (:actor, :action, :cid, :detail)"),
        {"actor": actor, "action": action, "cid": candidate_id, "detail": detail})


def log_access(action: str, name: str | None = None, detail: str = "",
               actor: str | None = None) -> None:
    """Standalone audit entry (e.g. viewing insights / exporting a report)."""
    cid = None
    if name:
        with get_engine().connect() as conn:
            row = conn.execute(
                text(f"SELECT candidate_id FROM {_DB}.candidate WHERE full_name = :n LIMIT 1"),
                {"n": name}).first()
            cid = int(row[0]) if row else None
    with get_engine().begin() as conn:
        _audit(conn, action, cid, detail, actor)
