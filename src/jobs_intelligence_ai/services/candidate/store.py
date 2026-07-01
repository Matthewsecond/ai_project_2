"""
store.py — MySQL persistence for the saved-candidate pipeline (reworked schema).

Backs the Saved-Jobs / Build-a-Candidate features with the reworked app tables in the
`Jobs_Intelligence_AI` schema (`config.APP_SCHEMA`):

    saved_candidates  — one row per candidate (identity + parsed profile). App-owned:
                        every row carries account_company_id (the firm = privacy boundary),
                        owner_id (the employee who created it) and country ('at'/'sk').
    saved_jobs        — one row per job shortlisted FOR a candidate (point-in-time JSON
                        snapshot + sales-pipeline status). Also owner/company/country.
    target_candidate  — guided-builder specs (NOT personal data).
    audit_log         — who viewed / edited / exported / deleted what.

Country is a column (config.COUNTRY), replacing the old sk_ table prefix. Ownership +
visibility (own/all, scoped to the account_company) gate who can see whose rows.

Ownership params (account_company_id / owner_id / visibility) are optional and default
safely (first company / its first user / 'all'), so callers can be threaded gradually
without breaking; the blueprints pass the real session values.

The public API is keyed by candidate NAME to match the existing routes/front-end;
internally we resolve each name to its surrogate id (get-or-create), scoped to the
caller's company + country.
"""
import json as _json
import logging
import re

from sqlalchemy import text

from jobs_intelligence_ai import config
from jobs_intelligence_ai.infra.database import get_engine

logger = logging.getLogger(__name__)

_DB      = config.APP_SCHEMA
_COUNTRY = config.COUNTRY            # 'at' | 'sk' — column value, not a table prefix

_T_CANDIDATE = f"{_DB}.saved_candidates"
_T_SAVED     = f"{_DB}.saved_jobs"
_T_TARGET    = f"{_DB}.target_candidate"
_T_AUDIT     = f"{_DB}.audit_log"

# Profile columns on saved_candidates filled by the CV parser / LinkedIn import.
_PROFILE_SCALARS = ("title", "experience_years", "location",
                    "languages", "salary_expectation", "availability", "summary",
                    "headline", "profile_pic_url", "public_identifier",
                    "seniority", "current_company", "industry", "role_category",
                    "education_level", "management_experience", "ai_summary",
                    "ai_model", "enriched_at")
_PROFILE_INTS = ("follower_count", "years_experience",
                 "estimated_salary_min", "estimated_salary_max")
_PROFILE_JSON = ("skills", "experiences", "education", "certifications",
                 "top_skills", "specializations", "strengths", "raw_profile")

_UNASSIGNED = "Unassigned"


# ── JSON helpers ──────────────────────────────────────────────────────────────
def _dump(v) -> str | None:
    if v is None:
        return None
    return _json.dumps(v, ensure_ascii=False, default=str)


def _load(v):
    if v is None or v == "":
        return None
    if isinstance(v, (list, dict)):
        return v
    try:
        return _json.loads(v)
    except (ValueError, TypeError):
        return None


# ── Ownership defaults ──────────────────────────────────────────────────────────
def _company_id(conn, account_company_id: int | None) -> int:
    """The caller's company, or the first one (single-tenant fallback)."""
    if account_company_id:
        return int(account_company_id)
    cid = conn.execute(text(
        f"SELECT id FROM {_DB}.account_company ORDER BY id LIMIT 1")).scalar()
    return int(cid) if cid else 1


def _owner_id(conn, owner_id: int | None, company_id: int) -> int:
    """The caller (owner), or the company's first user (fallback)."""
    if owner_id:
        return int(owner_id)
    oid = conn.execute(text(
        f"SELECT id FROM {_DB}.app_user WHERE account_company_id = :c ORDER BY id LIMIT 1"),
        {"c": company_id}).scalar()
    if oid is None:
        oid = conn.execute(text(f"SELECT id FROM {_DB}.app_user ORDER BY id LIMIT 1")).scalar()
    return int(oid) if oid else 1


