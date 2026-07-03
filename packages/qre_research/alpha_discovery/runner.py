from __future__ import annotations

import importlib
import json
import os
import tempfile
from collections.abc import Mapping
from contextlib import suppress
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pandas as pd

from packages.qre_data.dataset_catalog import materialize_data_truth
from packages.qre_research.generated_strategy_paths import validate_write_target

from .acquisition import execute_acquisition_once, throughput_snapshot
from .contracts import (
    EXECUTION_TIER_COMPILER_ONLY,
    EXECUTION_TIER_EMPIRICAL_SCREENING,
    EXECUTION_TIER_EXECUTOR_SMOKE,
    EXECUTION_TIER_LOCKED_OOS_VALIDATION,
    EXECUTION_TIERS,
    LESSON_TYPE_PROCESS,
    POLICY_VERSION,
    SCHEMA_VERSION,
    AcquisitionPlan,
    CampaignEvidence,
    CoverageAssessment,
    CoverageDecision,
    DiscoveryContext,
    EvidenceAssessment,
    ExperimentAdmissionDecision,
    HypothesisCritique,
    HypothesisRevision,
    HypothesisScorecard,
    MechanismImplementationAlignment,
    MechanisticHypothesis,
    ResearchLesson,
    RunBudgetUsage,
    content_id,
)
from .data_planner import build_data_requirement, resolve_data_plan
from .evaluation import CanonicalEvidenceEvaluator, DeterministicExAnteEvaluator
from .experiment_compiler import CanonicalExperimentPlanner
from .learning import StructuredLessonCompressor
from .observations import build_observation_snapshot
from .providers import (
    DeterministicHypothesisCritic,
    DeterministicHypothesisRewriter,
    DeterministicMechanisticHypothesisProvider,
)
from .strategy_compiler import build_alignment, build_strategy_spec, compile_strategy_spec
from .strategy_ir import ConditionNode, ControlNode, FeatureNode, PortfolioRule, SignalNode
from .universe_planner import plan_universe

OUTPUT_ROOT = Path("generated_research/alpha_discovery")
OBSERVATIONS_PATH = OUTPUT_ROOT / "observations" / "latest.json"
HYPOTHESES_PATH = OUTPUT_ROOT / "hypotheses" / "latest.json"
CRITIQUES_PATH = OUTPUT_ROOT / "critiques" / "latest.json"
REWRITES_PATH = OUTPUT_ROOT / "rewrites" / "latest.json"
SCORECARDS_PATH = OUTPUT_ROOT / "scorecards" / "latest.json"
EXPERIMENTS_PATH = OUTPUT_ROOT / "experiments" / "latest.json"
STRATEGIES_PATH = OUTPUT_ROOT / "strategies" / "latest.json"
DATA_PLANS_PATH = OUTPUT_ROOT / "data_plans" / "latest.json"
REQUIREMENTS_PATH = OUTPUT_ROOT / "requirements" / "latest.json"
UNIVERSE_PLANS_PATH = OUTPUT_ROOT / "universe_plans" / "latest.json"
ACQUISITIONS_PATH = OUTPUT_ROOT / "acquisitions" / "latest.json"
THROUGHPUT_PATH = OUTPUT_ROOT / "throughput" / "latest.json"
ADMISSIONS_PATH = OUTPUT_ROOT / "admissions" / "latest.json"
ALIGNMENTS_PATH = OUTPUT_ROOT / "alignments" / "latest.json"
EVIDENCE_ASSESSMENTS_PATH = OUTPUT_ROOT / "evidence_assessments" / "latest.json"
LESSONS_PATH = OUTPUT_ROOT / "lessons" / "latest.json"
REASSESSMENTS_PATH = OUTPUT_ROOT / "reassessments" / "latest.json"
RUNS_PATH = OUTPUT_ROOT / "runs" / "latest.json"
STATUS_PATH = OUTPUT_ROOT / "status" / "latest.json"

