"""
reporting/session_chat.py — grounded advisor chats for the Analytics and Radar tabs.

Two multi-turn chats that return prose guidance:
  - analytics_chat : the Analytics-tab assistant, grounded in the insights the user saved
                     during a session (helps them shape the report).
  - radar_chat     : the Radar-tab advisor, grounded in the current market snapshot.

Both use Structured Outputs (responses.parse → AdvisorReply, a single `answer` markdown
string) via the shared client, replacing the legacy `chat.completions` + raw `OpenAI()`
calls relocated from the analytics/radar blueprints in rework 2.4. History is passed in on
each turn (no server-side session), forwarded to the Responses API as a list of input
messages. Either raises on no API key / model error — the blueprint turns that into a 500.
"""
import logging

from jobs_intelligence_ai import config
from jobs_intelligence_ai.shared.llm import get_client
from .config import ADVISOR_MODEL, SUMMARY_CHAT_PROMPT, RADAR_CHAT_PROMPT, AdvisorReply

logger = logging.getLogger(__name__)

_TYPE_NAMES = {
    "recommendation": "Recommendation",
    "opportunity":    "Top Opportunity",
    "underserved":    "Underserved Market",
    "urgency":        "Urgency Alert",
    "trend":          "Trend Insight",
    "chat":           "Chat Insight",
}


def _history_messages(history: list[dict], limit: int) -> list[dict]:
    """Keep the last `limit` valid {role, content} turns for the Responses API input list."""
    msgs = []
    for h in history[-limit:]:
        if h.get("role") in ("user", "assistant") and h.get("content"):
            msgs.append({"role": h["role"], "content": h["content"]})
    return msgs


def _answer(instructions: str, input_messages: list[dict]) -> str:
    """Run one Structured-Outputs advisor call and return the reply string."""
    resp = get_client().responses.parse(
        model=ADVISOR_MODEL,
        instructions=instructions,
        input=input_messages,
        text_format=AdvisorReply,
    )
    if resp.output_parsed is None:
        raise ValueError("Model returned no reply")
    return resp.output_parsed.answer


def analytics_chat(history: list[dict], items: list[dict]) -> str:
    """Analytics-tab assistant: a prose reply grounded in the user's saved summary items.

    `history` is the running conversation ([{role, content}]); its last turn is the user's
    latest message. Returns the assistant's reply string; raises on no API key / model error."""
    if not config.OPENAI_API_KEY:
        raise RuntimeError("OpenAI API key not configured")

    lines = ["The user has saved the following insights during their analytics session:", ""]
    for i, item in enumerate(items, 1):
        tname   = _TYPE_NAMES.get(item.get("type", "chat"), "Insight")
        preview = (item.get("content") or "")[:200]
        lines.append(f"{i}. [{tname}] {item.get('label', '')} — {preview}")
    instructions = SUMMARY_CHAT_PROMPT + "\n\n" + "\n".join(lines)

    return _answer(instructions, _history_messages(history, 10))


def radar_chat(message: str, history: list[dict], context: dict) -> str:
    """Radar-tab advisor: a prose reply grounded in the current market snapshot `context`.

    `message` is the latest user turn; `history` the prior conversation. Returns the reply
    string; raises on no API key / model error."""
    if not config.OPENAI_API_KEY:
        raise RuntimeError("OpenAI API key not configured")

    instructions = RADAR_CHAT_PROMPT + "\n\n" + _format_snapshot(context or {})
    msgs = _history_messages(history, 8)
    msgs.append({"role": "user", "content": message})
    return _answer(instructions, msgs)


def _format_snapshot(ctx: dict) -> str:
    """Render the radar market snapshot the advisor reasons over (from the tab's context)."""
    lines = ["=== MARKET SNAPSHOT ==="]

    t = ctx.get("totals") or {}
    if t:
        lines += [
            f"Active jobs      : {t.get('total_active', '?')}",
            f"Stale 30+ days   : {t.get('stale_30', '?')}  ({round(t.get('stale_30', 0) / max(t.get('total_active', 1), 1) * 100)}%)",
            f"Stale 60+ days   : {t.get('stale_60', '?')}",
            f"Urgent ≤14 days  : {t.get('urgent_14d', '?')}",
            f"Sectors tracked  : {t.get('sector_count', '?')}",
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
            lines.append(f"  • {u.get('label')}: {u.get('count')} jobs, {u.get('note', '')}")

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
                f"{s.get('stale_30', 0)} stale30, {s.get('urgent_deadline', 0)} urgent, avg {sal}"
            )

    if ctx.get("filters"):
        lines += ["", f"Active scope filters: {ctx['filters']}"]

    return "\n".join(lines)