# ══════════════════════════════════════════════════════════════════════════════
#  Candidates (identity + parsed profile)
# ══════════════════════════════════════════════════════════════════════════════
def get_or_create_candidate(name: str, profile: dict | None = None,
                            created_by: str | None = None,
                            account_company_id: int | None = None,
                            owner_id: int | None = None) -> int:
    """Resolve a candidate NAME (within the caller's company + country) to its id,
    creating the row if needed. `profile` is merged in when supplied."""
    name = (name or "").strip() or _UNASSIGNED
    with get_engine().begin() as conn:
        cid_company = _company_id(conn, account_company_id)
        row = conn.execute(text(
            f"SELECT id FROM {_T_CANDIDATE} "
            f"WHERE full_name = :n AND account_company_id = :co AND country = :ct LIMIT 1"),
            {"n": name, "co": cid_company, "ct": _COUNTRY}).first()
        if row:
            cid = int(row[0])
            if profile:
                _apply_profile(conn, cid, profile)
            return cid

        cols = {"full_name": name, "account_company_id": cid_company,
                "owner_id": _owner_id(conn, owner_id, cid_company), "country": _COUNTRY}
        if profile:
            cols.update(_profile_columns(profile))
        keys = ", ".join(cols)
        vals = ", ".join(f":{k}" for k in cols)
        res = conn.execute(text(f"INSERT INTO {_T_CANDIDATE} ({keys}) VALUES ({vals})"), cols)
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
    cols = _profile_columns(profile)
    if not cols:
        return
    sets = ", ".join(f"{k} = :{k}" for k in cols)
    cols["cid"] = candidate_id
    conn.execute(text(f"UPDATE {_T_CANDIDATE} SET {sets} WHERE id = :cid"), cols)


def upsert_profile(name: str, profile: dict, created_by: str | None = None,
                   account_company_id: int | None = None,
                   owner_id: int | None = None) -> int:
    """Create-or-update a candidate's parsed profile. Returns the candidate id."""
    return get_or_create_candidate(name, profile, created_by=created_by,
                                   account_company_id=account_company_id, owner_id=owner_id)


def _scope(account_company_id: int | None) -> tuple[str, dict]:
    """A WHERE fragment + params restricting candidate rows to the caller's
    company + country. Used by the name-keyed lookups."""
    return ("account_company_id = :co AND country = :ct",
            {"co": account_company_id, "ct": _COUNTRY})


def lookup_candidate(name: str, account_company_id: int | None = None) -> dict | None:
    """Existence check for a candidate NAME → identity + pipeline status, or None."""
    name = (name or "").strip()
    if not name:
        return None
    with get_engine().connect() as conn:
        co = _company_id(conn, account_company_id)
        row = conn.execute(text(
            f"SELECT c.full_name, c.status, c.is_template, "
            f"  COALESCE(NULLIF(u.display_name, ''), u.username) AS owner_name, "
            f"  (SELECT COUNT(*) FROM {_T_SAVED} s WHERE s.saved_candidate_id = c.id) AS matches "
            f"FROM {_T_CANDIDATE} c "
            f"LEFT JOIN {_DB}.app_user u ON u.id = c.owner_id "
            f"WHERE c.full_name = :n AND c.account_company_id = :co AND c.country = :ct LIMIT 1"),
            {"n": name, "co": co, "ct": _COUNTRY}).mappings().first()
    if not row:
        return None
    return {"name": row["full_name"], "status": row["status"] or "New",
            "isTemplate": bool(row["is_template"]), "matches": int(row["matches"] or 0),
            "owner": row["owner_name"] or ""}


def _linkedin_slug(url: str) -> str:
    m = re.search(r"/in/([^/?#]+)", (url or "").lower())
    return m.group(1).strip() if m else ""


def lookup_by_linkedin(url: str, account_company_id: int | None = None) -> dict | None:
    """Find a saved candidate by their LinkedIn URL (matched on the /in/ handle)."""
    slug = _linkedin_slug(url)
    if not slug:
        return None
    with get_engine().connect() as conn:
        co = _company_id(conn, account_company_id)
        row = conn.execute(text(
            f"SELECT c.full_name, c.status, c.is_template, c.linkedin, "
            f"  (SELECT COUNT(*) FROM {_T_SAVED} s WHERE s.saved_candidate_id = c.id) AS matches "
            f"FROM {_T_CANDIDATE} c "
            f"WHERE c.account_company_id = :co AND c.country = :ct "
            f"  AND c.linkedin IS NOT NULL AND LOWER(c.linkedin) LIKE :pat "
            f"ORDER BY c.id DESC LIMIT 1"),
            {"co": co, "ct": _COUNTRY, "pat": f"%/in/{slug}%"}).mappings().first()
    if not row:
        return None
    return {"name": row["full_name"], "status": row["status"] or "New",
            "isTemplate": bool(row["is_template"]), "matches": int(row["matches"] or 0),
            "linkedin": row["linkedin"]}


