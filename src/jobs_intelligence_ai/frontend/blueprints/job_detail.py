"""
tabs/job_detail.py — Job Detail modal (routes used when a job card is opened).

Routes:
  POST /api/job_chat              → chat about a single job
  POST /api/job_chat/reset        → clear per-job chat session
  POST /api/desc_translate        → translate job description to English
  POST /api/desc_compact          → summarise job description (3-4 sentences)
  POST /api/desc_cv_questions     → generate gap-based interview questions
  POST /api/desc_outreach         → write candidate outreach message
  POST /api/candidate_strength    → score candidate against job on 5 dimensions

The job-chat routes delegate to `services/search/job_chat` (via `core`); the five one-shot AI
tools delegate to `services/job_detail` (Structured Outputs). The blueprint just validates input,
calls the service, and jsonifies — any service error becomes a 500.
"""
import traceback
from flask import Blueprint, request, jsonify

from jobs_intelligence_ai.core import send_job_message, clear_job_session
from jobs_intelligence_ai.services.job_detail import (
    translate_description, compact_description, generate_cv_questions,
    write_outreach, score_candidate_strength,
)

bp = Blueprint("job_detail", __name__, url_prefix="/api")


def _fail(e):
    """Map a service exception to the modal's 500 envelope (with a trace for the console)."""
    return jsonify({"ok": False, "error": str(e), "trace": traceback.format_exc()}), 500


@bp.route("/job_chat", methods=["POST"])
def api_job_chat():
    """Body: { session_id, message, job_context?: dict, candidate_text?: str, lang?: str }"""
    body           = request.get_json(silent=True) or {}
    session_id     = body.get("session_id", "").strip()
    message        = body.get("message", "").strip()
    job_context    = body.get("job_context", {})
    candidate_text = (body.get("candidate_text") or body.get("cv_text") or "").strip()
    lang           = body.get("lang", "en")

    if not message:
        return jsonify({"ok": False, "error": "message required"}), 400
    if not session_id:
        return jsonify({"ok": False, "error": "session_id required"}), 400

    try:
        result = send_job_message(session_id, message, job_context, lang=lang,
                                  candidate_text=candidate_text)
        return jsonify({"ok": True, **result})
    except Exception as e:
        return _fail(e)


@bp.route("/job_chat/reset", methods=["POST"])
def api_job_chat_reset():
    body       = request.get_json(silent=True) or {}
    session_id = body.get("session_id", "").strip()
    clear_job_session(session_id)
    return jsonify({"ok": True})


@bp.route("/desc_translate", methods=["POST"])
def api_desc_translate():
    """Body: { description }  →  { ok, text } (English translation)"""
    body        = request.get_json(silent=True) or {}
    description = body.get("description", "").strip()
    if not description:
        return jsonify({"ok": False, "error": "description required"}), 400
    try:
        return jsonify({"ok": True, "text": translate_description(description)})
    except Exception as e:
        return _fail(e)


@bp.route("/desc_compact", methods=["POST"])
def api_desc_compact():
    """Body: { description, lang? }  →  { ok, text } (3-4 sentence summary)"""
    body        = request.get_json(silent=True) or {}
    description = body.get("description", "").strip()
    lang        = body.get("lang", "de")
    if not description:
        return jsonify({"ok": False, "error": "description required"}), 400
    try:
        return jsonify({"ok": True, "text": compact_description(description, lang=lang)})
    except Exception as e:
        return _fail(e)


@bp.route("/desc_cv_questions", methods=["POST"])
def api_desc_cv_questions():
    """Body: { description, cv_text, lang? }  →  { ok, text } (gap-based interview questions)"""
    body        = request.get_json(silent=True) or {}
    description = body.get("description", "").strip()
    cv_text     = body.get("cv_text", "").strip()
    lang        = body.get("lang", "de")
    if not description or not cv_text:
        return jsonify({"ok": False, "error": "description and cv_text required"}), 400
    try:
        return jsonify({"ok": True, "text": generate_cv_questions(description, cv_text, lang=lang)})
    except Exception as e:
        return _fail(e)


@bp.route("/desc_outreach", methods=["POST"])
def api_desc_outreach():
    """Body: { job: dict, candidate_name?, cv_text?, lang? }  →  { ok, text }"""
    body           = request.get_json(silent=True) or {}
    job            = body.get("job", {})
    candidate_name = body.get("candidate_name", "").strip()
    cv_text        = body.get("cv_text", "").strip()
    lang           = body.get("lang", "de")
    if not job.get("title"):
        return jsonify({"ok": False, "error": "job.title required"}), 400
    try:
        text = write_outreach(job, candidate_name=candidate_name, cv_text=cv_text, lang=lang)
        return jsonify({"ok": True, "text": text})
    except Exception as e:
        return _fail(e)


@bp.route("/candidate_strength", methods=["POST"])
def api_candidate_strength():
    """Body: { job: dict, cv_text, lang? }  →  { ok, axes, scores, reasons, overall }"""
    body    = request.get_json(silent=True) or {}
    job     = body.get("job", {})
    cv_text = body.get("cv_text", "").strip()
    lang    = body.get("lang", "de")
    if not cv_text or not job.get("title"):
        return jsonify({"ok": False, "error": "job.title and cv_text required"}), 400
    try:
        return jsonify({"ok": True, **score_candidate_strength(job, cv_text, lang=lang)})
    except Exception as e:
        return _fail(e)
