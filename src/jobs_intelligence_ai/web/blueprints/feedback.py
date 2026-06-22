"""
tabs/feedback.py — Lightweight user feedback.

Stores free-text feedback ("things to improve or fix") in the Jobs_Intelligence_AI
schema. Not personal data; no candidate linkage. Austria and Slovakia use separate
tables (config.TABLE_PREFIX → `feedback` / `sk_feedback`) so they don't mix.

Routes:
  POST /api/feedback        body: { message, context? } → { ok, id }
  GET  /api/feedback        → { ok, feedback: [...] }   (newest first)
"""
from flask import Blueprint, request, jsonify
from sqlalchemy import text

from jobs_intelligence_ai import config
from jobs_intelligence_ai.infra.database import get_engine

bp = Blueprint("feedback", __name__, url_prefix="/api/feedback")

_T_FEEDBACK = f"{config.APP_SCHEMA}.{config.TABLE_PREFIX}feedback"


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
            f"INSERT INTO {_T_FEEDBACK} (message, context) VALUES (:m, :c)"),
            {"m": message[:5000], "c": context})
        return jsonify({"ok": True, "id": int(res.lastrowid)})


@bp.route("", methods=["GET"])
def api_feedback_list():
    """List feedback, newest first."""
    with get_engine().connect() as conn:
        rows = conn.execute(text(
            f"SELECT id, message, context, created_at "
            f"FROM {_T_FEEDBACK} ORDER BY id DESC LIMIT 500")).mappings().all()
    return jsonify({"ok": True, "feedback": [
        {"id": m["id"], "message": m["message"], "context": m["context"],
         "created_at": str(m["created_at"])} for m in rows]})
