"""
tabs/radar.py — Opportunities Radar tab.

Routes:
  GET  /api/opportunity                    → full radar snapshot (sectors, states, portals, trend)
  GET  /api/opportunity/jobs               → stale / urgent job finder
  POST /api/opportunity/filter-assist      → map free-text query → filter selections
  POST /api/opportunity/chat               → multi-turn chat grounded in radar snapshot
"""
from flask import Blueprint, request, jsonify
from jobs_intelligence_ai import config

bp = Blueprint("radar", __name__, url_prefix="/api/opportunity")


@bp.before_request
def _require_analytics_support():
    """Opportunities Radar is built on occupational_group + AT-specific joins.
    Countries without it (e.g. Slovakia) get a clean 404 instead of a DB error."""
    if not config.HAS_ANALYTICS:
        return jsonify({
            "ok": False,
            "error": f"Opportunities Radar is not available for {config.COUNTRY_LABEL}.",
        }), 404


@bp.route("", methods=["GET"])
def api_opportunity():
    """
    Optional query params: briefing, weeks, state, portal, occ_group, min_salary,
                           occ_groups[], states[], portals[] (multi-value).
    """
    include_briefing = request.args.get("briefing", "1") != "0"
    weeks            = int(request.args.get("weeks", 8))

    filters = {k: request.args.get(k) or None for k in ("state", "portal", "occ_group", "min_salary")}
    filters = {k: v for k, v in filters.items() if v}

    _occ_groups = [g for g in request.args.getlist("occ_groups") if g]
    _states     = [s for s in request.args.getlist("states")     if s]
    _portals    = [p for p in request.args.getlist("portals")    if p]
    if _occ_groups: filters["occ_groups"] = _occ_groups
    if _states:     filters["states"]     = _states
    if _portals:    filters["portals"]    = _portals

    try:
        from jobs_intelligence_ai.stats.opportunity import (
            get_sector_snapshot, get_state_snapshot, get_portal_snapshot,
            get_volume_trend, get_summary_totals,
        )
        sectors = get_sector_snapshot(limit=40, filters=filters)
        states  = get_state_snapshot(filters=filters)
        portals = get_portal_snapshot(filters=filters)
        trend   = get_volume_trend(weeks=weeks, filters=filters)
        totals  = get_summary_totals(filters=filters)

        briefing = {}
        if include_briefing:
            from jobs_intelligence_ai.services.opportunity_briefing import generate_briefing
            briefing = generate_briefing(sectors, states, portals, trend, totals)

        return jsonify({
            "ok":      True,
            "totals":  totals,
            "sectors": sectors,
            "states":  states,
            "portals": portals,
            "trend":   trend,
            "briefing": briefing,
            "filters": filters,
        })
    except Exception as e:
        import traceback
        return jsonify({"ok": False, "error": str(e), "trace": traceback.format_exc()}), 500


@bp.route("/jobs", methods=["GET"])
def api_opportunity_jobs():
    """
    Query params: mode (stale|urgent), limit, occ_group, state, portal,
                  min_days (stale), deadline (urgent).
    """
    mode      = request.args.get("mode", "stale")
    limit     = int(request.args.get("limit", 50))
    occ_group = request.args.get("occ_group") or None
    state     = request.args.get("state") or None
    portal    = request.args.get("portal") or None

    try:
        from jobs_intelligence_ai.stats.opportunity import get_stale_jobs, get_urgent_jobs
        if mode == "urgent":
            deadline = int(request.args.get("deadline", 14))
            jobs = get_urgent_jobs(deadline_days=deadline, limit=limit)
        else:
            min_days = int(request.args.get("min_days", 45))
            jobs = get_stale_jobs(min_days=min_days, limit=limit,
                                  occ_group=occ_group, state=state, portal=portal)
        return jsonify({"ok": True, "count": len(jobs), "jobs": jobs})
    except Exception as e:
        import traceback
        return jsonify({"ok": False, "error": str(e), "trace": traceback.format_exc()}), 500


@bp.route("/filter-assist", methods=["POST"])
def api_opportunity_filter_assist():
    """
    Body: { query, sectors?, states?, portals? }
    Returns: { occ_groups, states, portals, min_salary, explanation, count_hint }
    """
    data    = request.get_json(silent=True) or {}
    query   = (data.get("query") or "").strip()
    sectors = data.get("sectors") or []
    states  = data.get("states")  or []
    portals = data.get("portals") or []

    if not query:
        return jsonify({"ok": False, "error": "query is required"}), 400

    try:
        from jobs_intelligence_ai.services.opportunity_briefing import suggest_filters
        result = suggest_filters(query, sectors, states, portals)
        return jsonify({"ok": True, **result})
    except Exception as e:
        import traceback
        return jsonify({"ok": False, "error": str(e), "trace": traceback.format_exc()}), 500


