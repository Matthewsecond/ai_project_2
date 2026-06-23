"""
reporting/opportunity_briefing.py — LLM-powered opportunity analysis for the Radar tab.

Receives structured snapshot data from stats/opportunity.py and asks the model to reason
about WHERE the best recruitment opportunities currently are — which sectors are
underserved, which states have urgency, which portals are stale, etc. Plus an AI filter
suggestion that maps a free-text focus query onto concrete Radar filters.

No formulas: the LLM does the synthesis. The stats module just extracts facts. Both calls
use Structured Outputs (responses.parse → validated output_parsed) via the shared client,
and fall back to a minimal static structure on error or missing API key.
"""
import logging
from datetime import date

from jobs_intelligence_ai import config
from jobs_intelligence_ai.shared.llm import get_client
from .config import (
    BRIEFING_MODEL, BRIEFING_PROMPT, BriefingResult,
    FILTER_PROMPT, FilterSuggestion,
)

logger = logging.getLogger(__name__)


def generate_briefing(
    sector_snapshot: list[dict],
    state_snapshot: list[dict],
    portal_snapshot: list[dict],
    volume_trend: list[dict],
    summary_totals: dict,
) -> dict:
    """
    Run one Structured-Outputs LLM call and return the parsed briefing dict.
    Falls back to a minimal static structure on error or missing API key.
    """
    if not config.OPENAI_API_KEY:
        return _fallback(summary_totals)

    user_input = _build_prompt(
        sector_snapshot, state_snapshot,
        portal_snapshot, volume_trend, summary_totals
    )

    try:
        response = get_client().responses.parse(
            model=BRIEFING_MODEL,
            instructions=BRIEFING_PROMPT,
            input=user_input,
            text_format=BriefingResult,
        )
        if response.output_parsed is None:
            raise ValueError("no structured output")
        return response.output_parsed.model_dump()
    except Exception as exc:
        logger.warning("Opportunity briefing AI call failed (%s) — using fallback", exc)
        return _fallback(summary_totals)


# ── Prompt builder ────────────────────────────────────────────────────────────

def _build_prompt(sectors, states, portals, trend, totals) -> str:
    today = date.today().isoformat()
    lines = [f"Data snapshot for: {today}", ""]

    # Summary
    lines += [
        "=== SUMMARY TOTALS ===",
        f"Active jobs      : {totals.get('total_active', '?')}",
        f"Stale 30+ days   : {totals.get('stale_30', '?')}",
        f"Stale 60+ days   : {totals.get('stale_60', '?')}",
        f"Urgent (≤14 days): {totals.get('urgent_14d', '?')}",
        f"Sectors tracked  : {totals.get('sector_count', '?')}",
        f"States tracked   : {totals.get('state_count', '?')}",
        "",
    ]

    # Sectors
    lines.append("=== SECTOR SNAPSHOT (top 20 by volume) ===")
    lines.append(
        f"{'Sector':<40} {'Jobs':>6} {'AvgDays':>8} {'Stale30':>8} {'Stale60':>8} "
        f"{'Urgent':>7} {'AvgSal':>9}"
    )
    for s in (sectors[:20] if sectors else []):
        lines.append(
            f"{str(s.get('occ_group','')):<40} "
            f"{s.get('total_jobs',0):>6} "
            f"{_fmt(s.get('avg_days_in_system')):>8} "
            f"{s.get('stale_30',0):>8} "
            f"{s.get('stale_60',0):>8} "
            f"{s.get('urgent_deadline',0):>7} "
            f"{_sal(s.get('avg_salary')):>9}"
        )
    lines.append("")

    # States
    lines.append("=== STATE SNAPSHOT ===")
    lines.append(
        f"{'State':<25} {'Jobs':>6} {'AvgDays':>8} {'Stale30':>8} {'Urgent':>7} {'AvgSal':>9}"
    )
    for s in (states or []):
        lines.append(
            f"{str(s.get('state','')):<25} "
            f"{s.get('total_jobs',0):>6} "
            f"{_fmt(s.get('avg_days_in_system')):>8} "
            f"{s.get('stale_30',0):>8} "
            f"{s.get('urgent_deadline',0):>7} "
            f"{_sal(s.get('avg_salary')):>9}"
        )
    lines.append("")

    # Portals
    lines.append("=== PORTAL SNAPSHOT ===")
    lines.append(
        f"{'Portal':<25} {'Jobs':>6} {'AvgDays':>8} {'Stale60':>8} {'AvgSal':>9}"
    )
    for p in (portals or []):
        lines.append(
            f"{str(p.get('portal','')):<25} "
            f"{p.get('total_jobs',0):>6} "
            f"{_fmt(p.get('avg_days_in_system')):>8} "
            f"{p.get('stale_60',0):>8} "
            f"{_sal(p.get('avg_salary')):>9}"
        )
    lines.append("")

    # Volume trend
    lines.append("=== WEEKLY VOLUME TREND (created_at) ===")
    lines.append(f"{'Week':>10}  {'WeekStart':<12} {'JobsCreated':>12}")
    for w in (trend or []):
        lines.append(
            f"{str(w.get('year_week','')):>10}  "
            f"{str(w.get('week_start','')):12} "
            f"{w.get('jobs_created',0):>12}"
        )

    return "\n".join(lines)


