"""
clustering — group candidate CVs into talent segments, then describe + discuss each.

The multi-CV mode (Phase 1) pipeline:
  embed_profiles(texts)        → L2-normalized embeddings        (embeddings.py)
  cluster_labels(vectors, g)   → one segment label per CV        (segmenting.py)
  synthesize_persona(members)  → {title, summary, persona_text}  (persona.py)
  send_segment_message(...)    → chat about one segment          (segment_chat.py)
  segment_overview(segments)   → cross-segment opportunity overview (segment_analysis.py)
  grade_candidates_for_job(..) → per-candidate fit scores for one job (segment_analysis.py)

persona synthesis, the overview, and the grading use Structured Outputs; segment chat is
text-only. Public API — import from the package:

    from jobs_intelligence_ai.services.clustering import (
        embed_profiles, cluster_labels, synthesize_persona, send_segment_message,
        segment_overview, grade_candidates_for_job,
    )
"""
from .embeddings import embed_profiles
from .segmenting import cluster_labels
from .persona import synthesize_persona
from .segment_chat import send_segment_message, clear_segment_session
from .segment_analysis import segment_overview, grade_candidates_for_job

__all__ = [
    "embed_profiles",
    "cluster_labels",
    "synthesize_persona",
    "send_segment_message", "clear_segment_session",
    "segment_overview", "grade_candidates_for_job",
]
