"""
candidate — everything about the candidate the recruiter is working with.

Bundles the candidate-side features that were scattered across services/ and the old
chat.py:

- store          : MySQL persistence for the saved-candidate pipeline (DB; no LLM)
- example_cv     : sample candidate CV PDFs for the demo (pure reportlab)
- profile_enricher : AI-normalize a raw LinkedIn scrape (Structured Outputs)
- profile_parser  : parse a structured profile from raw CV text (Structured Outputs)
- guided_builder : the guided "target candidate" builder chat (Structured Outputs)

Public API — import from the package (the DB layer stays a submodule):

    from jobs_intelligence_ai.services.candidate import store
    from jobs_intelligence_ai.services.candidate import (
        enrich_linkedin_profile, parse_candidate_profile,
        generate_example_cv_pdf, extract_guided_fields, phrase_guided_reply,
    )
"""
from . import store
from .example_cv import (
    generate_example_cv_pdf, generate_example_cv_pdf_2, generate_example_cv_pdf_sk,
)
from .profile_enricher import enrich_linkedin_profile
from .profile_parser import parse_candidate_profile
from .guided_builder import extract_guided_fields, phrase_guided_reply

__all__ = [
    "store",
    "generate_example_cv_pdf", "generate_example_cv_pdf_2", "generate_example_cv_pdf_sk",
    "enrich_linkedin_profile",
    "parse_candidate_profile",
    "extract_guided_fields", "phrase_guided_reply",
]
