"""
tabs/saved.py — Saved tab (MySQL-backed, company-scoped pipeline).

Persists to the Jobs_Intelligence_AI schema via services.candidate.store:
saved_candidates + parsed profiles + saved_jobs + saved_companies + saved_contacts
+ audit log. Every call is scoped to the logged-in user's account_company, with
own/all visibility (the collaboration boundary).

Routes:
  GET    /api/saved              → list saved jobs
  POST   /api/saved              → add a job (for a candidate)
  PATCH  /api/saved/<job_id>     → edit status / notes / grade / snapshot fields
  DELETE /api/saved/<job_id>     → remove a job
  GET/POST /api/saved/companies  → list / save a target company
  PATCH  /api/saved/companies/<id> → edit a saved company's fields
  DELETE /api/saved/companies/<id>
  GET/POST /api/saved/contacts   → list / save a contact
  PATCH  /api/saved/contacts/<id>  → edit a saved contact's fields
  DELETE /api/saved/contacts/<id>
  POST   /api/saved/candidate    → save a candidate (profile only)
  POST   /api/saved/observation  → HR profile-override chat (alias: /api/saved/interview)
  POST   /api/saved/report       → generate PDF report
"""
import re
from flask import Blueprint, request, jsonify, make_response, session

from jobs_intelligence_ai.services.candidate import store
from jobs_intelligence_ai.services.search.utils import _within_days, _parse_salary_num

bp = Blueprint("saved", __name__, url_prefix="/api/saved")


# ── Session context (the collaboration scope) ───────────────────────────────────
def _aid() -> int | None:
    """The logged-in user's account_company (the privacy boundary)."""
    return session.get("account_company_id")


def _uid() -> int | None:
    """The logged-in user's id (owner of anything they create)."""
    return session.get("user_id")


def _vis() -> str:
    """The user's visibility within their company: 'own' or 'all'."""
    return session.get("visibility") or "all"


@bp.route("/users", methods=["GET"])
def api_saved_users():
    """Colleagues in the caller's firm — for the Pipeline tab's Sales Filter User dropdown."""
    return jsonify({"ok": True, "users": store.list_account_users(account_company_id=_aid())})


# ── Pipeline tab: Deal-Filter — narrows an already-saved list by request.args ──
# Not a DB-level filter (saved-item snapshots are sparse/inconsistent across
# sources), so it's applied in Python after the store fetch, the same way
# services.search.utils.passes_filters hard-filters Search results.
def _deal_filter_args() -> dict:
    args = {k: v for k, v in {
        "state":           request.args.get("state", "").strip(),
        "postcode":        request.args.get("postcode", "").strip(),
        "keyword":         request.args.get("keyword", "").strip(),
        "company":         request.args.get("company", "").strip(),
        "available_from":  request.args.get("available_from", "").strip(),
        "occ_group":       request.args.get("occ_group", "").strip(),
        "job_description": request.args.get("job_description", "").strip(),
        "skills":          request.args.get("skills", "").strip(),
        "portal":          request.args.get("portal", "").strip(),
    }.items() if v}
    min_jobs = request.args.get("min_jobs", type=int)
    if min_jobs:
        args["min_jobs"] = min_jobs
    online_since = request.args.get("online_since", type=int)
    if online_since:
        args["online_since"] = online_since
    salary_min = request.args.get("salary_min", type=float)
    if salary_min is not None:
        args["salary_min"] = salary_min
    salary_max = request.args.get("salary_max", type=float)
    if salary_max is not None:
        args["salary_max"] = salary_max
    return args


