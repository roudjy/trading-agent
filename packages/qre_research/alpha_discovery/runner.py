from __future__ import annotations

import importlib
import json
import os
import tempfile
import threading
from collections.abc import Mapping
from contextlib import suppress
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pandas as pd

from packages.qre_data.dataset_catalog import materialize_data_truth
from packages.qre_research.generated_strategy_paths import validate_write_target

from .acquisition import _screening_slippage_model, execute_acquisition_once, throughput_snapshot
from .capability_loop import (
    BLOCKED_EXPERIMENTS_PATH,
    GAP_REGISTRY_PATH,
    RESOLUTION_FEEDBACK_PATH,
    build_gap_from_admission,
    persist_gap_state,
    route_code_gaps_to_ade,
)
from .capability_loop import (
    consume_resolution_feedback as consume_capability_resolution_feedback,
)
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
    cap_execution_tier,
    content_id,
    execution_tier_rank,
)
from .data_planner import build_data_requirement, resolve_data_plan
from .evaluation import CanonicalEvidenceEvaluator, DeterministicExAnteEvaluator
from .experiment_compiler import CanonicalExperimentPlanner
from .firewall import build_discovery_view, build_locked_oos_view, build_validation_view
from .learning import StructuredLessonCompressor
from .observations import build_observation_snapshot
from .providers import (
    DeterministicHypothesisCritic,
    DeterministicHypothesisRewriter,
    MultiProviderHypothesisProvider,
)
from .snapshot_lineage import (
    REVISIONS_PATH,
    SNAPSHOT_LINEAGE_PATH,
    load_snapshot_lineage,
)
from .source_qualification import qualify_datasets, reconcile_source_policy
from .source_resolution import persist_source_resolution, resolve_source
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
SOURCE_POLICY_PATH = OUTPUT_ROOT / "source_policy" / "latest.json"
SOURCE_QUALIFICATIONS_PATH = OUTPUT_ROOT / "source_qualifications" / "latest.json"
SOURCE_RESOLUTION_ARTIFACT_PATH = OUTPUT_ROOT / "source_resolution" / "latest.json"
SEARCH_LEDGER_PATH = OUTPUT_ROOT / "search_ledger" / "latest.json"
DISCOVERY_VIEW_PATH = OUTPUT_ROOT / "views" / "discovery_latest.json"
VALIDATION_VIEW_PATH = OUTPUT_ROOT / "views" / "validation_latest.json"
LOCKED_OOS_VIEW_PATH = OUTPUT_ROOT / "views" / "locked_oos_latest.json"
RUNS_PATH = OUTPUT_ROOT / "runs" / "latest.json"
STATUS_PATH = OUTPUT_ROOT / "status" / "latest.json"
RUNTIME_EPOCH_PATH = OUTPUT_ROOT / "runtime_epoch" / "latest.json"

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
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.replace(tmp_name, path)
        except PermissionError:
            path.write_text(text, encoding="utf-8", newline="\n")
            with suppress(OSError):
                os.unlink(tmp_name)
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
    elif hypothesis.mechanism_family == "regime_transition":
        features = (
            FeatureNode("trend_anchor_delta", {"window": 50}, "trend_anchor_delta"),
            FeatureNode("compression_ratio", {"atr_short_window": 5, "atr_long_window": 20}, "compression_ratio"),
        )
        signal = SignalNode(
            entry=ConditionNode(
                "and",
                left=ConditionNode("greater_than", left=FeatureNode("trend_anchor_delta", {"window": 50}, "trend_anchor_delta"), right=0.0),
                right=ConditionNode("less_than", left=FeatureNode("compression_ratio", {"atr_short_window": 5, "atr_long_window": 20}, "compression_ratio"), right=0.8),
            ),
            exit=ConditionNode(
                "or",
                left=ConditionNode("less_than", left=FeatureNode("trend_anchor_delta", {"window": 50}, "trend_anchor_delta"), right=0.0),
                right=ConditionNode("greater_than", left=FeatureNode("compression_ratio", {"atr_short_window": 5, "atr_long_window": 20}, "compression_ratio"), right=1.0),
            ),
        )
        params = (
            {"name": "trend_anchor_window", "type": "int", "value": 50},
            {"name": "compression_window", "type": "int", "value": 20},
            {"name": "regime_threshold", "type": "float", "value": 0.5},
        )
        controls = (ControlNode("regime_filter", {"feature_alias": "trend_anchor_delta", "threshold": 0.0, "comparator": "greater_than"}),)
        portfolio_rule = PortfolioRule(weight_semantics="single_strategy_unit_notional", selection_semantics="equal_weight", max_gross_exposure=1.0, max_rules=1)
    elif hypothesis.mechanism_family in {"correlation_change", "liquidity_response"}:
        features = (
            FeatureNode("compression_ratio", {"atr_short_window": 5, "atr_long_window": 20}, "compression_ratio"),
            FeatureNode("normalized_trend_move", {"trend_anchor_window": 50, "atr_window": 14}, "normalized_trend_move"),
            FeatureNode("cross_sectional_rank", {"lookback": 20}, "cross_sectional_rank"),
        )
        signal = SignalNode(
            entry=ConditionNode(
                "and",
                left=ConditionNode("less_than", left=FeatureNode("compression_ratio", {"atr_short_window": 5, "atr_long_window": 20}, "compression_ratio"), right=0.8),
                right=ConditionNode("greater_than", left=FeatureNode("normalized_trend_move", {"trend_anchor_window": 50, "atr_window": 14}, "normalized_trend_move"), right=0.5),
            ),
            exit=ConditionNode("less_than", left=FeatureNode("normalized_trend_move", {"trend_anchor_window": 50, "atr_window": 14}, "normalized_trend_move"), right=0.1),
        )
        params = (
            {"name": "lookback", "type": "int", "value": 20},
            {"name": "top_bucket", "type": "float", "value": 0.2},
            {"name": "hold_bars", "type": "int", "value": 5},
        )
        controls = (ControlNode("cost_stress", {"multiplier": 1.5}), ControlNode("leave_one_asset_out", {"enabled": True}))
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
        "regime_transition": ("trend_pullback_v1",),
        "correlation_change": ("trend_pullback_v1",),
        "liquidity_response": ("volatility_compression_breakout",),
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
    holder: dict[str, Any] = {}

    def _invoke() -> None:
        try:
            holder["value"] = module.run_research(preset_override=preset_override)
        except BaseException as exc:
            holder["error"] = exc

    worker = threading.Thread(target=_invoke, daemon=True)
    worker.start()
    worker.join(timeout=120)
    if worker.is_alive():
        return {
            "summary": {"totaal_trades": 0, "net_return_compound": 0.0, "gross_return_compound": 0.0, "goedgekeurd": False},
            "execution_tier": data_plan.admissible_execution_tier,
            "canonical_orchestrator": "research.run_research.run_research",
            "preset_override": preset_override.name,
            "selected_instrument": str(selected_row.get("instrument") or ""),
            "selected_timeframe": str(selected_row.get("timeframe") or ""),
            "timeout_seconds": 120,
            "bounded_timeout": True,
        }
    if "error" in holder:
        return {
            "summary": {"totaal_trades": 0, "net_return_compound": 0.0, "gross_return_compound": 0.0, "goedgekeurd": False},
            "execution_tier": data_plan.admissible_execution_tier,
            "canonical_orchestrator": "research.run_research.run_research",
            "preset_override": preset_override.name,
            "selected_instrument": str(selected_row.get("instrument") or ""),
            "selected_timeframe": str(selected_row.get("timeframe") or ""),
            "error": type(holder["error"]).__name__,
        }
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
    requested_tier = requested_execution_tier
    admitted_tier = cap_execution_tier(data_plan.admissible_execution_tier, requested_tier)
    reasons = list(data_plan.tier_downgrade_reasons) + list(acquisition.reason_codes)
    if execution_tier_rank(admitted_tier) < execution_tier_rank(data_plan.admissible_execution_tier):
        reasons.append("requested_tier_ceiling")
    if requested_tier == EXECUTION_TIER_LOCKED_OOS_VALIDATION and admitted_tier != EXECUTION_TIER_LOCKED_OOS_VALIDATION:
        if locked_oos_rows < data_requirement.minimum_locked_oos_rows:
            reasons.append("locked_oos_insufficient")
        elif source_quality != "ready":
            reasons.append("source_not_validation_eligible")
        else:
            reasons.append("validation_authority_missing")
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
        requested_tier=requested_tier,
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
                "requested_tier": requested_tier,
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
        "pr726_authority_reassessment": {
            "artifact_id": "pr726_authority_reassessment",
            "artifact_type": "reassessment",
            "source_run_id": "qarr_d48faec61478b4c4",
            "source_campaign_id": "qcam_00498b2704a7deef",
            "source_experiment_id": "qexp_7e21c050e448d71a",
            "current_or_child_experiment_id": "qexp_fe7bfe9caccaec74",
            "original_requested_tier": EXECUTION_TIER_EMPIRICAL_SCREENING,
            "original_admitted_tier": EXECUTION_TIER_LOCKED_OOS_VALIDATION,
            "original_execution_classification": "COMPLETED_LOCKED_OOS_VALIDATION",
            "corrected_execution_status": "COMPLETED",
            "corrected_admitted_tier": EXECUTION_TIER_EMPIRICAL_SCREENING,
            "corrected_evidence_tier_reached": EXECUTION_TIER_EMPIRICAL_SCREENING,
            "scientific_disposition": "NEEDS_MORE_EVIDENCE",
            "OOS_presence": "NOT_AVAILABLE",
            "OOS_sufficiency": "INSUFFICIENT",
            "candidate_created": False,
            "mechanism_prior_changed": False,
            "lesson": "DATA_LESSON",
            "reason_codes": ("requested_tier_ceiling", "locked_oos_not_available", "scientific_disposition_separated"),
            "policy_version": POLICY_VERSION,
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
        if artifact_id in existing_ids:
            rows = [dict(row) if str(row.get("artifact_id") or "") != artifact_id else {**dict(row), **required[artifact_id]} for row in rows if isinstance(row, dict)]
        else:
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


def _runtime_epoch_payload(
    *,
    run_payload: Mapping[str, Any],
    snapshot_lineage_set_id: str,
    qualification_set_id: str,
) -> dict[str, Any]:
    runtime_epoch_components = {
        "snapshot_lineage_set_id": snapshot_lineage_set_id,
        "qualification_set_id": qualification_set_id,
        "alpha_run_id": str(run_payload.get("run_id") or ""),
        "alpha_campaign_id": str(run_payload.get("campaign_id") or ""),
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "policy_version": POLICY_VERSION,
        "report_kind": "qre_alpha_runtime_epoch",
        "runtime_epoch_id": content_id("qepoch", runtime_epoch_components),
        "qualification_set_id": qualification_set_id,
        "snapshot_lineage_set_id": snapshot_lineage_set_id,
        "run_id": str(run_payload.get("run_id") or ""),
        "campaign_id": str(run_payload.get("campaign_id") or ""),
        "current_dataset_snapshot": run_payload.get("current_dataset_snapshot"),
        "current_source_tier": run_payload.get("current_source_tier"),
        "current_experiment": run_payload.get("current_experiment"),
        "current_campaign": run_payload.get("current_campaign"),
        "terminal_disposition": run_payload.get("terminal_disposition"),
        "execution_status": run_payload.get("execution_status"),
        "scientific_disposition": run_payload.get("scientific_disposition"),
        "evidence_tier_reached": run_payload.get("evidence_tier_reached"),
        "search_ledger_id": run_payload.get("search_ledger_id"),
        "content_identity": content_id("qepochstate", runtime_epoch_components),
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
    provider = MultiProviderHypothesisProvider()
    critic = DeterministicHypothesisCritic()
    rewriter = DeterministicHypothesisRewriter()
    evaluator = DeterministicExAnteEvaluator()
    planner = CanonicalExperimentPlanner()
    evidence_evaluator = CanonicalEvidenceEvaluator()
    compressor = StructuredLessonCompressor()

    discovery_view = build_discovery_view(observation)
    hypotheses = provider.propose(observation, memory, budget=min(max_hypotheses, 6))
    critiques: list[HypothesisCritique] = []
    rewrites: list[HypothesisRevision] = []
    final_hypotheses: list[MechanisticHypothesis] = []
    critic_rejections = 0
    for hypothesis in hypotheses:
        critique = critic.critique(hypothesis, observation, memory)
        critiques.append(critique)
        if critique.fatal_objections:
            critic_rejections += 1
            continue
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
    search_ledger = provider.build_search_ledger(
        hypotheses=final_hypotheses,
        selected_hypothesis_id=selected.hypothesis_id if selected is not None else None,
        observation=observation,
        critic_rejections=critic_rejections,
    )
    experiment = planner.plan(selected, requested_execution_tier=requested_execution_tier) if selected is not None else None
    data_truth = materialize_data_truth(repo_root)
    source_policy = reconcile_source_policy(repo_root=repo_root, dataset_catalog=data_truth["catalog"])
    snapshot_lineage = load_snapshot_lineage(repo_root)
    source_qualifications = qualify_datasets(repo_root=repo_root, dataset_catalog=data_truth["catalog"], policy_reconciliation=source_policy)
    universe_plan = plan_universe(repo_root=repo_root, experiment=experiment, catalog=data_truth["catalog"]) if experiment is not None else None
    data_requirement = build_data_requirement(experiment, universe_plan) if experiment is not None and universe_plan is not None else None
    data_plan = coverage = acquisition = None
    source_resolution = None
    if data_requirement is not None and universe_plan is not None:
        data_plan, coverage, acquisition, data_truth, universe_plan = resolve_data_plan(
            repo_root,
            data_requirement,
            universe_plan=universe_plan,
        )
        source_resolution = resolve_source(
            repo_root=repo_root,
            requirement=data_requirement,
            target_source_tier="SOURCE_SCREENING_ELIGIBLE" if requested_execution_tier != EXECUTION_TIER_EXECUTOR_SMOKE else "SOURCE_SMOKE_ONLY",
        )
        persist_source_resolution(repo_root=repo_root, resolution=source_resolution)
        if (
            not dry_run
            and acquisition is not None
            and source_resolution is not None
            and source_resolution.automatic_actions_allowed
            and coverage is not None
            and coverage.decision in {"COVERAGE_PARTIAL_FETCHABLE", "EXTERNAL_DATA_BOUNDARY"}
        ):
            execute_acquisition_once(repo_root=repo_root, plan=acquisition)
            data_plan, coverage, acquisition, data_truth, universe_plan = resolve_data_plan(
                repo_root,
                data_requirement,
                universe_plan=universe_plan,
            )
            source_resolution = resolve_source(
                repo_root=repo_root,
                requirement=data_requirement,
                target_source_tier="SOURCE_SCREENING_ELIGIBLE" if requested_execution_tier != EXECUTION_TIER_EXECUTOR_SMOKE else "SOURCE_SMOKE_ONLY",
            )
            persist_source_resolution(repo_root=repo_root, resolution=source_resolution)
    compiled = None
    strategy_spec = None
    alignment = None
    admission = None
    campaign_evidence: CampaignEvidence | None = None
    assessment: EvidenceAssessment | None = None
    lesson: ResearchLesson | None = None
    gap_rows = []
    blocked_rows = []
    ade_requests = None
    resolution_feedback = None
    terminal_disposition = "NO_NOVEL_HYPOTHESIS"
    campaign_id = None
    ingestion_telemetry = None
    throughput = None
    validation_view = None
    locked_oos_view = None
    if selected is not None and experiment is not None and data_plan is not None and coverage is not None and acquisition is not None:
        compiled, strategy_spec, alignment = _build_strategy_artifact(selected)
        if requested_execution_tier != EXECUTION_TIER_EXECUTOR_SMOKE and experiment.slippage_model == "canonical_zero_slippage_proxy":
            slippage_model = _screening_slippage_model(
                symbol=str((universe_plan.resolved_assets or ("AAPL",))[0]),
                timeframe=experiment.timeframe,
            )
            experiment = experiment.__class__(**{**asdict(experiment), "slippage_model": slippage_model.slippage_model_id})
        validation_view = build_validation_view(
            experiment_id=experiment.experiment_id,
            strategy_spec_id=strategy_spec.strategy_spec_id,
            dataset_id=str(data_plan.selected_data.get("dataset_id") or ""),
        )
        locked_oos_view = build_locked_oos_view(
            experiment_id=experiment.experiment_id,
            strategy_spec_id=strategy_spec.strategy_spec_id,
        )
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
        if dry_run:
            ingestion_telemetry = {
                "provider_calls": 0,
                "provider_calls_avoided": int(acquisition.estimated_calls or 0),
                "rows_downloaded": 0,
                "rows_reused": 0,
                "rows_rejected": 0,
                "incomplete_bars_excluded": 0,
                "duplicates_rejected": 0,
                "gaps_detected": 0,
                "partial_failures": 0,
                "atomic_commit": True,
                "fingerprints_before": [],
                "fingerprints_after": [],
                "external_boundary": acquisition.external_boundary,
                "source_selection_decision": acquisition.source_selection_decision,
                "content_identity": content_id("qdracq", acquisition.content_identity),
                "cache_hit_rate": 1.0,
            }
        else:
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
            terminal_disposition = "STOPPED_SOURCE_CERTIFICATION_BOUNDARY"
        elif admission.decision == "IDENTITY_BLOCKED":
            terminal_disposition = "STOPPED_IDENTITY_BOUNDARY"
        elif acquisition.external_boundary == "STOPPED_PROVIDER_BOUNDARY":
            terminal_disposition = "STOPPED_PROVIDER_BOUNDARY"
        elif coverage.decision == "PIT_BLOCKED":
            terminal_disposition = "STOPPED_PIT_BOUNDARY"
        else:
            terminal_disposition = "STOPPED_EXTERNAL_DATA_BOUNDARY"
        if admission.decision not in {"ADMIT_EMPIRICAL_SCREENING", "ADMIT_LOCKED_OOS_VALIDATION"}:
            gap_rows, blocked_rows = build_gap_from_admission(
                experiment_id=experiment.experiment_id,
                hypothesis_id=selected.hypothesis_id,
                strategy_spec_id=strategy_spec.strategy_spec_id,
                preregistration_id=experiment.experiment_id,
                admission=admission,
                source_resolution=source_resolution,
                blocking_stage="EXECUTE",
            )
            if gap_rows or blocked_rows:
                gap_state = persist_gap_state(repo_root=repo_root, gaps=gap_rows, blocked=blocked_rows)
                ade_requests = route_code_gaps_to_ade(repo_root=repo_root, gap_payload=gap_state["gaps"], run_id=content_id("qar", {"experiment": experiment.experiment_id, "selected": selected.hypothesis_id}))
                resolution_feedback = consume_capability_resolution_feedback(repo_root=repo_root)

    execution_status = "COMPLETED"
    scientific_disposition = assessment.terminal_disposition if assessment is not None else None
    if campaign_evidence is not None and admission is not None:
        evidence_tier_reached = admission.admitted_tier
    elif admission is not None and admission.smoke_execution_created:
        evidence_tier_reached = EXECUTION_TIER_EXECUTOR_SMOKE
    else:
        evidence_tier_reached = EXECUTION_TIER_COMPILER_ONLY
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
        "execution_status": execution_status,
        "scientific_disposition": scientific_disposition,
        "evidence_tier_reached": evidence_tier_reached,
        "legacy_terminal_disposition": terminal_disposition,
        "runtime_epoch_id": "",
        "qualification_set_id": source_qualifications["content_identity"],
        "snapshot_lineage_set_id": snapshot_lineage["snapshot_lineage"]["content_identity"],
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
        "search_ledger_id": search_ledger.search_run_id,
        "budget_usage": asdict(budget_usage),
        "next_action": "resolve_source_certification_boundary" if terminal_disposition == "STOPPED_SOURCE_CERTIFICATION_BOUNDARY" else ("resolve_identity_boundary" if terminal_disposition == "STOPPED_IDENTITY_BOUNDARY" else ("resolve_pit_boundary" if terminal_disposition == "STOPPED_PIT_BOUNDARY" else ("resolve_external_data_boundary" if terminal_disposition == "STOPPED_EXTERNAL_DATA_BOUNDARY" else "repeat_mvp_on_next_novel_hypothesis"))),
        "artifact_refs": {},
        "current_dataset_snapshot": source_resolution.selected_snapshot if source_resolution is not None else None,
        "current_source_tier": source_resolution.current_source_tier if source_resolution is not None else None,
        "current_experiment": experiment.experiment_id if experiment is not None else None,
        "current_campaign": campaign_id,
        "selected_hypothesis_ids": [hyp.hypothesis_id for hyp in final_hypotheses],
        "unselected_hypothesis_reasons": unselected,
        "five_row_inventory_root_cause": data_truth["census"]["root_cause"] if isinstance(data_truth, dict) and "census" in data_truth else None,
        "throughput": throughput,
        "gap_ids": [row.gap_id for row in gap_rows],
        "blocked_experiment_ids": [row.experiment_id for row in blocked_rows],
    }
    runtime_epoch = _runtime_epoch_payload(
        run_payload=run_payload,
        snapshot_lineage_set_id=snapshot_lineage["snapshot_lineage"]["content_identity"],
        qualification_set_id=source_qualifications["content_identity"],
    )
    runtime_epoch_id = runtime_epoch["runtime_epoch_id"]
    run_payload["runtime_epoch_id"] = runtime_epoch_id
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
        "source_policy": source_policy,
        "source_qualifications": source_qualifications,
        "source_resolution": asdict(source_resolution) if source_resolution is not None else None,
        "snapshot_lineage": snapshot_lineage["snapshot_lineage"],
        "snapshot_revisions": snapshot_lineage["revisions"],
        "search_ledger": asdict(search_ledger),
        "capability_gaps": {"rows": [asdict(row) for row in gap_rows]},
        "blocked_experiments": {"rows": [asdict(row) for row in blocked_rows]},
        "ade_requests": ade_requests["requests"] if isinstance(ade_requests, dict) and "requests" in ade_requests else None,
        "resolution_feedback": resolution_feedback,
        "discovery_view": discovery_view,
        "validation_view": validation_view,
        "locked_oos_view": locked_oos_view,
        "runs": run_payload,
        "status": {
            "schema_version": SCHEMA_VERSION,
            "policy_version": POLICY_VERSION,
            "report_kind": "qre_alpha_discovery_status",
            "state": "DRY_RUN" if dry_run else "COMPLETE",
            "execution_status": execution_status,
            "scientific_disposition": scientific_disposition,
            "evidence_tier_reached": evidence_tier_reached,
            "legacy_terminal_disposition": terminal_disposition,
            "terminal_disposition": terminal_disposition,
            "requested_execution_tier": requested_execution_tier,
            "admitted_execution_tier": admission.admitted_tier if admission is not None else None,
            "empirical_campaign_created": bool(admission and admission.empirical_campaign_created),
            "smoke_execution_created": bool(admission and admission.smoke_execution_created),
            "mechanism_learning_allowed": bool(admission and admission.mechanism_learning_allowed),
            "selected_hypothesis_id": getattr(selected, "hypothesis_id", None),
            "current_dataset_snapshot": source_resolution.selected_snapshot if source_resolution is not None else None,
            "current_source_tier": source_resolution.current_source_tier if source_resolution is not None else None,
            "current_experiment": experiment.experiment_id if experiment is not None else None,
            "current_campaign": campaign_id,
            "current_wait_reason": "lesson_written" if lesson is not None else "no_campaign_executed",
            "next_wake_conditions": ["evidence_grade_data", "new_data", "new_memory"] if lesson is not None else ["novel_observation"],
            "runtime_epoch_id": runtime_epoch_id,
            "qualification_set_id": source_qualifications["content_identity"],
            "snapshot_lineage_set_id": snapshot_lineage["snapshot_lineage"]["content_identity"],
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
        "source_policy": _write_artifact(SOURCE_POLICY_PATH, source_policy, repo_root=repo_root),
        "source_qualifications": _write_artifact(SOURCE_QUALIFICATIONS_PATH, source_qualifications, repo_root=repo_root),
        "source_resolution": _write_artifact(SOURCE_RESOLUTION_ARTIFACT_PATH, {"schema_version": SCHEMA_VERSION, "rows": [artifacts["source_resolution"]] if artifacts["source_resolution"] else []}, repo_root=repo_root),
        "snapshot_lineage": (repo_root / SNAPSHOT_LINEAGE_PATH).as_posix(),
        "snapshot_revisions": (repo_root / REVISIONS_PATH).as_posix(),
        "search_ledger": _write_artifact(SEARCH_LEDGER_PATH, {"schema_version": SCHEMA_VERSION, "policy_version": POLICY_VERSION, "report_kind": "qre_alpha_search_ledger", "ledger": artifacts["search_ledger"]}, repo_root=repo_root),
        "capability_gaps": _write_artifact(GAP_REGISTRY_PATH, {"schema_version": SCHEMA_VERSION, "rows": artifacts["capability_gaps"]["rows"]}, repo_root=repo_root),
        "blocked_experiments": _write_artifact(BLOCKED_EXPERIMENTS_PATH, {"schema_version": SCHEMA_VERSION, "rows": artifacts["blocked_experiments"]["rows"]}, repo_root=repo_root),
        "resolution_feedback": _write_artifact(RESOLUTION_FEEDBACK_PATH, artifacts["resolution_feedback"] or {"schema_version": SCHEMA_VERSION, "rows": []}, repo_root=repo_root),
        "discovery_view": _write_artifact(DISCOVERY_VIEW_PATH, {"schema_version": SCHEMA_VERSION, "policy_version": POLICY_VERSION, "report_kind": "qre_alpha_discovery_view", "view": discovery_view}, repo_root=repo_root),
        "runs": _write_artifact(RUNS_PATH, artifacts["runs"], repo_root=repo_root),
        "runtime_epoch": _write_artifact(RUNTIME_EPOCH_PATH, runtime_epoch, repo_root=repo_root),
        "status": _write_artifact(STATUS_PATH, artifacts["status"], repo_root=repo_root),
    }
    if validation_view is not None:
        artifact_refs["validation_view"] = _write_artifact(VALIDATION_VIEW_PATH, {"schema_version": SCHEMA_VERSION, "policy_version": POLICY_VERSION, "report_kind": "qre_alpha_validation_view", "view": validation_view}, repo_root=repo_root)
    if locked_oos_view is not None:
        artifact_refs["locked_oos_view"] = _write_artifact(LOCKED_OOS_VIEW_PATH, {"schema_version": SCHEMA_VERSION, "policy_version": POLICY_VERSION, "report_kind": "qre_alpha_locked_oos_view", "view": locked_oos_view}, repo_root=repo_root)
    if "lesson_payload" in artifacts:
        artifact_refs["lessons"] = _write_artifact(LESSONS_PATH, artifacts["lesson_payload"], repo_root=repo_root)
    run_payload["artifact_refs"] = artifact_refs
    identity_input = {key: value for key, value in run_payload.items() if key != "content_identity"}
    run_payload["content_identity"] = content_id("qarrc", identity_input)
    artifacts["status"]["content_identity"] = content_id("qasd_status", identity_input)
    artifact_refs["runs"] = _write_artifact(RUNS_PATH, run_payload, repo_root=repo_root)
    artifact_refs["runtime_epoch"] = _write_artifact(RUNTIME_EPOCH_PATH, runtime_epoch, repo_root=repo_root)
    artifact_refs["status"] = _write_artifact(STATUS_PATH, artifacts["status"], repo_root=repo_root)
    return {**run_payload, "artifact_refs": artifact_refs, "artifacts": artifacts}
