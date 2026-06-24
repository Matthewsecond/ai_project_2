"""
job_detail — the one-shot AI tools behind the Job Detail modal (a single, already-retrieved job).

Bundles the model calls a recruiter triggers from an open job card:

- translate_description     : translate the description to English (prose)
- compact_description       : 3-4 sentence summary (prose)
- generate_cv_questions     : gap-based interview questions from job + CV (prose)
- write_outreach            : candidate outreach message (prose)
- score_candidate_strength  : 5-dimension candidate-vs-job fit score (JSON)

The single-job *chat* lives in `services/search/job_chat` (conversational); this package is the
stateless one-shot tools. Prompts + Structured-Outputs schemas live in `config.py`.

Public API — import from the package:

    from jobs_intelligence_ai.services.job_detail import (
        translate_description, compact_description, generate_cv_questions,
        write_outreach, score_candidate_strength,
    )
"""
from .operations import (
    translate_description, compact_description, generate_cv_questions,
    write_outreach, score_candidate_strength,
)

__all__ = [
    "translate_description", "compact_description", "generate_cv_questions",
    "write_outreach", "score_candidate_strength",
]
