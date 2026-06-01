"""
tabs/saved.py — Saved Jobs tab (in-memory candidate pipeline).

Routes:
  GET    /api/saved              → list saved jobs
  POST   /api/saved              → add a job
  PATCH  /api/saved/<job_id>     → update status / notes / extras
  DELETE /api/saved/<job_id>     → remove a job
  POST   /api/saved/report       → generate PDF report
"""
import re
from flask import Blueprint, request, jsonify, make_response

bp = Blueprint("saved", __name__, url_prefix="/api/saved")

# In-memory store — resets on server restart (fine for demo).
_saved_jobs: list[dict] = []


@bp.route("", methods=["GET"])
def api_saved_get():
    return jsonify({"ok": True, "count": len(_saved_jobs), "jobs": _saved_jobs})


@bp.route("", methods=["POST"])
def api_saved_add():
    """Body: { job: {...}, status?: str, extras?: dict }"""
    body   = request.get_json(silent=True) or {}
    job    = body.get("job")
    if not job:
        return jsonify({"ok": False, "error": "job required"}), 400

    job_id = job.get("job_id")
    if any(j.get("job_id") == job_id for j in _saved_jobs):
        return jsonify({"ok": True, "message": "Already saved", "jobs": _saved_jobs})

    entry = {
        **job,
        "pipeline_status": body.get("status", "New"),
        "notes": "",
        "extras": body.get("extras") or {},
    }
    _saved_jobs.append(entry)
    return jsonify({"ok": True, "count": len(_saved_jobs), "jobs": _saved_jobs})


@bp.route("/<job_id>", methods=["PATCH"])
def api_saved_update(job_id):
    """Body: { pipeline_status?, notes?, extras? }"""
    body = request.get_json(silent=True) or {}
    for job in _saved_jobs:
        if job.get("job_id") == job_id:
            if "pipeline_status" in body:
                job["pipeline_status"] = body["pipeline_status"]
            if "notes" in body:
                job["notes"] = body["notes"]
            if "extras" in body:
                job["extras"] = {**(job.get("extras") or {}), **body["extras"]}
            return jsonify({"ok": True, "job": job})
    return jsonify({"ok": False, "error": "Not found"}), 404


@bp.route("/report", methods=["POST"])
def api_saved_report():
    """Body: { jobs?: [...], candidate_profile?: {...} }"""
    from helpers.report_pipeline import generate_saved_jobs_pdf
    body              = request.get_json(silent=True) or {}
    jobs              = body.get("jobs") or _saved_jobs
    candidate_profile = body.get("candidate_profile") or None

    if not jobs:
        return jsonify({"ok": False, "error": "No saved jobs"}), 400

    try:
        pdf_bytes  = generate_saved_jobs_pdf(jobs, candidate_profile=candidate_profile)
        cand_name  = None
        if candidate_profile and candidate_profile.get("name"):
            cand_name = candidate_profile["name"]
        elif jobs and jobs[0].get("candidate_name"):
            cand_name = jobs[0]["candidate_name"]
        safe_name  = re.sub(r"[^\w\s-]", "", cand_name).strip().replace(" ", "_") if cand_name else "Candidate"
        filename   = f"{safe_name}_JobsAI.pdf"
        resp = make_response(pdf_bytes)
        resp.headers["Content-Type"]        = "application/pdf"
        resp.headers["Content-Disposition"] = f"attachment; filename={filename}"
        return resp
    except Exception as e:
        import traceback
        return jsonify({"ok": False, "error": str(e), "trace": traceback.format_exc()}), 500


@bp.route("/<job_id>", methods=["DELETE"])
def api_saved_delete(job_id):
    global _saved_jobs
    before     = len(_saved_jobs)
    _saved_jobs = [j for j in _saved_jobs if j.get("job_id") != job_id]
    return jsonify({"ok": True, "removed": before - len(_saved_jobs), "count": len(_saved_jobs)})
