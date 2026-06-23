"""
interview — live interview scoring for the job-detail modal.

`InterviewHelper` owns the whole interview loop for one (candidate, job) pair:
generate gap-based questions, score each recorded answer as the exchange unfolds,
suggest follow-ups, and roll the answers up into an overall recommendation — plus
candidate-facing coaching (model answers, improvement opportunities) and a running
per-aspect assessment. Every call uses Structured Outputs (responses.parse), and every
method degrades to a structured error dict instead of raising, so a flaky model call
never 500s the interview UI.

Public API — import from the package:

    from jobs_intelligence_ai.services.interview import InterviewHelper
"""
from .orchestrator import InterviewHelper

__all__ = ["InterviewHelper"]