def get_candidate_bundle(name: str, account_company_id: int | None = None,
                         owner_id: int | None = None, visibility: str = "all") -> dict:
    """Profile + saved jobs for a candidate NAME. {profile, jobs}."""
    name = (name or "").strip()
    return {
        "profile": get_profile(name, account_company_id=account_company_id),
        "jobs": _select_saved("c.full_name = :n", {"n": name},
                              account_company_id=account_company_id,
                              owner_id=owner_id, visibility=visibility),
    }


def get_profile(name: str, account_company_id: int | None = None) -> dict | None:
    """Reconstruct the parsed-profile dict for a candidate, or None if no profile."""
    name = (name or "").strip()
    with get_engine().connect() as conn:
        co = _company_id(conn, account_company_id)
        row = conn.execute(text(
            f"SELECT full_name, email, phone, linkedin, title, experience_years, location, "
            f"languages, skills, salary_expectation, availability, summary, "
            f"headline, profile_pic_url, public_identifier, follower_count, "
            f"experiences, education, certifications, "
            f"seniority, years_experience, current_company, industry, role_category, "
            f"education_level, management_experience, ai_summary, ai_model, enriched_at, "
            f"top_skills, specializations, strengths, "
            f"estimated_salary_min, estimated_salary_max "
            f"FROM {_T_CANDIDATE} "
            f"WHERE full_name = :n AND account_company_id = :co AND country = :ct LIMIT 1"),
            {"n": name, "co": co, "ct": _COUNTRY}).mappings().first()
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
        "headline":           row["headline"],
        "experiences":        _load(row["experiences"]) or [],
        "education":          _load(row["education"]) or [],
        "certifications":     _load(row["certifications"]) or [],
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
    has_content = any(profile.get(k) for k in
                      ("title", "summary", "ai_summary", "languages",
                       "salary_expectation", "headline", "seniority")) \
        or bool(profile["skills"]) or bool(profile["experiences"])
    return profile if has_content else None


# ══════════════════════════════════════════════════════════════════════════════
#  Saved jobs
# ══════════════════════════════════════════════════════════════════════════════
def _row_to_job(m) -> dict:
    """Rebuild the saved-job dict: the full snapshot + pipeline fields + candidate_name.
    Keeps the `pipeline_status` key the front-end expects (mapped from the `status` column)."""
    job = _load(m["job_snapshot"]) or {}
    job["candidate_name"]  = m["full_name"]
    job["pipeline_status"] = m["status"]
    job["notes"]           = m["notes"] or ""
    job["extras"]          = _load(m["extras"]) or {}
    if m["score"] is not None:
        job["score"] = float(m["score"])
    if m["grade"]:
        job["grade"] = m["grade"]
    job["job_id"] = str(m["job_id"])
    return job


def _vis_clause(owner_id: int | None, visibility: str) -> tuple[str, dict]:
    """Visibility filter within the company: 'own' → only the viewer's rows; 'all' → none."""
    if (visibility or "all") == "own" and owner_id:
        return " AND c.owner_id = :viewer", {"viewer": int(owner_id)}
    return "", {}


def _select_saved(where: str = "", params: dict | None = None,
                  account_company_id: int | None = None,
                  owner_id: int | None = None, visibility: str = "all") -> list[dict]:
    params = dict(params or {})
    with get_engine().connect() as conn:
        co = _company_id(conn, account_company_id)
        vclause, vparams = _vis_clause(owner_id, visibility)
        params.update({"co": co, "ct": _COUNTRY, **vparams})
        cond = "c.account_company_id = :co AND c.country = :ct" + vclause
        if where:
            cond += f" AND ({where})"
        sql = (f"SELECT s.job_id, s.job_snapshot, s.score, s.grade, s.status, "
               f"s.notes, s.extras, c.full_name "
               f"FROM {_T_SAVED} s "
               f"JOIN {_T_CANDIDATE} c ON c.id = s.saved_candidate_id "
               f"WHERE {cond} ORDER BY s.saved_at ASC")
        rows = conn.execute(text(sql), params).mappings().all()
    return [_row_to_job(m) for m in rows]


