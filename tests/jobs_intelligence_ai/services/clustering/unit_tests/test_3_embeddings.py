"""
Offline unit tests for embed_profiles (2.3 #6 — embeddings).

No network: patch `get_client` so `embeddings.create` returns canned vectors, and assert
the output rows are L2-normalized (unit length), with a zero vector left as zeros (no NaN).
"""
import numpy as np

import jobs_intelligence_ai.services.clustering.embeddings as emb_mod
from jobs_intelligence_ai.services.clustering import embed_profiles


class _FakeEmbeddings:
    """`.create()` returns objects exposing `.embedding`, mimicking the OpenAI SDK."""
    def __init__(self, vectors):
        self._vectors = vectors

    def create(self, **kwargs):
        data = [type("E", (), {"embedding": v})() for v in self._vectors]
        return type("Resp", (), {"data": data})()


def _patch(monkeypatch, vectors):
    client = type("C", (), {"embeddings": _FakeEmbeddings(vectors)})()
    monkeypatch.setattr(emb_mod, "get_client", lambda *a, **k: client)


def test_rows_are_l2_normalized(monkeypatch):
    """Each returned row is scaled to unit length."""
    _patch(monkeypatch, [[3.0, 4.0], [1.0, 0.0]])     # norms 5 and 1
    out = embed_profiles(["cv one", "cv two"])
    assert out.shape == (2, 2)
    np.testing.assert_allclose(np.linalg.norm(out, axis=1), [1.0, 1.0])
    np.testing.assert_allclose(out[0], [0.6, 0.8])


def test_zero_vector_stays_zero(monkeypatch):
    """A zero embedding is left as zeros (no divide-by-zero / NaN)."""
    _patch(monkeypatch, [[0.0, 0.0]])
    out = embed_profiles(["blank"])
    assert not np.isnan(out).any()
    np.testing.assert_allclose(out[0], [0.0, 0.0])
