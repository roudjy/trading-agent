"""v3.15.7 — kern test: trend/momentum candidate met win_rate < 0.50
moet exploratory passeren en promotion_grade falen.
"""

from __future__ import annotations

from research.screening_criteria import apply_phase_aware_criteria


def _trend_metrics() -> dict:
    """Trend/momentum-like candidate: low win_rate but positive
    expectancy and healthy profit_factor (typical for trend
    strategies — winnen weinig keer maar veel; verliezen vaak maar
    weinig).
    """
    return {
        "win_rate": 0.45,
        "expectancy": 0.012,
        "profit_factor": 1.30,
        "max_drawdown": 0.30,
        # The engine ``goedgekeurd`` AND-gate fails here because of
        # the win_rate gate; exploratory must NOT consult goedgekeurd.
        "goedgekeurd": False,
    }


def test_trend_case_passes_exploratory():
    passed, reason = apply_phase_aware_criteria(_trend_metrics(), "exploratory")
    assert passed is True, "exploratory must pass on positive expectancy"
    assert reason is None


def test_trend_case_fails_promotion_grade():
    passed, reason = apply_phase_aware_criteria(_trend_metrics(), "promotion_grade")
    assert passed is False
    assert reason == "screening_criteria_not_met"


def test_trend_case_fails_standard():
    """``standard`` is conservative legacy in v3.15.7."""
    passed, reason = apply_phase_aware_criteria(_trend_metrics(), "standard")
    assert passed is False
    assert reason == "screening_criteria_not_met"


def test_trend_case_fails_none_phase():
    """None falls through to legacy for backward compat."""
    passed, reason = apply_phase_aware_criteria(_trend_metrics(), None)
    assert passed is False
    assert reason == "screening_criteria_not_met"


def test_high_win_rate_strict_strategy_still_passes_promotion_grade():
    """Symmetry: a strategy that legitimately passes legacy must
    also pass exploratory.
    """
    metrics = {
        "win_rate": 0.60,
        "expectancy": 0.02,
        "profit_factor": 2.0,
        "max_drawdown": 0.20,
        "goedgekeurd": True,
    }
    legacy_passed, _ = apply_phase_aware_criteria(metrics, "promotion_grade")
    exploratory_passed, _ = apply_phase_aware_criteria(metrics, "exploratory")
    assert legacy_passed is True
    assert exploratory_passed is True