def list_saved_jobs(account_company_id: int | None = None,
                    owner_id: int | None = None, visibility: str = "all") -> list[dict]:
    """All saved jobs visible to the caller (company-scoped; own/all)."""
    return _select_saved(account_company_id=account_company_id,
                         owner_id=owner_id, visibility=visibility)


def candidates_index(account_company_id: int | None = None,
                     owner_id: int | None = None, visibility: str = "all") -> dict[str, list[dict]]:
    """Group visible saved jobs by candidate_name."""
    by_cand: dict[str, list[dict]] = {}
    for j in list_saved_jobs(account_company_id, owner_id, visibility):
        by_cand.setdefault(j.get("candidate_name") or _UNASSIGNED, []).append(j)
    return by_cand


def list_candidates_detailed(account_company_id: int | None = None,
                             owner_id: int | None = None, visibility: str = "all") -> list[dict]:
    """Per-candidate summary rows for the table view (company-scoped; own/all)."""
    with get_engine().connect() as conn:
        co = _company_id(conn, account_company_id)
        vclause, vparams = _vis_clause(owner_id, visibility)
        sql = f"""
            SELECT c.id, c.full_name, c.title, c.summary, c.status,
                   c.email, c.phone, c.linkedin, c.location, c.languages, c.skills,
                   c.experience_years, c.salary_expectation, c.availability,
                   c.source, c.is_template, c.owner_id, c.created_at,
                   c.seniority, c.years_experience, c.industry, c.role_category,
                   c.education_level, c.ai_summary, c.top_skills,
                   c.estimated_salary_min, c.estimated_salary_max,
                   COUNT(s.id)                                    AS matches,
                   SUM(CASE WHEN s.grade = 'A' THEN 1 ELSE 0 END) AS grade_a,
                   MAX(s.saved_at)                                AS last_saved
            FROM {_T_CANDIDATE} c
            LEFT JOIN {_T_SAVED} s ON s.saved_candidate_id = c.id
            WHERE c.account_company_id = :co AND c.country = :ct {vclause}
            GROUP BY c.id
            ORDER BY matches DESC, c.created_at DESC
        """
        rows = conn.execute(text(sql), {"co": co, "ct": _COUNTRY, **vparams}).mappings().all()
    out = []
    for r in rows:
        name = r["full_name"]
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
            "seniority":      r["seniority"] or "",
            "industry":       r["industry"] or "",
            "roleCategory":   r["role_category"] or "",
            "educationLevel": r["education_level"] or "",
            "estSalary":      est_salary,
            "aiSummary":      r["ai_summary"] or "",
            "isTemplate":   bool(r["is_template"]),
            "matches":      int(r["matches"] or 0),
            "gradeA":       int(r["grade_a"] or 0),
            "createdBy":    "",
            "ownerId":      int(r["owner_id"]) if r["owner_id"] is not None else None,
            "createdAt":    str(r["created_at"]) if r["created_at"] else "",
            "lastSaved":    str(r["last_saved"]) if r["last_saved"] else "",
            "hasProfile":   has_profile,
        })
    return out


_EDITABLE_FIELDS = ("status", "email", "phone", "linkedin", "title",
                    "experience_years", "location", "languages",
                    "salary_expectation", "availability", "summary")


def update_candidate(name: str, fields: dict, actor: str | None = None,
                     account_company_id: int | None = None,
                     user_id: int | None = None) -> bool:
    """Update editable candidate fields (status / contacts / profile)."""
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
    with get_engine().begin() as conn:
        co = _company_id(conn, account_company_id)
        row = conn.execute(text(
            f"SELECT id FROM {_T_CANDIDATE} "
            f"WHERE full_name = :n AND account_company_id = :co AND country = :ct LIMIT 1"),
            {"n": name, "co": co, "ct": _COUNTRY}).first()
        if not row:
            return False
        cols["cid"] = int(row[0])
        conn.execute(text(f"UPDATE {_T_CANDIDATE} SET {sets} WHERE id = :cid"), cols)
        _audit(conn, "update_candidate", "saved_candidate", int(row[0]),
               ", ".join(k for k in cols if k != "cid"), user_id, co)
    return True


