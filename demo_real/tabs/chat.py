"""
tabs/chat.py — Chat tab (conversational job search).

Routes:
  POST /api/chat         → send a message, get job results + reply
  POST /api/chat/reset   → clear conversation history for a session
"""
from flask import Blueprint, request, jsonify
from core.chat import send_message, clear_session, enrich_jobs_from_db

bp = Blueprint("chat", __name__, url_prefix="/api")


@bp.route("/chat", methods=["POST"])
def api_chat():
    """Body: { session_id, message, lang?, filters?, max_results? }"""
    body        = request.get_json(silent=True) or {}
    session_id  = body.get("session_id", "default")
    message     = body.get("message", "").strip()
    lang        = body.get("lang", "auto")
    filters     = body.get("filters") or {}
    max_results = int(body.get("max_results", 20))

    if not message:
        return jsonify({"ok": False, "error": "message required"}), 400

    try:
        result = send_message(session_id, message, lang=lang,
                              filters=filters, max_results=max_results)
        result["jobs"] = enrich_jobs_from_db(result.get("jobs") or [])
        return jsonify({"ok": True, **result})
    except Exception as e:
        import traceback
        return jsonify({"ok": False, "error": str(e), "trace": traceback.format_exc()}), 500


@bp.route("/chat/reset", methods=["POST"])
def api_chat_reset():
    body       = request.get_json(silent=True) or {}
    session_id = body.get("session_id", "default")
    clear_session(session_id)
    return jsonify({"ok": True})