def _passes_deal_filters(row: dict, filters: dict) -> bool:
    # Saved-item shapes differ per collection (jobs have state/city, candidates/
    # companies/contacts only have a freeform location), so region matching checks
    # whichever location-ish field is actually present on this row.
    if filters.get("state"):
        region = " ".join(str(row.get(k) or "") for k in ("state", "location", "city")).lower()
        if filters["state"].lower() not in region:
            return False
    # Postcode only exists on saved JOB rows (job_snapshot.zipcode) — guarded
    # the same way as the other Jobs-only filters below (missing key = skip,
    # not exclude, so it can't blank Contacts/Companies/Candidates).
    if filters.get("postcode") and "zipcode" in row:
        if not str(row.get("zipcode") or "").startswith(filters["postcode"]):
            return False
    if filters.get("company"):
        if filters["company"].lower() not in str(row.get("company") or row.get("name") or "").lower():
            return False
    if filters.get("keyword"):
        kw = filters["keyword"].lower()
        haystack = " ".join(str(row.get(k) or "") for k in ("title", "name", "company")).lower()
        if kw not in haystack:
            return False
    # min_jobs only applies to rows annotated with a market job_count (saved
    # contacts today) — rows without the key are left alone, so a stray min_jobs
    # param can't silently blank a collection that has no job-count concept.
    if filters.get("min_jobs") and "job_count" in row:
        if (row.get("job_count") or 0) < filters["min_jobs"]:
            return False
    # Job Status / Job Criteria — these read job_snapshot fields (posted, occ_group,
    # description, skills, salary, portal, start_timeline) that only exist on saved
    # JOB rows. Guarded the same way as min_jobs: a row missing the key is left
    # alone rather than silently excluded, so these params can't blank Contacts/
    # Companies/Candidates (the frontend also locks these fields there — see
    # saved.js _JOBS_ONLY_FIELD_IDS — this is defense in depth, not the only guard).
    if filters.get("online_since") and "posted" in row:
        if not _within_days(row.get("posted"), filters["online_since"]):
            return False
    if filters.get("available_from") and "start_timeline" in row:
        if filters["available_from"].lower() not in str(row.get("start_timeline") or "").lower():
            return False
    if filters.get("occ_group") and "occ_group" in row:
        if row.get("occ_group") != filters["occ_group"]:
            return False
    if filters.get("job_description") and "description" in row:
        if filters["job_description"].lower() not in str(row.get("description") or "").lower():
            return False
    if filters.get("skills") and ("skills" in row or "skills_en" in row):
        skills_val = " ".join([str(row.get("skills") or ""), str(row.get("skills_en") or "")]).lower()
        terms = [t.strip().lower() for t in filters["skills"].split(",") if t.strip()]
        if terms and not any(t in skills_val for t in terms):
            return False
    if (filters.get("salary_min") is not None or filters.get("salary_max") is not None) and "salary" in row:
        num = _parse_salary_num(row.get("salary"))
        if num is None:
            return False
        if filters.get("salary_min") is not None and num < filters["salary_min"]:
            return False
        if filters.get("salary_max") is not None and num > filters["salary_max"]:
            return False
    if filters.get("portal") and "portal" in row:
        if row.get("portal") != filters["portal"]:
            return False
    return True


@bp.route("", methods=["GET"])
def api_saved_get():
    jobs = store.list_saved_jobs(account_company_id=_aid(), owner_id=_uid(), visibility=_vis(),
                                 filter_user_id=request.args.get("user_id", type=int),
                                 sales_status=request.args.get("sales_status") or None)
    filters = _deal_filter_args()
    if filters:
        jobs = [j for j in jobs if _passes_deal_filters(j, filters)]
    return jsonify({"ok": True, "count": len(jobs), "jobs": jobs})


# Saved-job sales pipeline — canonical codes stored in `saved_jobs.status`;
# the UI maps them to EN/DE labels. Distinct from the candidate hiring pipeline.
_JOB_PIPELINE = ("new", "in_progress", "proposal_sent", "won", "lost")


@bp.route("", methods=["POST"])
def api_saved_add():
    """Body: { job: {...}, status?: str, extras?: dict, candidate_profile?: {...} }"""
    body = request.get_json(silent=True) or {}
    job  = body.get("job")
    if not job:
        return jsonify({"ok": False, "error": "job required"}), 400
    status = body.get("status", "new")
    if status not in _JOB_PIPELINE:
        return jsonify({"ok": False, "error": f"invalid status {status!r}"}), 400

    profile = body.get("candidate_profile")
    try:
        added = store.add_saved_job(
            job, status=status,
            extras=body.get("extras") or {}, profile=profile,
            account_company_id=_aid(), owner_id=_uid())
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400

    jobs = store.list_saved_jobs(account_company_id=_aid(), owner_id=_uid(), visibility=_vis())
    if not added:
        return jsonify({"ok": True, "message": "Already saved", "count": len(jobs), "jobs": jobs})
    return jsonify({"ok": True, "count": len(jobs), "jobs": jobs})