def add_saved_job(job: dict, status: str = "new", extras: dict | None = None,
                  profile: dict | None = None, actor: str | None = None,
                  account_company_id: int | None = None,
                  owner_id: int | None = None) -> bool:
    """Save a job for a candidate. Returns False if it was already saved for them."""
    name   = job.get("candidate_name") or (profile or {}).get("name") or _UNASSIGNED
    job_id = str(job.get("job_id") or "").strip()
    if not job_id:
        raise ValueError("job_id required")

    cid = get_or_create_candidate(name, profile, created_by=actor,
                                  account_company_id=account_company_id, owner_id=owner_id)
    score = job.get("score")
    try:
        score = float(score) if score not in (None, "") else None
    except (TypeError, ValueError):
        score = None
    grade = (job.get("grade") or "").strip().upper()[:1] or None

    with get_engine().begin() as conn:
        co  = _company_id(conn, account_company_id)
        oid = _owner_id(conn, owner_id, co)
        exists = conn.execute(text(
            f"SELECT 1 FROM {_T_SAVED} WHERE saved_candidate_id = :cid AND country = :ct "
            f"AND job_id = :jid LIMIT 1"),
            {"cid": cid, "ct": _COUNTRY, "jid": job_id}).first()
        if exists:
            return False
        conn.execute(text(
            f"INSERT INTO {_T_SAVED} "
            f"(account_company_id, owner_id, saved_candidate_id, country, job_id, "
            f" job_snapshot, score, grade, status, notes, extras) "
            f"VALUES (:co, :oid, :cid, :ct, :jid, :snap, :score, :grade, :status, '', :extras)"),
            {"co": co, "oid": oid, "cid": cid, "ct": _COUNTRY, "jid": job_id,
             "snap": _dump(job), "score": score, "grade": grade,
             "status": status, "extras": _dump(extras or {})})
        _audit(conn, "save_job", "saved_job", cid, f"job_id={job_id}", oid, co)
    return True


def update_saved_job(job_id: str, fields: dict, actor: str | None = None,
                     account_company_id: int | None = None,
                     user_id: int | None = None) -> dict | None:
    """Patch status / notes / extras on a saved job (company-scoped). Returns the job, or None."""
    job_id = str(job_id or "").strip()
    sets, params = [], {"jid": job_id, "ct": _COUNTRY}
    # The front-end still sends "pipeline_status"; it maps to the `status` column.
    new_status = fields.get("pipeline_status", fields.get("status"))
    if new_status is not None:
        sets.append("status = :status"); params["status"] = new_status
    if "notes" in fields:
        sets.append("notes = :notes"); params["notes"] = fields["notes"]

    with get_engine().begin() as conn:
        co = _company_id(conn, account_company_id)
        params["co"] = co
        row = conn.execute(text(
            f"SELECT saved_candidate_id, extras FROM {_T_SAVED} "
            f"WHERE job_id = :jid AND country = :ct AND account_company_id = :co LIMIT 1"),
            {"jid": job_id, "ct": _COUNTRY, "co": co}).mappings().first()
        if not row:
            return None
        if "extras" in fields:
            merged = {**(_load(row["extras"]) or {}), **(fields["extras"] or {})}
            sets.append("extras = :extras"); params["extras"] = _dump(merged)
        if sets:
            conn.execute(text(
                f"UPDATE {_T_SAVED} SET {', '.join(sets)} "
                f"WHERE job_id = :jid AND country = :ct AND account_company_id = :co"), params)
            _audit(conn, "update_job", "saved_job", int(row["saved_candidate_id"]),
                   f"job_id={job_id}", user_id, co)

    found = _select_saved("s.job_id = :jid", {"jid": job_id},
                          account_company_id=account_company_id)
    return found[0] if found else None


def delete_saved_job(job_id: str, actor: str | None = None,
                     account_company_id: int | None = None,
                     user_id: int | None = None) -> int:
    """Remove one saved job (company-scoped). Returns rows removed (0 or 1)."""
    job_id = str(job_id or "").strip()
    with get_engine().begin() as conn:
        co = _company_id(conn, account_company_id)
        row = conn.execute(text(
            f"SELECT saved_candidate_id FROM {_T_SAVED} "
            f"WHERE job_id = :jid AND country = :ct AND account_company_id = :co LIMIT 1"),
            {"jid": job_id, "ct": _COUNTRY, "co": co}).first()
        res = conn.execute(text(
            f"DELETE FROM {_T_SAVED} "
            f"WHERE job_id = :jid AND country = :ct AND account_company_id = :co"),
            {"jid": job_id, "ct": _COUNTRY, "co": co})
        if row:
            _audit(conn, "delete_job", "saved_job", int(row[0]), f"job_id={job_id}", user_id, co)
        return res.rowcount or 0


