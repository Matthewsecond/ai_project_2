"""
grade() score → A/B/C banding. Moved from services/search/utils.py to
shared/grading.py in Stage 2.5 (kills the search→enrichment sideways import).
"""
import pytest

from jobs_intelligence_ai.shared.grading import grade

A_MIN, B_MIN = 0.80, 0.60


@pytest.mark.parametrize("score,expected", [
    (1.00, "A"),
    (0.80, "A"),   # boundary: >= a_min
    (0.799, "B"),
    (0.60, "B"),   # boundary: >= b_min
    (0.599, "C"),
    (0.00, "C"),
])
def test_grade_bands(score, expected):
    assert grade(score, A_MIN, B_MIN) == expected
