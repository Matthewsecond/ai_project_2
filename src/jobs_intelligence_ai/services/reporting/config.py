"""
config.py — settings for the `reporting` service (flat constants, per rework §5).

The single home for this module's knobs: the model each call uses, the per-call prompts,
and the Structured-Outputs Pydantic schemas the LLM calls are constrained to.

Three LLM calls live in this package, all converted to Structured Outputs in rework 2.3 #4
(`responses.parse(text_format=<schema below>)` → validated `output_parsed`, no
"respond with ONLY JSON" boilerplate):
  - opportunity_briefing.generate_briefing → BriefingResult     (CLASSIFIER_MODEL)
  - opportunity_briefing.suggest_filters   → FilterSuggestion   (CLASSIFIER_MODEL)
  - report_generator.elaborate_items       → ElaborationList    (CHAT_MODEL)

report_pipeline.py is a pure PDF builder (no LLM call) — nothing to configure here.
"""
from typing import Literal, Optional

from pydantic import BaseModel

from jobs_intelligence_ai import config

# Briefing + filter suggestion are cheap classification/synthesis → classifier model.
# The session-report elaboration is long-form reasoning → the main chat model.
BRIEFING_MODEL    = config.CLASSIFIER_MODEL
ELABORATION_MODEL = config.CHAT_MODEL


# ── opportunity_briefing.generate_briefing ─────────────────────────────────────
BRIEFING_PROMPT = """\
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
     (high volume + not yet stale, urgent deadlines, above-average salaries). Tag each
     signal "strong" or "moderate".
  2. UNDERSERVED MARKETS — sectors or states with high staleness (jobs sitting 30+ days
     unfilled), or with above-average salaries but few applicants implied.
  3. URGENCY ALERTS — any sectors/states with many urgent deadlines in the next 14 days,
     with the count.
  4. TREND SUMMARY — is the market accelerating or decelerating? What does recent trend say?
  5. RECOMMENDATIONS — 3-5 concrete actionable recommendations for where to source.
  6. HEADLINE — one punchy headline summarising today's market.

Rules:
  - Be specific: name the actual sectors, states, portals from the data.
  - Back every claim with the numbers given, but write them as readable sentences —
    e.g. "584 open roles in Vienna, 8 of which are urgent" not "(584 jobs, Urgent 8, AvgSal €31,590)".
  - Each recommendation must be a complete, plain-English sentence a non-technical manager
    can understand. Avoid metric abbreviations like AvgDays, Stale60, Stale30 in the text itself;
    instead say "jobs sitting unfilled for 60+ days" or "average time to fill".
  - Avoid generic platitudes.
  - Tone: clear and direct, like a briefing to a senior recruiter who values plain language."""


class _Opportunity(BaseModel):
    label: str
    reason: str
    signal: Literal["strong", "moderate"]


class _Underserved(BaseModel):
    label: str
    reason: str


class _UrgencyAlert(BaseModel):
    label: str
    count: int
    note: str


class BriefingResult(BaseModel):
    """the opportunity briefing for the Radar tab — sectors/states/portals synthesis."""
    top_opportunities: list[_Opportunity]
    underserved: list[_Underserved]
    urgency_alerts: list[_UrgencyAlert]
    trend_summary: str
    recommendations: list[str]
    headline: str


# ── opportunity_briefing.suggest_filters ───────────────────────────────────────
FILTER_PROMPT = """\
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
- explanation: 2-3 sentences in English explaining why you chose these filters.
- count_hint: rough estimate like "~200-400 jobs expected"."""


class FilterSuggestion(BaseModel):
    """a free-text query mapped onto concrete Radar filter selections."""
    occ_groups: list[str]
    states: list[str]
    portals: list[str]
    min_salary: Optional[int]
    explanation: str
    count_hint: str


# ── report_generator.elaborate_items ───────────────────────────────────────────
ELABORATION_PROMPT = """\
You are writing an analytics session report for an HR team in Austria.
You receive a list of insights saved during an analytics session, plus market context.

For EACH item write a clear section in plain business English — no jargon.
- index: the item's index, echoed back so the section can be matched to its source
- heading: short title, max 8 words
- elaboration: 2-3 paragraphs. First: restate the finding simply. Second: what it means
  for the team. Third (if needed): nuance or caveats. Separate paragraphs with a blank line.
- action_steps: 2-3 concrete, immediately actionable steps

Do NOT use markdown. Plain text only."""


class _Elaboration(BaseModel):
    index: int
    heading: str
    elaboration: str
    action_steps: list[str]


class ElaborationList(BaseModel):
    """one elaborated section per saved insight, keyed back by `index`."""
    items: list[_Elaboration]


# ── session_chat: advisor chats for the Analytics + Radar tabs ──────────────────
# Two grounded, multi-turn advisor chats that return prose. Converted to Structured Outputs
# in rework 2.4 (`responses.parse(text_format=AdvisorReply)` → a single markdown `answer`),
# replacing the legacy chat.completions calls relocated from the analytics/radar blueprints.
ADVISOR_MODEL = config.CHAT_MODEL

SUMMARY_CHAT_PROMPT = """\
You are an expert HR analytics assistant helping an HR professional in Austria prepare their session report.
Your role: help the user think through the report — what to include, what's most important,
how to frame findings, suggest a logical order, or clarify any of the data points.
Be concise and direct. These are HR professionals, not data analysts.
Use **bold** for key points or figures (markdown will be rendered).
Keep responses to 3 short paragraphs max."""

RADAR_CHAT_PROMPT = """\
You are a recruitment advisor helping HR professionals in Austria understand their job market.
Your audience is HR managers and recruiters — not data analysts. They need clear, actionable guidance.

Tone and format rules (follow strictly):
- Lead every answer with the key action or decision, then briefly explain why using 1-2 numbers.
- Never open with a statistic. Open with what the person should DO or KNOW.
- Use plain business language. Avoid jargon like 'backlog-conversion', 'top-of-funnel', 'stale demand'.
  Say 'unfilled for 30+ days' not 'stale'. Say 'harder to fill' not 'underserved'.
- Keep it to 2-3 short paragraphs. No walls of text.
- Use **bold** for the most important figures or action words (markdown will be rendered).
- Use bullet points only when listing 3+ parallel items.
- If the data does not contain what was asked, say so in one sentence."""


class AdvisorReply(BaseModel):
    """A single prose advisor reply (markdown) for the Analytics + Radar session chats."""
    answer: str
