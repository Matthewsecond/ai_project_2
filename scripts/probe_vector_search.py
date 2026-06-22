"""
probe_vector_search.py — READ-ONLY probe of the OpenAI vector store.

Calls the direct `client.vector_stores.search(...)` endpoint (no generative model
in the loop) for the Peter Varga profile and dumps the raw shape of each result —
score, filename, attributes/metadata, and a content snippet — so we can see
whether `job_id` is reachable directly (in attributes or parseable from text)
before deciding to rewrite Stage 1 around this endpoint.

Changes nothing. Run it with:

    COUNTRY=sk python scripts/probe_vector_search.py
"""
import json
import os
import sys

# Pick the country profile BEFORE any config-bound import resolves it.
os.environ.setdefault("COUNTRY", "sk")

from openai import OpenAI

from jobs_intelligence_ai import config

# Same profile the convergence test uses, trimmed — retrieval keys off this text.
PETER_VARGA = (
    "B2B Sales Manager with 10 years of experience in enterprise software and SaaS "
    "sales, based in Bratislava. Senior Account Executive managing 35 enterprise "
    "accounts (EUR 2.0M ARR), full sales cycle. Skills: B2B sales, SaaS, enterprise "
    "account management, Salesforce CRM, pipeline management, consultative selling. "
    "Open to Sales Manager or Head of Sales roles in Slovakia."
)

MAX_RESULTS = 10


def _dump(obj):
    """Best-effort dict view of an SDK model for printing."""
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    return obj


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")   # Slovak diacritics
    except Exception:
        pass

    if not config.OPENAI_API_KEY or not config.VECTOR_STORE_ID:
        print("Missing OPENAI_API_KEY or VECTOR_STORE_ID — set them (and COUNTRY) first.")
        return 1

    client = OpenAI(api_key=config.OPENAI_API_KEY)
    print(f"=== vector_stores.search probe | {config.COUNTRY_LABEL} | "
          f"store {config.VECTOR_STORE_ID}\n")

    page = client.vector_stores.search(
        vector_store_id=config.VECTOR_STORE_ID,
        query=PETER_VARGA,
        max_num_results=MAX_RESULTS,
        ranking_options={"ranker": "auto"},
        rewrite_query=True,
    )

    results = list(page.data or [])
    print(f"got {len(results)} results\n")

    # Show the FULL raw shape of the first result once, so we can see every field
    # the endpoint returns (this is the structure we'd build the rewrite on).
    if results:
        print("--- raw shape of result[0] ---")
        print(json.dumps(_dump(results[0]), indent=2, ensure_ascii=False, default=str))
        print("--- end raw shape ---\n")

    # Then a compact per-result view focused on the question: score, file,
    # attributes (where job_id would live), and a content snippet.
    for i, r in enumerate(results):
        d = _dump(r)
        score = d.get("score")
        filename = d.get("filename") or d.get("file_id")
        attributes = d.get("attributes")
        content = d.get("content") or []
        text = ""
        if isinstance(content, list) and content:
            first = content[0]
            text = (first.get("text") if isinstance(first, dict) else str(first)) or ""
        snippet = text.replace("\n", " ")[:220]
        print(f"[{i}] score={score}  file={filename}")
        print(f"     attributes={attributes}")
        print(f"     snippet={snippet}\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
