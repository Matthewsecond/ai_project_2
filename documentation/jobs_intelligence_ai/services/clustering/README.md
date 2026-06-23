# services/clustering/

Group candidate CVs into talent segments (multi-CV mode, Phase 1), describe each segment as
a synthetic persona, and chat about it. Packaged in rework Stage 2.3 #6 from the loose
`services/clustering.py` + `services/persona.py`, plus the segment chat relocated here from
the old `chat.py` (per the distribute-by-domain decision).

## Layout
```
services/clustering/
├── __init__.py        # public API
├── config.py          # embedding model + granularity + persona prompt/schema + segment-chat prompt
├── embeddings.py      # embed_profiles()  — one batched OpenAI embeddings call (L2-normalized)
├── segmenting.py      # cluster_labels()  — Ward-linkage dendrogram cut (scipy), adaptive height
├── persona.py         # synthesize_persona() — segment → synthetic candidate (Structured Outputs)
├── segment_chat.py    # send_segment_message() — chat about one segment (text-only)
└── segment_analysis.py # segment_overview() + grade_candidates_for_job() (Structured Outputs)
```

## Public API
```python
from jobs_intelligence_ai.services.clustering import (
    embed_profiles, cluster_labels, synthesize_persona, send_segment_message,
    segment_overview, grade_candidates_for_job,
)
```
Consumer: `frontend/blueprints/cluster.py` — embeds the candidate pool, cuts it into segments,
synthesizes a persona per segment (concurrently), powers `/api/cluster/chat`, and (via
`segment_analysis`) the cross-segment overview + opt-in "Grade with AI" per-job scoring.

## Structured-Outputs status (2.3 #6)
- ✅ **persona.synthesize_persona** → `responses.parse(text_format=PersonaResult)` +
  `shared.llm.get_client`; the hand-rolled `_parse_json_obj` is **deleted** and the "Return
  ONLY valid JSON" boilerplate dropped. Fallback kept: on any failure it uses the first
  member profile as `persona_text`.
- **embeddings** — `embeddings.create` is not a JSON/text-gen call (nothing to convert);
  switched to `shared.llm.get_client`.
- **segmenting** — pure scipy/numpy, no LLM.
- **segment_chat** — text-only chat; no Structured Outputs. Prompt + language map in `config.py`.

## Structured-Outputs status (2.4) — segment_analysis
Both calls relocated from the cluster blueprint and converted to `responses.parse` via the
shared client:
- ✅ **segment_overview** → `SegmentOverview` (single prose `text`) — was a bare
  `responses.create` returning `output_text`.
- ✅ **grade_candidates_for_job** → `CandidateGrades` (a `list[{score, reason}]` in input
  order) — replaces the "respond with ONLY a JSON array" prompt + `search_utils.parse_json`.
  Both raise on no-key / model error (the blueprint maps to a 500); the score→grade-letter
  shaping stays in the blueprint (uses the shared `grade` thresholds).

## Tests
`tests/jobs_intelligence_ai/services/clustering/unit_tests/` (15, offline): `test_1_persona`
(SO mock + fallback), `test_2_segmenting` (pure cluster_labels edge cases + separation),
`test_3_embeddings` (mock embeddings; L2-normalization, zero-vector safety), `test_4_segment_chat`
(reply, session continuity, fallbacks), `test_5_segment_analysis` (overview text + ordered grade
dicts, inputs grounded into the prompt, no-key/null/error raise). `smoke_tests/test_clustering_smoke`
(5, live-asserting): embed+cluster splits two professions, persona synthesis, segment chat,
segment overview, per-job candidate grading.
