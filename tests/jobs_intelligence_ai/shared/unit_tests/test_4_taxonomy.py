"""
Pin the CURRENT behavior of the role/sector taxonomy before it moves to
shared/taxonomy.py (Stage 2.1e). Imports flip to shared in 2.1e; asserts stay identical.
"""
from jobs_intelligence_ai import taxonomy


def test_constants_present():
    assert taxonomy.OTHER == "Other"
    assert isinstance(taxonomy.SECTORS, list) and taxonomy.SECTORS
    for s in taxonomy.SECTORS:
        assert "id" in s and "label" in s and "pattern" in s


def test_find_sector_roundtrip_by_label_and_id():
    s0 = taxonomy.SECTORS[0]
    assert taxonomy.find_sector([s0["label"]]) == s0["id"]
    assert taxonomy.find_sector([s0["id"]]) == s0["id"]


def test_find_sector_misses_return_none():
    assert taxonomy.find_sector([]) is None
    assert taxonomy.find_sector(["zzz-not-a-real-sector-zzz"]) is None


def test_family_labels_are_listed_for_sectors_with_families():
    # At least one sector should expose role families (the funnel's tier 2).
    assert any(taxonomy.family_labels(s["id"]) for s in taxonomy.SECTORS)
