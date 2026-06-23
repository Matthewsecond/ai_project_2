"""
segmenting.py — Cut embedded CVs into talent segments (multi-CV mode, Phase 1).

Clusters the L2-normalized profile embeddings (from embeddings.embed_profiles) with a
Ward-linkage hierarchy (scipy) — Ward avoids the "chaining" that makes average/single linkage
collapse a varied pool into one blob, giving balanced, well-separated segments. The segment
count is auto-discovered by cutting the dendrogram at an ADAPTIVE height (a quantile of the
merge distances), so it self-calibrates to the pool's spread. A `granularity` knob (0..1)
sets that quantile: higher granularity → lower cut → finer, more segments.
"""
import numpy as np

from .config import DEFAULT_GRANULARITY


def cluster_labels(vectors: np.ndarray, granularity: float = DEFAULT_GRANULARITY) -> list[int]:
    """Ward-linkage clustering of the embeddings with an adaptive distance threshold.
    Returns one integer segment label per row.

    granularity 0..1 maps to the dendrogram cut height: 0 = coarse (few big segments),
    1 = fine (many small segments). Singletons are their own labels.
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
