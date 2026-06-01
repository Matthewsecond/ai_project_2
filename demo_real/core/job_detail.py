"""
job_detail.py — Canonical representation of a single job offer.

Normalises data from any source (DB search, AI chat, test fixtures) into a
consistent shape. Computes derived fields (grade, score_pct, skill_list, etc.)
so the template always gets clean, predictable data.
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import Optional


def _parse_salary(v) -> Optional[float]:
    """Extract a numeric salary from any string/number representation."""
    if v is None:
        return None
    s = re.sub(r"[^\d.]", "", str(v))
    try:
        n = float(s)
        return n if n > 100 else None
    except ValueError:
        return None


def _grade_from_score(score: Optional[float]) -> str:
    if score is None:
        return "C"
    pct = score * 100 if score <= 1 else score
    return "A" if pct >= 70 else "B" if pct >= 50 else "C"


def _split_skills(raw: Optional[str]) -> list[str]:
    if not raw:
        return []
    return [s.strip() for s in raw.split(",") if s.strip() and s.strip() != "-" and len(s.strip()) > 1]


@dataclass
class JobDetail:
    # ── Core identity ─────────────────────────────────────────
    job_id:    str
    title:     str
    company:   str

    # ── Location ──────────────────────────────────────────────
    state:     str = ""
    city:      str = ""
    lat:       Optional[float] = None
    lon:       Optional[float] = None

    # ── Posting metadata ──────────────────────────────────────
    salary:    Optional[str]   = None
    occ_group: Optional[str]   = None
    portal:    Optional[str]   = None
    posted:    Optional[str]   = None
    url:       Optional[str]   = None

    # ── Content ───────────────────────────────────────────────
    description:         Optional[str] = None
    description_snippet: Optional[str] = None
    skills:              Optional[str] = None   # original language
    skills_en:           Optional[str] = None   # English

    # ── Match quality ─────────────────────────────────────────
    score:        Optional[float] = None
    grade:        Optional[str]   = None        # A / B / C (override)
    match_reason: Optional[str]   = None

    # ── Internal batch tag (not serialised) ───────────────────
    _batch: str = field(default="search", repr=False)

    # ── Computed properties ───────────────────────────────────

    @property
    def grade_computed(self) -> str:
        """A/B/C — prefers explicit grade, falls back to score-based computation."""
        if self.grade and self.grade not in ("?", ""):
            return self.grade
        return _grade_from_score(self.score)

    @property
    def score_pct(self) -> Optional[str]:
        if self.score is None:
            return None
        pct = round(self.score * 100) if self.score <= 1 else round(self.score)
        return f"{pct}%"

    @property
    def score_int(self) -> Optional[int]:
        if self.score is None:
            return None
        return round(self.score * 100) if self.score <= 1 else round(self.score)

    @property
    def grade_label(self) -> str:
        return {"A": "Strong match", "B": "Good match", "C": "Weak match"}.get(self.grade_computed, "")

    @property
    def location(self) -> str:
        return ", ".join(filter(None, [self.city, self.state]))

    @property
    def salary_float(self) -> Optional[float]:
        return _parse_salary(self.salary)

    @property
    def salary_display(self) -> str:
        n = self.salary_float
        if n is None:
            return "Not specified"
        return f"€{n:,.0f}/mo"

    @property
    def skill_list_en(self) -> list[str]:
        return _split_skills(self.skills_en) or _split_skills(self.skills)

    @property
    def skill_list_original(self) -> list[str]:
        return _split_skills(self.skills)

    @property
    def description_text(self) -> str:
        return self.description or self.description_snippet or ""

    @property
    def has_location(self) -> bool:
        return self.lat is not None and self.lon is not None

    # ── Constructors ──────────────────────────────────────────

    @classmethod
    def from_dict(cls, data: dict) -> "JobDetail":
        """Build a JobDetail from any raw job dict (search, chat, fixture)."""
        score_raw = data.get("score")
        try:
            score = float(score_raw) if score_raw is not None else None
        except (TypeError, ValueError):
            score = None

        grade_raw = data.get("grade")
        grade = grade_raw if grade_raw and grade_raw not in ("?", "") else None

        return cls(
            job_id=str(data.get("job_id") or ""),
            title=str(data.get("title") or ""),
            company=str(data.get("company") or ""),
            state=str(data.get("state") or ""),
            city=str(data.get("city") or ""),
            lat=_float_or_none(data.get("lat")),
            lon=_float_or_none(data.get("lon")),
            salary=_str_or_none(data.get("salary")),
            occ_group=_str_or_none(data.get("occ_group")),
            portal=_str_or_none(data.get("portal")),
            posted=_str_or_none(data.get("posted")),
            url=_str_or_none(data.get("url")),
            description=_str_or_none(data.get("description")),
            description_snippet=_str_or_none(data.get("description_snippet")),
            skills=_str_or_none(data.get("skills")),
            skills_en=_str_or_none(data.get("skills_en")),
            score=score,
            grade=grade,
            match_reason=_str_or_none(data.get("match_reason")),
            _batch=str(data.get("_batch") or "search"),
        )

    def to_dict(self) -> dict:
        """Serialise to a flat dict suitable for JSON / Jinja template rendering."""
        return {
            "job_id":        self.job_id,
            "title":         self.title,
            "company":       self.company,
            "state":         self.state,
            "city":          self.city,
            "location":      self.location,
            "lat":           self.lat,
            "lon":           self.lon,
            "salary":        self.salary,
            "salary_float":  self.salary_float,
            "salary_display": self.salary_display,
            "occ_group":     self.occ_group,
            "portal":        self.portal,
            "posted":        (self.posted or "")[:10] or None,
            "url":           self.url,
            "description":   self.description,
            "description_snippet": self.description_snippet,
            "description_text": self.description_text,
            "skills":        self.skills,
            "skills_en":     self.skills_en,
            "skill_list_en": self.skill_list_en,
            "score":         self.score,
            "score_int":     self.score_int,
            "score_pct":     self.score_pct,
            "grade":         self.grade_computed,
            "grade_label":   self.grade_label,
            "match_reason":  self.match_reason,
            "_batch":        self._batch,
        }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _float_or_none(v) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _str_or_none(v) -> Optional[str]:
    if v is None:
        return None
    s = str(v).strip()
    return s if s and s.lower() not in ("none", "null", "undefined") else None
