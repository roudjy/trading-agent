"""Screening dry-run executor for controlled subset screening plans.

This module consumes screening dry-run plan records and materializes deterministic
local dry-run result records. It does not call run_research, campaign_launcher,
subprocesses, network, external data, validation, broker execution, paper/shadow/live,
or mutate research_latest.json / strategy_matrix.csv.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Final


SCHEMA_VERSION: Final[str] = "1.0"
REPORT_KIND: Final[str] = "qre_controlled_subset_screening_dry_run_executor"

DEFAULT_INPUT_PATH: Final[Path] = Path(
    "logs/qre_controlled_subset_screening_dry_run_plan/latest.json"
)
DEFAULT_OUTPUT_DIR: Final[Path] = Path(
    "logs/qre_controlled_subset_screening_dry_run_executor"
)

FORBIDDEN_ASSET_CLASSES: Final[set[str]] = {"crypto", "crypto_legacy"}
REQUIRED_PLAN_FIELDS: Final[tuple[str, ...]] = (
    "screening_dry_run_plan_id",
    "local_runner_envelope_id",
    "runner_dry_run_intent_id",
    "candidate_plan_id",
    "instrument_symbol",
    "asset_class",
    "region",
    "behavior_preset_id",
    "timeframe",
    "primary_data_provider_symbol",
    "plan_status",
    "screening_mode",
)


class ScreeningDryRunExecutorError(RuntimeError):
    """Raised when screening dry-run executor input cannot be read."""


def _read_json(path: Path) -> Any:
    if not path.exists():
        raise ScreeningDryRunExecutorError(
            f"screening dry-run plan packet does not exist: {path.as_posix()}"
        )
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _require_packet(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ScreeningDryRunExecutorError("screening dry-run input must be a JSON object")
    return payload


def _plan_records(payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw_records = payload.get("screening_dry_run_plan_records")
    if not isinstance(raw_records, list):
        raise ScreeningDryRunExecutorError("screening_dry_run_plan_records must be a list")
    records: list[dict[str, Any]] = []
    for index, record in enumerate(raw_records, start=1):
        if not isinstance(record, dict):
            raise ScreeningDryRunExecutorError(
                f"screening_dry_run_plan_records[{index}] is not an object"
            )
        records.append(record)
    return records


def _input_packet_ready(payload: dict[str, Any]) -> bool:
    summary = payload.get("summary")
    if not isinstance(summary, dict):
        return False
    return (
        payload.get("report_kind") == "qre_controlled_subset_screening_dry_run_plan"
        and summary.get("screening_dry_run_plan_ready") is True
        and int(summary.get("blocker_count") or 0) == 0
        and summary.get("screening_executed") is False
        and summary.get("validation_executed") is False
        and summary.get("execution_performed") is False
        and summary.get("subprocess_called") is False
        and summary.get("network_called") is False
        and summary.get("run_research_called") is False
        and summary.get("campaign_launcher_called") is False
        and summary.get("safe_to_execute_research") is False
    )


def _plan_blockers(record: dict[str, Any], *, index: int) -> list[str]:
    blockers: list[str] = []

    for field in REQUIRED_PLAN_FIELDS:
        if record.get(field) in (None, "", []):
            blockers.append(f"missing_required_field:{field}")

    symbol = str(record.get("instrument_symbol") or "")
    asset_class = str(record.get("asset_class") or "").lower()

    if asset_class in FORBIDDEN_ASSET_CLASSES:
        blockers.append(f"forbidden_asset_class:{asset_class}")
    if "-USD" in symbol.upper() or symbol.upper() in {"BTC", "ETH", "SOL", "DOGE", "XRP"}:
        blockers.append("crypto_symbol_marker_detected")

    if str(record.get("plan_status")) != "screening_dry_run_planned_not_executed":
        blockers.append("plan_status_not_planned_not_executed")
    if str(record.get("screening_mode")) != "local_dry_run_no_subprocess_no_network_no_mutation":
        blockers.append("unexpected_screening_mode")

    for field in (
        "screening_executed",
        "validation_executed",
        "execution_performed",
        "subprocess_called",
        "network_called",
        "run_research_called",
        "campaign_launcher_called",
        "candidate_registry_mutated",
        "campaign_artifacts_mutated",
        "queue_mutated",
        "strategy_registered",
        "preset_mutated",
        "research_latest_mutated",
        "strategy_matrix_mutated",
        "candidate_promotion_allowed",
        "paper_activation_allowed",
        "shadow_activation_allowed",
        "live_activation_allowed",
        "broker_execution_allowed",
        "risk_authority_allowed",
    ):
        if bool(record.get(field, False)):
            blockers.append(f"{field}_true")

    return [f"plan_{index}:{blocker}" for blocker in blockers]


def _screening_result_record(record: dict[str, Any], *, index: int) -> dict[str, Any]:
    plan_id = str(record.get("screening_dry_run_plan_id"))
    return {
        "screening_dry_run_result_id": f"screening-dryrun-result::{plan_id}",
        "result_sequence_number": index,
        "screening_dry_run_plan_id": plan_id,
        "local_runner_envelope_id": str(record.get("local_runner_envelope_id")),
        "runner_dry_run_intent_id": str(record.get("runner_dry_run_intent_id")),
        "candidate_plan_id": str(record.get("candidate_plan_id")),
        "instrument_symbol": str(record.get("instrument_symbol")),
        "asset_class": str(record.get("asset_class")),
        "region": str(record.get("region")),
        "behavior_preset_id": str(record.get("behavior_preset_id")),
        "timeframe": str(record.get("timeframe")),
        "primary_data_provider_symbol": str(record.get("primary_data_provider_symbol")),
        "result_status": "screening_dry_run_result_materialized",
        "screening_mode": "deterministic_local_metadata_check_only",
        "screening_executed": True,
        "screening_result": "metadata_only_pass",
        "screening_reason": (
            "Required controlled subset metadata is present and all execution, "
            "network, mutation, validation, promotion, and trading permissions remain false."
        ),
        "validation_executed": False,
        "validation_result": "not_run",
        "execution_performed": False,
        "subprocess_called": False,
        "network_called": False,
        "run_research_called": False,
        "campaign_launcher_called": False,
        "external_data_called": False,
        "candidate_registry_mutated": False,
        "campaign_artifacts_mutated": False,
        "queue_mutated": False,
        "strategy_registered": False,
        "preset_mutated": False,
        "research_latest_mutated": False,
        "strategy_matrix_mutated": False,
        "candidate_promotion_allowed": False,
        "paper_activation_allowed": False,
        "shadow_activation_allowed": False,
        "live_activation_allowed": False,
        "broker_execution_allowed": False,
        "risk_authority_allowed": False,
        "expected_artifact_scope": "logs_only",
        "not_alpha_claim": True,
        "not_trade_signal": True,
    }


def build_screening_dry_run_executor_packet(
    input_path: Path = DEFAULT_INPUT_PATH,
) -> dict[str, Any]:
    packet = _require_packet(_read_json(input_path))
    records = _plan_records(packet)

    blockers: list[str] = []
    if not _input_packet_ready(packet):
        blockers.append("input_screening_dry_run_plan_not_ready")

    plan_ids = [str(record.get("screening_dry_run_plan_id")) for record in records]
    duplicate_plan_ids = sorted(
        plan_id
        for plan_id, count in Counter(plan_ids).items()
        if count > 1
    )
    for plan_id in duplicate_plan_ids:
        blockers.append(f"duplicate_screening_dry_run_plan_id:{plan_id}")

    for index, record in enumerate(records, start=1):
        blockers.extend(_plan_blockers(record, index=index))

    result_records = [
        _screening_result_record(record, index=index)
        for index, record in enumerate(records, start=1)
    ]

    region_counts = Counter(record["region"] for record in result_records)
    asset_class_counts = Counter(record["asset_class"] for record in result_records)
    preset_counts = Counter(record["behavior_preset_id"] for record in result_records)
    timeframe_counts = Counter(record["timeframe"] for record in result_records)
    screening_result_counts = Counter(record["screening_result"] for record in result_records)

    executor_ready = not blockers

    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "input_path": input_path.as_posix(),
        "authority_boundaries": {
            "screening_dry_run_executor_only": True,
            "metadata_only_screening": True,
            "not_alpha_authority": True,
            "not_trade_signal_generation": True,
            "not_data_fetching": True,
            "not_validation_execution": True,
            "not_campaign_launch": True,
            "not_queue_mutation": True,
            "not_candidate_promotion": True,
            "not_strategy_registration": True,
            "not_preset_mutation": True,
            "not_paper_shadow_live": True,
            "not_broker_execution": True,
            "not_risk_authority": True,
            "does_not_call_subprocess": True,
            "does_not_call_network": True,
            "does_not_call_external_data": True,
            "does_not_call_run_research": True,
            "does_not_call_campaign_launcher": True,
            "does_not_mutate_research_latest": True,
            "does_not_mutate_strategy_matrix": True,
        },
        "safety_invariants": {
            "writes_logs_only": True,
            "uses_network": False,
            "uses_external_data": False,
            "uses_subprocess": False,
            "uses_embeddings": False,
            "uses_vector_db": False,
            "uses_llm_authority": False,
            "mutates_campaigns": False,
            "mutates_candidates": False,
            "mutates_queues": False,
            "mutates_strategies": False,
            "mutates_presets": False,
            "mutates_frozen_contracts": False,
            "validation_forbidden": True,
            "paper_shadow_live_forbidden": True,
            "broker_risk_execution_forbidden": True,
        },
        "summary": {
            "screening_dry_run_executor_ready": executor_ready,
            "input_screening_plan_count": len(records),
            "screening_result_count": len(result_records),
            "blocker_count": len(blockers),
            "duplicate_screening_dry_run_plan_id_count": len(duplicate_plan_ids),
            "screening_executed": executor_ready,
            "screening_execution_mode": "metadata_only_local_dry_run",
            "validation_executed": False,
            "execution_performed": False,
            "subprocess_called": False,
            "network_called": False,
            "external_data_called": False,
            "run_research_called": False,
            "campaign_launcher_called": False,
            "safe_to_execute_research": False,
            "candidate_promotion_allowed": False,
            "paper_shadow_live_allowed": False,
            "final_recommendation": (
                "screening_dry_run_results_ready_for_operator_review_not_validation"
                if executor_ready
                else "screening_dry_run_executor_blocked"
            ),
            "operator_summary": (
                "Controlled screening dry-run results are materialized as deterministic "
                "metadata-only logs. No validation, subprocess, network, external data, "
                "run_research, campaign_launcher, paper/shadow/live, broker, or risk "
                "authority was invoked."
                if executor_ready
                else "Controlled screening dry-run executor has blockers and produced only blocked metadata."
            ),
            "region_counts": dict(sorted(region_counts.items())),
            "asset_class_counts": dict(sorted(asset_class_counts.items())),
            "preset_counts": dict(sorted(preset_counts.items())),
            "timeframe_counts": dict(sorted(timeframe_counts.items())),
            "screening_result_counts": dict(sorted(screening_result_counts.items())),
        },
        "blockers": blockers,
        "screening_dry_run_result_records": result_records,
    }


def render_operator_summary(packet: dict[str, Any]) -> str:
    summary = packet["summary"]
    lines = [
        "# QRE Controlled Subset Screening Dry-Run Executor",
        "",
        f"- {summary['operator_summary']}",
        "",
        "## Current Status",
        "",
        f"- screening_dry_run_executor_ready: {summary['screening_dry_run_executor_ready']}",
        f"- input_screening_plan_count: {summary['input_screening_plan_count']}",
        f"- screening_result_count: {summary['screening_result_count']}",
        f"- blocker_count: {summary['blocker_count']}",
        f"- screening_executed: {summary['screening_executed']}",
        f"- screening_execution_mode: {summary['screening_execution_mode']}",
        f"- validation_executed: {summary['validation_executed']}",
        f"- execution_performed: {summary['execution_performed']}",
        f"- subprocess_called: {summary['subprocess_called']}",
        f"- network_called: {summary['network_called']}",
        f"- external_data_called: {summary['external_data_called']}",
        f"- run_research_called: {summary['run_research_called']}",
        f"- campaign_launcher_called: {summary['campaign_launcher_called']}",
        f"- safe_to_execute_research: {summary['safe_to_execute_research']}",
        f"- candidate_promotion_allowed: {summary['candidate_promotion_allowed']}",
        f"- paper_shadow_live_allowed: {summary['paper_shadow_live_allowed']}",
        f"- final_recommendation: {summary['final_recommendation']}",
        "",
        "## Screening Result Counts",
        "",
    ]
    for key, value in summary["screening_result_counts"].items():
        lines.append(f"- {key}: {value}")

    lines.extend(["", "## Region Counts", ""])
    for key, value in summary["region_counts"].items():
        lines.append(f"- {key}: {value}")

    if packet["blockers"]:
        lines.extend(["", "## Blockers", ""])
        for blocker in packet["blockers"]:
            lines.append(f"- {blocker}")

    lines.extend(
        [
            "",
            "## Authority Boundary",
            "",
            "- This executor only performs deterministic metadata-only screening dry-runs.",
            "- It does not execute validation, subprocess, network, external data, run_research, campaign_launcher, paper/shadow/live, broker execution, risk changes, queue mutation, candidate promotion, strategy registration, or preset mutation.",
        ]
    )
    return "\n".join(lines) + "\n"


def write_outputs(packet: dict[str, Any], output_dir: Path = DEFAULT_OUTPUT_DIR) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    latest_path = output_dir / "latest.json"
    summary_path = output_dir / "operator_summary.md"

    latest_path.write_text(json.dumps(packet, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summary_path.write_text(render_operator_summary(packet), encoding="utf-8")

    return {
        "latest": latest_path.as_posix(),
        "operator_summary": summary_path.as_posix(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Execute deterministic metadata-only screening dry-run results."
    )
    parser.add_argument("--input", default=DEFAULT_INPUT_PATH.as_posix())
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)

    packet = build_screening_dry_run_executor_packet(Path(args.input))
    if args.write:
        packet["_artifact_paths"] = write_outputs(packet)

    print(json.dumps(packet, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())