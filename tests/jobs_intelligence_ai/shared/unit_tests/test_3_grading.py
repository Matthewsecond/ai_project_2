"""
Pin the CURRENT behavior of grade() (score → A/B/C banding) before it moves to
shared/grading.py (Stage 2.1d). Imports flip to shared in 2.1d; asserts stay identical.
"""
import pytest

from jobs_intelligence_ai.search.utils import grade

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
