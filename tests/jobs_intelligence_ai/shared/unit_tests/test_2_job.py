"""
Pin the CURRENT behavior of serialize_job (the DB-row → flat job-dict mapping)
before it moves to shared/job.py (Stage 2.1c).

serialize_job is the "fresh dict" path; chat._apply_row is the "overlay" path.
They share the same field map — when shared/job.py is built, BOTH serialize_job
and the new overlay_job must reproduce these results. Imports flip to shared in 2.1c;
asserts stay identical (equivalence guard).
"""
from jobs_intelligence_ai.services.search.utils import serialize_job


def test_serialize_maps_core_fields(sample_job_row):
    out = serialize_job(sample_job_row)
    assert out["job_id"] == "1166922"
    assert out["title"] == "Key Account Manager"
    assert out["company"] == "CoolPeople s. r. o."
    assert out["city"] == "Bratislava"
    assert out["url"] == "https://example.com/jobs/1166922"
    assert out["portal"] == "profesia.sk"


def test_serialize_applies_defaults_for_missing():
    out = serialize_job({})
    assert out["title"] == "Untitled"      # default when absent
    assert out["company"] == "Unknown"     # default when absent
    assert out["job_id"] is None


def test_serialize_blank_strings_become_none_or_default(col):
    row = {col["title"]: "   ", col["company"]: "", col["city"]: "  Vienna  "}
    out = serialize_job(row)
    assert out["title"] == "Untitled"      # whitespace-only → None → default
    assert out["company"] == "Unknown"
    assert out["city"] == "Vienna"         # _str strips surrounding whitespace


def test_serialize_shape_is_stable(sample_job_row):
    out = serialize_job(sample_job_row)
    # A representative slice of the canonical job-dict shape that downstream
    # (API, templates, chat) depends on. Pinned so the merge can't silently drop keys.
    expected = {"job_id", "title", "company", "state", "city", "salary", "url",
                "portal", "occ_group", "posted", "description", "lat", "lon"}
    assert expected <= set(out.keys())
