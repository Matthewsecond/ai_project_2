"""
helpers/profile_enricher.py — AI analysis of a raw LinkedIn scrape.

Instead of mechanically copying LinkedIn fields, we let gpt-5.4 (CHAT_MODEL) read
the raw scrape and produce a normalized, recruiter-ready record: inferred seniority,
years of experience, industry, a written brief, ranked skills, a salary estimate, etc.

The mechanical `map_to_profile` result is passed in as `base` and kept as the
accurate foundation (structured experiences/education/certifications, contact
details, raw signals); the AI fields are merged on top. If the model is unavailable
or errors, we fall back to `base` so ingestion never breaks.
"""
import re
import json
import logging
from datetime import datetime

import config

logger = logging.getLogger(__name__)

_SYSTEM = """You are a senior recruiter analyzing a candidate's LinkedIn profile for the Austrian job market.
Read the raw profile JSON and produce a normalized, recruiter-ready structured record.
INFER where reasonable (seniority, total years of experience, industry, salary) from the
work history, titles, skills and dates — do not merely copy fields. Be conservative: never
invent specific employers, credentials or facts not supported by the data.

Salaries in this market are AUSTRIAN MONTHLY GROSS in euros (~14 salaries/year). Estimate a
realistic monthly-gross range for this candidate's role, seniority and location. This is an
ESTIMATE derived from the role — LinkedIn does not provide it.

Return ONLY valid JSON (no prose, no code fences) with EXACTLY these keys:
{
  "name": "full name",
  "title": "current or most-recent role title",
  "current_company": "current employer, or null",
  "headline": "their headline, cleaned up",
  "seniority": "exactly one of: Junior, Mid, Senior, Lead, Executive",
  "years_experience": <integer total years of professional experience>,
  "industry": "primary industry / sector",
  "role_category": "broad role family, e.g. 'Software Engineering', 'Sales', 'Logistics'",
  "education_level": "highest level e.g. 'PhD','MSc','BSc','Apprenticeship', or null",
  "management_experience": "short note, e.g. 'Yes — led ~12' or 'No'",
  "top_skills": ["8-12 most relevant skills, ranked, normalized"],
  "specializations": ["3-6 domains / focus areas"],
  "languages": "languages with levels if known, e.g. 'German (native), English C1'",
  "location": "city, region/country",
  "ai_summary": "2-3 sentence recruiter brief: who they are and where they fit",
  "strengths": ["3-5 short strength bullets"],
  "estimated_salary_min": <integer monthly gross EUR>,
  "estimated_salary_max": <integer monthly gross EUR>
}
Use null (or [] for lists) for anything you genuinely cannot determine."""

# AI-inferred keys we merge over the mechanical base.
_AI_KEYS = (
    "name", "title", "current_company", "headline", "seniority", "years_experience",
    "industry", "role_category", "education_level", "management_experience",
    "top_skills", "specializations", "languages", "location", "ai_summary",
    "strengths", "estimated_salary_min", "estimated_salary_max",
)


def _compact(item: dict) -> dict:
    """Trim the raw scrape to the fields worth analyzing (keeps the prompt small)."""
    def _exp(e):
        return {"title": e.get("title"), "company": e.get("company"),
                "starts_at": e.get("starts_at"), "ends_at": e.get("ends_at"),
                "description": (e.get("description") or "")[:300]}

    def _edu(e):
        return {"school": e.get("school"), "degree": e.get("degree_name") or e.get("degree"),
                "starts_at": e.get("starts_at"), "ends_at": e.get("ends_at")}

    return {
        "full_name":   item.get("full_name"),
        "headline":    item.get("headline"),
        "summary":     item.get("summary"),
        "city":        item.get("city"),
        "country":     item.get("country"),
        "open_to_work": item.get("open_to_work"),
        "skills":         [s for s in (item.get("skills") or []) if s],
        "languages":      item.get("languages") or [],
        "certifications": item.get("certifications") or [],
        "current_company": {
            "name":     item.get("company_name"),
            "industry": item.get("company_industry"),
            "size":     item.get("company_size"),
        },
        "experiences": [_exp(e) for e in (item.get("experiences") or []) if isinstance(e, dict)],
        "education":   [_edu(e) for e in (item.get("education") or []) if isinstance(e, dict)],
    }


def _parse_json(text: str) -> dict:
    """Best-effort JSON object extraction from the model's reply."""
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else {}
    except Exception:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            try:
                data = json.loads(m.group())
                return data if isinstance(data, dict) else {}
            except Exception:
                return {}
    return {}


def _coerce_int(v):
    try:
        return int(round(float(v)))
    except (TypeError, ValueError):
        return None


def enrich_linkedin_profile(item: dict, base: dict | None = None) -> dict:
    """Run gpt-5.4 over the raw LinkedIn scrape → rich normalized profile dict.

    `base` is the mechanical map_to_profile result; AI-inferred fields are merged
    on top of it. Returns `base` unchanged if no API key or on any error."""
    base = dict(base or {})
    if not config.OPENAI_API_KEY:
        return base

    try:
        from openai import OpenAI
        client = OpenAI(api_key=config.OPENAI_API_KEY)
        resp = client.responses.create(
            model=config.CHAT_MODEL,
            instructions=_SYSTEM,
            input=json.dumps(_compact(item), ensure_ascii=False),
        )
        ai = _parse_json(resp.output_text or "")
    except Exception as e:
        logger.warning("LinkedIn AI enrichment failed (%s) — using mechanical map only", e)
        return base

    if not ai:
        return base

    merged = dict(base)
    for k in _AI_KEYS:
        v = ai.get(k)
        if k in ("years_experience", "estimated_salary_min", "estimated_salary_max"):
            iv = _coerce_int(v)
            if iv is not None:
                merged[k] = iv
        elif v not in (None, "", []):
            merged[k] = v

    # Provenance — lets us re-analyze later and shows the data is AI-derived.
    merged["raw_profile"] = item
    merged["ai_model"]    = config.CHAT_MODEL
    merged["enriched_at"] = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    merged["source"]      = "imported"
    return merged
