from __future__ import annotations

from packages.qre_research.alpha_discovery.contracts import (
    EXECUTION_TIER_EMPIRICAL_SCREENING,
    EXECUTION_TIER_EXECUTOR_SMOKE,
    CampaignEvidence,
    ExperimentAdmissionDecision,
    ExperimentContract,
    content_id,
)
from packages.qre_research.alpha_discovery.evaluation import CanonicalEvidenceEvaluator
from packages.qre_research.alpha_discovery.learning import StructuredLessonCompressor


def _experiment() -> ExperimentContract:
    return ExperimentContract(
        experiment_id="qexp_fixture",
        hypothesis_id="qah_fixture",
        research_question="fixture",
        predicted_observable="fixture observable",
        counter_hypothesis="fixture counter",
        universe_spec="single_asset_liquid_cache_universe",
        timeframe="1d",
        sampling_frequency="1d",
        required_data_fields=("close",),
        required_history="fixture",
        required_point_in_time_metadata=("timestamp_utc",),
        required_features=("close",),
        signal_semantics="fixture",
        position_semantics="long_only",
        entry_semantics="fixture",
        exit_semantics="fixture",
        portfolio_semantics="fixture",
        null_models=("null_hold",),
        falsification_tests=("fixture",),
        confounder_controls=("cost_only_baseline",),
        transaction_cost_model="canonical_fixed_cost_proxy",
        slippage_model="canonical_zero_slippage_proxy",
        IS_policy="fixture",
        validation_policy="fixture",
        locked_OOS_policy="fixture",
        embargo_policy="fixture",
        warmup_policy="fixture",
        minimum_signal_count=3,
        minimum_trade_count=3,
        success_criteria=("fixture",),
        failure_criteria=("fixture",),
        required_evidence_families=("controlled_evaluation",),
        requested_execution_tier=EXECUTION_TIER_EMPIRICAL_SCREENING,
        content_identity=content_id("qexp", "fixture"),
    )


def _admission(*, decision: str, admitted_tier: str, oos_sufficiency: str = "INSUFFICIENT") -> ExperimentAdmissionDecision:
    return ExperimentAdmissionDecision(
        hypothesis_id="qah_fixture",
        experiment_id="qexp_fixture",
        strategy_spec_id="qss_fixture",
        data_requirement_id="qdr_fixture",
        requested_tier=EXECUTION_TIER_EMPIRICAL_SCREENING,
        admitted_tier=admitted_tier,
        source_quality="READY",
        identity_readiness="SUFFICIENT",
        history_sufficiency="SUFFICIENT",
        activity_sufficiency="INSUFFICIENT",
        validation_sufficiency="SUFFICIENT",
        OOS_sufficiency=oos_sufficiency,
        cost_model_sufficiency="SUFFICIENT",
        slippage_model_sufficiency="INSUFFICIENT",
        null_control_readiness="SUFFICIENT",
        stability_readiness="SUFFICIENT",
        fragility_readiness="INSUFFICIENT",
        outlier_readiness="SUFFICIENT",
        requested_tier_not_met=False,
        empirical_campaign_created=admitted_tier != EXECUTION_TIER_EXECUTOR_SMOKE,
        smoke_execution_created=admitted_tier == EXECUTION_TIER_EXECUTOR_SMOKE,
        mechanism_learning_allowed=admitted_tier != EXECUTION_TIER_EXECUTOR_SMOKE,
        decision=decision,
        reason_codes=(),
        content_identity=content_id("qadm", {"decision": decision, "tier": admitted_tier}),
    )


def test_smoke_run_produces_process_lesson_without_prior_adjustment() -> None:
    evaluator = CanonicalEvidenceEvaluator()
    compressor = StructuredLessonCompressor()
    assessment = evaluator.evaluate(
        _experiment(),
        CampaignEvidence(
            campaign_id="qcam_fixture",
            experiment_id="qexp_fixture",
            strategy_spec_id="qss_fixture",
            execution_tier=EXECUTION_TIER_EXECUTOR_SMOKE,
            empirical=False,
            backtest_result={"summary": {"totaal_trades": 1, "net_return_compound": 0.01}},
            data_plan={},
            content_identity=content_id("qcev", "fixture"),
        ),
        _admission(decision="ADMIT_EXECUTOR_SMOKE", admitted_tier=EXECUTION_TIER_EXECUTOR_SMOKE),
    )

    lesson = compressor.compress(assessment, {"strategy_spec_id": "qss_fixture"})

    assert assessment.evidence_grade == "smoke_only"
    assert assessment.prior_adjustment_allowed is False
    assert lesson.lesson_type == "PROCESS_LESSON"
    assert lesson.prior_adjustment_allowed is False


def test_insufficient_activity_keeps_mechanism_inconclusive_even_if_null_is_rejected() -> None:
    evaluator = CanonicalEvidenceEvaluator()
    assessment = evaluator.evaluate(
        _experiment(),
        CampaignEvidence(
            campaign_id="qcam_fixture",
            experiment_id="qexp_fixture",
            strategy_spec_id="qss_fixture",
            execution_tier=EXECUTION_TIER_EMPIRICAL_SCREENING,
            empirical=True,
            backtest_result={"summary": {"totaal_trades": 0, "net_return_compound": -0.02}},
            data_plan={},
            content_identity=content_id("qcev", "fixture"),
        ),
        _admission(decision="ADMIT_EMPIRICAL_SCREENING", admitted_tier=EXECUTION_TIER_EMPIRICAL_SCREENING),
    )

    assert assessment.null_outcome == "INCONCLUSIVE"
    assert assessment.mechanism_support_outcome == "INCONCLUSIVE"
    assert assessment.slippage_sufficiency == "INSUFFICIENT"
    assert assessment.OOS_sufficiency == "INSUFFICIENT"


def test_data_lesson_never_recommends_threshold_relaxation() -> None:
    evaluator = CanonicalEvidenceEvaluator()
    compressor = StructuredLessonCompressor()
    assessment = evaluator.evaluate(
        _experiment(),
        CampaignEvidence(
            campaign_id="qcam_fixture",
            experiment_id="qexp_fixture",
            strategy_spec_id="qss_fixture",
            execution_tier=EXECUTION_TIER_EMPIRICAL_SCREENING,
            empirical=True,
            backtest_result={"summary": {"totaal_trades": 0, "net_return_compound": 0.0}},
            data_plan={},
            content_identity=content_id("qcev", "fixture"),
        ),
        _admission(decision="ADMIT_EMPIRICAL_SCREENING", admitted_tier=EXECUTION_TIER_EMPIRICAL_SCREENING),
    )

    lesson = compressor.compress(assessment, {"strategy_spec_id": "qss_fixture"})

    assert lesson.lesson_type == "DATA_LESSON"
    assert "lower the minimum activity threshold" not in lesson.recommended_next_question
    assert lesson.prior_adjustment_allowed is False
