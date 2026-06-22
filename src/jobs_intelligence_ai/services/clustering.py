"""
clustering.py — Group candidate CVs into talent segments (multi-CV mode, Phase 1).

OpenAI offers embeddings, not clustering, so this is the standard two-step recipe
(the same one OpenAI's own cookbook uses): embed each candidate profile with
text-embedding-3-small in ONE batched call, then cluster the vectors. We build a
Ward-linkage hierarchy (scipy) over the L2-normalized embeddings — Ward avoids the
"chaining" that makes average/single linkage collapse a varied pool into one blob,
giving balanced, well-separated segments — and auto-discover the segment count by
cutting the dendrogram at an ADAPTIVE height (a quantile of the merge distances),
so it self-calibrates to the pool's spread. A `granularity` knob (0..1) sets that
quantile: higher granularity → lower cut → finer, more segments.
"""
import logging

import numpy as np

from jobs_intelligence_ai import config
from jobs_intelligence_ai.chat import get_client

logger = logging.getLogger(__name__)


def embed_profiles(texts: list[str]) -> np.ndarray:
    """One batched OpenAI embeddings call → L2-normalized row vectors."""
    client = get_client()
    resp = client.embeddings.create(
        model=config.EMBEDDING_MODEL,
        input=[(t or "")[:8000] for t in texts],
    )
    vecs = np.array([d.embedding for d in resp.data], dtype=float)
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return vecs / norms


def cluster_labels(vectors: np.ndarray, granularity: float = 0.5) -> list[int]:
    """Agglomerative (average-linkage, cosine) clustering with an auto distance
    threshold. Returns one integer segment label per row.

    granularity 0..1 maps to the cosine-distance cutoff: 0 = coarse (few big
    segments), 1 = fine (many small segments). Singletons are their own labels.
    """
    n = len(vectors)
    if n <= 1:
        return [0] * n

    from scipy.cluster.hierarchy import linkage, fcluster

    # Ward linkage on the (L2-normalized) embeddings, then cut the dendrogram at an
    # adaptive height: a quantile of the n-1 merge distances. This self-calibrates to
    # the pool — short one-liners spread wider than full CVs, and a fixed cut would
    # over-split one and over-merge the other. Higher granularity → lower cut → more,
    # smaller segments.
    g = min(max(float(granularity), 0.0), 1.0)
    Z = linkage(vectors, method="ward")
    q = 0.62 + (1.0 - g) * 0.33          # g=0 → q0.95 (coarse), g=1 → q0.62 (fine)
    threshold = float(np.quantile(Z[:, 2], q))
    labels = fcluster(Z, t=threshold, criterion="distance")
    return [int(x) for x in labels]
