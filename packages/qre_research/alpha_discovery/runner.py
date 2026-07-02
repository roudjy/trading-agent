from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Mapping
from contextlib import suppress
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pandas as pd

from packages.qre_research.generated_strategy_paths import validate_write_target

from .contracts import (
    CampaignEvidence,
    CoverageDecision,
    DiscoveryContext,
    ExperimentContract,
    EvidenceAssessment,
    HypothesisCritique,
    HypothesisRevision,
    HypothesisScorecard,
    MechanisticHypothesis,
    ObservationSnapshot,
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
    DeterministicMechanisticHypothesisProvider,
    DeterministicHypothesisRewriter,
)
from .strategy_compiler import build_strategy_spec, compile_strategy_spec
from .strategy_ir import ConditionNode, FeatureNode, SignalNode

OUTPUT_ROOT = Path("generated_research/alpha_discovery")
OBSERVATIONS_PATH = OUTPUT_ROOT / "observations" / "latest.json"
HYPOTHESES_PATH = OUTPUT_ROOT / "hypotheses" / "latest.json"
CRITIQUES_PATH = OUTPUT_ROOT / "critiques" / "latest.json"
REWRITES_PATH = OUTPUT_ROOT / "rewrites" / "latest.json"
SCORECARDS_PATH = OUTPUT_ROOT / "scorecards" / "latest.json"
EXPERIMENTS_PATH = OUTPUT_ROOT / "experiments" / "latest.json"
STRATEGIES_PATH = OUTPUT_ROOT / "strategies" / "latest.json"
DATA_PLANS_PATH = OUTPUT_ROOT / "data_plans" / "latest.json"
EVIDENCE_ASSESSMENTS_PATH = OUTPUT_ROOT / "evidence_assessments" / "latest.json"
LESSONS_PATH = OUTPUT_ROOT / "lessons" / "latest.json"
RUNS_PATH = OUTPUT_ROOT / "runs" / "latest.json"
STATUS_PATH = OUTPUT_ROOT / "status" / "latest.json"


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


def _public_data_plan(data_plan: CoverageDecision | None) -> dict[str, Any] | None:
    if data_plan is None:
        return None
    return {
        key: value
        for key, value in data_plan.selected_data.items()
        if key != "frame"
    }


def _build_hypothesis_specs(hypothesis: MechanisticHypothesis) -> tuple[FeatureNode, SignalNode, tuple[dict[str, Any], ...]]:
    if hypothesis.mechanism_family == "trend_persistence":
        features = (
            FeatureNode("trend_anchor_delta", {"window": 50}, "trend_anchor_delta"),
            FeatureNode("normalized_trend_move", {"trend_anchor_window": 50, "atr_window": 14}, "normalized_trend_move"),
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
    elif hypothesis.mechanism_family == "volatility_breakout":
        features = (
            FeatureNode("compression_ratio", {"atr_short_window": 5, "atr_long_window": 20}, "compression_ratio"),
            FeatureNode("normalized_trend_move", {"trend_anchor_window": 50, "atr_window": 14}, "normalized_trend_move"),
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
    return features, signal, params


def _select_hypothesis(
    hypotheses: list[MechanisticHypothesis],
    scorecards: list[HypothesisScorecard],
    *,
    suppressed_fingerprint: str | None = None,
) -> tuple[MechanisticHypothesis | None, list[dict[str, Any]]]:
    ranked = sorted(
        list(zip(hypotheses, scorecards)),
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
        reasons.append(
            {
                "hypothesis_id": hypothesis.hypothesis_id,
                "reason": reason,
                "overall_score": scorecard.overall_score,
            }
        )
    return selected, reasons


def _build_strategy_artifact(
    hypothesis: MechanisticHypothesis,
    *,
    data_plan: CoverageDecision,
) -> tuple[dict[str, Any], Any, str]:
    features, signal, params = _build_hypothesis_specs(hypothesis)
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
    )
    compiled = compile_strategy_spec(spec)
    return compiled, spec, content_id("qastr", {"hypothesis_id": hypothesis.hypothesis_id, "spec": spec.to_payload()})


def _run_backtest(repo_root: Path, strategy_callable: Any, data_plan: CoverageDecision, hypothesis: MechanisticHypothesis) -> dict[str, Any]:
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
            raise ValueError("data plan missing frame for local evaluation")
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
            "goedgekeurd": bool(trade_count > 0 and net_return >= 0),
        },
        "signals": signal.tolist(),
        "fallback": "local_frame_evaluation",
        "selected_instrument": instrument,
        "selected_timeframe": timeframe,
    }


