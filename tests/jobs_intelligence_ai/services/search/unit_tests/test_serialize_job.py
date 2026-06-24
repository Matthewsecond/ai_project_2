"""
Behavior of serialize_job (the DB-row → flat job-dict mapping) in services/search/utils.

Originally a pinning test for a planned move to shared/job.py, but that move was DROPPED
(2.5): the only second caller, chat._apply_row, was deleted with the job-search chat (2.3 #5),
so serialize_job is single-domain and stays in search/utils. Relocated here from
shared/unit_tests in the 2.5 follow-up.
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
