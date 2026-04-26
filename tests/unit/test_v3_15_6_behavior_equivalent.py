"""v3.15.6 behavior contract — superseded by v3.15.7 phase-aware dispatch.

The original v3.15.6 contract (no-branching on screening_phase,
no phase-specific constants in the screening layer) is
**intentionally superseded** by v3.15.7. This file keeps the
historical pin available — but reformulated so it pins the
v3.15.7-aware behavior instead of the now-incorrect v3.15.6
no-branching invariant.

Tests retained:

- ``test_kwarg_acceptance_is_uniform_across_phases`` — still
  valid; the signature contract did not change.

Tests reformulated:

- ``test_v3_15_7_intentionally_supersedes_v3_15_6_no_branching``
  (was ``test_screening_process_does_not_branch_on_screening_phase``)
- ``test_v3_15_7_phase_specific_constants_in_screening_criteria_only``
  (was ``test_no_phase_specific_constants_or_thresholds_introduced``)

Both reformulated tests carry an explicit docstring describing
the supersession.
"""

from __future__ import annotations

import inspect

import pytest

import research.screening_criteria as screening_criteria
import research.screening_process as screening_process
import research.screening_runtime as screening_runtime


VALID_PHASES = ["exploratory", "standard", "promotion_grade"]


def test_v3_15_7_intentionally_supersedes_v3_15_6_no_branching():
    """v3.15.6 invariant intentionally superseded by v3.15.7
    phase-aware dispatch.

    v3.15.6 pinned that ``execute_screening_candidate_isolated``
    discarded the ``screening_phase`` kwarg via
    ``del screening_phase`` and contained no branching strings —
    that contract is now superseded. v3.15.7 propagates the phase
    into ``execute_screening_candidate_samples`` and dispatches via
    the pure helper ``apply_phase_aware_criteria``.

    What this test now pins:

    - ``screening_runtime`` imports the v3.15.7 helper.
    - ``screening_runtime.execute_screening_candidate_samples``
      accepts ``screening_phase`` and references the helper.
    - The screening_process boundary still accepts the kwarg
      (v3.15.6 seam contract).
    """
    runtime_src = inspect.getsource(screening_runtime)
    assert "from research.screening_criteria import apply_phase_aware_criteria" in runtime_src
    assert "apply_phase_aware_criteria(metrics, screening_phase)" in runtime_src
    samples_sig = inspect.signature(
        screening_runtime.execute_screening_candidate_samples
    )
    assert "screening_phase" in samples_sig.parameters
    process_sig = inspect.signature(
        screening_process.execute_screening_candidate_isolated
    )
    assert "screening_phase" in process_sig.parameters


def test_v3_15_7_phase_specific_constants_in_screening_criteria_only():
    """v3.15.6 invariant intentionally superseded by v3.15.7.

    v3.15.6 forbade phase-specific thresholds anywhere in the
    screening layer. v3.15.7 introduces three exploratory
    thresholds, but they live exclusively in
    ``research/screening_criteria.py`` — NOT in
    ``screening_runtime.py`` or ``screening_process.py``. This
    keeps the dispatch site discoverable in one place.
    """
    crit_src = inspect.getsource(screening_criteria)
    runtime_src = inspect.getsource(screening_runtime)
    process_src = inspect.getsource(screening_process)

    # The three constants exist exactly once, in screening_criteria.
    for name in (
        "EXPLORATORY_MIN_EXPECTANCY",
        "EXPLORATORY_MIN_PROFIT_FACTOR",
        "EXPLORATORY_MAX_DRAWDOWN",
    ):
        assert name in crit_src, f"{name} must live in screening_criteria.py"
        # Must NOT appear in the runtime / process source — those
        # files import the helper, not the constants.
        assert name not in runtime_src, (
            f"{name} leaked into screening_runtime.py — keep dispatch "
            "site in screening_criteria.py only."
        )
        assert name not in process_src, (
            f"{name} leaked into screening_process.py — keep dispatch "
            "site in screening_criteria.py only."
        )


# ---- preserved invariants --------------------------------------------------


@pytest.mark.parametrize("phase", VALID_PHASES)
def test_kwarg_acceptance_is_uniform_across_phases(phase):
    """v3.15.6 signature-binding contract — preserved verbatim.

    All three phase values bind cleanly through the same signature
    path. Differences would betray a hidden type-narrowing bug.
    """
    sig = inspect.signature(
        screening_process.execute_screening_candidate_isolated
    )
    bound = sig.bind_partial(
        strategy={"name": "x", "params": {}},
        candidate={"candidate_id": "c1", "asset": "A", "interval": "1d",
                   "strategy_name": "x"},
        interval_range={"start": "2024-01-01", "end": "2024-12-31"},
        evaluation_config={},
        regime_config=None,
        budget_seconds=1,
        max_samples=1,
        screening_phase=phase,
    )
    assert bound.arguments["screening_phase"] == phase