TIER_ALIAS = {
    "compiler": EXECUTION_TIER_COMPILER_ONLY,
    "smoke": EXECUTION_TIER_EXECUTOR_SMOKE,
    "screening": EXECUTION_TIER_EMPIRICAL_SCREENING,
    "oos": EXECUTION_TIER_LOCKED_OOS_VALIDATION,
    "auto": EXECUTION_TIER_EMPIRICAL_SCREENING,
}


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    validate_write_target(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
    if path.is_file():
        with suppress(OSError):
            if path.read_text(encoding="utf-8-sig") == text:
                return
    fd, tmp_name = tempfile.mkstemp(prefix=".qre_alpha_discovery.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        os.replace(tmp_name, path)
    except Exception:
        with suppress(OSError):
            os.unlink(tmp_name)
        raise


def _write_artifact(path: Path, payload: Mapping[str, Any], *, repo_root: Path) -> str:
    resolved = repo_root / path
    _atomic_json(resolved, payload)
    return resolved.as_posix()


def _serialize(items: list[Any]) -> list[Any]:
    serialized: list[Any] = []
    for item in items:
        if hasattr(item, "to_payload"):
            serialized.append(item.to_payload())
        elif hasattr(item, "__dataclass_fields__"):
            serialized.append(asdict(item))
        else:
            serialized.append(item)
    return serialized


def _latest_payload(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return None


def _public_data_plan(data_plan: CoverageDecision | None) -> dict[str, Any] | None:
    if data_plan is None:
        return None
    selected_data = {key: value for key, value in data_plan.selected_data.items() if key != "frame"}
    return {
        "decision": data_plan.decision,
        "coverage_decision": data_plan.coverage_decision,
        "requested_execution_tier": data_plan.requested_execution_tier,
        "admissible_execution_tier": data_plan.admissible_execution_tier,
        "tier_downgrade_reasons": list(data_plan.tier_downgrade_reasons),
        "reason_codes": list(data_plan.reason_codes),
        "selected_data": selected_data,
        "dataset_inventory": [
            {key: value for key, value in dict(item).items() if not str(key).startswith("__")}
            for item in data_plan.dataset_inventory
        ],
        "content_identity": data_plan.content_identity,
    }


def _build_hypothesis_specs(
    hypothesis: MechanisticHypothesis,
) -> tuple[tuple[FeatureNode, ...], SignalNode, tuple[dict[str, Any], ...], tuple[ControlNode, ...], PortfolioRule]:
    if hypothesis.mechanism_family == "trend_persistence":
        features = (
            FeatureNode("trend_anchor_delta", {"window": 50}, "trend_anchor_delta"),
            FeatureNode("normalized_trend_move", {"trend_anchor_window": 50, "atr_window": 14}, "normalized_trend_move"),
            FeatureNode("trend_anchor", {"window": 50}, "trend_anchor"),
        )
        signal = SignalNode(
            entry=ConditionNode(
                "and",
                left=ConditionNode("greater_than", left=FeatureNode("trend_anchor_delta", {"window": 50}, "trend_anchor_delta"), right=0.0),
                right=ConditionNode("greater_than", left=FeatureNode("normalized_trend_move", {"trend_anchor_window": 50, "atr_window": 14}, "normalized_trend_move"), right=0.75),
            ),
            exit=ConditionNode(
                "or",
                left=ConditionNode("less_than", left=FeatureNode("trend_anchor_delta", {"window": 50}, "trend_anchor_delta"), right=0.0),
                right=ConditionNode("less_than", left=FeatureNode("normalized_trend_move", {"trend_anchor_window": 50, "atr_window": 14}, "normalized_trend_move"), right=0.10),
            ),
        )
        params = (
            {"name": "trend_anchor_window", "type": "int", "value": 50},
            {"name": "atr_window", "type": "int", "value": 14},
            {"name": "entry_threshold", "type": "float", "value": 0.75},
        )
        controls = (ControlNode("regime_filter", {"feature_alias": "trend_anchor_delta", "threshold": 0.0, "comparator": "greater_than"}),)
        portfolio_rule = PortfolioRule(weight_semantics="single_strategy_unit_notional", selection_semantics="equal_weight", max_gross_exposure=1.0, max_rules=1)
    elif hypothesis.mechanism_family == "volatility_breakout":
        features = (
            FeatureNode("compression_ratio", {"atr_short_window": 5, "atr_long_window": 20}, "compression_ratio"),
            FeatureNode("normalized_trend_move", {"trend_anchor_window": 50, "atr_window": 14}, "normalized_trend_move"),
            FeatureNode("rolling_high_previous", {"window": 20}, "rolling_high_previous"),
        )
        signal = SignalNode(
            entry=ConditionNode(
                "and",
                left=ConditionNode("less_than", left=FeatureNode("compression_ratio", {"atr_short_window": 5, "atr_long_window": 20}, "compression_ratio"), right=0.6),
                right=ConditionNode("greater_than", left=FeatureNode("normalized_trend_move", {"trend_anchor_window": 50, "atr_window": 14}, "normalized_trend_move"), right=0.75),
            ),
            exit=ConditionNode(
                "or",
                left=ConditionNode("greater_than", left=FeatureNode("compression_ratio", {"atr_short_window": 5, "atr_long_window": 20}, "compression_ratio"), right=1.0),
                right=ConditionNode("less_than", left=FeatureNode("normalized_trend_move", {"trend_anchor_window": 50, "atr_window": 14}, "normalized_trend_move"), right=0.10),
            ),
        )
        params = (
            {"name": "atr_short_window", "type": "int", "value": 5},
            {"name": "atr_long_window", "type": "int", "value": 20},
            {"name": "compression_threshold", "type": "float", "value": 0.6},
        )
        controls = (
            ControlNode("regime_filter", {"feature_alias": "compression_ratio", "threshold": 1.0, "comparator": "less_than"}),
            ControlNode("cost_stress", {"multiplier": 1.5}),
        )
        portfolio_rule = PortfolioRule(weight_semantics="single_strategy_unit_notional", selection_semantics="equal_weight", max_gross_exposure=1.0, max_rules=1)
    else:
        features = (
            FeatureNode("zscore", {"lookback": 20}, "zscore"),
            FeatureNode("rolling_volatility", {"window": 20}, "rolling_volatility"),
        )
        signal = SignalNode(
            entry=ConditionNode("less_than", left=FeatureNode("zscore", {"lookback": 20}, "zscore"), right=-1.5),
            exit=ConditionNode("greater_than", left=FeatureNode("zscore", {"lookback": 20}, "zscore"), right=-0.25),
        )
        params = (
            {"name": "lookback", "type": "int", "value": 20},
            {"name": "entry_z", "type": "float", "value": -1.5},
            {"name": "exit_z", "type": "float", "value": -0.25},
        )
        controls = (ControlNode("cost_stress", {"multiplier": 1.5}),)
        portfolio_rule = PortfolioRule(weight_semantics="single_strategy_unit_notional", selection_semantics="equal_weight", max_gross_exposure=1.0, max_rules=1)
    return features, signal, params, controls, portfolio_rule


def _select_hypothesis(
    hypotheses: list[MechanisticHypothesis],
    scorecards: list[HypothesisScorecard],
    *,
    suppressed_fingerprint: str | None = None,
) -> tuple[MechanisticHypothesis | None, list[dict[str, Any]]]:
    ranked = sorted(
        zip(hypotheses, scorecards, strict=False),
        key=lambda item: (
            bool(item[1].hard_blockers),
            -item[1].overall_score,
            -item[1].expected_information_gain,
            -item[1].expected_decisiveness,
            item[1].estimated_compute_cost,
            item[0].hypothesis_id,
        ),
    )
    selected_index = 0
    if suppressed_fingerprint:
        for index, (hypothesis, _scorecard) in enumerate(ranked):
            if hypothesis.stable_fingerprint != suppressed_fingerprint:
                selected_index = index
                break
        else:
            selected_index = -1
    selected = ranked[selected_index][0] if ranked and selected_index >= 0 else None
    reasons = []
    for index, (hypothesis, scorecard) in enumerate(ranked):
        if selected is not None and index == selected_index:
            continue
        reason = "lower_rank"
        if suppressed_fingerprint and hypothesis.stable_fingerprint == suppressed_fingerprint:
            reason = "suppressed_by_recent_lesson"
        reasons.append({"hypothesis_id": hypothesis.hypothesis_id, "reason": reason, "overall_score": scorecard.overall_score})
    return selected, reasons


def _build_strategy_artifact(hypothesis: MechanisticHypothesis) -> tuple[dict[str, Any], Any, MechanismImplementationAlignment]:
    features, signal, params, controls, portfolio_rule = _build_hypothesis_specs(hypothesis)
    spec = build_strategy_spec(
        hypothesis_id=hypothesis.hypothesis_id,
        mechanism_family=hypothesis.mechanism_family,
        behavior_family=hypothesis.behavior_family,
        universe=hypothesis.universe_intent,
        timeframe=hypothesis.timeframe_intent,
        regime_scope=hypothesis.regime_scope,
        feature_nodes=features,
        signal=signal,
        parameters=params,
        controls=controls,
        portfolio_rule=portfolio_rule,
    )
    compiled = compile_strategy_spec(spec)
    alignment = compiled.get("alignment") if compiled.get("alignment") else build_alignment(spec)
    return compiled, spec, alignment


def _run_smoke_backtest(repo_root: Path, strategy_callable: Any, data_plan: CoverageDecision) -> dict[str, Any]:
    selected_row = dict(data_plan.selected_data.get("selected_row") or {})
    instrument = str(selected_row.get("instrument") or "unknown")
    timeframe = str(selected_row.get("timeframe") or "1d")
    frame = data_plan.selected_data.get("frame")
    if frame is None:
        data_path = selected_row.get("path") or data_plan.selected_data.get("data_path")
        if data_path:
            frame = pd.read_parquet(repo_root / str(data_path))
            if "timestamp_utc" in frame.columns:
                frame = frame.copy()
                frame["timestamp_utc"] = pd.to_datetime(frame["timestamp_utc"], utc=True)
                frame = frame.sort_values("timestamp_utc")
                frame = frame.set_index("timestamp_utc")
    if frame is None:
        raise ValueError("data plan missing frame for smoke evaluation")
    features = strategy_callable._feature_requirements  # type: ignore[attr-defined]
    from agent.backtesting.thin_strategy import build_features_for

    feature_map = build_features_for(features, frame)
    signal = strategy_callable(frame, feature_map).astype(int)
    close = frame["close"].astype(float)
    returns = close.pct_change().fillna(0.0)
    position = signal.shift(1).fillna(0).astype(int)
    gross = position.astype(float) * returns.astype(float)
    trade_count = int((position.diff().abs().fillna(position.abs()) > 0).sum())
    net_return = float((1.0 + gross).prod() - 1.0)
    return {
        "summary": {
            "totaal_trades": trade_count,
            "net_return_compound": net_return,
            "gross_return_compound": net_return,
            "goedgekeurd": False,
        },
        "signals": signal.tolist(),
        "execution_tier": EXECUTION_TIER_EXECUTOR_SMOKE,
        "fallback": "local_smoke_evaluation_only",
        "selected_instrument": instrument,
        "selected_timeframe": timeframe,
    }


def _canonical_preset_for_hypothesis(hypothesis: MechanisticHypothesis, instrument: str, timeframe: str):
    presets = importlib.import_module("research.presets")
    ResearchPreset = presets.ResearchPreset
    bundle_map = {
        "trend_persistence": ("trend_pullback_v1",),
        "volatility_breakout": ("volatility_compression_breakout",),
        "mean_reversion": ("zscore_mean_reversion",),
    }
    bundle = bundle_map.get(hypothesis.mechanism_family)
    if not bundle:
        raise ValueError(f"no canonical preset mapping for mechanism_family={hypothesis.mechanism_family}")
    return ResearchPreset(
        name=f"alpha_discovery__{hypothesis.hypothesis_id}",
        hypothesis="Alpha discovery empirical admission path via canonical run_research orchestrator.",
        universe=(instrument,),
        timeframe=timeframe,
        bundle=bundle,
        screening_mode="strict",
        screening_phase="exploratory",
        cost_mode="realistic",
        status="stable",
        enabled=True,
        diagnostic_only=False,
        excluded_from_daily_scheduler=True,
        excluded_from_candidate_promotion=False,
        hypothesis_id=hypothesis.hypothesis_id,
        preset_class="experimental",
        rationale="Evidence-grade alpha-discovery empirical execution through canonical orchestration only.",
        expected_behavior="Writes canonical screening and evidence artifacts through run_research.",
        falsification=("insufficient empirical evidence", "insufficient OOS validation"),
        enablement_criteria=("no paper/shadow/live authority", "research-only empirical execution",),
    )


def _run_empirical_campaign_via_canonical_orchestrator(
    repo_root: Path,
    *,
    hypothesis: MechanisticHypothesis,
    experiment,
    data_plan: CoverageDecision,
) -> dict[str, Any]:
    selected_row = dict(data_plan.selected_data.get("selected_row") or {})
    preset_override = _canonical_preset_for_hypothesis(
        hypothesis,
        instrument=str(selected_row.get("instrument") or "AAPL"),
        timeframe=str(selected_row.get("timeframe") or experiment.timeframe),
    )
    module = importlib.import_module("research.run_research")
    module.run_research(preset_override=preset_override)
    return {
        "summary": {"totaal_trades": 0, "net_return_compound": 0.0, "gross_return_compound": 0.0, "goedgekeurd": False},
        "execution_tier": data_plan.admissible_execution_tier,
        "canonical_orchestrator": "research.run_research.run_research",
        "preset_override": preset_override.name,
        "selected_instrument": str(selected_row.get("instrument") or ""),
        "selected_timeframe": str(selected_row.get("timeframe") or ""),
    }


def _assess_admission(
    *,
    selected: MechanisticHypothesis,
    experiment,
    strategy_spec,
    data_requirement,
    data_plan: CoverageDecision,
    coverage: CoverageAssessment,
    acquisition: AcquisitionPlan,
    alignment: MechanismImplementationAlignment,
    requested_execution_tier: str,
) -> ExperimentAdmissionDecision:
    selected_data = data_plan.selected_data
    source_quality = str(selected_data.get("effective_research_quality_status") or "blocked")
    identity = str(selected_data.get("source_identity_status") or "ambiguous")
    row_count = int(selected_data.get("row_count") or 0)
    activity = int(selected_data.get("estimated_activity") or 0)
    validation_rows = int(selected_data.get("validation_rows") or 0)
    locked_oos_rows = int(selected_data.get("locked_oos_rows") or 0)
    admitted_tier = data_plan.admissible_execution_tier
    reasons = list(data_plan.tier_downgrade_reasons) + list(acquisition.reason_codes)
    if alignment.alignment_status != "ALIGNED":
        reasons.append("mechanism_alignment_blocked")
    decision = f"ADMIT_{admitted_tier}"
    if coverage.decision == "SOURCE_QUALITY_BLOCKED" or source_quality != "ready":
        decision = "SOURCE_QUALITY_BLOCKED"
    elif coverage.decision == "IDENTITY_BLOCKED" or identity != "ready":
        decision = "IDENTITY_BLOCKED"
    elif coverage.decision == "PIT_BLOCKED" or alignment.alignment_status != "ALIGNED":
        decision = "POLICY_BLOCKED"
    elif admitted_tier == EXECUTION_TIER_EXECUTOR_SMOKE and requested_execution_tier != EXECUTION_TIER_EXECUTOR_SMOKE:
        decision = "ADMIT_EXECUTOR_SMOKE"
    elif admitted_tier == EXECUTION_TIER_COMPILER_ONLY:
        decision = "ADMIT_COMPILER_ONLY"
    empirical_created = decision in {"ADMIT_EMPIRICAL_SCREENING", "ADMIT_LOCKED_OOS_VALIDATION"}
    smoke_created = decision == "ADMIT_EXECUTOR_SMOKE"
    learning_allowed = empirical_created and admitted_tier in {EXECUTION_TIER_EMPIRICAL_SCREENING, EXECUTION_TIER_LOCKED_OOS_VALIDATION}
    return ExperimentAdmissionDecision(
        hypothesis_id=selected.hypothesis_id,
        experiment_id=experiment.experiment_id,
        strategy_spec_id=strategy_spec.strategy_spec_id,
        data_requirement_id=data_requirement.requirement_id,
        requested_tier=requested_execution_tier,
        admitted_tier=admitted_tier,
        source_quality=source_quality.upper(),
        identity_readiness="SUFFICIENT" if identity == "ready" else "INSUFFICIENT",
        history_sufficiency="SUFFICIENT" if row_count >= data_requirement.minimum_rows else "INSUFFICIENT",
        activity_sufficiency="SUFFICIENT" if activity >= data_requirement.minimum_expected_trades else "INSUFFICIENT",
        validation_sufficiency="SUFFICIENT" if validation_rows >= data_requirement.minimum_validation_rows else "INSUFFICIENT",
        OOS_sufficiency="SUFFICIENT" if locked_oos_rows >= data_requirement.minimum_locked_oos_rows and data_requirement.minimum_locked_oos_rows > 0 else "INSUFFICIENT",
        cost_model_sufficiency="SUFFICIENT" if experiment.transaction_cost_model != "" else "INSUFFICIENT",
        slippage_model_sufficiency="INSUFFICIENT" if "zero_slippage" in experiment.slippage_model else "SUFFICIENT",
        null_control_readiness="SUFFICIENT" if experiment.null_models else "INSUFFICIENT",
        stability_readiness="SUFFICIENT" if validation_rows > 0 else "INSUFFICIENT",
        fragility_readiness="SUFFICIENT" if activity > 1 else "INSUFFICIENT",
        outlier_readiness="SUFFICIENT" if validation_rows > 0 else "INSUFFICIENT",
        requested_tier_not_met=admitted_tier != requested_execution_tier,
        empirical_campaign_created=empirical_created,
        smoke_execution_created=smoke_created,
        mechanism_learning_allowed=learning_allowed,
        decision=decision,
        reason_codes=tuple(sorted(set(reasons))),
        content_identity=content_id(
            "qadm",
            {
                "hypothesis_id": selected.hypothesis_id,
                "requested_tier": requested_execution_tier,
                "admitted_tier": admitted_tier,
                "decision": decision,
            },
        ),
    )


def _historical_reassessments(repo_root: Path) -> dict[str, Any]:
    previous = _latest_payload(repo_root / REASSESSMENTS_PATH) or {}
    rows = list(previous.get("rows") or [])
    required = {
        "qcam_4c691604bc936a8e": {
            "artifact_id": "qcam_4c691604bc936a8e",
            "artifact_type": "campaign",
            "execution_validity": "valid_smoke_execution",
            "corrected_evidence_tier": EXECUTION_TIER_EXECUTOR_SMOKE,
            "empirical_authority": "none",
            "mechanism_prior_authority": "none",
            "historical_provenance_retained": True,
        },
        "qrl_48a61c8a441143f6": {
            "artifact_id": "qrl_48a61c8a441143f6",
            "artifact_type": "lesson",
            "corrected_lesson_type": LESSON_TYPE_PROCESS,
            "prior_adjustment_retained": False,
            "reason": "INSUFFICIENT_EMPIRICAL_EVIDENCE",
            "historical_provenance_retained": True,
        },
        "qcam_91538224108520b6": {
            "artifact_id": "qcam_91538224108520b6",
            "artifact_type": "campaign",
            "execution_validity": "valid_smoke_execution",
            "corrected_evidence_tier": EXECUTION_TIER_EXECUTOR_SMOKE,
            "empirical_authority": "none",
            "mechanism_prior_authority": "none",
            "historical_provenance_retained": True,
        },
    }
    existing_ids = {str(row.get("artifact_id") or "") for row in rows if isinstance(row, dict)}
    for artifact_id, row in required.items():
        if artifact_id not in existing_ids:
            rows.append(dict(row))
    return {
        "schema_version": SCHEMA_VERSION,
        "policy_version": POLICY_VERSION,
        "report_kind": "qre_alpha_discovery_reassessments",
        "rows": sorted(rows, key=lambda item: str(item.get("artifact_id") or "")),
        "content_identity": content_id("qras", rows),
    }


def read_status(repo_root: Path) -> dict[str, Any]:
    payload = _latest_payload(repo_root / STATUS_PATH)
    if payload is not None:
        return payload
    return {
        "schema_version": SCHEMA_VERSION,
        "policy_version": POLICY_VERSION,
        "report_kind": "qre_alpha_discovery_status",
        "state": "WAITING_FOR_TRIGGER",
        "current_wait_reason": "status_not_materialized",
        "content_identity": content_id("qasd_status", "status_not_materialized"),
    }


def run_alpha_discovery_mvp(
    *,
    repo_root: Path,
    dry_run: bool = False,
    max_hypotheses: int = 3,
    execution_tier: str = "auto",
) -> dict[str, Any]:
    requested_execution_tier = TIER_ALIAS.get(execution_tier, execution_tier)
    if requested_execution_tier not in EXECUTION_TIERS:
        raise ValueError(f"unsupported execution_tier={execution_tier!r}")
    context = DiscoveryContext(
        repo_root=repo_root,
        dry_run=dry_run,
        max_hypotheses=max_hypotheses,
        requested_execution_tier=requested_execution_tier,
    )
    observation = build_observation_snapshot(context)
    latest_lesson_payload = _latest_payload(repo_root / LESSONS_PATH) or {}
    memory = {
        "lesson": latest_lesson_payload.get("lesson", {}),
        "prior_run": (_latest_payload(repo_root / RUNS_PATH) or {}),
        "reassessments": (_latest_payload(repo_root / REASSESSMENTS_PATH) or {}).get("rows", []),
    }
    lesson_fingerprint = str(latest_lesson_payload.get("prior_fingerprint") or "")
    provider = DeterministicMechanisticHypothesisProvider()
    critic = DeterministicHypothesisCritic()
    rewriter = DeterministicHypothesisRewriter()
    evaluator = DeterministicExAnteEvaluator()
    planner = CanonicalExperimentPlanner()
    evidence_evaluator = CanonicalEvidenceEvaluator()
    compressor = StructuredLessonCompressor()

    hypotheses = provider.propose(observation, memory, budget=max_hypotheses)
    critiques: list[HypothesisCritique] = []
    rewrites: list[HypothesisRevision] = []
    final_hypotheses: list[MechanisticHypothesis] = []
    for hypothesis in hypotheses:
        critique = critic.critique(hypothesis, observation, memory)
        critiques.append(critique)
        revised = rewriter.revise(hypothesis, critique)
        if revised.hypothesis_id != hypothesis.hypothesis_id:
            rewrites.append(
                HypothesisRevision(
                    original_hypothesis_id=hypothesis.hypothesis_id,
                    critique_id=critique.critique_id,
                    revised_hypothesis_id=revised.hypothesis_id,
                    changes_applied=("regime_conditioning", "explicit_cost_falsification"),
                    changes_rejected=(),
                    content_identity=content_id("qahrv", {"original": hypothesis.hypothesis_id, "revised": revised.hypothesis_id}),
                )
            )
        final_hypotheses.append(revised)

    scorecards = [evaluator.evaluate(hypothesis, critique, observation) for hypothesis, critique in zip(final_hypotheses, critiques, strict=False)]
    selected, unselected = _select_hypothesis(final_hypotheses, scorecards, suppressed_fingerprint=lesson_fingerprint or None)
    experiment = planner.plan(selected, requested_execution_tier=requested_execution_tier) if selected is not None else None
    data_truth = materialize_data_truth(repo_root)
    universe_plan = plan_universe(repo_root=repo_root, experiment=experiment, catalog=data_truth["catalog"]) if experiment is not None else None
    data_requirement = build_data_requirement(experiment, universe_plan) if experiment is not None and universe_plan is not None else None
    data_plan = coverage = acquisition = None
    if data_requirement is not None and universe_plan is not None:
        data_plan, coverage, acquisition, data_truth, universe_plan = resolve_data_plan(
            repo_root,
            data_requirement,
            universe_plan=universe_plan,
        )
    compiled = None
    strategy_spec = None
    alignment = None
    admission = None
    campaign_evidence: CampaignEvidence | None = None
    assessment: EvidenceAssessment | None = None
    lesson: ResearchLesson | None = None
    terminal_disposition = "NO_NOVEL_HYPOTHESIS"
    campaign_id = None
    ingestion_telemetry = None
    throughput = None
    if selected is not None and experiment is not None and data_plan is not None and coverage is not None and acquisition is not None:
        compiled, strategy_spec, alignment = _build_strategy_artifact(selected)
        admission = _assess_admission(
            selected=selected,
            experiment=experiment,
            strategy_spec=strategy_spec,
            data_requirement=data_requirement,
            data_plan=data_plan,
            coverage=coverage,
            acquisition=acquisition,
            alignment=alignment,
            requested_execution_tier=requested_execution_tier,
        )
        ingestion_telemetry = execute_acquisition_once(repo_root=repo_root, plan=acquisition)
        throughput = throughput_snapshot(catalog=data_truth["catalog"], telemetry=ingestion_telemetry)
        if compiled["status"] != "VERIFIED":
            terminal_disposition = "POLICY_BLOCKED"
        elif dry_run:
            terminal_disposition = "DRY_RUN"
        elif admission.decision == "ADMIT_EXECUTOR_SMOKE" and requested_execution_tier == EXECUTION_TIER_EXECUTOR_SMOKE:
            result = _run_smoke_backtest(repo_root, compiled["callable"], data_plan)
            campaign_id = content_id("qcam", {"experiment_id": experiment.experiment_id, "hypothesis_id": selected.hypothesis_id, "tier": admission.admitted_tier})
            campaign_evidence = CampaignEvidence(
                campaign_id=campaign_id,
                experiment_id=experiment.experiment_id,
                strategy_spec_id=strategy_spec.strategy_spec_id,
                execution_tier=EXECUTION_TIER_EXECUTOR_SMOKE,
                empirical=False,
                backtest_result=result,
                data_plan=_public_data_plan(data_plan) or {},
                content_identity=content_id("qcev", {"campaign_id": campaign_id, "experiment_id": experiment.experiment_id}),
            )
            assessment = evidence_evaluator.evaluate(experiment, campaign_evidence, admission)
            lesson = compressor.compress(assessment, {"strategy_spec_id": strategy_spec.strategy_spec_id})
            terminal_disposition = "COMPLETED_SMOKE_ONLY"
        elif admission.decision in {"ADMIT_EMPIRICAL_SCREENING", "ADMIT_LOCKED_OOS_VALIDATION"}:
            result = _run_empirical_campaign_via_canonical_orchestrator(repo_root, hypothesis=selected, experiment=experiment, data_plan=data_plan)
            campaign_id = content_id("qcam", {"experiment_id": experiment.experiment_id, "hypothesis_id": selected.hypothesis_id, "tier": admission.admitted_tier})
            campaign_evidence = CampaignEvidence(
                campaign_id=campaign_id,
                experiment_id=experiment.experiment_id,
                strategy_spec_id=strategy_spec.strategy_spec_id,
                execution_tier=admission.admitted_tier,
                empirical=True,
                backtest_result=result,
                data_plan=_public_data_plan(data_plan) or {},
                content_identity=content_id("qcev", {"campaign_id": campaign_id, "experiment_id": experiment.experiment_id}),
            )
            assessment = evidence_evaluator.evaluate(experiment, campaign_evidence, admission)
            lesson = compressor.compress(assessment, {"strategy_spec_id": strategy_spec.strategy_spec_id})
            terminal_disposition = "COMPLETED_LOCKED_OOS_VALIDATION" if admission.admitted_tier == EXECUTION_TIER_LOCKED_OOS_VALIDATION else "COMPLETED_EMPIRICAL_SCREENING"
        elif admission.decision == "SOURCE_QUALITY_BLOCKED":
            terminal_disposition = "STOPPED_SOURCE_QUALITY_BOUNDARY"
        elif admission.decision == "IDENTITY_BLOCKED":
            terminal_disposition = "STOPPED_IDENTITY_BOUNDARY"
        elif acquisition.external_boundary == "STOPPED_PROVIDER_BOUNDARY":
            terminal_disposition = "STOPPED_PROVIDER_BOUNDARY"
        elif coverage.decision == "PIT_BLOCKED":
            terminal_disposition = "STOPPED_PIT_BOUNDARY"
        else:
            terminal_disposition = "STOPPED_EXTERNAL_DATA_BOUNDARY"

    budget_usage = RunBudgetUsage(
        observation_snapshots=1,
        raw_hypotheses=len(hypotheses),
        critiques=len(critiques),
        rewrites=len(rewrites),
        scorecards=len(scorecards),
        selected_hypotheses=1 if selected is not None else 0,
        compiled_experiments=1 if experiment is not None else 0,
        strategy_specs=1 if strategy_spec is not None else 0,
        data_refresh_retries=0,
        campaigns_executed=0 if dry_run else int(bool(campaign_evidence)),
        lessons_written=0 if lesson is None else 1,
    )
    reassessments = _historical_reassessments(repo_root)
    run_payload = {
        "schema_version": SCHEMA_VERSION,
        "policy_version": POLICY_VERSION,
        "report_kind": "qre_alpha_discovery_run",
        "run_id": content_id("qarr", {"observation": observation.content_identity, "selected": getattr(selected, "hypothesis_id", ""), "tier": requested_execution_tier}),
        "state_trace": [
            "OBSERVE",
            "GENERATE",
            "CRITIQUE",
            "REWRITE",
            "SCORE",
            "SELECT",
            "PLAN",
            "COMPILE",
            "RESOLVE_DATA",
            "EXECUTE" if campaign_evidence is not None else "STOP",
            "EVALUATE" if assessment is not None else "STOP",
            "REMEMBER" if lesson is not None else "STOP",
        ],
        "observation_snapshot_id": observation.observation_snapshot_id,
        "hypotheses_generated": len(hypotheses),
        "critiques_created": len(critiques),
        "hypotheses_rewritten": len(rewrites),
        "scorecards": _serialize(scorecards),
        "selected_hypothesis": selected.to_payload() if selected is not None else None,
        "experiment_id": experiment.experiment_id if experiment is not None else None,
        "strategy_spec_id": strategy_spec.strategy_spec_id if strategy_spec is not None else None,
        "verification_result": compiled["status"] if compiled is not None else None,
        "requested_execution_tier": requested_execution_tier,
        "admitted_execution_tier": admission.admitted_tier if admission is not None else None,
        "empirical_campaign_created": bool(admission and admission.empirical_campaign_created),
        "smoke_execution_created": bool(admission and admission.smoke_execution_created),
        "evidence_grade": assessment.evidence_grade if assessment is not None else None,
        "mechanism_learning_allowed": bool(admission and admission.mechanism_learning_allowed),
        "prior_adjustment_allowed": bool(assessment and assessment.prior_adjustment_allowed),
        "data_boundary": acquisition.external_boundary if acquisition is not None else None,
        "exact_blockers": list(admission.reason_codes) if admission is not None else [],
        "data_plan_status": data_plan.decision if data_plan is not None else None,
        "coverage_decision": coverage.decision if coverage is not None else None,
        "acquisition_decision": acquisition.source_selection_decision if acquisition is not None else None,
        "campaign_id": campaign_id,
        "terminal_disposition": terminal_disposition,
        "lesson_id": lesson.lesson_id if lesson is not None else None,
        "budget_usage": asdict(budget_usage),
        "next_action": "resolve_source_quality_boundary" if terminal_disposition == "STOPPED_SOURCE_QUALITY_BOUNDARY" else ("resolve_identity_boundary" if terminal_disposition == "STOPPED_IDENTITY_BOUNDARY" else ("resolve_pit_boundary" if terminal_disposition == "STOPPED_PIT_BOUNDARY" else ("resolve_external_data_boundary" if terminal_disposition == "STOPPED_EXTERNAL_DATA_BOUNDARY" else "repeat_mvp_on_next_novel_hypothesis"))),
        "artifact_refs": {},
        "selected_hypothesis_ids": [hyp.hypothesis_id for hyp in final_hypotheses],
        "unselected_hypothesis_reasons": unselected,
        "five_row_inventory_root_cause": data_truth["census"]["root_cause"] if isinstance(data_truth, dict) and "census" in data_truth else None,
        "throughput": throughput,
    }
    artifacts = {
        "observation": observation.to_payload(),
        "hypotheses": [hyp.to_payload() for hyp in final_hypotheses],
        "critiques": [asdict(crit) for crit in critiques],
        "rewrites": [asdict(rev) for rev in rewrites],
        "scorecards": _serialize(scorecards),
        "experiments": asdict(experiment) if experiment is not None else None,
        "strategies": strategy_spec.to_payload() if strategy_spec is not None else None,
        "requirements": asdict(data_requirement) if data_requirement is not None else None,
        "universe_plans": asdict(universe_plan) if universe_plan is not None else None,
        "acquisitions": asdict(acquisition) if acquisition is not None else None,
        "throughput": throughput,
        "alignments": asdict(alignment) if alignment is not None else None,
        "admissions": asdict(admission) if admission is not None else None,
        "data_plans": _public_data_plan(data_plan),
        "coverage": asdict(coverage) if coverage is not None else None,
        "evidence_assessments": asdict(assessment) if assessment is not None else None,
        "lessons": asdict(lesson) if lesson is not None else None,
        "reassessments": reassessments,
        "runs": run_payload,
        "status": {
            "schema_version": SCHEMA_VERSION,
            "policy_version": POLICY_VERSION,
            "report_kind": "qre_alpha_discovery_status",
            "state": "COMPLETE" if not dry_run else "DRY_RUN",
            "terminal_disposition": terminal_disposition,
            "requested_execution_tier": requested_execution_tier,
            "admitted_execution_tier": admission.admitted_tier if admission is not None else None,
            "empirical_campaign_created": bool(admission and admission.empirical_campaign_created),
            "smoke_execution_created": bool(admission and admission.smoke_execution_created),
            "mechanism_learning_allowed": bool(admission and admission.mechanism_learning_allowed),
            "selected_hypothesis_id": getattr(selected, "hypothesis_id", None),
            "current_wait_reason": "lesson_written" if lesson is not None else "no_campaign_executed",
            "next_wake_conditions": ["evidence_grade_data", "new_data", "new_memory"] if lesson is not None else ["novel_observation"],
            "content_identity": content_id("qasd_status", run_payload),
        },
    }
    if not dry_run and lesson is not None:
        lesson_payload = {
            "schema_version": SCHEMA_VERSION,
            "policy_version": POLICY_VERSION,
            "report_kind": "qre_alpha_discovery_lesson",
            "lesson": asdict(lesson),
            "prior_fingerprint": selected.stable_fingerprint if selected is not None else "",
            "selected_hypothesis_id": selected.hypothesis_id if selected is not None else "",
        }
        artifacts["lesson_payload"] = lesson_payload
    artifact_refs = {
        "observation": _write_artifact(OBSERVATIONS_PATH, artifacts["observation"], repo_root=repo_root),
        "hypotheses": _write_artifact(HYPOTHESES_PATH, {"schema_version": SCHEMA_VERSION, "rows": artifacts["hypotheses"]}, repo_root=repo_root),
        "critiques": _write_artifact(CRITIQUES_PATH, {"schema_version": SCHEMA_VERSION, "rows": artifacts["critiques"]}, repo_root=repo_root),
        "rewrites": _write_artifact(REWRITES_PATH, {"schema_version": SCHEMA_VERSION, "rows": artifacts["rewrites"]}, repo_root=repo_root),
        "scorecards": _write_artifact(SCORECARDS_PATH, {"schema_version": SCHEMA_VERSION, "rows": artifacts["scorecards"]}, repo_root=repo_root),
        "experiments": _write_artifact(EXPERIMENTS_PATH, {"schema_version": SCHEMA_VERSION, "rows": [artifacts["experiments"]] if artifacts["experiments"] else []}, repo_root=repo_root),
        "strategies": _write_artifact(STRATEGIES_PATH, {"schema_version": SCHEMA_VERSION, "rows": [artifacts["strategies"]] if artifacts["strategies"] else []}, repo_root=repo_root),
        "requirements": _write_artifact(REQUIREMENTS_PATH, {"schema_version": SCHEMA_VERSION, "rows": [artifacts["requirements"]] if artifacts["requirements"] else []}, repo_root=repo_root),
        "universe_plans": _write_artifact(UNIVERSE_PLANS_PATH, {"schema_version": SCHEMA_VERSION, "rows": [artifacts["universe_plans"]] if artifacts["universe_plans"] else []}, repo_root=repo_root),
        "acquisitions": _write_artifact(ACQUISITIONS_PATH, {"schema_version": SCHEMA_VERSION, "rows": [artifacts["acquisitions"]] if artifacts["acquisitions"] else []}, repo_root=repo_root),
        "throughput": _write_artifact(THROUGHPUT_PATH, {"schema_version": SCHEMA_VERSION, "rows": [artifacts["throughput"]] if artifacts["throughput"] else []}, repo_root=repo_root),
        "alignments": _write_artifact(ALIGNMENTS_PATH, {"schema_version": SCHEMA_VERSION, "rows": [artifacts["alignments"]] if artifacts["alignments"] else []}, repo_root=repo_root),
        "admissions": _write_artifact(ADMISSIONS_PATH, {"schema_version": SCHEMA_VERSION, "rows": [artifacts["admissions"]] if artifacts["admissions"] else []}, repo_root=repo_root),
        "data_plans": _write_artifact(DATA_PLANS_PATH, {"schema_version": SCHEMA_VERSION, "rows": [artifacts["data_plans"]] if artifacts["data_plans"] else []}, repo_root=repo_root),
        "coverage": _write_artifact(DATA_PLANS_PATH.with_name("coverage_latest.json"), {"schema_version": SCHEMA_VERSION, "rows": [artifacts["coverage"]] if artifacts["coverage"] else []}, repo_root=repo_root),
        "evidence_assessments": _write_artifact(EVIDENCE_ASSESSMENTS_PATH, {"schema_version": SCHEMA_VERSION, "rows": [artifacts["evidence_assessments"]] if artifacts["evidence_assessments"] else []}, repo_root=repo_root),
        "reassessments": _write_artifact(REASSESSMENTS_PATH, reassessments, repo_root=repo_root),
        "runs": _write_artifact(RUNS_PATH, artifacts["runs"], repo_root=repo_root),
        "status": _write_artifact(STATUS_PATH, artifacts["status"], repo_root=repo_root),
    }
    if "lesson_payload" in artifacts:
        artifact_refs["lessons"] = _write_artifact(LESSONS_PATH, artifacts["lesson_payload"], repo_root=repo_root)
    run_payload["artifact_refs"] = artifact_refs
    identity_input = {key: value for key, value in run_payload.items() if key != "content_identity"}
    run_payload["content_identity"] = content_id("qarrc", identity_input)
    artifacts["status"]["content_identity"] = content_id("qasd_status", identity_input)
    artifact_refs["runs"] = _write_artifact(RUNS_PATH, run_payload, repo_root=repo_root)
    artifact_refs["status"] = _write_artifact(STATUS_PATH, artifacts["status"], repo_root=repo_root)
    return {**run_payload, "artifact_refs": artifact_refs, "artifacts": artifacts}
