"""
tabs/analytics.py — Analytics Summary tab.

Routes:
  POST /api/analytics/report   → generate AI-elaborated PDF from saved summary items
  POST /api/analytics/chat     → multi-turn chat grounded in saved summary items
"""
from flask import Blueprint, request, jsonify, Response
import config

bp = Blueprint("analytics", __name__, url_prefix="/api/analytics")


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
        from helpers.report_generator import elaborate_items, generate_pdf
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

    try:
        from openai import OpenAI
        client   = OpenAI(api_key=config.OPENAI_API_KEY)
        system   = _build_summary_chat_system(items)
        messages = [{"role": "system", "content": system}]
        for h in history[-10:]:
            if h.get("role") in ("user", "assistant") and h.get("content"):
                messages.append({"role": h["role"], "content": h["content"]})

        resp   = client.chat.completions.create(
            model=config.CHAT_MODEL, messages=messages,
            max_completion_tokens=600, temperature=0.55,
        )
        answer = resp.choices[0].message.content or ""
        return jsonify({"ok": True, "answer": answer})
    except Exception as e:
        import traceback
        return jsonify({"ok": False, "error": str(e), "trace": traceback.format_exc()}), 500


# ── System-prompt builder ────────────────────────────────────────────────────

def _build_summary_chat_system(items: list) -> str:
    type_names = {
        "recommendation": "Recommendation",
        "opportunity":    "Top Opportunity",
        "underserved":    "Underserved Market",
        "urgency":        "Urgency Alert",
        "trend":          "Trend Insight",
        "chat":           "Chat Insight",
    }
    lines = [
        "You are an expert HR analytics assistant helping an HR professional in Austria prepare their session report.",
        "The user has saved the following insights during their analytics session:",
        "",
    ]
    for i, item in enumerate(items, 1):
        tname   = type_names.get(item.get("type", "chat"), "Insight")
        preview = (item.get("content") or "")[:200]
        lines.append(f"{i}. [{tname}] {item.get('label','')} — {preview}")

    lines += [
        "",
        "Your role: help the user think through the report — what to include, what's most important,",
        "how to frame findings, suggest a logical order, or clarify any of the data points.",
        "Be concise and direct. These are HR professionals, not data analysts.",
        "Use **bold** for key points or figures (markdown will be rendered).",
        "Keep responses to 3 short paragraphs max.",
    ]
    return "\n".join(lines)
