"""v3.15.9 — near-pass classification (REV 3 §6.10).

Pins:
  - eligibility limited to exactly one failed exploratory criterion
    in NEAR_PASS_ELIGIBLE_REASONS,
  - explicit unit-aware bands (expectancy 0.0005, profit/drawdown
    5% relative),
  - INELIGIBLE reasons (insufficient_trades, no_oos_samples, errors,
    timeouts) never near-pass,
  - non-exploratory phases never near-pass,
  - near-pass NEVER mutates pass/fail (invariant).
"""

from __future__ import annotations

from research.screening_criteria import (
    EXPLORATORY_MAX_DRAWDOWN,
    EXPLORATORY_MIN_EXPECTANCY,
    EXPLORATORY_MIN_PROFIT_FACTOR,
)
from research.screening_evidence import (
    EXPLORATORY_DRAWDOWN_NEAR_REL_BAND,
    EXPLORATORY_EXPECTANCY_NEAR_BAND,
    EXPLORATORY_PROFIT_FACTOR_NEAR_REL_BAND,
    NEAR_PASS_ELIGIBLE_REASONS,
    NEAR_PASS_INELIGIBLE_REASONS,
    is_near_pass,
)


def test_near_pass_constants_match_rev3() -> None:
    assert EXPLORATORY_EXPECTANCY_NEAR_BAND == 0.0005
    assert EXPLORATORY_PROFIT_FACTOR_NEAR_REL_BAND == 0.05
    assert EXPLORATORY_DRAWDOWN_NEAR_REL_BAND == 0.05
    assert NEAR_PASS_ELIGIBLE_REASONS == frozenset({
        "expectancy_not_positive",
        "profit_factor_below_floor",
        "drawdown_above_exploratory_limit",
    })
    assert "insufficient_trades" in NEAR_PASS_INELIGIBLE_REASONS


def test_expectancy_near_band_inside() -> None:
    is_near, payload = is_near_pass(
        screening_phase="exploratory",
        failure_reasons=["expectancy_not_positive"],
        metrics={"expectancy": -0.0001},
    )
    assert is_near is True
    assert payload is not None and payload["nearest_failed_criterion"] == "expectancy_not_positive"
    assert payload["distance"] == 0.0001


def test_expectancy_outside_band() -> None:
    is_near, _ = is_near_pass(
        screening_phase="exploratory",
        failure_reasons=["expectancy_not_positive"],
        metrics={"expectancy": -0.001},  # outside 0.0005 band
    )
    assert is_near is False


def test_profit_factor_near_band_inside() -> None:
    floor = EXPLORATORY_MIN_PROFIT_FACTOR
    pf = floor * (1.0 - EXPLORATORY_PROFIT_FACTOR_NEAR_REL_BAND)
    is_near, payload = is_near_pass(
        screening_phase="exploratory",
        failure_reasons=["profit_factor_below_floor"],
        metrics={"profit_factor": pf},
    )
    assert is_near is True
    assert payload is not None and payload["nearest_failed_criterion"] == "profit_factor_below_floor"


def test_profit_factor_outside_band() -> None:
    floor = EXPLORATORY_MIN_PROFIT_FACTOR
    pf = floor * 0.5
    is_near, _ = is_near_pass(
        screening_phase="exploratory",
        failure_reasons=["profit_factor_below_floor"],
        metrics={"profit_factor": pf},
    )
    assert is_near is False


def test_drawdown_near_band_inside() -> None:
    ceiling = EXPLORATORY_MAX_DRAWDOWN
    dd = ceiling * (1.0 + EXPLORATORY_DRAWDOWN_NEAR_REL_BAND)
    is_near, payload = is_near_pass(
        screening_phase="exploratory",
        failure_reasons=["drawdown_above_exploratory_limit"],
        metrics={"max_drawdown": dd},
    )
    assert is_near is True
    assert payload is not None and payload["nearest_failed_criterion"] == "drawdown_above_exploratory_limit"


def test_drawdown_outside_band() -> None:
    ceiling = EXPLORATORY_MAX_DRAWDOWN
    dd = ceiling * 1.5
    is_near, _ = is_near_pass(
        screening_phase="exploratory",
        failure_reasons=["drawdown_above_exploratory_limit"],
        metrics={"max_drawdown": dd},
    )
    assert is_near is False


def test_legacy_phase_never_near_pass() -> None:
    for phase in ("standard", "promotion_grade", None):
        is_near, _ = is_near_pass(
            screening_phase=phase,
            failure_reasons=["expectancy_not_positive"],
            metrics={"expectancy": -0.0001},
        )
        assert is_near is False


def test_insufficient_trades_never_near_pass() -> None:
    is_near, _ = is_near_pass(
        screening_phase="exploratory",
        failure_reasons=["insufficient_trades"],
        metrics={"expectancy": -0.0001},
    )
    assert is_near is False


def test_no_oos_samples_never_near_pass() -> None:
    is_near, _ = is_near_pass(
        screening_phase="exploratory",
        failure_reasons=["no_oos_samples"],
        metrics={},
    )
    assert is_near is False


def test_candidate_budget_exceeded_never_near_pass() -> None:
    is_near, _ = is_near_pass(
        screening_phase="exploratory",
        failure_reasons=["candidate_budget_exceeded"],
        metrics={},
    )
    assert is_near is False


def test_screening_candidate_error_never_near_pass() -> None:
    is_near, _ = is_near_pass(
        screening_phase="exploratory",
        failure_reasons=["screening_candidate_error"],
        metrics={},
    )
    assert is_near is False


def test_two_failure_reasons_never_near_pass() -> None:
    is_near, _ = is_near_pass(
        screening_phase="exploratory",
        failure_reasons=["expectancy_not_positive", "profit_factor_below_floor"],
        metrics={"expectancy": -0.0001, "profit_factor": 1.0},
    )
    assert is_near is False


def test_zero_failure_reasons_never_near_pass() -> None:
    """A passed screening has no failure reasons; near_pass must
    not promote it to a different stage_result via this path.
    """
    is_near, _ = is_near_pass(
        screening_phase="exploratory",
        failure_reasons=[],
        metrics={"expectancy": 0.001},
    )
    assert is_near is False


def test_unknown_failure_reason_never_near_pass() -> None:
    is_near, _ = is_near_pass(
        screening_phase="exploratory",
        failure_reasons=["screening_criteria_not_met"],  # legacy reason
        metrics={"expectancy": 0.001},
    )
    assert is_near is False


def test_metric_none_never_near_pass() -> None:
    is_near, _ = is_near_pass(
        screening_phase="exploratory",
        failure_reasons=["expectancy_not_positive"],
        metrics={"expectancy": None},
    )
    assert is_near is False


def test_min_expectancy_constant_used() -> None:
    """The boundary case expectancy == EXPLORATORY_MIN_EXPECTANCY (0.0)
    is inclusive — a candidate exactly at zero is the closest possible
    expectancy near-pass.
    """
    is_near, payload = is_near_pass(
        screening_phase="exploratory",
        failure_reasons=["expectancy_not_positive"],
        metrics={"expectancy": EXPLORATORY_MIN_EXPECTANCY},
    )
    assert is_near is True
    assert payload is not None and payload["distance"] == 0.0
