"""
embeddings.py — Embed candidate CVs for talent-segment clustering (multi-CV mode, Phase 1).

OpenAI offers embeddings, not clustering, so segmentation is a two-step recipe (the same one
OpenAI's own cookbook uses): embed each candidate profile with text-embedding-3-small in ONE
batched call here, then cluster the vectors in segmenting.py. Vectors are L2-normalized so
the downstream Ward linkage works on unit vectors.
"""
import logging

import numpy as np

from jobs_intelligence_ai.shared.llm import get_client
from .config import EMBEDDING_MODEL

logger = logging.getLogger(__name__)


def embed_profiles(texts: list[str]) -> np.ndarray:
    """One batched OpenAI embeddings call → L2-normalized row vectors."""
    client = get_client()
    resp = client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=[(t or "")[:8000] for t in texts],
    )
    vecs = np.array([d.embedding for d in resp.data], dtype=float)
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return vecs / norms