@bp.route("/<job_id>", methods=["PATCH"])
def api_saved_update(job_id):
    """Body: { pipeline_status?, notes?, grade?, extras?, and any editable job_snapshot
    field (title, company, location, salary, url, portal, …) }. The store enforces the
    field allow-list, so forwarding the whole body is safe."""
    body = request.get_json(silent=True) or {}
    new_status = body.get("pipeline_status", body.get("status"))
    if new_status is not None and new_status not in _JOB_PIPELINE:
        return jsonify({"ok": False, "error": f"invalid status {new_status!r}"}), 400
    job = store.update_saved_job(job_id, body, account_company_id=_aid(), user_id=_uid())
    if job is None:
        return jsonify({"ok": False, "error": "Not found"}), 404
    return jsonify({"ok": True, "job": job})


def _strength(jobs: list[dict]) -> float:
    scores = []
    for j in jobs:
        try:
            s = float(j.get("score") or 0)
        except (TypeError, ValueError):
            s = 0.0
        if s > 0:
            scores.append(s)
    return round(sum(scores) / len(scores) * 100) if scores else 0


def _candidates_index() -> dict[str, list[dict]]:
    """Group visible saved jobs by candidate_name (company-scoped)."""
    return store.candidates_index(account_company_id=_aid(), owner_id=_uid(), visibility=_vis())


@bp.route("/candidates", methods=["GET"])
def api_saved_candidates():
    """List saved candidates visible to the caller — drives the switcher + table view."""
    candidates = store.list_candidates_detailed(
        account_company_id=_aid(), owner_id=_uid(), visibility=_vis(),
        filter_user_id=request.args.get("user_id", type=int),
        sales_status=request.args.get("sales_status") or None)
    filters = _deal_filter_args()
    if filters:
        candidates = [c for c in candidates
                     if _passes_deal_filters({**c, "title": c.get("title") or c.get("name")}, filters)]
    return jsonify({"ok": True, "candidates": candidates})


@bp.route("/lookup", methods=["GET"])
def api_saved_lookup():
    """Query: ?name=<name> OR ?linkedin=<url> → { exists, candidate? } (company-scoped)."""
    name     = (request.args.get("name") or "").strip()
    linkedin = (request.args.get("linkedin") or "").strip()
    if linkedin:
        cand = store.lookup_by_linkedin(linkedin, account_company_id=_aid())
    else:
        cand = store.lookup_candidate(name, account_company_id=_aid()) if name else None
    return jsonify({"ok": True, "exists": cand is not None, "candidate": cand})


@bp.route("/load", methods=["GET"])
def api_saved_load():
    """Query: ?name=<name> → { profile, jobs } for a saved candidate (company-scoped)."""
    name = (request.args.get("name") or "").strip()
    if not name:
        return jsonify({"ok": False, "error": "name required"}), 400
    bundle = store.get_candidate_bundle(name, account_company_id=_aid(),
                                        owner_id=_uid(), visibility=_vis())
    if bundle["profile"] is None and not bundle["jobs"]:
        return jsonify({"ok": False, "error": "Candidate not found"}), 404
    store.log_access("load_candidate", name, account_company_id=_aid(), user_id=_uid())
    return jsonify({"ok": True, **bundle})


# ── Saved companies (bookmarked target companies) ───────────────────────────────
@bp.route("/companies", methods=["GET"])
def api_list_saved_companies():
    """List the company's saved target companies (the database view)."""
    from jobs_intelligence_ai.frontend.blueprints.company import company_job_counts
    companies = store.list_saved_companies(
        account_company_id=_aid(), owner_id=_uid(), visibility=_vis(),
        filter_user_id=request.args.get("user_id", type=int))
    # Annotate each company with its active-job count from the market catalogue —
    # shown as the grid's "Open jobs" column (mirrors saved contacts' job_count).
    counts = company_job_counts([c.get("target_company_id") for c in companies])
    for c in companies:
        tcid = c.get("target_company_id")
        c["job_count"] = counts.get(int(tcid), 0) if str(tcid or "").isdigit() else 0
    filters = _deal_filter_args()
    if filters:
        companies = [c for c in companies if _passes_deal_filters(c, filters)]
    return jsonify({"ok": True, "companies": companies})


@bp.route("/companies", methods=["POST"])
def api_save_company():
    """Body: { target_company_id, snapshot?: {name,...}, notes? } — bookmark a target company."""
    body = request.get_json(silent=True) or {}
    tcid = body.get("target_company_id")
    if not tcid:
        return jsonify({"ok": False, "error": "target_company_id required"}), 400
    try:
        added = store.add_saved_company(
            tcid, snapshot=body.get("snapshot"), notes=body.get("notes") or "",
            account_company_id=_aid(), owner_id=_uid())
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    return jsonify({"ok": True, "added": added, "companies": store.list_saved_companies(
        account_company_id=_aid(), owner_id=_uid(), visibility=_vis())})


