"""
reporting/company_summary.py — AI summary of a company's hiring profile (Company tab).

Given the aggregated stats the company blueprint computes from the DB (active postings, top
roles/occupational groups, salary range, states, portals, work types), produce a 2-3 sentence
recruiter-facing summary. Uses Structured Outputs (responses.parse → CompanySummary, a single
prose `summary`) via the shared client. The summary is an optional flourish on the company
response, so this returns "" on missing API key or any error rather than raising — relocated
from the inline chat.completions call in the company blueprint and converted in rework 2.4.
"""
import logging

from jobs_intelligence_ai import config
from jobs_intelligence_ai.shared.llm import get_client
from .config import COMPANY_SUMMARY_MODEL, COMPANY_SUMMARY_PROMPT, CompanySummary

logger = logging.getLogger(__name__)


def summarize_company(company_name, total, top_titles, top_occ, sal_stats,
                      states, portals, work_types) -> str:
    """Return a 2-3 sentence AI summary of the company's hiring profile, or "" on no key/error."""
    if not config.OPENAI_API_KEY:
        return ""

    titles_str = ", ".join(f"{t['title']} ×{t['count']}" for t in top_titles[:5])
    occ_str    = ", ".join(f"{o['group']} ({o['count']})" for o in top_occ[:4])
    sal_str    = (
        f"€{sal_stats['min']:,}–€{sal_stats['max']:,}, average €{sal_stats['mean']:,}"
        if sal_stats else "not disclosed"
    )
    user_input = (
        f"Company: {company_name}\n"
        f"Active job postings: {total}\n"
        f"Top roles: {titles_str or '—'}\n"
        f"Occupational groups: {occ_str or '—'}\n"
        f"Salary range: {sal_str}\n"
        f"Active states: {', '.join(states[:5]) if states else '—'}\n"
        f"Job portals: {', '.join(portals) if portals else '—'}\n"
        f"Work types: {', '.join(f'{k} ({v})' for k, v in work_types.items()) or '—'}\n"
    )

    try:
        resp = get_client().responses.parse(
            model=COMPANY_SUMMARY_MODEL,
            instructions=COMPANY_SUMMARY_PROMPT,
            input=user_input,
            text_format=CompanySummary,
        )
        if resp.output_parsed is None:
            return ""
        return (resp.output_parsed.summary or "").strip()
    except Exception as exc:
        logger.warning("Company summary AI call failed (%s)", exc)
        return ""
