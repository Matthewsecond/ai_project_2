"""
core — Thin orchestration / assembly layer.

`core` is the single import surface the web layer uses: it imports the domain
modules and re-exports their public classes/API, so blueprints depend on `core`
rather than reaching into individual feature modules. Heavy logic lives in the
domain modules themselves (search/, chat, taxonomy, services); infra
(infra/database) is a leaf imported directly by services/stats.
"""
from jobs_intelligence_ai.services.search.orchestrator import Orchestrator
from jobs_intelligence_ai.services.search.job_chat import send_job_message, clear_job_session
from jobs_intelligence_ai.services.enrichment import Rescorer, Highlighter
from jobs_intelligence_ai.shared.llm import get_client
from jobs_intelligence_ai.services.candidate import (
    send_candidate_message,
    clear_candidate_session,
)
from jobs_intelligence_ai import taxonomy

__all__ = [
    # search
    "Orchestrator",
    # result-set operations
    "Rescorer", "Highlighter",
    # single-job chat (search domain)
    "send_job_message", "clear_job_session",
    # candidate assistant (services/candidate/)
    "send_candidate_message", "clear_candidate_session",
    # shared OpenAI client
    "get_client",
    # taxonomy
    "taxonomy",
]
