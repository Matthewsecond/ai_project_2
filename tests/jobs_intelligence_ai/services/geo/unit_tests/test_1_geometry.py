"""
Offline unit tests for the geo reference geometry (2.3 #8).

Pure data (no LLM, no DB): pin the shape of the Austria polygon set so a bad regeneration
or accidental edit is caught — all 9 Bundesländer present, positive canvas dimensions, and
every polygon a list of (x, y) coordinate pairs within the declared bounds.
"""
from jobs_intelligence_ai.services.geo import AT_POLYGONS, AT_WIDTH, AT_HEIGHT

_STATES = {
    "VORARLBERG", "TIROL", "WIEN", "KÄRNTEN", "BURGENLAND",
    "OBERÖSTERREICH", "NIEDERÖSTERREICH", "STEIERMARK", "SALZBURG",
}


def test_all_nine_bundeslaender_present():
    """The geometry covers exactly Austria's 9 Bundesländer."""
    assert set(AT_POLYGONS) == _STATES


def test_canvas_dimensions_are_positive():
    """The normalized canvas has positive width/height for scaling."""
    assert AT_WIDTH > 0 and AT_HEIGHT > 0


def test_polygons_are_coordinate_pairs_in_bounds():
    """Every ring is a list of (x, y) pairs inside the declared canvas bounds."""
    for state, rings in AT_POLYGONS.items():
        assert rings, f"{state} has no rings"
        for ring in rings:
            assert len(ring) >= 3                      # a polygon needs ≥3 points
            for pt in ring:
                assert len(pt) == 2
                x, y = pt
                assert 0.0 <= x <= AT_WIDTH
                assert 0.0 <= y <= AT_HEIGHT
