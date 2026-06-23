"""
tabs/analytics.py — Analytics Summary tab.

Routes:
  POST /api/analytics/report   → generate AI-elaborated PDF from saved summary items
  POST /api/analytics/chat     → multi-turn chat grounded in saved summary items
"""
from flask import Blueprint, request, jsonify, Response
from jobs_intelligence_ai import config

bp = Blueprint("analytics", __name__, url_prefix="/api/analytics")


@bp.before_request
def _require_analytics_support():
    """The analytics report is built on occupational_group + AT geometry.
    Countries without it (e.g. Slovakia) get a clean 404 instead of a DB error."""
    if not config.HAS_ANALYTICS:
        return jsonify({
            "ok": False,
            "error": f"Analytics is not available for {config.COUNTRY_LABEL}.",
        }), 404


@bp.route("/report", methods=["POST"])
def api_analytics_report():
    """
    Body: { items: [{type, label, content}], context?: dict, charts?: [{title, data_url}] }
    """
    data   = request.get_json(silent=True) or {}
    items  = data.get("items") or []
    context = data.get("context") or {}
    charts  = data.get("charts") or []

    if not items:
        return jsonify({"ok": False, "error": "No items provided"}), 400

    try:
        from jobs_intelligence_ai.services.reporting import elaborate_items, generate_pdf
        elaborated = elaborate_items(items, context)
        pdf_bytes  = generate_pdf(elaborated, context, charts=charts)
        return Response(
            pdf_bytes,
            mimetype="application/pdf",
            headers={
                "Content-Disposition": 'attachment; filename="analytics-report.pdf"',
                "Content-Length": str(len(pdf_bytes)),
            },
        )
    except Exception as e:
        import traceback
        return jsonify({"ok": False, "error": str(e), "trace": traceback.format_exc()}), 500


@bp.route("/chat", methods=["POST"])
def api_analytics_chat():
    """
    Body: { history: [{role, content}], items?: [{type, label, content}] }
    Multi-turn chat grounded in the user's saved summary items.
    """
    data    = request.get_json(silent=True) or {}
    history = data.get("history") or []
    items   = data.get("items") or []

    if not history:
        return jsonify({"ok": False, "error": "history required"}), 400
    if not config.OPENAI_API_KEY:
        return jsonify({"ok": False, "error": "OpenAI API key not configured"}), 503

    from jobs_intelligence_ai.services.reporting import analytics_chat
    try:
        answer = analytics_chat(history, items)
        return jsonify({"ok": True, "answer": answer})
    except Exception as e:
        import traceback
        return jsonify({"ok": False, "error": str(e), "trace": traceback.format_exc()}), 500