@bp.route("/chat", methods=["POST"])
def api_opportunity_chat():
    """
    Body: { message, history?: [{role, content}], context?: dict }
    Multi-turn chat grounded in the current radar snapshot.
    """
    data    = request.get_json(silent=True) or {}
    message = (data.get("message") or "").strip()
    history = data.get("history") or []
    context = data.get("context") or {}

    if not message:
        return jsonify({"ok": False, "error": "message required"}), 400
    if not config.OPENAI_API_KEY:
        return jsonify({"ok": False, "error": "OpenAI API key not configured"}), 503

    try:
        from openai import OpenAI
        client   = OpenAI(api_key=config.OPENAI_API_KEY)
        system   = _build_radar_chat_system(context)
        messages = [{"role": "system", "content": system}]
        for h in history[-8:]:
            if h.get("role") in ("user", "assistant") and h.get("content"):
                messages.append({"role": h["role"], "content": h["content"]})
        messages.append({"role": "user", "content": message})

        resp   = client.chat.completions.create(
            model=config.CHAT_MODEL, messages=messages,
            max_completion_tokens=600, temperature=0.65,
        )
        answer = resp.choices[0].message.content or ""
        return jsonify({"ok": True, "answer": answer})
    except Exception as e:
        import traceback
        return jsonify({"ok": False, "error": str(e), "trace": traceback.format_exc()}), 500


# ── System-prompt builder ────────────────────────────────────────────────────

def _build_radar_chat_system(ctx: dict) -> str:
    lines = [
        "You are a recruitment advisor helping HR professionals in Austria understand their job market.",
        "Your audience is HR managers and recruiters — not data analysts. They need clear, actionable guidance.",
        "",
        "Tone and format rules (follow strictly):",
        "- Lead every answer with the key action or decision, then briefly explain why using 1-2 numbers.",
        "- Never open with a statistic. Open with what the person should DO or KNOW.",
        "- Use plain business language. Avoid jargon like 'backlog-conversion', 'top-of-funnel', 'stale demand'.",
        "  Say 'unfilled for 30+ days' not 'stale'. Say 'harder to fill' not 'underserved'.",
        "- Keep it to 2-3 short paragraphs. No walls of text.",
        "- Use **bold** for the most important figures or action words (markdown will be rendered).",
        "- Use bullet points only when listing 3+ parallel items.",
        "- If the data does not contain what was asked, say so in one sentence.",
        "",
        "=== MARKET SNAPSHOT ===",
    ]

    t = ctx.get("totals") or {}
    if t:
        lines += [
            f"Active jobs      : {t.get('total_active','?')}",
            f"Stale 30+ days   : {t.get('stale_30','?')}  ({round(t.get('stale_30',0)/max(t.get('total_active',1),1)*100)}%)",
            f"Stale 60+ days   : {t.get('stale_60','?')}",
            f"Urgent ≤14 days  : {t.get('urgent_14d','?')}",
            f"Sectors tracked  : {t.get('sector_count','?')}",
        ]

    if ctx.get("headline"):
        lines += ["", f"Headline: {ctx['headline']}"]

    if ctx.get("top_opportunities"):
        lines += ["", "Top opportunities:"]
        for o in ctx["top_opportunities"][:6]:
            lines.append(f"  • {o.get('label')} — {o.get('reason')} [signal:{o.get('signal')}]")

    if ctx.get("underserved"):
        lines += ["", "Underserved markets:"]
        for u in ctx["underserved"][:4]:
            lines.append(f"  • {u.get('label')} — {u.get('reason')}")

    if ctx.get("urgency_alerts"):
        lines += ["", "Urgency alerts:"]
        for u in ctx["urgency_alerts"][:4]:
            lines.append(f"  • {u.get('label')}: {u.get('count')} jobs, {u.get('note','')}")

    if ctx.get("trend_summary"):
        lines += ["", f"Volume trend: {ctx['trend_summary']}"]

    if ctx.get("recommendations"):
        lines += ["", "Recommendations:"]
        for i, r in enumerate(ctx["recommendations"][:5], 1):
            lines.append(f"  {i}. {r}")

    if ctx.get("top_sectors"):
        lines += ["", "Top sectors (by volume):"]
        for s in ctx["top_sectors"][:8]:
            sal = f"€{s.get('avg_salary'):,}" if s.get("avg_salary") else "—"
            lines.append(
                f"  • {s.get('occ_group')}: {s.get('total_jobs')} jobs, "
                f"{s.get('stale_30',0)} stale30, {s.get('urgent_deadline',0)} urgent, avg {sal}"
            )

    if ctx.get("filters"):
        lines += ["", f"Active scope filters: {ctx['filters']}"]

    return "\n".join(lines)
