"""v3.15.7 — phase-aware screening criteria dispatch (pure)."""

from __future__ import annotations

import pytest

from research.screening_criteria import (
    EXPLORATORY_MAX_DRAWDOWN,
    EXPLORATORY_MIN_EXPECTANCY,
    EXPLORATORY_MIN_PROFIT_FACTOR,
    apply_phase_aware_criteria,
)


def _good_legacy_metrics() -> dict:
    return {"goedgekeurd": True}


def _bad_legacy_metrics() -> dict:
    return {"goedgekeurd": False}


def _good_exploratory_metrics() -> dict:
    return {
        "goedgekeurd": False,  # legacy fail; exploratory ignores it
        "expectancy": 0.05,
        "profit_factor": 1.5,
        "max_drawdown": 0.30,
        "win_rate": 0.45,
    }


def test_thresholds_have_expected_constants():
    """Pin v3.15.7 start-values."""
    assert EXPLORATORY_MIN_EXPECTANCY == 0.0
    assert EXPLORATORY_MIN_PROFIT_FACTOR == 1.05
    assert EXPLORATORY_MAX_DRAWDOWN == 0.45


@pytest.mark.parametrize("phase", [None, "standard", "promotion_grade"])
def test_legacy_phases_use_goedgekeurd_pass(phase):
    passed, reason = apply_phase_aware_criteria(_good_legacy_metrics(), phase)
    assert passed is True
    assert reason is None


@pytest.mark.parametrize("phase", [None, "standard", "promotion_grade"])
def test_legacy_phases_use_goedgekeurd_fail(phase):
    passed, reason = apply_phase_aware_criteria(_bad_legacy_metrics(), phase)
    assert passed is False
    assert reason == "screening_criteria_not_met"


def test_exploratory_passes_when_metrics_meet_floor():
    passed, reason = apply_phase_aware_criteria(
        _good_exploratory_metrics(), "exploratory"
    )
    assert passed is True
    assert reason is None


def test_exploratory_ignores_goedgekeurd():
    """Trend-case parity: legacy fails, exploratory passes."""
    metrics = _good_exploratory_metrics()
    metrics["goedgekeurd"] = False  # explicit
    legacy_passed, _ = apply_phase_aware_criteria(metrics, "promotion_grade")
    exploratory_passed, _ = apply_phase_aware_criteria(metrics, "exploratory")
    assert legacy_passed is False
    assert exploratory_passed is True


def test_exploratory_fails_on_zero_expectancy():
    metrics = _good_exploratory_metrics()
    metrics["expectancy"] = 0.0  # exactly 0; helper requires strict > 0
    passed, reason = apply_phase_aware_criteria(metrics, "exploratory")
    assert passed is False
    assert reason == "expectancy_not_positive"


def test_exploratory_fails_on_negative_expectancy():
    metrics = _good_exploratory_metrics()
    metrics["expectancy"] = -0.01
    passed, reason = apply_phase_aware_criteria(metrics, "exploratory")
    assert passed is False
    assert reason == "expectancy_not_positive"


def test_exploratory_fails_on_low_profit_factor():
    metrics = _good_exploratory_metrics()
    metrics["profit_factor"] = 1.0  # < 1.05 floor
    passed, reason = apply_phase_aware_criteria(metrics, "exploratory")
    assert passed is False
    assert reason == "profit_factor_below_floor"


def test_exploratory_fails_on_drawdown_above_limit():
    metrics = _good_exploratory_metrics()
    metrics["max_drawdown"] = 0.50  # > 0.45 ceiling
    passed, reason = apply_phase_aware_criteria(metrics, "exploratory")
    assert passed is False
    assert reason == "drawdown_above_exploratory_limit"


def test_exploratory_does_not_check_win_rate():
    """win_rate is diagnostic-only for exploratory."""
    metrics = _good_exploratory_metrics()
    metrics["win_rate"] = 0.0  # extreme low; exploratory still passes
    passed, reason = apply_phase_aware_criteria(metrics, "exploratory")
    assert passed is True
    assert reason is None


def test_unknown_phase_falls_through_to_legacy():
    """Defensive fallback — preset validation catches unknown phases
    upstream, but the helper must not branch on undefined values.
    """
    passed_pass, _ = apply_phase_aware_criteria(_good_legacy_metrics(), "future_phase")
    assert passed_pass is True
    passed_fail, reason = apply_phase_aware_criteria(_bad_legacy_metrics(), "future_phase")
    assert passed_fail is False
    assert reason == "screening_criteria_not_met"


def test_all_three_promotion_grade_gates_failures_collapse_to_one_reason():
    """Legacy path uses goedgekeurd AND-gate; reason is always
    ``screening_criteria_not_met`` regardless of which engine
    criterion failed.
    """
    passed, reason = apply_phase_aware_criteria(
        {"goedgekeurd": False, "win_rate": 0.30}, "promotion_grade"
    )
    assert reason == "screening_criteria_not_met"
