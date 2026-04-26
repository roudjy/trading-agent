"""v3.15.7 — outcome dict additive visibility for screening pass/fail.

Pins the matrix from §8.2 of the v3.15.7 plan: ``pass_kind`` is
set ONLY on screening pass, mirroring the phase. Rejected samples
have ``pass_kind=None``. ``screening_criteria_set`` is "exploratory"
only when phase == "exploratory" — else "legacy".

Critical v3.15.6 invariant: outcome dict must NOT contain a
``screening_phase`` key.
"""

from __future__ import annotations

import json
from typing import Any

import pytest


def _build_outcome(
    *,
    legacy_status: str,
    screening_phase: str | None,
    last_metrics: dict | None = None,
) -> dict[str, Any]:
    """Mirror the construction in
    ``research/screening_runtime.py::execute_screening_candidate_samples``.
    Avoids running the engine; this test pins the aggregate logic
    that is sample-loop-independent.
    """
    last_metrics = last_metrics or {}
    if legacy_status == "promoted_to_validation":
        pass_kind: str | None = screening_phase
    else:
        pass_kind = None
    screening_criteria_set = (
        "exploratory" if screening_phase == "exploratory" else "legacy"
    )
    diagnostic_metrics = {
        "expectancy": float(last_metrics.get("expectancy", 0.0)),
        "profit_factor": float(last_metrics.get("profit_factor", 0.0)),
        "win_rate": float(last_metrics.get("win_rate", 0.0)),
        "max_drawdown": float(last_metrics.get("max_drawdown", 0.0)),
    }
    return {
        "legacy_decision": {"status": legacy_status},
        "decision": legacy_status,
        "pass_kind": pass_kind,
        "screening_criteria_set": screening_criteria_set,
        "diagnostic_metrics": diagnostic_metrics,
    }


PASS_FAIL_MATRIX = [
    # (phase, status, expected pass_kind, expected criteria_set)
    ("exploratory",     "promoted_to_validation",   "exploratory",     "exploratory"),
    ("exploratory",     "rejected_in_screening",    None,              "exploratory"),
    ("standard",        "promoted_to_validation",   "standard",        "legacy"),
    ("standard",        "rejected_in_screening",    None,              "legacy"),
    ("promotion_grade", "promoted_to_validation",   "promotion_grade", "legacy"),
    ("promotion_grade", "rejected_in_screening",    None,              "legacy"),
    (None,              "promoted_to_validation",   None,              "legacy"),
    (None,              "rejected_in_screening",    None,              "legacy"),
]


@pytest.mark.parametrize("phase,status,exp_pass_kind,exp_criteria", PASS_FAIL_MATRIX)
def test_pass_kind_matrix_per_v3_15_7_section_8_2(
    phase, status, exp_pass_kind, exp_criteria
) -> None:
    outcome = _build_outcome(legacy_status=status, screening_phase=phase)
    assert outcome["pass_kind"] == exp_pass_kind
    assert outcome["screening_criteria_set"] == exp_criteria


def test_outcome_dict_does_not_contain_screening_phase_key():
    """v3.15.6 invariant: the outcome dict surfaces ``pass_kind`` as
    its phase-mirror — but the literal key ``screening_phase`` is
    forbidden, since v3.15.6's propagation tests pin its absence
    against the screening_process source.
    """
    for phase in ("exploratory", "standard", "promotion_grade", None):
        for status in ("promoted_to_validation", "rejected_in_screening"):
            outcome = _build_outcome(legacy_status=status, screening_phase=phase)
            assert "screening_phase" not in outcome


def test_diagnostic_metrics_keys_are_finite_floats():
    outcome = _build_outcome(
        legacy_status="promoted_to_validation",
        screening_phase="exploratory",
        last_metrics={"expectancy": 0.05, "profit_factor": 1.5,
                      "win_rate": 0.45, "max_drawdown": 0.30},
    )
    diag = outcome["diagnostic_metrics"]
    assert set(diag.keys()) == {"expectancy", "profit_factor", "win_rate", "max_drawdown"}
    json.dumps(diag, allow_nan=False)


def test_diagnostic_metrics_default_to_zero_when_no_metrics():
    outcome = _build_outcome(
        legacy_status="rejected_in_screening",
        screening_phase=None,
        last_metrics=None,
    )
    for value in outcome["diagnostic_metrics"].values():
        assert value == 0.0


def test_screening_runtime_outcome_includes_v3_15_7_fields():
    """Source-level pin: the production screening_runtime.py must
    add the three new keys to its outcome dict.
    """
    import inspect
    import research.screening_runtime as runtime_module

    src = inspect.getsource(runtime_module.execute_screening_candidate_samples)
    assert '"pass_kind"' in src
    assert '"screening_criteria_set"' in src
    assert '"diagnostic_metrics"' in src
    assert '"screening_phase"' not in src or src.count('"screening_phase"') == 0
