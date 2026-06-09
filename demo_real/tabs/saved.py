"""
tabs/saved.py — Saved Jobs tab (MySQL-backed candidate pipeline).

Persists to the Jobs_Intelligence_AI schema via helpers.candidate_store:
candidates + parsed profiles + saved jobs + audit log.

Routes:
  GET    /api/saved              → list saved jobs
  POST   /api/saved              → add a job
  PATCH  /api/saved/<job_id>     → update status / notes / extras
  DELETE /api/saved/<job_id>     → remove a job
  POST   /api/saved/report       → generate PDF report
"""
import re
from flask import Blueprint, request, jsonify, make_response, session

from helpers import candidate_store as store

bp = Blueprint("saved", __name__, url_prefix="/api/saved")


def _user() -> str | None:
    """The logged-in user's name, for created_by / audit attribution."""
    return session.get("display_name") or session.get("username") or None


@bp.route("", methods=["GET"])
def api_saved_get():
    jobs = store.list_saved_jobs()
    return jsonify({"ok": True, "count": len(jobs), "jobs": jobs})


@bp.route("", methods=["POST"])
def api_saved_add():
    """Body: { job: {...}, status?: str, extras?: dict, candidate_profile?: {...} }"""
    body = request.get_json(silent=True) or {}
    job  = body.get("job")
    if not job:
        return jsonify({"ok": False, "error": "job required"}), 400

    profile = body.get("candidate_profile")
    try:
        added = store.add_saved_job(
            job, status=body.get("status", "New"),
            extras=body.get("extras") or {}, profile=profile, actor=_user())
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400

    jobs = store.list_saved_jobs()
    if not added:
        return jsonify({"ok": True, "message": "Already saved", "count": len(jobs), "jobs": jobs})
    return jsonify({"ok": True, "count": len(jobs), "jobs": jobs})


@bp.route("/<job_id>", methods=["PATCH"])
def api_saved_update(job_id):
    """Body: { pipeline_status?, notes?, extras? }"""
    body = request.get_json(silent=True) or {}
    fields = {k: body[k] for k in ("pipeline_status", "notes", "extras") if k in body}
    job = store.update_saved_job(job_id, fields, actor=_user())
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
    """Group saved jobs by candidate_name (DB-backed)."""
    return store.candidates_index()


@bp.route("/candidates", methods=["GET"])
def api_saved_candidates():
    """List saved candidates from the DB — drives both the switcher and the table
    view (name, initials, matches, gradeA, hasProfile + title/createdBy/createdAt)."""
    return jsonify({"ok": True, "candidates": store.list_candidates_detailed()})


@bp.route("/lookup", methods=["GET"])
def api_saved_lookup():
    """Query: ?name=<name>  OR  ?linkedin=<url>  →  { exists, candidate? }.

    Lets the search/candidate tab warn when a candidate is already saved in the
    database (returns the existing pipeline status). CV mode looks up by name;
    LinkedIn mode looks up by profile URL so it can warn before re-scraping."""
    name     = (request.args.get("name") or "").strip()
    linkedin = (request.args.get("linkedin") or "").strip()
    if linkedin:
        cand = store.lookup_by_linkedin(linkedin)
    else:
        cand = store.lookup_candidate(name) if name else None
    return jsonify({"ok": True, "exists": cand is not None, "candidate": cand})


@bp.route("/load", methods=["GET"])
def api_saved_load():
    """Query: ?name=<name>  →  { profile, jobs } for a saved candidate.

    Powers the "Load from database" action on the duplicate warning: reload a
    candidate's parsed profile + saved jobs into the search tab instead of
    re-parsing a CV or paying to re-scrape a LinkedIn profile already on file."""
    name = (request.args.get("name") or "").strip()
    if not name:
        return jsonify({"ok": False, "error": "name required"}), 400
    bundle = store.get_candidate_bundle(name)
    if bundle["profile"] is None and not bundle["jobs"]:
        return jsonify({"ok": False, "error": "Candidate not found"}), 404
    store.log_access("load_candidate", name, actor=_user())
    return jsonify({"ok": True, **bundle})


