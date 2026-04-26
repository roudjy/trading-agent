"""v3.15.5 SCREENING_REASON_CODES — frozenset shape + repo-presence pin.

The taxonomy frozenset MUST stay synchronized with the codes the
screening layer actually emits. We assert both:

1. The frozenset has the canonical v3.15.5 set.
2. Every code appears as a string literal somewhere inside the
   screening layer source (defensive guard against speculative
   codes drifting in).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from research.rejection_taxonomy import SCREENING_REASON_CODES


CANONICAL = frozenset({
    "insufficient_trades",
    "no_oos_samples",
    "screening_criteria_not_met",
})


def test_screening_reason_codes_is_frozenset():
    assert isinstance(SCREENING_REASON_CODES, frozenset)


def test_screening_reason_codes_canonical_set():
    assert SCREENING_REASON_CODES == CANONICAL


SCREENING_LAYER_FILES = (
    Path("research/screening_runtime.py"),
    Path("research/screening_process.py"),
    Path("research/candidate_pipeline.py"),
)


def test_screening_reason_codes_exist_in_screening_layer():
    blob = "\n".join(
        p.read_text(encoding="utf-8") for p in SCREENING_LAYER_FILES if p.exists()
    )
    missing = [code for code in SCREENING_REASON_CODES if code not in blob]
    assert missing == [], (
        f"v3.15.5 SCREENING_REASON_CODES drift: codes not found in "
        f"screening layer: {missing}. Either remove them from the set "
        f"or add the corresponding emission in the screening layer."
    )