def _latest_payload(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return None


def read_status(repo_root: Path) -> dict[str, Any]:
    payload = _latest_payload(repo_root / STATUS_PATH)
    if payload is not None:
        return payload
    return {
        "schema_version": "1.0",
        "policy_version": "qre_alpha_discovery_mvp_v2",
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
) -> dict[str, Any]:
    context = DiscoveryContext(repo_root=repo_root, dry_run=dry_run, max_hypotheses=max_hypotheses)
    observation = build_observation_snapshot(context)
    memory = {
        "lesson": (_latest_payload(repo_root / LESSONS_PATH) or {}).get("lesson", {}),
        "prior_run": (_latest_payload(repo_root / RUNS_PATH) or {}),
    }
    lesson_fingerprint = str((_latest_payload(repo_root / LESSONS_PATH) or {}).get("prior_fingerprint") or "")
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
                    changes_rejected=tuple(),
                    content_identity=content_id("qahrv", {"original": hypothesis.hypothesis_id, "revised": revised.hypothesis_id}),
                )
            )
        final_hypotheses.append(revised)

    scorecards = [evaluator.evaluate(hypothesis, critique, observation) for hypothesis, critique in zip(final_hypotheses, critiques, strict=False)]
    selected, unselected = _select_hypothesis(final_hypotheses, scorecards, suppressed_fingerprint=lesson_fingerprint or None)
    experiment = planner.plan(selected) if selected is not None else None
    data_requirement = build_data_requirement(experiment) if experiment is not None else None
    data_plan = resolve_data_plan(repo_root, data_requirement) if data_requirement is not None else None
    compiled = None
    strategy_spec = None
    campaign_evidence: CampaignEvidence | None = None
    assessment: EvidenceAssessment | None = None
    lesson: ResearchLesson | None = None
    terminal_disposition = "NO_NOVEL_HYPOTHESIS"
    campaign_id = None
    if selected is not None and experiment is not None:
        compiled, strategy_spec, _strategy_identity = _build_strategy_artifact(selected, data_plan=data_plan)
        if data_plan is not None:
            if compiled["status"] == "VERIFIED" and not dry_run:
                strategy_callable = compiled["callable"]
                result = _run_backtest(repo_root, strategy_callable, data_plan, selected)
                campaign_id = content_id("qcam", {"experiment_id": experiment.experiment_id, "hypothesis_id": selected.hypothesis_id})
                campaign_evidence = CampaignEvidence(
                    campaign_id=campaign_id,
                    experiment_id=experiment.experiment_id,
                    strategy_spec_id=strategy_spec.strategy_spec_id,
                    backtest_result=result,
                    data_plan=_public_data_plan(data_plan) or {},
                    content_identity=content_id("qcev", {"campaign_id": campaign_id, "experiment_id": experiment.experiment_id}),
                )
                assessment = evidence_evaluator.evaluate(experiment, campaign_evidence)
                lesson = compressor.compress(assessment, {"strategy_spec_id": strategy_spec.strategy_spec_id})
                terminal_disposition = assessment.terminal_disposition
            elif compiled["status"] == "VERIFIED" and dry_run:
                terminal_disposition = "DRY_RUN"
            else:
                terminal_disposition = "POLICY_BLOCKED"
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
    run_payload = {
        "schema_version": "1.0",
        "policy_version": "qre_alpha_discovery_mvp_v2",
        "report_kind": "qre_alpha_discovery_run",
        "run_id": content_id("qarr", {"observation": observation.content_identity, "selected": getattr(selected, "hypothesis_id", "")}),
        "state_trace": [
            "OBSERVE",
            "GENERATE",
            "CRITIQUE",
            "REWRITE",
            "SCORE",
            "SELECT",
            "PLAN",
            "VERIFY",
            "RESOLVE_DATA",
            "MATERIALIZE_CAMPAIGN",
            "EXECUTE" if not dry_run else "STOP",
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
        "data_plan_status": data_plan.decision if data_plan is not None else None,
        "campaign_id": campaign_id,
        "terminal_disposition": terminal_disposition,
        "lesson_id": lesson.lesson_id if lesson is not None else None,
        "budget_usage": asdict(budget_usage),
        "next_action": "repeat_mvp_on_next_novel_hypothesis" if terminal_disposition in {"READY_FOR_SYNTHESIS", "REJECTED", "NEEDS_MORE_EVIDENCE", "DRY_RUN"} else "wait",
        "artifact_refs": {},
        "selected_hypothesis_ids": [hyp.hypothesis_id for hyp in final_hypotheses],
        "unselected_hypothesis_reasons": unselected,
    }
    artifacts = {
        "observation": observation.to_payload(),
        "hypotheses": [hyp.to_payload() for hyp in final_hypotheses],
        "critiques": [asdict(crit) for crit in critiques],
        "rewrites": [asdict(rev) for rev in rewrites],
        "scorecards": _serialize(scorecards),
        "experiments": asdict(experiment) if experiment is not None else None,
        "strategies": strategy_spec.to_payload() if strategy_spec is not None else None,
        "data_plans": _public_data_plan(data_plan),
        "evidence_assessments": asdict(assessment) if assessment is not None else None,
        "lessons": asdict(lesson) if lesson is not None else None,
        "runs": run_payload,
        "status": {
            "schema_version": "1.0",
            "policy_version": "qre_alpha_discovery_mvp_v2",
            "report_kind": "qre_alpha_discovery_status",
            "state": "COMPLETE" if not dry_run else "DRY_RUN",
            "terminal_disposition": terminal_disposition,
            "selected_hypothesis_id": getattr(selected, "hypothesis_id", None),
            "current_wait_reason": "lesson_written" if lesson is not None else "no_campaign_executed",
            "next_wake_conditions": ["new_data", "new_lesson", "new_memory"] if lesson is not None else ["novel_observation"],
            "content_identity": content_id("qasd_status", run_payload),
        },
    }
    if not dry_run and lesson is not None:
        lesson_payload = {
            "schema_version": "1.0",
            "policy_version": "qre_alpha_discovery_mvp_v2",
            "report_kind": "qre_alpha_discovery_lesson",
            "lesson": asdict(lesson),
            "prior_fingerprint": selected.stable_fingerprint if selected is not None else "",
            "selected_hypothesis_id": selected.hypothesis_id if selected is not None else "",
        }
        artifacts["lesson_payload"] = lesson_payload
    artifact_refs = {
        "observation": _write_artifact(OBSERVATIONS_PATH, artifacts["observation"], repo_root=repo_root),
        "hypotheses": _write_artifact(HYPOTHESES_PATH, {"schema_version": "1.0", "rows": artifacts["hypotheses"]}, repo_root=repo_root),
        "critiques": _write_artifact(CRITIQUES_PATH, {"schema_version": "1.0", "rows": artifacts["critiques"]}, repo_root=repo_root),
        "rewrites": _write_artifact(REWRITES_PATH, {"schema_version": "1.0", "rows": artifacts["rewrites"]}, repo_root=repo_root),
        "scorecards": _write_artifact(SCORECARDS_PATH, {"schema_version": "1.0", "rows": artifacts["scorecards"]}, repo_root=repo_root),
        "experiments": _write_artifact(EXPERIMENTS_PATH, {"schema_version": "1.0", "rows": [artifacts["experiments"]] if artifacts["experiments"] else []}, repo_root=repo_root),
        "strategies": _write_artifact(STRATEGIES_PATH, {"schema_version": "1.0", "rows": [artifacts["strategies"]] if artifacts["strategies"] else []}, repo_root=repo_root),
        "data_plans": _write_artifact(
            DATA_PLANS_PATH,
            {
                "schema_version": "1.0",
                "rows": [
                    {
                        key: value
                        for key, value in artifacts["data_plans"].items()
                        if key != "frame"
                    }
                ]
                if artifacts["data_plans"]
                else [],
            },
            repo_root=repo_root,
        ),
        "evidence_assessments": _write_artifact(EVIDENCE_ASSESSMENTS_PATH, {"schema_version": "1.0", "rows": [artifacts["evidence_assessments"]] if artifacts["evidence_assessments"] else []}, repo_root=repo_root),
        "runs": _write_artifact(RUNS_PATH, artifacts["runs"], repo_root=repo_root),
        "status": _write_artifact(STATUS_PATH, artifacts["status"], repo_root=repo_root),
    }
    if "lesson_payload" in artifacts:
        artifact_refs["lessons"] = _write_artifact(LESSONS_PATH, artifacts["lesson_payload"], repo_root=repo_root)
    run_payload["artifact_refs"] = artifact_refs
    artifacts["runs"] = run_payload
    artifact_refs["runs"] = _write_artifact(RUNS_PATH, run_payload, repo_root=repo_root)
    identity_input = {key: value for key, value in run_payload.items() if key != "content_identity"}
    run_payload["content_identity"] = content_id("qarrc", identity_input)
    artifacts["status"]["content_identity"] = content_id("qasd_status", identity_input)
    artifact_refs["runs"] = _write_artifact(RUNS_PATH, run_payload, repo_root=repo_root)
    artifact_refs["status"] = _write_artifact(STATUS_PATH, artifacts["status"], repo_root=repo_root)
    return {
        **run_payload,
        "artifact_refs": artifact_refs,
        "artifacts": artifacts,
    }
