"""
config.py — Settings for the `search` module, divided per class.

  EmbeddingConfig   → EmbeddingSearch  (stage 1: retrieve relevant job ids)
  ConvergenceConfig → Orchestrator     (stage 1: the wave loop)
  GraderConfig      → Grader           (stage 2: score the converged set)
  SearchConfig      → bundles them + auth

Two-stage design: stage 1 converges on WHICH jobs are relevant (the id set);
stage 2 grades them in one batched call. Defaults are sourced from the global
config/settings.py, but every field is overridable per instance.
"""
from dataclasses import dataclass, field

from jobs_intelligence_ai import config

# Search-owned retrieval setting (moved out of global config in rework 2.2b — it's
# search-only). How many documents file_search retrieves from the vector store per query.
MAX_NUM_RESULTS = 30


# Stage 1 — retrieval only. We just want the ids of relevant jobs; the grading
# happens later, so this prompt does not ask the model to score anything.
EMBEDDING_PROMPT = """You are a job retrieval engine for Jobs Intelligence {label}.
The user provides a candidate profile. Use file_search to find the job postings most
relevant to that candidate.

Respond with ONLY a JSON array of the job_id integers read from the matching documents —
no prose, no markdown fences, no scores. Example: [12345, 67890]
Return up to {max_results} ids, most relevant first.
"""


# Stage 2 — scoring. One batched, rubric-anchored judgment over the fixed set, so
# grades are reproducible. The bands line up with the A/B/C score thresholds.
GRADER_PROMPT = """You are a job-matching grader for Jobs Intelligence {label}.
You are given ONE candidate profile and a FIXED list of jobs. Score how well THIS \
candidate fits EACH job, one entry per job IN THE SAME ORDER. Do not add or drop jobs.

For each job provide:
  score        — 0.0–1.0 fit confidence
  match_reason — one sentence, max 22 words

Scoring rubric — use the FULL range and be decisive:
  0.80–1.00  strong fit  — core role, skills and seniority clearly align
  0.60–0.79  good fit    — clear overlap but real gaps (stack, focus, or seniority)
  below 0.60 weak fit    — only partial or tangential overlap
Judge genuine fit for the candidate, not mere keyword presence."""


@dataclass
class EmbeddingConfig:
    """Tunables for retrieval (EmbeddingSearch)."""
    model:           str = config.CHAT_MODEL
    vector_store_id: str = config.VECTOR_STORE_ID
    country_label:   str = config.COUNTRY_LABEL
    max_num_results: int = MAX_NUM_RESULTS          # chunks retrieved per search (cap 50)
    score_threshold: float | None = None            # drop chunks below this retrieval score (direct mode)
    rewrite_query:   bool = False                    # let a model rephrase the query first; off = deterministic
    prompt_template: str = EMBEDDING_PROMPT          # legacy file_search-tool path only


@dataclass
class GraderConfig:
    """Tunables for scoring the converged set (Grader)."""
    model:           str   = config.CHAT_MODEL
    country_label:   str   = config.COUNTRY_LABEL
    score_a_min:     float = config.SCORE_A_MIN     # grade thresholds applied per job
    score_b_min:     float = config.SCORE_B_MIN
    prompt_template: str   = GRADER_PROMPT


@dataclass
class ConvergenceConfig:
    """Tunables for the retrieval wave loop (Orchestrator).

    Reproducibility comes from a FIXED pass budget plus a quorum cut, not from a
    noise-driven early stop. We always run `passes` retrieval passes (so the
    sampling denominator is the same every run), then keep only the ids that
    `quorum` or more of those passes returned. That drops the one-off long-tail
    ids a single lucky pass turns up — the borderline jobs that otherwise make
    the final set churn run to run.
    """
    wave_size: int = 4    # retrieval passes run in parallel per wave
    passes:    int = 12   # total retrieval passes — fixed, so the denominator is reproducible
    quorum:    int = 2    # keep ids returned by >= this many passes (drops noisy singletons)


@dataclass
class SearchConfig:
    """Everything the Orchestrator needs. Pass a customized instance to override."""
    embedding:   EmbeddingConfig   = field(default_factory=EmbeddingConfig)
    grader:      GraderConfig      = field(default_factory=GraderConfig)
    convergence: ConvergenceConfig = field(default_factory=ConvergenceConfig)
    api_key:     str = config.OPENAI_API_KEY
    # Stage-1 strategy. True → one DETERMINISTIC vector_stores.search call (no model
    # in the loop). False → the legacy stochastic file_search-tool wave loop, kept
    # for A/B comparison. The convergence knobs apply only when this is False.
    direct_retrieval: bool = True
