"""
core — Thin orchestration / assembly layer.

`core` is the single import surface the web layer uses: it imports the domain
modules and re-exports their public classes/API, so blueprints depend on `core`
rather than reaching into individual feature modules. Heavy logic lives in the
domain modules themselves (search/, chat, taxonomy, services); infra
(infra/database) is a leaf imported directly by services/stats.
"""
from jobs_intelligence_ai.search.orchestrator import Orchestrator
from jobs_intelligence_ai.services.rescorer import Rescorer
from jobs_intelligence_ai.services.highlighter import Highlighter
from jobs_intelligence_ai.chat import (
    send_message,
    clear_session,
    enrich_jobs_from_db,
    send_job_message,
    clear_job_session,
    send_candidate_message,
    clear_candidate_session,
    get_client,
)
from jobs_intelligence_ai import taxonomy

__all__ = [
    # search
    "Orchestrator",
    # result-set operations
    "Rescorer", "Highlighter",
    # chat
    "send_message", "clear_session", "enrich_jobs_from_db",
    "send_job_message", "clear_job_session",
    "send_candidate_message", "clear_candidate_session", "get_client",
    # taxonomy
    "taxonomy",
]