@bp.route("/companies/<int:saved_id>", methods=["PATCH"])
def api_update_saved_company(saved_id):
    """Body: any editable snapshot field (name, industry, location, …) and/or notes."""
    body = request.get_json(silent=True) or {}
    if not store.update_saved_company(saved_id, body, account_company_id=_aid(), user_id=_uid()):
        return jsonify({"ok": False, "error": "Not found or no editable fields"}), 404
    return jsonify({"ok": True})


@bp.route("/companies/<int:saved_id>", methods=["DELETE"])
def api_delete_saved_company(saved_id):
    removed = store.delete_saved_company(saved_id, account_company_id=_aid(), user_id=_uid())
    return jsonify({"ok": True, "removed": removed})


# ── Saved contacts (bookmarked people at target companies) ──────────────────────
@bp.route("/contacts", methods=["GET"])
def api_list_saved_contacts():
    from jobs_intelligence_ai.frontend.blueprints.company import contact_job_counts
    contacts = store.list_saved_contacts(
        account_company_id=_aid(), owner_id=_uid(), visibility=_vis(),
        filter_user_id=request.args.get("user_id", type=int))
    # Annotate each contact with its active-job count from the market catalogue —
    # shown as the grid's "Open jobs" column and matched by the Deal-Filter's
    # min_jobs field. Contacts saved without a market id count as 0.
    counts = contact_job_counts([c.get("contact_id") for c in contacts])
    for c in contacts:
        cid = c.get("contact_id")
        c["job_count"] = counts.get(int(cid), 0) if str(cid or "").isdigit() else 0
    filters = _deal_filter_args()
    if filters:
        contacts = [c for c in contacts if _passes_deal_filters(c, filters)]
    return jsonify({"ok": True, "contacts": contacts})


@bp.route("/contacts", methods=["POST"])
def api_save_contact():
    """Body: { contact_id, snapshot?: {name,...}, notes? } — bookmark a contact."""
    body = request.get_json(silent=True) or {}
    cid = body.get("contact_id")
    if not cid:
        return jsonify({"ok": False, "error": "contact_id required"}), 400
    try:
        added = store.add_saved_contact(
            cid, snapshot=body.get("snapshot"), notes=body.get("notes") or "",
            account_company_id=_aid(), owner_id=_uid())
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    return jsonify({"ok": True, "added": added, "contacts": store.list_saved_contacts(
        account_company_id=_aid(), owner_id=_uid(), visibility=_vis())})


@bp.route("/contacts/<int:saved_id>", methods=["PATCH"])
def api_update_saved_contact(saved_id):
    """Body: any editable snapshot field (name, title, email, …) and/or notes."""
    body = request.get_json(silent=True) or {}
    if not store.update_saved_contact(saved_id, body, account_company_id=_aid(), user_id=_uid()):
        return jsonify({"ok": False, "error": "Not found or no editable fields"}), 404
    return jsonify({"ok": True})


@bp.route("/contacts/<int:saved_id>", methods=["DELETE"])
def api_delete_saved_contact(saved_id):
    removed = store.delete_saved_contact(saved_id, account_company_id=_aid(), user_id=_uid())
    return jsonify({"ok": True, "removed": removed})


@bp.route("/candidate", methods=["POST"])
def api_candidate_create():
    """Body: { profile: {...} } — persist a session-built candidate (profile only).

    Company-wide dedup: a candidate NAME already in this account_company (saved by
    anyone) is not added again — we return already_saved:true so the UI can flag it.
    """
    body    = request.get_json(silent=True) or {}
    profile = body.get("profile") or {}
    name    = (profile.get("name") or "").strip()
    if not name:
        return jsonify({"ok": False, "error": "candidate name required"}), 400
    existing = store.lookup_candidate(name, account_company_id=_aid())
    if existing:
        return jsonify({"ok": True, "added": False, "already_saved": True,
                        "name": name, "owner": existing.get("owner") or ""})
    store.upsert_profile(name, profile, account_company_id=_aid(), owner_id=_uid())
    store.log_access("save_candidate", name, account_company_id=_aid(), user_id=_uid())
    return jsonify({"ok": True, "added": True, "name": name})


