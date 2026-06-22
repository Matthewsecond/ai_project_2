"""
embedding_search.py — Retrieval over the vector store (Stage 1).

EmbeddingSearch talks to OpenAI ONLY. Given a candidate profile, it returns the
job_ids of the relevant postings — nothing else. The rows are fetched and graded
in later stages.

Two retrieval modes:

  search_scored() — the DIRECT vector_stores.search endpoint. No generative model
     in the loop, so per OpenAI's docs the ranked result is deterministic for a
     given query. Returns (job_id, score) pairs, deduped by job_id (a file is
     chunked, so one job can surface in several chunks — we keep its best score).
     The job_id comes from the filename (`job_<id>.txt`), not the chunk text.

  search() — the legacy file_search-as-a-tool pass: a model reads ids out of the
     matched documents and emits them. Stochastic (model in the loop) and under-
     covers, so the Orchestrator used to repeat + pool these. Kept for A/B only.
"""
import logging
import re

from . import utils
from .exceptions import EmbeddingSearchError

logger = logging.getLogger(__name__)

# Files are indexed one job per file, named `job_<job_id>.txt`. The id lives in
# the filename (chunk `attributes` are empty), so we read it from there.
_FILENAME_ID = re.compile(r"job_(\d+)", re.IGNORECASE)


class EmbeddingSearch:
    """Retrieves relevant job ids from the vector store."""

    def __init__(self, client, config):
        self._client = client
        self._cfg = config

    def search_scored(self, candidate_text: str,
                      max_results: int | None = None) -> list[tuple[str, float]]:
        """One DIRECT vector-store search → [(job_id, score), ...] ranked best
        first, deduped by job_id (best chunk score wins). Deterministic: no model
        in the loop. `score` is retrieval similarity (0–1), NOT a fit grade.

        max_results overrides the configured retrieval breadth for this call (capped
        at the API's 50) — used by "find more jobs" to pull a wider candidate set."""
        cfg = self._cfg
        n = min(max_results or cfg.max_num_results, 50)
        ranking: dict = {"ranker": "auto"}
        if getattr(cfg, "score_threshold", None) is not None:
            ranking["score_threshold"] = cfg.score_threshold
        try:
            page = self._client.vector_stores.search(
                vector_store_id=cfg.vector_store_id,
                query=candidate_text,
                max_num_results=n,
                ranking_options=ranking,
                rewrite_query=getattr(cfg, "rewrite_query", False),
            )
        except Exception as e:
            raise EmbeddingSearchError(f"vector-store search failed: {e}") from e

        best: dict[str, float] = {}
        for r in (getattr(page, "data", None) or []):
            jid = self._id_from_filename(getattr(r, "filename", None))
            if not jid:
                continue
            score = float(getattr(r, "score", 0.0) or 0.0)
            if jid not in best or score > best[jid]:
                best[jid] = score
        return sorted(best.items(), key=lambda kv: kv[1], reverse=True)

    @staticmethod
    def _id_from_filename(filename: str | None) -> str | None:
        m = _FILENAME_ID.search(filename or "")
        return m.group(1) if m else None

    def search(self, candidate_text: str) -> list[str]:
        cfg = self._cfg
        try:
            response = self._client.responses.create(
                model=cfg.model,
                instructions=cfg.prompt_template.format(max_results=cfg.max_num_results,
                                                        label=cfg.country_label),
                input=f"Find the best matching jobs for this candidate:\n\n{candidate_text}",
                tools=[{
                    "type": "file_search",
                    "vector_store_ids": [cfg.vector_store_id],
                    "max_num_results": min(cfg.max_num_results, 50),
                }],
            )
        except Exception as e:
            raise EmbeddingSearchError(f"vector-store pass failed: {e}") from e

        raw = utils.parse_json(response.output_text or "")
        if not raw:
            logger.warning("Could not parse JSON from model response")
            return []

        # Accept either bare ids ([12345, ...]) or objects ([{job_id: 12345}, ...]).
        ids = []
        for item in raw:
            jid = item.get("job_id") if isinstance(item, dict) else item
            if jid:
                ids.append(str(jid))
        return ids
