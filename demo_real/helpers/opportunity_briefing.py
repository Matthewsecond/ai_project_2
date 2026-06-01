"""
helpers/opportunity_briefing.py — LLM-powered opportunity analysis for the Radar tab.

Receives structured snapshot data from stats/opportunity.py and asks the model
to reason about WHERE the best recruitment opportunities currently are — which
sectors are underserved, which states have urgency, which portals are stale, etc.

No formulas: the LLM does the synthesis.  The stats module just extracts facts.
"""
import json
import logging
import re
from datetime import date

from openai import OpenAI
import config

logger = logging.getLogger(__name__)

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=config.OPENAI_API_KEY)
    return _client


_SYSTEM = """\
You are a recruitment market analyst for Austria's labor market.
You receive structured snapshot data about currently active job postings:
  - Sector (occupational group) breakdown: volume, staleness, salary, urgency
  - State (Bundesland) breakdown: volume, staleness, urgency
  - Portal breakdown: volume, staleness
  - Weekly volume trend
  - Summary totals

Your task: produce a concise opportunity briefing for a recruitment professional.

Focus on:
  1. TOP OPPORTUNITIES — which sectors/states/portals show the most promising signals
     (high volume + not yet stale, urgent deadlines, above-average salaries).
  2. UNDERSERVED MARKETS — sectors or states with high staleness (jobs sitting 30+ days
     unfilled), or with above-average salaries but few applicants implied.
  3. URGENCY ALERT — any sectors/states with many urgent deadlines in the next 14 days.
  4. VOLUME TREND — is the market accelerating or decelerating?  What does recent trend say?
  5. RECOMMENDED FOCUS — 3-5 concrete actionable recommendations for where to source.

Rules:
  - Be specific: name the actual sectors, states, portals from the data.
  - Back every claim with the numbers given, but write them as readable sentences —
    e.g. "584 open roles in Vienna, 8 of which are urgent" not "(584 jobs, Urgent 8, AvgSal €31,590)".
  - Each recommendation must be a complete, plain-English sentence a non-technical manager
    can understand. Avoid metric abbreviations like AvgDays, Stale60, Stale30 in the text itself;
    instead say "jobs sitting unfilled for 60+ days" or "average time to fill".
  - Avoid generic platitudes.
  - Tone: clear and direct, like a briefing to a senior recruiter who values plain language.

Respond with ONLY a valid JSON object — no prose, no markdown:
{
  "top_opportunities": [
    { "label": "Sector / State", "reason": "...", "signal": "strong|moderate" }
  ],
  "underserved": [
    { "label": "...", "reason": "..." }
  ],
  "urgency_alerts": [
    { "label": "...", "count": 12, "note": "..." }
  ],
  "trend_summary": "One or two sentences about the volume trend.",
  "recommendations": [
    "Concrete action 1",
    "Concrete action 2"
  ],
  "headline": "One punchy headline summarising today's market"
}
"""


def generate_briefing(
    sector_snapshot: list[dict],
    state_snapshot: list[dict],
    portal_snapshot: list[dict],
    volume_trend: list[dict],
    summary_totals: dict,
) -> dict:
    """
    Run one LLM call and return the parsed briefing dict.
    Falls back to a minimal static structure on error or missing API key.
    """
    if not config.OPENAI_API_KEY:
        return _fallback(summary_totals)

    user_input = _build_prompt(
        sector_snapshot, state_snapshot,
        portal_snapshot, volume_trend, summary_totals
    )

    try:
        client = _get_client()
        response = client.responses.create(
            model=config.CLASSIFIER_MODEL,
            instructions=_SYSTEM,
            input=user_input,
        )
        raw = (response.output_text or "").strip()
        raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.MULTILINE).strip()
        result = json.loads(raw)
        if not isinstance(result, dict):
            raise ValueError("Expected JSON object")
        return result
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

_FILTER_SYSTEM = """\
You are a labor market analyst for Austria's job market.
The user describes the type of roles they want to focus on.
Your job: select the most relevant filters from the provided option lists.

Rules:
- occ_groups: return ONLY strings that appear EXACTLY in the provided sectors list (copy-paste exact).
  Select up to 12 groups maximum. Prefer specificity over breadth.
- states: return ONLY strings from the provided states list. Leave empty if no geographic focus.
- portals: return ONLY strings from the provided portals list. Leave empty unless user mentions
  a specific platform or source.
- min_salary: integer (monthly EUR) if the user mentions pay expectations, otherwise null.
- explanation: 2–3 sentences in English explaining why you chose these filters.
- count_hint: rough estimate like "~200–400 jobs expected".

Respond ONLY with valid JSON — no prose, no markdown fences:
{
  "occ_groups": ["exact sector name", ...],
  "states": [],
  "portals": [],
  "min_salary": null,
  "explanation": "...",
  "count_hint": "..."
}
"""


def suggest_filters(
    query: str,
    sectors: list[str],
    states: list[str],
    portals: list[str],
) -> dict:
    """
    Ask the LLM to map a free-text query to concrete filter selections.
    Returns dict with occ_groups, states, portals, min_salary, explanation, count_hint.
    Falls back gracefully if the API call fails.
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
        client = _get_client()
        response = client.responses.create(
            model=config.CLASSIFIER_MODEL,
            instructions=_FILTER_SYSTEM,
            input=user_msg,
        )
        raw = (response.output_text or "").strip()
        raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.MULTILINE).strip()
        result = json.loads(raw)
        if not isinstance(result, dict):
            raise ValueError("Expected JSON object")

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