@bp.route("/insights", methods=["GET"])
def api_saved_insights():
    """Query: ?candidate=<name>  →  the Match Insights payload for that candidate."""
    from jobs_intelligence_ai.services.enrichment import build_insights
    candidate = (request.args.get("candidate") or "").strip()
    by_cand   = _candidates_index()

    if not candidate:
        if not by_cand:
            return jsonify({"ok": False, "error": "No saved candidates"}), 404
        candidate = max(by_cand, key=lambda k: len(by_cand[k]))

    jobs = by_cand.get(candidate)
    if not jobs:
        return jsonify({"ok": False, "error": f"No saved jobs for '{candidate}'"}), 404

    all_strengths = [_strength(js) for js in by_cand.values()]
    profile       = store.get_profile(candidate, account_company_id=_aid())
    store.log_access("view_insights", candidate, account_company_id=_aid(), user_id=_uid())
    try:
        payload = build_insights(candidate, jobs, profile, all_strengths=all_strengths)
        return jsonify({"ok": True, "insights": payload})
    except Exception as e:
        import traceback
        return jsonify({"ok": False, "error": str(e), "trace": traceback.format_exc()}), 500


# ── Interview chat — profile-override conversation ───────────────────────────

def _compute_impact(overrides: dict, old_ins: dict, new_ins: dict) -> dict:
    """Diff the key 'positions available' metrics between old and new insights."""
    impact = {}

    def _pot(lever_str: str):
        s = (lever_str or "").replace(" ", "")
        try:
            return int(s.split("→")[-1])
        except (ValueError, IndexError):
            return None

    old_pot = _pot(old_ins.get("leverTotal", ""))
    new_pot = _pot(new_ins.get("leverTotal", ""))
    if old_pot is not None and new_pot is not None and old_pot != new_pot:
        impact["pipeline_before"] = old_pot
        impact["pipeline_after"]  = new_pot
        impact["pipeline_delta"]  = new_pot - old_pot

    if "salary_expectation" in overrides:
        old_ov = (old_ins.get("salaryStat") or {}).get("overlap")
        new_ov = (new_ins.get("salaryStat") or {}).get("overlap")
        if old_ov is not None and new_ov is not None and old_ov != new_ov:
            impact["overlap_before"] = old_ov
            impact["overlap_after"]  = new_ov

    if "skills" in overrides:
        old_gaps = len(old_ins.get("gaps") or [])
        new_gaps = len(new_ins.get("gaps") or [])
        if old_gaps != new_gaps:
            impact["gaps_before"] = old_gaps
            impact["gaps_after"]  = new_gaps

    return impact


def _impact_text(impact: dict) -> str:
    if not impact:
        return "No significant change in pipeline metrics."
    lines = []
    if "pipeline_before" in impact:
        d = impact["pipeline_delta"]
        sign = f"+{d}" if d > 0 else str(d)
        lines.append(
            f"Pipeline potential: {impact['pipeline_before']} → {impact['pipeline_after']} roles ({sign})")
    if "overlap_before" in impact:
        lines.append(
            f"Salary match on saved roles: {impact['overlap_before']}% → {impact['overlap_after']}%")
    if "gaps_before" in impact:
        lines.append(
            f"Skill gaps: {impact['gaps_before']} → {impact['gaps_after']}")
    return " · ".join(lines)


@bp.route("/observation", methods=["POST"])
@bp.route("/interview", methods=["POST"])  # legacy alias — drop once no client calls it
def api_saved_observation():
    """Body: { candidate, message } — HR profile-override conversation."""
    from jobs_intelligence_ai.services.enrichment import (
        build_insights, extract_profile_overrides, phrase_observation_reply,
    )

    body      = request.get_json(silent=True) or {}
    candidate = (body.get("candidate") or "").strip()
    message   = (body.get("message") or "").strip()
    if not candidate or not message:
        return jsonify({"ok": False, "error": "candidate and message required"}), 400

    old_profile = dict(store.get_profile(candidate, account_company_id=_aid()) or {})
    by_cand     = _candidates_index()
    jobs        = by_cand.get(candidate) or []
    all_strengths = [_strength(js) for js in by_cand.values()]

    try:
        overrides = extract_profile_overrides(old_profile, message)
    except Exception as e:
        import traceback
        return jsonify({"ok": False, "error": str(e), "trace": traceback.format_exc()}), 500

    if "skills" in overrides and isinstance(overrides["skills"], list):
        existing = old_profile.get("skills") or []
        overrides["skills"] = list(dict.fromkeys(existing + overrides["skills"]))

    try:
        old_insights = build_insights(candidate, jobs, old_profile, all_strengths=all_strengths)
        new_profile  = {**old_profile, **overrides}
        new_insights = build_insights(candidate, jobs, new_profile, all_strengths=all_strengths)
    except Exception as e:
        import traceback
        return jsonify({"ok": False, "error": str(e), "trace": traceback.format_exc()}), 500

    impact = _compute_impact(overrides, old_insights, new_insights)
    reply  = phrase_observation_reply(message, overrides, _impact_text(impact))

    if overrides:
        store.upsert_profile(candidate, new_profile, account_company_id=_aid(), owner_id=_uid())
        store.log_access("interview_update", candidate,
                         detail=", ".join(sorted(overrides)),
                         account_company_id=_aid(), user_id=_uid())

    return jsonify({
        "ok":       True,
        "reply":    reply,
        "overrides": overrides,
        "impact":   impact,
        "insights": new_insights,
    })


