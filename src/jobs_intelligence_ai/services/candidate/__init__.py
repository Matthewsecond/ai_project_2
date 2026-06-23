"""
candidate — everything about the candidate the recruiter is working with.

Bundles the candidate-side features that were scattered across services/ and the old
chat.py:

- store          : MySQL persistence for the saved-candidate pipeline (DB; no LLM)
- example_cv     : sample candidate CV PDFs for the demo (pure reportlab)
- profile_enricher : AI-normalize a raw LinkedIn scrape (Structured Outputs)
- assistant      : the candidate-assistant chat — discuss + edit one candidate (Structured Outputs)

Public API — import from the package (the DB layer stays a submodule):

    from jobs_intelligence_ai.services.candidate import store
    from jobs_intelligence_ai.services.candidate import (
        enrich_linkedin_profile, send_candidate_message, generate_example_cv_pdf,
    )
"""
from . import store
from .example_cv import (
    generate_example_cv_pdf, generate_example_cv_pdf_2, generate_example_cv_pdf_sk,
)
from .profile_enricher import enrich_linkedin_profile
from .assistant import send_candidate_message, clear_candidate_session

__all__ = [
    "store",
    "generate_example_cv_pdf", "generate_example_cv_pdf_2", "generate_example_cv_pdf_sk",
    "enrich_linkedin_profile",
    "send_candidate_message", "clear_candidate_session",
]
