"""
tabs/feedback.py — Lightweight user feedback.

Stores free-text feedback ("things to improve or fix") in the
Jobs_Intelligence_AI.feedback table. Not personal data; no candidate linkage.

Routes:
  POST /api/feedback        body: { message, context? } → { ok, id }
  GET  /api/feedback        → { ok, feedback: [...] }   (newest first)
"""
from flask import Blueprint, request, jsonify
from sqlalchemy import text

from core.database import get_engine

bp = Blueprint("feedback", __name__, url_prefix="/api/feedback")

_DB = "Jobs_Intelligence_AI"


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
            f"INSERT INTO {_DB}.feedback (message, context) VALUES (:m, :c)"),
            {"m": message[:5000], "c": context})
        return jsonify({"ok": True, "id": int(res.lastrowid)})


@bp.route("", methods=["GET"])
def api_feedback_list():
    """List feedback, newest first."""
    with get_engine().connect() as conn:
        rows = conn.execute(text(
            f"SELECT id, message, context, created_at "
            f"FROM {_DB}.feedback ORDER BY id DESC LIMIT 500")).mappings().all()
    return jsonify({"ok": True, "feedback": [
        {"id": m["id"], "message": m["message"], "context": m["context"],
         "created_at": str(m["created_at"])} for m in rows]})
