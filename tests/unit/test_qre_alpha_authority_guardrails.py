from __future__ import annotations

from types import SimpleNamespace

from packages.qre_research.alpha_discovery.contracts import (
    EXECUTION_TIER_COMPILER_ONLY,
    EXECUTION_TIER_EMPIRICAL_SCREENING,
    EXECUTION_TIER_EXECUTOR_SMOKE,
    EXECUTION_TIER_LOCKED_OOS_VALIDATION,
)
from packages.qre_research.alpha_discovery.runner import _assess_admission


def _admission(*, requested_tier: str, admissible_tier: str, locked_oos_rows: int, source_quality: str = "ready"):
    selected = SimpleNamespace(hypothesis_id="qah_fixture")
    experiment = SimpleNamespace(
        experiment_id="qexp_fixture",
        transaction_cost_model="canonical_costs",
        slippage_model="canonical_slippage",
        minimum_trade_count=3,
        null_models=("null",),
    )
    strategy_spec = SimpleNamespace(strategy_spec_id="qspec_fixture")
    data_requirement = SimpleNamespace(
        requirement_id="qdr_fixture",
        minimum_rows=90,
        minimum_expected_trades=3,
        minimum_validation_rows=20,
        minimum_locked_oos_rows=20,
    )
    data_plan = SimpleNamespace(
        selected_data={
            "effective_research_quality_status": source_quality,
            "source_identity_status": "ready",
            "row_count": 120,
            "estimated_activity": 5,
            "validation_rows": 25,
            "locked_oos_rows": locked_oos_rows,
        },
        admissible_execution_tier=admissible_tier,
        tier_downgrade_reasons=(),
        reason_codes=(),
    )
    coverage = SimpleNamespace(decision="COVERAGE_READY")
    acquisition = SimpleNamespace(reason_codes=())
    alignment = SimpleNamespace(alignment_status="ALIGNED")
    return _assess_admission(
        selected=selected,
        experiment=experiment,
        strategy_spec=strategy_spec,
        data_requirement=data_requirement,
        data_plan=data_plan,
        coverage=coverage,
        acquisition=acquisition,
        alignment=alignment,
        requested_execution_tier=requested_tier,
    )


def test_admitted_tier_never_exceeds_requested_tier() -> None:
    cases = (
        (EXECUTION_TIER_COMPILER_ONLY, EXECUTION_TIER_LOCKED_OOS_VALIDATION, EXECUTION_TIER_COMPILER_ONLY),
        (EXECUTION_TIER_EXECUTOR_SMOKE, EXECUTION_TIER_LOCKED_OOS_VALIDATION, EXECUTION_TIER_EXECUTOR_SMOKE),
        (EXECUTION_TIER_EMPIRICAL_SCREENING, EXECUTION_TIER_LOCKED_OOS_VALIDATION, EXECUTION_TIER_EMPIRICAL_SCREENING),
    )
    for requested_tier, admissible_tier, expected_tier in cases:
        admission = _admission(
            requested_tier=requested_tier,
            admissible_tier=admissible_tier,
            locked_oos_rows=0,
        )
        assert admission.requested_tier == requested_tier
        assert admission.admitted_tier == expected_tier
        assert admission.reason_codes


def test_locked_oos_request_needs_actual_locked_oos_rows() -> None:
    admission = _admission(
        requested_tier=EXECUTION_TIER_LOCKED_OOS_VALIDATION,
        admissible_tier=EXECUTION_TIER_EMPIRICAL_SCREENING,
        locked_oos_rows=0,
    )

    assert admission.requested_tier == EXECUTION_TIER_LOCKED_OOS_VALIDATION
    assert admission.admitted_tier == EXECUTION_TIER_EMPIRICAL_SCREENING
    assert admission.decision == "ADMIT_EMPIRICAL_SCREENING"
    assert "locked_oos_insufficient" in admission.reason_codes


def test_screening_only_source_cannot_promote_to_validation() -> None:
    admission = _admission(
        requested_tier=EXECUTION_TIER_LOCKED_OOS_VALIDATION,
        admissible_tier=EXECUTION_TIER_EMPIRICAL_SCREENING,
        locked_oos_rows=25,
        source_quality="ready",
    )

    assert admission.admitted_tier != EXECUTION_TIER_LOCKED_OOS_VALIDATION
    assert admission.decision != "ADMIT_LOCKED_OOS_VALIDATION"
    assert "validation_authority_missing" in admission.reason_codes or "requested_tier_ceiling" in admission.reason_codes
