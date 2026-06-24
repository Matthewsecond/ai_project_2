"""
grading.py — Score → A/B/C letter banding.

Shared because the search grader, the enrichment rescorer, and the cluster
blueprint all band a 0–1 match score into the same A/B/C letter. Keeping the one
rule here stops a service from importing it sideways out of `services/search`
(see RESTRUCTURE_PLAN §3 — a service never reaches into another service).

Thresholds stay caller-supplied (they live in global config as the cross-cutting
SCORE_A_MIN / SCORE_B_MIN) so this module is pure and dependency-free.
"""


def grade(score: float, a_min: float, b_min: float) -> str:
    """A/B/C letter for a score, using caller-supplied thresholds (from config)."""
    if score >= a_min:
        return "A"
    if score >= b_min:
        return "B"
    return "C"
