"""Controlled closed-loop dry-run runner for the QRE research loop.

This module proves a bounded closed research loop:

market intake -> hypothesis -> strategy intent -> preset intent -> campaign dry-run
intent -> controlled result summary -> analysis -> learning feedback -> next-loop seed.

It intentionally does not call run_research, campaign_launcher, subprocesses, network,
external data, paper/shadow/live, broker/risk, candidate promotion, strategy/preset
mutation, or protected public output mutation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Final


SCHEMA_VERSION: Final[str] = "1.0"
REPORT_KIND: Final[str] = "qre_controlled_closed_loop_dry_run"

DEFAULT_INPUT_PATH: Final[Path] = Path(
    "logs/qre_controlled_subset_screening_dry_run_executor/latest.json"
)
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_controlled_closed_loop_dry_run")

CONTROLLED_ASSET_SET: Final[set[str]] = {
    "ADYEN",
    "ASML",
    "AAPL",
    "MSFT",
    "SONY",
    "TM",
    "SPY",
    "EWJ",
}
FORBIDDEN_ASSET_CLASSES: Final[set[str]] = {"crypto", "crypto_legacy"}
FORBIDDEN_SYMBOL_MARKERS: Final[tuple[str, ...]] = ("-USD", "BTC", "ETH", "SOL", "DOGE", "XRP")
PROTECTED_PUBLIC_OUTPUTS: Final[tuple[Path, ...]] = (
    Path("research/research_latest.json"),
    Path("research/strategy_matrix.csv"),
)


class ControlledClosedLoopError(RuntimeError):
    """Raised when controlled closed-loop dry-run cannot safely proceed."""


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _read_json(path: Path) -> Any:
    if not path.exists():
        raise ControlledClosedLoopError(f"input packet does not exist: {path.as_posix()}")
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _file_fingerprint(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"exists": False, "sha256": None}
    return {"exists": True, "sha256": _sha256_bytes(path.read_bytes())}


def _protected_fingerprints() -> dict[str, dict[str, Any]]:
    return {path.as_posix(): _file_fingerprint(path) for path in PROTECTED_PUBLIC_OUTPUTS}


def _assert_protected_outputs_unchanged(before: dict[str, dict[str, Any]]) -> None:
    after = _protected_fingerprints()
    if before != after:
        raise ControlledClosedLoopError(
            "protected public outputs changed during closed-loop dry-run"
        )


def _assert_output_path_inside(output_dir: Path, path: Path) -> None:
    root = output_dir.resolve()
    resolved = path.resolve()
    if root != resolved and root not in resolved.parents:
        raise ControlledClosedLoopError(
            f"refusing to write outside output root: {path.as_posix()}"
        )


def _safe_write_text(output_dir: Path, path: Path, content: str) -> None:
    _assert_output_path_inside(output_dir, path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _require_packet(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ControlledClosedLoopError("closed-loop input must be a JSON object")
    return payload


def _result_records(payload: dict[str, Any]) -> list[dict[str, Any]]:
    records = payload.get("screening_dry_run_result_records")
    if not isinstance(records, list):
        raise ControlledClosedLoopError("screening_dry_run_result_records must be a list")

    normalized: list[dict[str, Any]] = []
    for index, record in enumerate(records, start=1):
        if not isinstance(record, dict):
            raise ControlledClosedLoopError(
                f"screening_dry_run_result_records[{index}] must be an object"
            )
        normalized.append(record)
    return normalized


def _validate_executor_packet(payload: dict[str, Any], records: list[dict[str, Any]]) -> list[str]:
    blockers: list[str] = []
    summary = payload.get("summary")

    if payload.get("report_kind") != "qre_controlled_subset_screening_dry_run_executor":
        blockers.append("input_report_kind_not_screening_dry_run_executor")

    if not isinstance(summary, dict):
        blockers.append("input_summary_missing")
        return blockers

    required_false_summary_flags = (
        "validation_executed",
        "execution_performed",
        "subprocess_called",
        "network_called",
        "external_data_called",
        "run_research_called",
        "campaign_launcher_called",
        "safe_to_execute_research",
        "candidate_promotion_allowed",
        "paper_shadow_live_allowed",
    )
    for flag in required_false_summary_flags:
        if summary.get(flag) is not False:
            blockers.append(f"summary_{flag}_not_false")

    if summary.get("screening_dry_run_executor_ready") is not True:
        blockers.append("screening_dry_run_executor_not_ready")
    if int(summary.get("screening_result_count", -1)) != 8:
        blockers.append("screening_result_count_not_8")
    if int(summary.get("blocker_count", -1)) != 0:
        blockers.append("input_blocker_count_not_zero")
    if summary.get("screening_result_counts") != {"metadata_only_pass": 8}:
        blockers.append("screening_result_counts_not_all_metadata_only_pass")

    symbols = {str(record.get("instrument_symbol") or "") for record in records}
    if symbols != CONTROLLED_ASSET_SET:
        blockers.append(
            "controlled_asset_set_mismatch:"
            + ",".join(sorted(symbols))
        )

    if len(records) != 8:
        blockers.append(f"record_count_not_8:{len(records)}")

    for index, record in enumerate(records, start=1):
        symbol = str(record.get("instrument_symbol") or "")
        symbol_upper = symbol.upper()
        asset_class = str(record.get("asset_class") or "").lower()

        if asset_class in FORBIDDEN_ASSET_CLASSES:
            blockers.append(f"record_{index}_forbidden_asset_class:{asset_class}")
        if "-USD" in symbol_upper or symbol_upper in FORBIDDEN_SYMBOL_MARKERS:
            blockers.append(f"record_{index}_crypto_symbol_marker:{symbol}")

        required_false_record_flags = (
            "validation_executed",
            "execution_performed",
            "subprocess_called",
            "network_called",
            "external_data_called",
            "run_research_called",
            "campaign_launcher_called",
            "candidate_promotion_allowed",
            "paper_activation_allowed",
            "shadow_activation_allowed",
            "live_activation_allowed",
            "broker_execution_allowed",
            "risk_authority_allowed",
            "candidate_registry_mutated",
            "campaign_artifacts_mutated",
            "queue_mutated",
            "strategy_registered",
            "preset_mutated",
            "research_latest_mutated",
            "strategy_matrix_mutated",
        )
        for flag in required_false_record_flags:
            if record.get(flag) is not False:
                blockers.append(f"record_{index}_{flag}_not_false")

        if record.get("screening_result") != "metadata_only_pass":
            blockers.append(f"record_{index}_screening_result_not_metadata_only_pass")
        if record.get("not_trade_signal") is not True:
            blockers.append(f"record_{index}_not_trade_signal_not_true")

    return blockers


def _build_market_intake(
    records: list[dict[str, Any]],
    *,
    loop_index: int,
    previous_learning_feedback: dict[str, Any] | None,
) -> dict[str, Any]:
    assets = sorted(str(record["instrument_symbol"]) for record in records)
    regions = sorted({str(record["region"]) for record in records})
    asset_classes = sorted({str(record["asset_class"]) for record in records})
    preset_ids = sorted({str(record["behavior_preset_id"]) for record in records})
    timeframes = sorted({str(record["timeframe"]) for record in records})

    intake_source = "controlled_subset_screening_dry_run_executor"
    previous_feedback_summary = None
    if previous_learning_feedback is not None:
        intake_source = "previous_loop_learning_feedback"
        previous_feedback_summary = previous_learning_feedback.get("learning_statement")

    return {
        "phase": "market_intake",
        "phase_status": "materialized",
        "loop_index": loop_index,
        "intake_source": intake_source,
        "previous_feedback_summary": previous_feedback_summary,
        "controlled_universe": assets,
        "asset_count": len(assets),
        "region_counts": {
            region: sum(1 for record in records if record.get("region") == region)
            for region in regions
        },
        "asset_class_counts": {
            asset_class: sum(1 for record in records if record.get("asset_class") == asset_class)
            for asset_class in asset_classes
        },
        "preset_ids": preset_ids,
        "timeframes": timeframes,
        "market_observation": (
            "Controlled non-crypto subset has complete metadata-only screening results "
            "and is eligible for closed-loop reasoning, but not for validation, promotion, "
            "paper/shadow/live, broker, or risk execution."
        ),
    }


def _formulate_hypothesis(
    market_intake: dict[str, Any],
    *,
    loop_index: int,
    previous_learning_feedback: dict[str, Any] | None,
) -> dict[str, Any]:
    if previous_learning_feedback is None:
        hypothesis_family = "trend_continuation_metadata_readiness"
        hypothesis_statement = (
            "The controlled non-crypto multi-region subset may be suitable for a daily "
            "trend-continuation research path if metadata readiness remains clean and "
            "future bounded metric evidence confirms enough observations and trades."
        )
        hypothesis_adjustment = "initial_engine_formulated_hypothesis"
    else:
        prior_result = str(previous_learning_feedback.get("learning_result") or "")
        if prior_result == "all_assets_metadata_passed":
            hypothesis_family = "bounded_metric_evidence_readiness"
            hypothesis_statement = (
                "Because all controlled assets passed metadata-only screening, the next "
                "research loop should not rotate assets first; it should test whether the "
                "same hypothesis and preset can produce bounded metric evidence without "
                "public-output mutation."
            )
            hypothesis_adjustment = "advanced_from_metadata_screening_to_metric_evidence"
        else:
            hypothesis_family = "hypothesis_or_preset_fit_reassessment"
            hypothesis_statement = (
                "Because the prior loop reported content blockers, the next loop should "
                "reassess hypothesis or preset fit before rotating assets."
            )
            hypothesis_adjustment = "reassess_hypothesis_before_asset_rotation"

    return {
        "phase": "hypothesis_generation",
        "phase_status": "materialized",
        "loop_index": loop_index,
        "hypothesis_id": f"controlled-loop-hypothesis::{loop_index}",
        "hypothesis_family": hypothesis_family,
        "hypothesis_statement": hypothesis_statement,
        "hypothesis_adjustment": hypothesis_adjustment,
        "formulation_mode": "engine_rule_based_from_market_intake_and_prior_feedback",
        "not_alpha_claim": True,
        "not_trade_signal": True,
    }


def _build_strategy_intent(hypothesis: dict[str, Any], *, loop_index: int) -> dict[str, Any]:
    family = str(hypothesis["hypothesis_family"])
    if family == "bounded_metric_evidence_readiness":
        strategy_family = "bounded_metric_evidence_probe"
        strategy_statement = (
            "Prepare a no-mutation metric-evidence path for the controlled subset before "
            "any validation or promotion is allowed."
        )
    elif family == "hypothesis_or_preset_fit_reassessment":
        strategy_family = "hypothesis_preset_reassessment"
        strategy_statement = (
            "Reassess whether trend-continuation daily is the correct preset family before "
            "changing the asset universe."
        )
    else:
        strategy_family = "trend_continuation_daily"
        strategy_statement = (
            "Use the existing trend_continuation_daily_v1 preset as the read-only strategy "
            "intent for the initial closed-loop proof."
        )

    return {
        "phase": "strategy_formulation",
        "phase_status": "materialized",
        "loop_index": loop_index,
        "strategy_intent_id": f"controlled-loop-strategy-intent::{loop_index}",
        "strategy_family": strategy_family,
        "strategy_statement": strategy_statement,
        "strategy_registered": False,
        "strategy_registry_mutated": False,
        "not_alpha_claim": True,
        "not_trade_signal": True,
    }


def _build_preset_intent(strategy_intent: dict[str, Any], *, loop_index: int) -> dict[str, Any]:
    return {
        "phase": "preset_selection",
        "phase_status": "materialized",
        "loop_index": loop_index,
        "preset_intent_id": f"controlled-loop-preset-intent::{loop_index}",
        "selected_preset_id": "trend_continuation_daily_v1",
        "selection_reason": (
            "Read-only existing preset selected for controlled-loop continuity; no preset "
            "registration or mutation is allowed in this dry-run."
        ),
        "strategy_intent_id": strategy_intent["strategy_intent_id"],
        "preset_mutated": False,
        "new_preset_registered": False,
    }


def _build_campaign_dry_run_intent(
    market_intake: dict[str, Any],
    hypothesis: dict[str, Any],
    strategy_intent: dict[str, Any],
    preset_intent: dict[str, Any],
    *,
    loop_index: int,
) -> dict[str, Any]:
    return {
        "phase": "campaign_planning",
        "phase_status": "materialized",
        "loop_index": loop_index,
        "campaign_dry_run_intent_id": f"controlled-loop-campaign-dryrun::{loop_index}",
        "campaign_mode": "controlled_closed_loop_dry_run_no_launcher_no_mutation",
        "controlled_universe": market_intake["controlled_universe"],
        "hypothesis_id": hypothesis["hypothesis_id"],
        "strategy_intent_id": strategy_intent["strategy_intent_id"],
        "preset_intent_id": preset_intent["preset_intent_id"],
        "selected_preset_id": preset_intent["selected_preset_id"],
        "closest_existing_safe_command": "python -m research.campaign_launcher --dry-run",
        "closest_existing_safe_command_limitation": (
            "Safe policy dry-run only; it does not produce true metrics and does not provide "
            "an exact controlled 8-asset allowlist."
        ),
        "true_metric_execution_blocked_until": [
            "run_research --dry-run",
            "run_research --output-root",
            "run_research --cache-only",
            "run_research --no-public-output-mutation",
            "run_research --exact-universe",
            "run_research --no-process-pool",
        ],
        "campaign_launcher_called": False,
        "run_research_called": False,
        "campaign_artifacts_mutated": False,
        "queue_mutated": False,
        "candidate_promotion_allowed": False,
    }


def _build_controlled_result_summary(
    records: list[dict[str, Any]],
    *,
    loop_index: int,
) -> dict[str, Any]:
    assets = sorted(str(record["instrument_symbol"]) for record in records)
    metadata_pass_count = sum(
        1 for record in records if record.get("screening_result") == "metadata_only_pass"
    )
    return {
        "phase": "controlled_result",
        "phase_status": "materialized",
        "loop_index": loop_index,
        "result_source": "qre_controlled_subset_screening_dry_run_executor",
        "controlled_assets": assets,
        "screening_result_count": len(records),
        "metadata_only_pass_count": metadata_pass_count,
        "true_metric_result_available": False,
        "trade_count_available": False,
        "oos_performance_available": False,
        "metric_placeholders": {
            "trade_count": None,
            "deflated_sharpe": None,
            "max_drawdown": None,
            "oos_return": None,
            "reason": (
                "True metrics are intentionally blocked until the engine has a safe exact "
                "universe, cache-only, no-public-output-mutation run path."
            ),
        },
        "validation_executed": False,
        "execution_performed": False,
        "not_alpha_claim": True,
        "not_trade_signal": True,
    }


def _build_analysis(
    market_intake: dict[str, Any],
    result_summary: dict[str, Any],
    *,
    loop_index: int,
) -> dict[str, Any]:
    all_metadata_passed = (
        result_summary["metadata_only_pass_count"] == result_summary["screening_result_count"]
        and result_summary["screening_result_count"] == 8
    )
    content_blockers: list[str] = []
    if not all_metadata_passed:
        content_blockers.append("not_all_controlled_assets_metadata_passed")
    if result_summary["true_metric_result_available"] is False:
        content_blockers.append("true_metric_execution_not_yet_safe")

    return {
        "phase": "analysis",
        "phase_status": "materialized",
        "loop_index": loop_index,
        "all_controlled_assets_metadata_passed": all_metadata_passed,
        "content_blockers": content_blockers,
        "safety_blockers": [],
        "analysis_statement": (
            "The controlled subset is ready for a bounded metric-evidence readiness feature, "
            "not for validation, candidate promotion, or paper/shadow/live execution."
            if all_metadata_passed
            else "The closed loop should reassess hypothesis/preset fit before rotating assets."
        ),
        "recommended_next_engine_capability": (
            "add_safe_run_research_metric_dry_run_path"
        ),
    }


def _build_learning_feedback(
    hypothesis: dict[str, Any],
    analysis: dict[str, Any],
    *,
    loop_index: int,
) -> dict[str, Any]:
    all_passed = bool(analysis["all_controlled_assets_metadata_passed"])
    learning_result = "all_assets_metadata_passed" if all_passed else "content_blockers_detected"

    if all_passed:
        learning_statement = (
            "Controlled non-crypto trend-continuation subset passed metadata-only screening. "
            "The next loop should keep the same asset universe and test whether the hypothesis "
            "and preset can produce bounded metric evidence, rather than rotating assets."
        )
    else:
        learning_statement = (
            "Controlled subset did not fully pass metadata screening. The next loop should "
            "reassess hypothesis or preset fit before changing assets."
        )

    return {
        "phase": "learning_feedback",
        "phase_status": "materialized",
        "loop_index": loop_index,
        "learning_feedback_id": f"controlled-loop-learning::{loop_index}",
        "source_hypothesis_id": hypothesis["hypothesis_id"],
        "learning_result": learning_result,
        "learning_statement": learning_statement,
        "routing_hints": {
            "do_not_rotate_assets_first": all_passed,
            "reassess_hypothesis_before_asset_rotation": not all_passed,
            "next_requested_capability": "bounded_metric_evidence_dry_run",
            "paper_shadow_live_allowed": False,
        },
        "next_experiment": {
            "experiment_family": "bounded_metric_evidence_readiness",
            "requires_safe_engine_flags": [
                "--dry-run",
                "--output-root",
                "--cache-only",
                "--no-public-output-mutation",
                "--exact-universe",
            ],
        },
    }


def _build_next_loop_seed(
    learning_feedback: dict[str, Any],
    *,
    loop_index: int,
) -> dict[str, Any]:
    return {
        "phase": "next_loop_seed",
        "phase_status": "materialized",
        "loop_index": loop_index,
        "next_loop_seed_id": f"controlled-loop-next-seed::{loop_index}",
        "seed_source_learning_feedback_id": learning_feedback["learning_feedback_id"],
        "seed_statement": learning_feedback["learning_statement"],
        "next_loop_should_use_previous_learning": True,
        "next_loop_recommended_focus": learning_feedback["routing_hints"][
            "next_requested_capability"
        ],
    }


def _build_engine_readiness_probe(*, loop_index: int) -> dict[str, Any]:
    return {
        "phase": "engine_readiness_probe",
        "phase_status": "materialized",
        "loop_index": loop_index,
        "existing_engine_can_true_campaign_dry_run_now": False,
        "closest_safe_existing_command": "python -m research.campaign_launcher --dry-run",
        "closest_safe_command_produces_true_metrics": False,
        "run_research_blocked_reason": (
            "Current run_research path mutates protected public outputs and can use external "
            "data on cache miss; a safe metric dry-run requires output-root, cache-only, "
            "exact-universe, and no-public-output-mutation controls."
        ),
        "recommended_route": "controlled_closed_loop_adapter_now_add_safe_metric_runner_next",
    }


def _build_closed_loop_run(
    records: list[dict[str, Any]],
    *,
    loop_index: int,
    run_group_id: str,
    previous_learning_feedback: dict[str, Any] | None,
) -> dict[str, Any]:
    market_intake = _build_market_intake(
        records,
        loop_index=loop_index,
        previous_learning_feedback=previous_learning_feedback,
    )
    hypothesis = _formulate_hypothesis(
        market_intake,
        loop_index=loop_index,
        previous_learning_feedback=previous_learning_feedback,
    )
    strategy_intent = _build_strategy_intent(hypothesis, loop_index=loop_index)
    preset_intent = _build_preset_intent(strategy_intent, loop_index=loop_index)
    campaign_intent = _build_campaign_dry_run_intent(
        market_intake,
        hypothesis,
        strategy_intent,
        preset_intent,
        loop_index=loop_index,
    )
    result_summary = _build_controlled_result_summary(records, loop_index=loop_index)
    analysis = _build_analysis(market_intake, result_summary, loop_index=loop_index)
    learning_feedback = _build_learning_feedback(hypothesis, analysis, loop_index=loop_index)
    next_loop_seed = _build_next_loop_seed(learning_feedback, loop_index=loop_index)
    readiness_probe = _build_engine_readiness_probe(loop_index=loop_index)

    phases = [
        market_intake,
        hypothesis,
        strategy_intent,
        preset_intent,
        campaign_intent,
        result_summary,
        analysis,
        learning_feedback,
        next_loop_seed,
        readiness_probe,
    ]

    content_blockers = list(analysis["content_blockers"])
    safety_blockers = list(analysis["safety_blockers"])

    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "run_id": f"{run_group_id}::loop::{loop_index}",
        "run_group_id": run_group_id,
        "loop_index": loop_index,
        "created_at_utc": _utc_timestamp(),
        "phase_order": [str(phase["phase"]) for phase in phases],
        "phases": phases,
        "summary": {
            "closed_loop_run_ready": not safety_blockers,
            "full_loop_materialized": True,
            "market_intake_materialized": True,
            "hypothesis_generated": True,
            "strategy_intent_materialized": True,
            "preset_intent_materialized": True,
            "campaign_dry_run_intent_materialized": True,
            "controlled_result_materialized": True,
            "analysis_materialized": True,
            "learning_feedback_materialized": True,
            "next_loop_seed_materialized": True,
            "content_blocker_count": len(content_blockers),
            "safety_blocker_count": len(safety_blockers),
            "screening_result_count": result_summary["screening_result_count"],
            "metadata_only_pass_count": result_summary["metadata_only_pass_count"],
            "true_metric_result_available": False,
            "run_research_called": False,
            "campaign_launcher_called": False,
            "subprocess_called": False,
            "network_called": False,
            "external_data_called": False,
            "validation_executed": False,
            "execution_performed": False,
            "candidate_promotion_allowed": False,
            "paper_shadow_live_allowed": False,
            "broker_risk_allowed": False,
            "research_latest_mutated": False,
            "strategy_matrix_mutated": False,
            "learning_result": learning_feedback["learning_result"],
            "next_recommended_action": (
                "add_safe_metric_evidence_dry_run_path"
            ),
            "final_recommendation": (
                "closed_loop_learning_ready_for_next_seed_not_validation"
            ),
        },
        "content_blockers": content_blockers,
        "safety_blockers": safety_blockers,
        "learning_feedback": learning_feedback,
        "next_loop_seed": next_loop_seed,
    }


def build_closed_loop_packet(
    input_path: Path = DEFAULT_INPUT_PATH,
    *,
    max_loops: int = 2,
) -> dict[str, Any]:
    if max_loops < 1:
        raise ControlledClosedLoopError("--max-loops must be at least 1")
    if max_loops > 25:
        raise ControlledClosedLoopError("--max-loops is capped at 25 for operator safety")

    payload = _require_packet(_read_json(input_path))
    records = _result_records(payload)
    input_blockers = _validate_executor_packet(payload, records)
    if input_blockers:
        raise ControlledClosedLoopError(
            "input safety validation failed: " + "; ".join(input_blockers)
        )

    run_group_id = "controlled-closed-loop-" + _sha256_bytes(
        json.dumps(
            {
                "input_path": input_path.as_posix(),
                "assets": sorted(CONTROLLED_ASSET_SET),
                "max_loops": max_loops,
            },
            sort_keys=True,
        ).encode("utf-8")
    )[:16]

    runs: list[dict[str, Any]] = []
    previous_learning_feedback: dict[str, Any] | None = None

    for loop_index in range(1, max_loops + 1):
        run = _build_closed_loop_run(
            records,
            loop_index=loop_index,
            run_group_id=run_group_id,
            previous_learning_feedback=previous_learning_feedback,
        )
        runs.append(run)
        previous_learning_feedback = run["learning_feedback"]

    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "run_group_id": run_group_id,
        "input_path": input_path.as_posix(),
        "created_at_utc": _utc_timestamp(),
        "max_loops": max_loops,
        "authority_boundaries": {
            "controlled_closed_loop_dry_run_only": True,
            "does_not_call_run_research": True,
            "does_not_call_campaign_launcher": True,
            "does_not_call_subprocess": True,
            "does_not_call_network": True,
            "does_not_call_external_data": True,
            "does_not_execute_validation": True,
            "does_not_promote_candidates": True,
            "does_not_register_strategy": True,
            "does_not_register_preset": True,
            "does_not_mutate_research_latest": True,
            "does_not_mutate_strategy_matrix": True,
            "does_not_mutate_campaign_registry": True,
            "does_not_mutate_queue": True,
            "not_paper_shadow_live": True,
            "not_broker_execution": True,
            "not_risk_authority": True,
        },
        "summary": {
            "closed_loop_packet_ready": True,
            "loop_count": len(runs),
            "last_run_id": runs[-1]["run_id"],
            "full_loop_materialized": all(
                run["summary"]["full_loop_materialized"] for run in runs
            ),
            "learning_feedback_count": len(runs),
            "next_loop_seed_count": len(runs),
            "run_research_called": False,
            "campaign_launcher_called": False,
            "subprocess_called": False,
            "network_called": False,
            "external_data_called": False,
            "validation_executed": False,
            "execution_performed": False,
            "paper_shadow_live_allowed": False,
            "broker_risk_allowed": False,
            "true_metric_execution_available": False,
            "true_metric_execution_blocked_until_safe_runner_exists": True,
            "final_recommendation": (
                "controlled_closed_loop_ready_for_operator_review_add_safe_metric_runner_next"
            ),
        },
        "runs": runs,
    }


def render_operator_summary(packet: dict[str, Any]) -> str:
    summary = packet["summary"]
    lines = [
        "# QRE Controlled Closed-Loop Dry-Run",
        "",
        "- Controlled closed-loop research dry-run completed without invoking run_research, campaign_launcher, subprocess, network, external data, validation, paper/shadow/live, broker, or risk authority.",
        "- The loop proves market intake -> hypothesis -> strategy intent -> preset intent -> campaign dry-run intent -> result -> analysis -> learning feedback -> next-loop seed.",
        "",
        "## Current Status",
        "",
        f"- closed_loop_packet_ready: {summary['closed_loop_packet_ready']}",
        f"- loop_count: {summary['loop_count']}",
        f"- last_run_id: {summary['last_run_id']}",
        f"- full_loop_materialized: {summary['full_loop_materialized']}",
        f"- learning_feedback_count: {summary['learning_feedback_count']}",
        f"- next_loop_seed_count: {summary['next_loop_seed_count']}",
        f"- run_research_called: {summary['run_research_called']}",
        f"- campaign_launcher_called: {summary['campaign_launcher_called']}",
        f"- subprocess_called: {summary['subprocess_called']}",
        f"- network_called: {summary['network_called']}",
        f"- external_data_called: {summary['external_data_called']}",
        f"- validation_executed: {summary['validation_executed']}",
        f"- execution_performed: {summary['execution_performed']}",
        f"- true_metric_execution_available: {summary['true_metric_execution_available']}",
        f"- final_recommendation: {summary['final_recommendation']}",
        "",
        "## Loop Learning",
        "",
    ]

    for run in packet["runs"]:
        run_summary = run["summary"]
        learning = run["learning_feedback"]
        next_seed = run["next_loop_seed"]
        lines.extend(
            [
                f"### Loop {run['loop_index']}",
                "",
                f"- run_id: {run['run_id']}",
                f"- learning_result: {run_summary['learning_result']}",
                f"- metadata_only_pass_count: {run_summary['metadata_only_pass_count']}",
                f"- screening_result_count: {run_summary['screening_result_count']}",
                f"- content_blocker_count: {run_summary['content_blocker_count']}",
                f"- safety_blocker_count: {run_summary['safety_blocker_count']}",
                f"- learning_statement: {learning['learning_statement']}",
                f"- next_loop_seed: {next_seed['seed_statement']}",
                "",
            ]
        )

    lines.extend(
        [
            "## Engine Readiness Verdict",
            "",
            "- Existing `campaign_launcher --dry-run` is safe but does not produce true metrics.",
            "- Existing `run_research` is blocked for this loop because it can mutate protected public outputs and may use external data on cache miss.",
            "- Next implementation target: safe metric evidence runner with exact universe, cache-only, output-root, and no-public-output-mutation controls.",
        ]
    )

    return "\n".join(lines) + "\n"


def write_outputs(
    packet: dict[str, Any],
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    runs_dir = output_dir / "runs"

    latest_path = output_dir / "latest.json"
    ledger_path = output_dir / "ledger.jsonl"
    operator_summary_path = output_dir / "operator_summary.md"

    _safe_write_text(
        output_dir,
        latest_path,
        json.dumps(packet, indent=2, sort_keys=True) + "\n",
    )
    _safe_write_text(output_dir, operator_summary_path, render_operator_summary(packet))

    written_run_paths: list[str] = []
    for run in packet["runs"]:
        safe_run_id = str(run["run_id"]).replace(":", "_").replace("/", "_")
        run_path = runs_dir / f"{safe_run_id}.json"
        _safe_write_text(
            output_dir,
            run_path,
            json.dumps(run, indent=2, sort_keys=True) + "\n",
        )
        written_run_paths.append(run_path.as_posix())

    ledger_lines = [
        json.dumps(
            {
                "schema_version": SCHEMA_VERSION,
                "report_kind": REPORT_KIND,
                "run_group_id": packet["run_group_id"],
                "run_id": run["run_id"],
                "loop_index": run["loop_index"],
                "created_at_utc": run["created_at_utc"],
                "learning_result": run["summary"]["learning_result"],
                "next_recommended_action": run["summary"]["next_recommended_action"],
                "run_research_called": False,
                "campaign_launcher_called": False,
                "validation_executed": False,
                "paper_shadow_live_allowed": False,
            },
            sort_keys=True,
        )
        for run in packet["runs"]
    ]
    ledger_existing = ""
    if ledger_path.exists():
        ledger_existing = ledger_path.read_text(encoding="utf-8")
    ledger_payload = ledger_existing + "".join(line + "\n" for line in ledger_lines)
    _safe_write_text(output_dir, ledger_path, ledger_payload)

    return {
        "latest": latest_path.as_posix(),
        "operator_summary": operator_summary_path.as_posix(),
        "ledger": ledger_path.as_posix(),
        "runs": ",".join(written_run_paths),
    }


def run_closed_loop(
    *,
    input_path: Path = DEFAULT_INPUT_PATH,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    max_loops: int = 2,
    sleep_seconds: float = 0.0,
    write: bool = False,
) -> dict[str, Any]:
    before = _protected_fingerprints()
    packet = build_closed_loop_packet(input_path, max_loops=max_loops)

    if sleep_seconds < 0:
        raise ControlledClosedLoopError("--sleep-seconds cannot be negative")
    if sleep_seconds and max_loops > 1:
        for _ in range(max_loops - 1):
            time.sleep(sleep_seconds)

    if write:
        packet["_artifact_paths"] = write_outputs(packet, output_dir=output_dir)

    _assert_protected_outputs_unchanged(before)
    return packet


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run controlled closed-loop dry-run ledger.")
    parser.add_argument("--input", default=DEFAULT_INPUT_PATH.as_posix())
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR.as_posix())
    parser.add_argument("--max-loops", type=int, default=2)
    parser.add_argument("--sleep-seconds", type=float, default=0.0)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)

    packet = run_closed_loop(
        input_path=Path(args.input),
        output_dir=Path(args.output_dir),
        max_loops=args.max_loops,
        sleep_seconds=args.sleep_seconds,
        write=args.write,
    )
    print(json.dumps(packet, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())