def _fmt(val) -> str:
    if val is None:
        return "—"
    return f"{float(val):.1f}"


def _sal(val) -> str:
    if val is None:
        return "—"
    try:
        return f"€{int(float(val)):,}"
    except (ValueError, TypeError):
        return "—"


# ── AI Filter Suggestion ──────────────────────────────────────────────────────

def suggest_filters(
    query: str,
    sectors: list[str],
    states: list[str],
    portals: list[str],
) -> dict:
    """
    Ask the LLM to map a free-text query to concrete filter selections (Structured Outputs).
    Returns dict with occ_groups, states, portals, min_salary, explanation, count_hint.
    Falls back gracefully if the API call fails. The returned occ_groups/states/portals are
    re-validated against the provided lists so only real options survive.
    """
    if not config.OPENAI_API_KEY:
        return _filter_fallback("No OpenAI API key configured.")

    # Build the user message — sectors first (most important), then states & portals
    sector_block = "\n".join(sectors[:300])  # already sorted by frequency
    state_block  = "\n".join(states)
    portal_block = ", ".join(portals[:50])   # portals are less relevant, keep compact

    user_msg = (
        f'User query: "{query}"\n\n'
        f"Available occupational groups ({len(sectors)} total, ordered by job count):\n"
        f"{sector_block}\n\n"
        f"Available states:\n{state_block}\n\n"
        f"Available portals (only use if explicitly relevant):\n{portal_block}"
    )

    try:
        response = get_client().responses.parse(
            model=BRIEFING_MODEL,
            instructions=FILTER_PROMPT,
            input=user_msg,
            text_format=FilterSuggestion,
        )
        if response.output_parsed is None:
            raise ValueError("no structured output")
        result = response.output_parsed.model_dump()

        # Validate: keep only exact matches from provided lists
        valid_sectors = set(sectors)
        valid_states  = set(states)
        valid_portals = set(portals)
        result["occ_groups"] = [g for g in result.get("occ_groups", []) if g in valid_sectors]
        result["states"]     = [s for s in result.get("states",     []) if s in valid_states]
        result["portals"]    = [p for p in result.get("portals",    []) if p in valid_portals]
        return result

    except Exception as exc:
        logger.warning("Filter suggestion AI call failed (%s)", exc)
        return _filter_fallback(str(exc))


def _filter_fallback(reason: str) -> dict:
    return {
        "occ_groups":  [],
        "states":      [],
        "portals":     [],
        "min_salary":  None,
        "explanation": f"AI suggestion unavailable: {reason}",
        "count_hint":  "",
    }


# ── Fallback ──────────────────────────────────────────────────────────────────

def _fallback(totals: dict) -> dict:
    active  = totals.get("total_active", 0)
    stale30 = totals.get("stale_30", 0)
    urgent  = totals.get("urgent_14d", 0)
    stale_pct = round(stale30 / active * 100) if active else 0
    return {
        "headline":         f"{active:,} active jobs — {stale_pct}% stale 30+ days, {urgent} urgent",
        "top_opportunities": [],
        "underserved":       [],
        "urgency_alerts":    [{"label": "All sectors", "count": urgent,
                               "note": "Urgent deadlines within 14 days"}] if urgent else [],
        "trend_summary":     "Trend data unavailable (AI briefing offline).",
        "recommendations":   ["Check back once AI briefing is online."],
    }
