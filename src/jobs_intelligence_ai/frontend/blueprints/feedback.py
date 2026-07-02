"""
tabs/feedback.py — Lightweight user feedback.

Stores free-text feedback ("things to improve or fix") in the shared `feedback`
table of the Jobs_Intelligence_AI schema, attributed to the logged-in user and
their account company. Not personal candidate data. One table for both markets
(the old per-country `feedback` / `sk_feedback` split was retired with the
country-column rework).

Routes:
  POST /api/feedback        body: { message, context? } → { ok, id }
  GET  /api/feedback        → { ok, feedback: [...] }   (newest first)
"""
from flask import Blueprint, request, jsonify, session
from sqlalchemy import text

from jobs_intelligence_ai import config
from jobs_intelligence_ai.infra.database import get_engine

bp = Blueprint("feedback", __name__, url_prefix="/api/feedback")

_T_FEEDBACK = f"{config.APP_SCHEMA}.feedback"


@bp.route("", methods=["POST"])
def api_feedback_add():
    """Body: { message, context? } — store one free-text feedback note."""
    body    = request.get_json(silent=True) or {}
    message = (body.get("message") or "").strip()
    if not message:
        return jsonify({"ok": False, "error": "message required"}), 400
    context = (body.get("context") or "").strip()[:64] or None

    with get_engine().begin() as conn:
        res = conn.execute(text(
            f"INSERT INTO {_T_FEEDBACK} "
            f"(account_company_id, user_id, message, context, created_by) "
            f"VALUES (:co, :uid, :m, :c, :by)"),
            {"co": session.get("account_company_id"), "uid": session.get("user_id"),
             "m": message[:5000], "c": context,
             "by": session.get("display_name") or session.get("username")})
        return jsonify({"ok": True, "id": int(res.lastrowid)})


@bp.route("", methods=["GET"])
def api_feedback_list():
    """List feedback, newest first."""
    with get_engine().connect() as conn:
        rows = conn.execute(text(
            f"SELECT id, message, context, created_by, created_at "
            f"FROM {_T_FEEDBACK} ORDER BY id DESC LIMIT 500")).mappings().all()
    return jsonify({"ok": True, "feedback": [
        {"id": m["id"], "message": m["message"], "context": m["context"],
         "created_by": m["created_by"], "created_at": str(m["created_at"])} for m in rows]})
