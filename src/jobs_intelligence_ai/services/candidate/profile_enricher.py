"""
profile_enricher.py — AI analysis of a raw LinkedIn scrape.

Instead of mechanically copying LinkedIn fields, we let CHAT_MODEL read the raw scrape and
produce a normalized, recruiter-ready record: inferred seniority, years of experience,
industry, a written brief, ranked skills, a salary estimate, etc.

The mechanical `map_to_profile` result is passed in as `base` and kept as the accurate
foundation (structured experiences/education/certifications, contact details, raw signals);
the AI fields are merged on top. The model call uses Structured Outputs
(responses.parse → validated LinkedInProfile); if the model is unavailable or errors, we
fall back to `base` so ingestion never breaks.
"""
import json
import logging
from datetime import datetime

from jobs_intelligence_ai import config
from jobs_intelligence_ai.shared.llm import get_client
from .config import CHAT_MODEL, ENRICH_PROMPT, AI_KEYS, LinkedInProfile

logger = logging.getLogger(__name__)


def _compact(prof: dict) -> dict:
    """Trim the normalized profile (map_to_profile output) to the fields worth analyzing,
    keeping the prompt small. Reads the app profile shape — not the raw actor scrape — so
    the enricher stays decoupled from whichever LinkedIn actor produced the data."""
    def _exp(e):
        return {"title": e.get("title"), "company": e.get("company"),
                "starts_at": e.get("starts_at"), "ends_at": e.get("ends_at"),
                "description": (e.get("description") or "")[:300]}

    def _edu(e):
        return {"school": e.get("school"), "degree": e.get("degree"),
                "starts_at": e.get("starts_at"), "ends_at": e.get("ends_at")}

    cc = prof.get("current_company") or {}
    return {
        "full_name":   prof.get("name"),
        "headline":    prof.get("headline"),
        "summary":     prof.get("summary"),
        "location":    prof.get("location"),
        "open_to_work": bool(prof.get("availability")),
        "skills":         [s for s in (prof.get("skills") or []) if s],
        "languages":      prof.get("languages") or "",
        "certifications": prof.get("certifications") or [],
        "current_company": {
            "name":     cc.get("name"),
            "industry": cc.get("industry"),
            "size":     cc.get("size"),
        },
        "experiences": [_exp(e) for e in (prof.get("experiences") or []) if isinstance(e, dict)],
        "education":   [_edu(e) for e in (prof.get("education") or []) if isinstance(e, dict)],
    }


def enrich_linkedin_profile(item: dict, base: dict | None = None) -> dict:
    """Run CHAT_MODEL over the raw LinkedIn scrape → rich normalized profile dict.

    `base` is the mechanical map_to_profile result; AI-inferred fields are merged on top of
    it. Returns `base` unchanged if no API key or on any error."""
    base = dict(base or {})
    if not config.OPENAI_API_KEY:
        return base

    try:
        resp = get_client().responses.parse(
            model=CHAT_MODEL,
            instructions=ENRICH_PROMPT,
            input=json.dumps(_compact(base), ensure_ascii=False),
            text_format=LinkedInProfile,
        )
        ai = resp.output_parsed.model_dump() if resp.output_parsed else {}
    except Exception as e:
        logger.warning("LinkedIn AI enrichment failed (%s) — using mechanical map only", e)
        return base

    if not ai:
        return base

    # Merge AI-inferred fields over the mechanical base; skip anything the model left
    # empty/null so it never blanks out a good base value.
    merged = dict(base)
    for k in AI_KEYS:
        v = ai.get(k)
        if v not in (None, "", []):
            merged[k] = v

    # Provenance — lets us re-analyze later and shows the data is AI-derived.
    merged["raw_profile"] = item
    merged["ai_model"]    = CHAT_MODEL
    merged["enriched_at"] = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    merged["source"]      = "imported"
    return merged