def delete_candidate(name: str, actor: str | None = None,
                     account_company_id: int | None = None,
                     user_id: int | None = None) -> bool:
    """GDPR erasure: delete a candidate (saved jobs cascade). Company-scoped."""
    name = (name or "").strip()
    with get_engine().begin() as conn:
        co = _company_id(conn, account_company_id)
        row = conn.execute(text(
            f"SELECT id FROM {_T_CANDIDATE} "
            f"WHERE full_name = :n AND account_company_id = :co AND country = :ct LIMIT 1"),
            {"n": name, "co": co, "ct": _COUNTRY}).first()
        if not row:
            return False
        cid = int(row[0])
        conn.execute(text(f"DELETE FROM {_T_CANDIDATE} WHERE id = :cid"), {"cid": cid})
        _audit(conn, "erase_candidate", "saved_candidate", None,
               f"candidate_id={cid} name={name}", user_id, co)
        return True


# ══════════════════════════════════════════════════════════════════════════════
#  Saved companies / contacts — user-owned bookmarks of market-catalogue rows
#  (the country-DB `companies` / `contacts`). Thin junctions: owner + country +
#  the market row's id + a snapshot (name etc., for display without a cross-DB join).
# ══════════════════════════════════════════════════════════════════════════════
def _add_saved_ref(table: str, id_col: str, ref_id, snapshot, notes: str,
                   account_company_id: int | None, owner_id: int | None,
                   action: str) -> bool:
    try:
        rid = int(ref_id)
    except (TypeError, ValueError):
        raise ValueError(f"{id_col} required")
    with get_engine().begin() as conn:
        co  = _company_id(conn, account_company_id)
        oid = _owner_id(conn, owner_id, co)
        exists = conn.execute(text(
            f"SELECT 1 FROM {_DB}.{table} "
            f"WHERE owner_id = :oid AND country = :ct AND {id_col} = :r LIMIT 1"),
            {"oid": oid, "ct": _COUNTRY, "r": rid}).first()
        if exists:
            return False
        conn.execute(text(
            f"INSERT INTO {_DB}.{table} "
            f"(account_company_id, owner_id, country, {id_col}, snapshot, notes) "
            f"VALUES (:co, :oid, :ct, :r, :snap, :notes)"),
            {"co": co, "oid": oid, "ct": _COUNTRY, "r": rid,
             "snap": _dump(snapshot), "notes": notes or ""})
        _audit(conn, action, table.rstrip("s"), rid, f"{id_col}={rid}", oid, co)
    return True


def _list_saved_refs(table: str, id_col: str, account_company_id: int | None,
                     owner_id: int | None, visibility: str) -> list[dict]:
    with get_engine().connect() as conn:
        co = _company_id(conn, account_company_id)
        where, params = "account_company_id = :co AND country = :ct", {"co": co, "ct": _COUNTRY}
        if (visibility or "all") == "own" and owner_id:
            where += " AND owner_id = :viewer"; params["viewer"] = int(owner_id)
        rows = conn.execute(text(
            f"SELECT id, {id_col}, snapshot, notes, owner_id, saved_at "
            f"FROM {_DB}.{table} WHERE {where} ORDER BY saved_at DESC"), params).mappings().all()
    out = []
    for m in rows:
        snap = _load(m["snapshot"]) or {}
        out.append({"id": int(m["id"]), id_col: int(m[id_col]), "notes": m["notes"] or "",
                    "ownerId": int(m["owner_id"]), "savedAt": str(m["saved_at"]), **snap})
    return out


def _delete_saved_ref(table: str, saved_id, account_company_id: int | None,
                      user_id: int | None, action: str) -> int:
    with get_engine().begin() as conn:
        co = _company_id(conn, account_company_id)
        res = conn.execute(text(
            f"DELETE FROM {_DB}.{table} WHERE id = :id AND account_company_id = :co"),
            {"id": int(saved_id), "co": co})
        if res.rowcount:
            _audit(conn, action, table.rstrip("s"), int(saved_id), "", user_id, co)
        return res.rowcount or 0


