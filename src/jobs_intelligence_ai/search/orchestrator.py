"""
orchestrator.py — The search entry point the rest of the app uses.

Orchestrator owns the one shared OpenAI client and the SearchConfig, and runs the
search as two cleanly-separated stages:

  STAGE 1 — Retrieve (recall). By default, ONE direct vector_stores.search call
     (no model in the loop) → a deterministic ranked id set. The legacy path
     (config.direct_retrieval=False) instead runs a fixed budget of stochastic
     file_search passes in parallel waves, tallying id occurrences in a ResultPool
     and keeping the ids that cleared a quorum. Either way: which jobs are relevant
     (the id set). Retrieval scores are not used as grades.
  STAGE 2 — Grade (authoritative). JobSearch fetches the converged ids' rows from
     MySQL in one query; the Grader scores them all in one batched, rubric-anchored
     call. Output: reproducible scores/grades — no max-over-passes inflation.

Stage 1 touches OpenAI's vector store; stage 2 touches MySQL + one scoring call —
so the DB, grading and seniority work happen once on the final set, not per pass.

  stream() — yields progress per wave, then a final done event (drives the live UI)
  run()    — drains stream() and returns just the final ranked list
"""
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from openai import OpenAI

from jobs_intelligence_ai.services.seniority_classifier import classify_seniority

from .config import SearchConfig
from .embedding_search import EmbeddingSearch
from .exceptions import ConfigError, EmbeddingSearchError
from .grader import Grader
from .job_search import JobSearch
from .result_pool import ResultPool

logger = logging.getLogger(__name__)


class Orchestrator:
    """Coordinates the search workers through the two stages.

    Does no searching itself — it drives EmbeddingSearch + ResultPool (stage 1)
    and JobSearch + Grader (stage 2). Reuse one instance app-wide (it holds the
    shared OpenAI client)."""

    def __init__(self, config: SearchConfig | None = None):
        self.config = config or SearchConfig()
        self._client: OpenAI | None = None
        self._embedding: EmbeddingSearch | None = None
        self._job_search: JobSearch | None = None
        self._grader: Grader | None = None

    def _ensure_ready(self) -> None:
        """Lazily create the shared client + the stage workers on first use."""
        if self._client is None:
            if not self.config.api_key or self.config.api_key == "your_key_here":
                raise ConfigError("OpenAI API key not configured — search unavailable")
            self._client = OpenAI(api_key=self.config.api_key)
            self._embedding = EmbeddingSearch(self._client, self.config.embedding)
            self._job_search = JobSearch()
            self._grader = Grader(self._client, self.config.grader)

    def stream(self, candidate_text: str, filters: dict | None = None,
               max_results: int | None = None):
        """Run the search as its two phases, yielding progress events:

            {"event": "cycle", "cycle": k, "added": a, "total": t}  ← ids after each wave
            {"event": "done",  "jobs": [...], "cycles": k, "total": t}  ← final ranked jobs

        Returns every matching job; pass filters["limit"] to cap the count, and
        max_results to widen Stage-1 retrieval (used by "find more jobs").
        """
        self._ensure_ready()
        filters = filters or {}

        ids, cycles = yield from self._retrieve(candidate_text, max_results)  # stage 1: ids
        jobs = self._resolve(candidate_text, ids, filters)                    # stage 2: grade

        print(f"  [search] {cycles} pass(es) -> {len(ids)} ids -> {len(jobs)} jobs",
              flush=True)
        yield {"event": "done", "jobs": jobs, "cycles": cycles, "total": len(ids)}

    def _retrieve(self, candidate_text: str, max_results: int | None = None):
        """Stage 1 dispatcher — one deterministic direct search (default) or the
        legacy stochastic convergence loop. Both yield cycle events and return
        (ids, passes)."""
        if self.config.direct_retrieval:
            return (yield from self._retrieve_direct(candidate_text, max_results))
        return (yield from self._converge(candidate_text))

    def _retrieve_direct(self, candidate_text: str, max_results: int | None = None):
        """Stage 1 (direct) — one vector_stores.search call, no model in the loop.
        Deterministic for a given query, so no waves or quorum are needed.
        max_results widens the candidate set for "find more jobs"."""
        scored = self._embedding.search_scored(candidate_text, max_results=max_results)
        ids = [jid for jid, _ in scored]
        yield {"event": "cycle", "cycle": 1, "added": len(ids), "total": len(ids)}
        return ids, 1

    def _converge(self, candidate_text: str):
        """Phase 1 — run a FIXED budget of EmbeddingSearch passes in parallel waves,
        tallying how often each id is retrieved, then keep only the ids that cleared
        the quorum (resurfaced in >= cc.quorum passes).

        The fixed budget keeps the sampling denominator the same every run, and the
        quorum cut drops the one-off long-tail ids a single lucky pass turns up — so
        the returned id set is reproducible instead of a noise-sized union.

        Yields a cycle event per wave; returns the (quorum ids, passes run).
        """
        cc = self.config.convergence
        pool = ResultPool()
        cycle = 0
        while cycle < cc.passes:
            n = min(cc.wave_size, cc.passes - cycle)
            added = 0
            with ThreadPoolExecutor(max_workers=n) as ex:
                futures = [ex.submit(self._embedding.search, candidate_text)
                           for _ in range(n)]
                for fut in as_completed(futures):
                    try:
                        added += pool.add(fut.result() or [])
                    except EmbeddingSearchError as e:
                        # A single pass failing is tolerable — the wave loop carries
                        # on. Anything that isn't a search error propagates.
                        logger.warning("Search pass failed: %s", e)
            cycle += n
            yield {"event": "cycle", "cycle": cycle, "added": added, "total": len(pool)}
        return pool.ids(cc.quorum), cycle

    def _resolve(self, candidate_text: str, ids: list[str], filters: dict) -> list[dict]:
        """Stage 2 — fetch the quorum ids' rows, grade them in one batched call,
        then rank, apply the optional limit, and enrich with seniority."""
        candidates = self._job_search.fetch(ids, filters)            # rows + hard-filter
        jobs = self._grader.grade(candidate_text, candidates)         # authoritative scores
        jobs.sort(key=lambda j: j["score"], reverse=True)
        limit = filters.get("limit")
        if limit:
            jobs = jobs[:int(limit)]
        classify_seniority(jobs)
        return jobs

    def match_url(self, candidate_text: str, url: str) -> dict | None:
        """Grade ONE specific job — looked up by its posting URL — against the
        candidate, skipping retrieval entirely. Returns the graded job dict, or
        None if the url isn't in the DB (the caller can then offer scraping, which
        is not implemented yet)."""
        self._ensure_ready()
        job = self._job_search.fetch_by_url(url)
        if job is None:
            return None
        graded = self._grader.grade(candidate_text, [job])   # same authoritative scorer
        classify_seniority(graded)
        return graded[0] if graded else None

    def run(self, candidate_text: str, filters: dict | None = None,
            max_results: int | None = None) -> list[dict]:
        """Non-streaming variant: run to completion, return only the final jobs."""
        final: list[dict] = []
        for event in self.stream(candidate_text, filters, max_results):
            if event["event"] == "done":
                final = event["jobs"]
        return final
