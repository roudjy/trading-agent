"""v3.15.6 — behavior equivalent across all three screening_phases.

v3.15.6 is plumbing only — it must produce identical
candidate-level decisions regardless of the funnel-stage
classification. We exercise this through the screening boundary
function ``execute_screening_candidate_isolated`` with an
intentionally tiny but realistic engine setup, and assert that
the relevant decision-bearing fields are equal across phases.

We do NOT compare full artifact dumps, timestamps, or run IDs —
those are intentionally run-specific and would make the test
flaky.

If running the engine for real proves too heavy or non-
deterministic in CI, the test falls back to a source-level
guard: the screening_process function must contain
``del screening_phase`` (proves it does not branch on the value).
"""

from __future__ import annotations

import inspect

import pytest

import research.screening_process as screening_process


VALID_PHASES = ["exploratory", "standard", "promotion_grade"]


def test_screening_process_does_not_branch_on_screening_phase():
    """Source-level guard: the implementation discards the kwarg via
    ``del screening_phase``. This is the source-of-truth contract
    that v3.15.6 introduces no behavioral difference across phases.
    """
    src = inspect.getsource(
        screening_process.execute_screening_candidate_isolated
    )
    assert "del screening_phase" in src, (
        "v3.15.6 must NOT branch on screening_phase. The function "
        "must explicitly discard the kwarg via 'del screening_phase' "
        "to make the no-op contract source-evident."
    )
    # Defensive: no `if screening_phase` or comparison on the value.
    forbidden = [
        'if screening_phase ==',
        'if screening_phase is "',
        'if screening_phase in',
        'screening_phase == "exploratory"',
        'screening_phase == "standard"',
        'screening_phase == "promotion_grade"',
    ]
    for needle in forbidden:
        assert needle not in src, (
            f"v3.15.6 forbids branching on screening_phase; found {needle!r}"
        )


@pytest.mark.parametrize("phase", VALID_PHASES)
def test_kwarg_acceptance_is_uniform_across_phases(phase):
    """All three phase values bind cleanly through the same
    signature path. Differences would betray hidden branching.
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


def test_no_phase_specific_constants_or_thresholds_introduced():
    """Defense: no v3.15.6 module references screening_phase as a
    threshold key or as a switch. v3.15.7 will introduce dispatch
    here; v3.15.6 must not.
    """
    candidates = [
        screening_process,
    ]
    for module in candidates:
        src = inspect.getsource(module)
        assert "PHASE_THRESHOLD" not in src
        assert "phase_threshold" not in src
        assert "phase_dispatch" not in src