def add_saved_company(target_company_id, snapshot: dict | None = None, notes: str = "",
                      account_company_id: int | None = None, owner_id: int | None = None) -> bool:
    """Bookmark a target company (market-catalogue row). False if already saved."""
    return _add_saved_ref("saved_companies", "target_company_id", target_company_id,
                          snapshot, notes, account_company_id, owner_id, "save_company")


def list_saved_companies(account_company_id: int | None = None,
                         owner_id: int | None = None, visibility: str = "all") -> list[dict]:
    return _list_saved_refs("saved_companies", "target_company_id",
                            account_company_id, owner_id, visibility)


def delete_saved_company(saved_id, account_company_id: int | None = None,
                         user_id: int | None = None) -> int:
    return _delete_saved_ref("saved_companies", saved_id, account_company_id,
                             user_id, "delete_company")


def add_saved_contact(contact_id, snapshot: dict | None = None, notes: str = "",
                      account_company_id: int | None = None, owner_id: int | None = None) -> bool:
    """Bookmark a contact (market-catalogue row). False if already saved."""
    return _add_saved_ref("saved_contacts", "contact_id", contact_id,
                          snapshot, notes, account_company_id, owner_id, "save_contact")


def list_saved_contacts(account_company_id: int | None = None,
                        owner_id: int | None = None, visibility: str = "all") -> list[dict]:
    return _list_saved_refs("saved_contacts", "contact_id",
                            account_company_id, owner_id, visibility)


def delete_saved_contact(saved_id, account_company_id: int | None = None,
                         user_id: int | None = None) -> int:
    return _delete_saved_ref("saved_contacts", saved_id, account_company_id,
                             user_id, "delete_contact")


# ══════════════════════════════════════════════════════════════════════════════
#  Target candidates (guided builder) — NOT personal data
# ══════════════════════════════════════════════════════════════════════════════
def save_target(draft: dict, label: str | None = None, created_by: str | None = None) -> int:
    """Persist a guided-builder draft spec. Returns its id."""
    label = label or (draft or {}).get("name")
    with get_engine().begin() as conn:
        res = conn.execute(text(
            f"INSERT INTO {_T_TARGET} (label, draft, created_by) VALUES (:label, :draft, :by)"),
            {"label": label, "draft": _dump(draft or {}), "by": created_by})
        return int(res.lastrowid)


def list_targets() -> list[dict]:
    """List saved guided-builder specs."""
    with get_engine().connect() as conn:
        rows = conn.execute(text(
            f"SELECT id, label, draft, created_by, created_at "
            f"FROM {_T_TARGET} ORDER BY created_at DESC")).mappings().all()
    return [{"id": m["id"], "label": m["label"], "draft": _load(m["draft"]) or {},
             "created_by": m["created_by"], "created_at": str(m["created_at"])} for m in rows]


# ══════════════════════════════════════════════════════════════════════════════
#  Audit log
# ══════════════════════════════════════════════════════════════════════════════
def _audit(conn, action: str, entity_type: str | None, entity_id: int | None,
           detail: str = "", user_id: int | None = None,
           account_company_id: int | None = None) -> None:
    """Write one audit row on the SAME transaction as the change it records."""
    conn.execute(text(
        f"INSERT INTO {_T_AUDIT} "
        f"(account_company_id, user_id, action, entity_type, entity_id, detail) "
        f"VALUES (:co, :uid, :action, :etype, :eid, :detail)"),
        {"co": account_company_id, "uid": user_id, "action": action,
         "etype": entity_type, "eid": entity_id, "detail": detail})


def log_access(action: str, name: str | None = None, detail: str = "",
               actor: str | None = None, account_company_id: int | None = None,
               user_id: int | None = None) -> None:
    """Standalone audit entry (e.g. viewing insights / exporting a report)."""
    with get_engine().begin() as conn:
        co = _company_id(conn, account_company_id)
        cid = None
        if name:
            row = conn.execute(text(
                f"SELECT id FROM {_T_CANDIDATE} "
                f"WHERE full_name = :n AND account_company_id = :co AND country = :ct LIMIT 1"),
                {"n": (name or "").strip(), "co": co, "ct": _COUNTRY}).first()
            cid = int(row[0]) if row else None
        _audit(conn, action, "saved_candidate" if cid else None, cid, detail, user_id, co)
