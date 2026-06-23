"""
reporting — turn saved insights / saved jobs into briefings and polished PDF reports.

Three concerns, grouped because they all produce recruiter-facing reports:

- opportunity_briefing : LLM market briefing + AI filter suggestion for the Radar tab
- report_generator     : Analytics session report — LLM elaboration + PDF (analytics tab)
- report_pipeline      : Candidate Pipeline Report PDF (saved-jobs export; pure rendering)
- session_chat         : grounded advisor chats for the Analytics + Radar tabs (prose)

The LLM calls (briefing, filter suggestion, elaboration, session chats) use Structured
Outputs; the PDF builders are pure reportlab. Public API — import from the package:

    from jobs_intelligence_ai.services.reporting import (
        generate_briefing, suggest_filters,        # opportunity_briefing
        elaborate_items, generate_pdf,             # report_generator
        generate_insights_pdf, generate_saved_jobs_pdf,  # report_pipeline
        analytics_chat, radar_chat,                # session_chat
    )
"""
from .opportunity_briefing import generate_briefing, suggest_filters
from .report_generator import elaborate_items, generate_pdf
from .report_pipeline import generate_insights_pdf, generate_saved_jobs_pdf
from .session_chat import analytics_chat, radar_chat

__all__ = [
    "generate_briefing", "suggest_filters",
    "elaborate_items", "generate_pdf",
    "generate_insights_pdf", "generate_saved_jobs_pdf",
    "analytics_chat", "radar_chat",
]
