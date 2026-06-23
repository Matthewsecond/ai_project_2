"""
Offline unit tests for cluster_labels (2.3 #6 — segmenting).

Pure scipy/numpy (no network): assert the trivial edge cases and that two clearly
separated groups of unit vectors fall into two segments, with one label per row.
"""
import numpy as np

from jobs_intelligence_ai.services.clustering import cluster_labels


def test_empty_and_singleton():
    """0 or 1 vectors short-circuit to a label per row without clustering."""
    assert cluster_labels(np.zeros((0, 3))) == []
    assert cluster_labels(np.array([[1.0, 0.0, 0.0]])) == [0]


def test_two_separated_groups_give_two_segments():
    """Two tight, well-separated clusters of unit vectors → two segments, one label/row."""
    vecs = np.array([
        [1.0, 0.0], [0.99, 0.01], [0.98, 0.02],   # group A (≈ x-axis)
        [0.0, 1.0], [0.01, 0.99], [0.02, 0.98],   # group B (≈ y-axis)
    ])
    labels = cluster_labels(vecs, granularity=0.5)
    assert len(labels) == len(vecs)
    assert len(set(labels)) == 2
    # rows within a group share a label; the two groups differ
    assert labels[0] == labels[1] == labels[2]
    assert labels[3] == labels[4] == labels[5]
    assert labels[0] != labels[3]