@bp.route("/companies", methods=["POST"])
def api_save_companies():
    """Body: { candidate, companies:[{name, linkedin_url?, title?, starts_at?,
    ends_at?, industry?, size?, website?}], candidate_profile? }

    Saves the candidate's employers into the company catalogue and links who
    worked where. Creates/updates the candidate row so the link is valid."""
    body      = request.get_json(silent=True) or {}
    name      = (body.get("candidate") or "").strip()
    companies = body.get("companies") or []
    if not name:
        return jsonify({"ok": False, "error": "candidate required"}), 400
    if not companies:
        return jsonify({"ok": False, "error": "no companies to save"}), 400
    cid   = store.get_or_create_candidate(
        name, body.get("candidate_profile") or None, created_by=_user())
    saved = store.save_companies(cid, companies, created_by=_user())
    return jsonify({"ok": True, "saved": saved, "companies": store.list_companies()})


@bp.route("/companies", methods=["GET"])
def api_list_companies():
    """List the saved employer catalogue (name, metadata, # candidates worked there)."""
    return jsonify({"ok": True, "companies": store.list_companies()})


@bp.route("/candidate", methods=["POST"])
def api_candidate_create():
    """Body: { profile: {...} } — persist a session-built ("local") candidate to
    the candidate table, profile only (no saved jobs). Powers the "Save to
    database" button on the Local view. Returns the refreshed candidate list."""
    body    = request.get_json(silent=True) or {}
    profile = body.get("profile") or {}
    name    = (profile.get("name") or "").strip()
    if not name:
        return jsonify({"ok": False, "error": "candidate name required"}), 400
    store.upsert_profile(name, profile, created_by=_user())
    store.log_access("save_candidate", name, actor=_user())
    return jsonify({"ok": True, "name": name,
                    "candidates": store.list_candidates_detailed()})


@bp.route("/insights", methods=["GET"])
def api_saved_insights():
    """Query: ?candidate=<name>  →  the Match Insights payload for that candidate."""
    from helpers.match_insights import build_insights
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
    profile       = store.get_profile(candidate)
    store.log_access("view_insights", candidate, actor=_user())
    try:
        payload = build_insights(candidate, jobs, profile, all_strengths=all_strengths)
        return jsonify({"ok": True, "insights": payload})
    except Exception as e:
        import traceback
        return jsonify({"ok": False, "error": str(e), "trace": traceback.format_exc()}), 500


# ── Interview chat — GPT prompts ─────────────────────────────────────────────

_EXTRACT_SYSTEM = """Extract profile parameter updates implied by the HR manager's interview observation.
Current candidate profile: {profile}
Return ONLY valid JSON with no extra text:
{{"overrides": {{
  "salary_expectation": "string e.g. 4500-5500 or >4000 — only if salary was mentioned",
  "location": "string — only if location/relocation was mentioned",
  "skills": ["list — full updated skill list, add confirmed skills to existing ones"],
  "availability": "string e.g. 2026-09-01 or immediate — only if mentioned",
  "title": "string — only if role preference was mentioned",
  "languages": "string — only if mentioned",
  "experience_years": "number — only if mentioned"
}}}}
Only include keys where the note gives new information. Empty overrides are fine."""

_REPLY_SYSTEM = """You are a concise recruitment intelligence assistant.
The HR manager shared this observation about a candidate: "{message}"
You extracted these profile updates: {overrides}
Pipeline impact after applying the updates: {impact}
Write 1-2 natural sentences acknowledging what you understood.
If there is a concrete pipeline impact, weave in the exact numbers (e.g. "roles drop from X to Y").
If there is no pipeline impact, just acknowledge the observation — do NOT mention pipeline metrics.
Return ONLY valid JSON: {{"reply": "<your reply>"}}"""


def _gpt_json(system: str, user: str) -> dict:
    """Single GPT call → parsed JSON dict. Strips markdown fences if needed."""
    import json as _json
    import config as cfg
    from openai import OpenAI
    if not cfg.OPENAI_API_KEY:
        return {}
    try:
        resp = OpenAI(api_key=cfg.OPENAI_API_KEY).responses.create(
            model=cfg.CHAT_MODEL, instructions=system, input=user)
        text = (resp.output_text or "").strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        return _json.loads(text)
    except Exception as e:
        return {"_error": str(e)}


def _compute_impact(overrides: dict, old_ins: dict, new_ins: dict) -> dict:
    """Diff the key 'positions available' metrics between old and new insights."""
    impact = {}

    def _pot(lever_str: str):
        # leverTotal format: "2 → 561" — extract the potential (right side)
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