@bp.route("/report", methods=["POST"])
def api_saved_report():
    """Body: { candidate?: <name> }  →  Match Insights PDF for that candidate."""
    from jobs_intelligence_ai.services.enrichment import build_insights
    from jobs_intelligence_ai.services.reporting import generate_insights_pdf

    body      = request.get_json(silent=True) or {}
    candidate = (body.get("candidate") or "").strip()
    by_cand   = _candidates_index()

    if not by_cand:
        return jsonify({"ok": False, "error": "No saved candidates"}), 400

    if not candidate:
        candidate = max(by_cand, key=lambda k: len(by_cand[k]))

    jobs = by_cand.get(candidate)
    if not jobs:
        return jsonify({"ok": False, "error": f"No saved jobs for '{candidate}'"}), 404

    all_strengths = [_strength(js) for js in by_cand.values()]
    profile       = store.get_profile(candidate, account_company_id=_aid())
    store.log_access("export_report", candidate, account_company_id=_aid(), user_id=_uid())

    try:
        insights  = build_insights(candidate, jobs, profile, all_strengths=all_strengths)
        pdf_bytes = generate_insights_pdf(insights)
        safe_name = re.sub(r"[^\w\s-]", "", candidate).strip().replace(" ", "_") or "Candidate"
        filename  = f"{safe_name}_MatchInsights.pdf"
        resp = make_response(pdf_bytes)
        resp.headers["Content-Type"]        = "application/pdf"
        resp.headers["Content-Disposition"] = f"attachment; filename={filename}"
        return resp
    except Exception as e:
        import traceback
        return jsonify({"ok": False, "error": str(e), "trace": traceback.format_exc()}), 500


@bp.route("/<job_id>", methods=["DELETE"])
def api_saved_delete(job_id):
    removed = store.delete_saved_job(job_id, account_company_id=_aid(), user_id=_uid())
    count   = len(store.list_saved_jobs(account_company_id=_aid(), owner_id=_uid(), visibility=_vis()))
    return jsonify({"ok": True, "removed": removed, "count": count})


# Candidate fields the table view may edit inline.
_CANDIDATE_EDIT_FIELDS = (
    "status", "email", "phone", "linkedin", "title", "experience_years",
    "location", "languages", "salary_expectation", "availability", "summary",
    "skills", "seniority")


@bp.route("/candidate/<path:name>", methods=["PATCH"])
def api_candidate_update(name):
    """Body: any subset of the editable candidate fields."""
    body   = request.get_json(silent=True) or {}
    fields = {k: body[k] for k in _CANDIDATE_EDIT_FIELDS if k in body}
    if not fields:
        return jsonify({"ok": False, "error": "no editable fields provided"}), 400
    if not store.update_candidate(name, fields, account_company_id=_aid(), user_id=_uid()):
        return jsonify({"ok": False, "error": "Candidate not found"}), 404
    return jsonify({"ok": True, "name": name, "fields": fields})


@bp.route("/candidate/<path:name>", methods=["DELETE"])
def api_candidate_erase(name):
    """GDPR erasure: remove a candidate and all their saved jobs (cascade)."""
    erased = store.delete_candidate(name, account_company_id=_aid(), user_id=_uid())
    if not erased:
        return jsonify({"ok": False, "error": "Candidate not found"}), 404
    return jsonify({"ok": True, "erased": name})
