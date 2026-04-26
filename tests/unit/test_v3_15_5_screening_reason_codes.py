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


# v3.15.5 canonical base set. Later versions (v3.15.7+) MAY add
# additional codes additively; this test asserts the base set is
# preserved as a subset, not exact equality.
V3_15_5_BASE = frozenset({
    "insufficient_trades",
    "no_oos_samples",
    "screening_criteria_not_met",
})


def test_screening_reason_codes_is_frozenset():
    assert isinstance(SCREENING_REASON_CODES, frozenset)


def test_screening_reason_codes_v3_15_5_base_preserved():
    """v3.15.5 base codes must remain in SCREENING_REASON_CODES.
    Later versions (v3.15.7) extend the set additively.
    """
    assert V3_15_5_BASE.issubset(SCREENING_REASON_CODES)


SCREENING_LAYER_FILES = (
    Path("research/screening_runtime.py"),
    Path("research/screening_process.py"),
    Path("research/candidate_pipeline.py"),
    # v3.15.7: phase-aware criteria emit additional reason codes
    # (expectancy_not_positive, profit_factor_below_floor,
    #  drawdown_above_exploratory_limit). Include the dispatch
    # module so the source-presence check stays comprehensive.
    Path("research/screening_criteria.py"),
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