@bp.route("/interview", methods=["POST"])
def api_saved_interview():
    """Body: { candidate, message }
    Two-pass flow: (1) extract overrides, (2) compute Python impact diff,
    (3) phrase reply naturally with impact numbers.
    """
    import json as _json
    from helpers.match_insights import build_insights

    body      = request.get_json(silent=True) or {}
    candidate = (body.get("candidate") or "").strip()
    message   = (body.get("message") or "").strip()
    if not candidate or not message:
        return jsonify({"ok": False, "error": "candidate and message required"}), 400

    old_profile = dict(store.get_profile(candidate) or {})
    by_cand     = _candidates_index()
    jobs        = by_cand.get(candidate) or []
    all_strengths = [_strength(js) for js in by_cand.values()]

    # ── Pass 1: extract overrides ────────────────────────────────────────────
    extract_system = _EXTRACT_SYSTEM.format(
        profile=_json.dumps(old_profile, ensure_ascii=False))
    extracted = _gpt_json(extract_system, message)
    if "_error" in extracted:
        return jsonify({"ok": False, "error": extracted["_error"]}), 500

    overrides = extracted.get("overrides") or {}

    # Merge skills (extend, not replace)
    if "skills" in overrides and isinstance(overrides["skills"], list):
        existing = old_profile.get("skills") or []
        overrides["skills"] = list(dict.fromkeys(existing + overrides["skills"]))

    # ── Build old + new insights, compute impact ─────────────────────────────
    try:
        old_insights = build_insights(candidate, jobs, old_profile, all_strengths=all_strengths)
        new_profile  = {**old_profile, **overrides}
        new_insights = build_insights(candidate, jobs, new_profile, all_strengths=all_strengths)
    except Exception as e:
        import traceback
        return jsonify({"ok": False, "error": str(e), "trace": traceback.format_exc()}), 500

    impact = _compute_impact(overrides, old_insights, new_insights)

    # ── Pass 2: phrase reply naturally with impact numbers ───────────────────
    reply_system = _REPLY_SYSTEM.format(
        message=message,
        overrides=_json.dumps(overrides, ensure_ascii=False),
        impact=_impact_text(impact))
    reply_result = _gpt_json(reply_system, message)
    reply = reply_result.get("reply") or "Profile updated."

    # ── Persist new profile ──────────────────────────────────────────────────
    if overrides:
        store.upsert_profile(candidate, new_profile, created_by=_user())
        store.log_access("interview_update", candidate,
                         detail=", ".join(sorted(overrides)), actor=_user())

    return jsonify({
        "ok":       True,
        "reply":    reply,
        "overrides": overrides,
        "impact":   impact,
        "insights": new_insights,
    })


@bp.route("/report", methods=["POST"])
def api_saved_report():
    """Body: { candidate?: <name> }  →  Match Insights PDF for that candidate.

    Mirrors the on-screen Match Insights dashboard for the selected candidate.
    """
    from helpers.match_insights import build_insights
    from helpers.report_pipeline import generate_insights_pdf

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
    profile       = store.get_profile(candidate)
    store.log_access("export_report", candidate, actor=_user())

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
    removed = store.delete_saved_job(job_id, actor=_user())
    count   = len(store.list_saved_jobs())
    return jsonify({"ok": True, "removed": removed, "count": count})


# Candidate fields the table view may edit inline (status + contacts + the parsed
# profile columns a recruiter might quickly tweak). `skills` is comma-separated.
_CANDIDATE_EDIT_FIELDS = (
    "status", "email", "phone", "linkedin", "title", "experience_years",
    "location", "languages", "salary_expectation", "availability", "summary", "skills")


@bp.route("/candidate/<path:name>", methods=["PATCH"])
def api_candidate_update(name):
    """Body: any subset of the editable candidate fields (status, contacts, and
    parsed-profile columns like title/location/languages/skills/salary). Editing a
    profile field changes the inputs to Match Insights, which recompute on next view."""
    body   = request.get_json(silent=True) or {}
    fields = {k: body[k] for k in _CANDIDATE_EDIT_FIELDS if k in body}
    if not fields:
        return jsonify({"ok": False, "error": "no editable fields provided"}), 400
    if not store.update_candidate(name, fields, actor=_user()):
        return jsonify({"ok": False, "error": "Candidate not found"}), 404
    return jsonify({"ok": True, "name": name, "fields": fields})


@bp.route("/candidate/<path:name>", methods=["DELETE"])
def api_candidate_erase(name):
    """GDPR erasure: remove a candidate and all their saved jobs (cascade)."""
    erased = store.delete_candidate(name, actor=_user())
    if not erased:
        return jsonify({"ok": False, "error": "Candidate not found"}), 404
    return jsonify({"ok": True, "erased": name})
