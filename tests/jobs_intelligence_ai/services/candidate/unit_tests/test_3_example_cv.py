"""
Offline unit tests for the example-CV PDF builders (2.3 #7).

example_cv is pure reportlab (no LLM, no DB), so just exercise each public generator and
assert it emits a real, non-empty PDF.
"""
import pytest

from jobs_intelligence_ai.services.candidate import (
    generate_example_cv_pdf, generate_example_cv_pdf_2, generate_example_cv_pdf_sk,
)


@pytest.mark.parametrize("gen", [
    generate_example_cv_pdf, generate_example_cv_pdf_2, generate_example_cv_pdf_sk,
])
def test_example_cv_emits_pdf(gen):
    """Each sample-CV generator returns non-empty PDF bytes."""
    pdf = gen()
    assert pdf[:5] == b"%PDF-"
    assert len(pdf) > 1000
