"""Screening dry-run plan for controlled subset local runner envelopes.

This module consumes local runner harness envelopes and materializes screening
dry-run plan records. It deliberately does not run screening, validation,
run_research, campaign_launcher, subprocesses, network, broker execution,
paper/shadow/live, or mutate research_latest.json / strategy_matrix.csv.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Final


SCHEMA_VERSION: Final[str] = "1.0"
REPORT_KIND: Final[str] = "qre_controlled_subset_screening_dry_run_plan"

DEFAULT_INPUT_PATH: Final[Path] = Path(
    "logs/qre_controlled_subset_local_runner_harness/latest.json"
)
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_controlled_subset_screening_dry_run_plan")

FORBIDDEN_ASSET_CLASSES: Final[set[str]] = {"crypto", "crypto_legacy"}
REQUIRED_ENVELOPE_FIELDS: Final[tuple[str, ...]] = (
    "local_runner_envelope_id",
    "runner_dry_run_intent_id",
    "candidate_plan_id",
    "instrument_symbol",
    "asset_class",
    "region",
    "behavior_preset_id",
    "timeframe",
    "primary_data_provider_symbol",
    "envelope_status",
)


class ScreeningDryRunPlanError(RuntimeError):
    """Raised when screening dry-run plan input cannot be read."""


def _read_json(path: Path) -> Any:
    if not path.exists():
        raise ScreeningDryRunPlanError(
            f"local runner harness packet does not exist: {path.as_posix()}"
        )
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _require_packet(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ScreeningDryRunPlanError("local runner harness input must be a JSON object")
    return payload


def _envelopes(payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw_envelopes = payload.get("local_runner_envelopes")
    if not isinstance(raw_envelopes, list):
        raise ScreeningDryRunPlanError("local_runner_envelopes must be a list")
    envelopes: list[dict[str, Any]] = []
    for index, envelope in enumerate(raw_envelopes, start=1):
        if not isinstance(envelope, dict):
            raise ScreeningDryRunPlanError(f"local_runner_envelopes[{index}] is not an object")
        envelopes.append(envelope)
    return envelopes


def _input_packet_ready(payload: dict[str, Any]) -> bool:
    summary = payload.get("summary")
    if not isinstance(summary, dict):
        return False
    return (
        payload.get("report_kind") == "qre_controlled_subset_local_runner_harness"
        and summary.get("local_runner_harness_ready") is True
        and int(summary.get("blocker_count") or 0) == 0
        and summary.get("execution_performed") is False
        and summary.get("subprocess_called") is False
        and summary.get("network_called") is False
        and summary.get("run_research_called") is False
        and summary.get("campaign_launcher_called") is False
        and summary.get("screening_called") is False
        and summary.get("validation_called") is False
        and summary.get("safe_to_execute_research") is False
    )


def _envelope_blockers(envelope: dict[str, Any], *, index: int) -> list[str]:
    blockers: list[str] = []

    for field in REQUIRED_ENVELOPE_FIELDS:
        if envelope.get(field) in (None, "", []):
            blockers.append(f"missing_required_field:{field}")

    symbol = str(envelope.get("instrument_symbol") or "")
    asset_class = str(envelope.get("asset_class") or "").lower()

    if asset_class in FORBIDDEN_ASSET_CLASSES:
        blockers.append(f"forbidden_asset_class:{asset_class}")
    if "-USD" in symbol.upper() or symbol.upper() in {"BTC", "ETH", "SOL", "DOGE", "XRP"}:
        blockers.append("crypto_symbol_marker_detected")

    if str(envelope.get("envelope_status")) != "local_harness_envelope_materialized_not_executed":
        blockers.append("envelope_status_not_materialized_not_executed")

    for field in (
        "execution_performed",
        "subprocess_called",
        "network_called",
        "run_research_called",
        "campaign_launcher_called",
        "screening_called",
        "validation_called",
        "candidate_registry_mutated",
        "campaign_artifacts_mutated",
        "queue_mutated",
        "strategy_registered",
        "preset_mutated",
        "research_latest_mutated",
        "strategy_matrix_mutated",
        "paper_activation_allowed",
        "shadow_activation_allowed",
        "live_activation_allowed",
        "broker_execution_allowed",
        "risk_authority_allowed",
    ):
        if bool(envelope.get(field, False)):
            blockers.append(f"{field}_true")

    return [f"envelope_{index}:{blocker}" for blocker in blockers]


def _screening_plan_record(envelope: dict[str, Any], *, index: int) -> dict[str, Any]:
    envelope_id = str(envelope.get("local_runner_envelope_id"))
    return {
        "screening_dry_run_plan_id": f"screening-dryrun-plan::{envelope_id}",
        "plan_sequence_number": index,
        "local_runner_envelope_id": envelope_id,
        "runner_dry_run_intent_id": str(envelope.get("runner_dry_run_intent_id")),
        "candidate_plan_id": str(envelope.get("candidate_plan_id")),
        "instrument_symbol": str(envelope.get("instrument_symbol")),
        "asset_class": str(envelope.get("asset_class")),
        "region": str(envelope.get("region")),
        "behavior_preset_id": str(envelope.get("behavior_preset_id")),
        "timeframe": str(envelope.get("timeframe")),
        "primary_data_provider_symbol": str(envelope.get("primary_data_provider_symbol")),
        "plan_status": "screening_dry_run_planned_not_executed",
        "screening_mode": "local_dry_run_no_subprocess_no_network_no_mutation",
        "expected_artifact_scope": "logs_only",
        "not_alpha_claim": True,
        "screening_executed": False,
        "validation_executed": False,
        "execution_performed": False,
        "subprocess_called": False,
        "network_called": False,
        "run_research_called": False,
        "campaign_launcher_called": False,
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
    }


def build_screening_dry_run_plan(input_path: Path = DEFAULT_INPUT_PATH) -> dict[str, Any]:
    packet = _require_packet(_read_json(input_path))
    envelopes = _envelopes(packet)

    blockers: list[str] = []
    if not _input_packet_ready(packet):
        blockers.append("input_local_runner_harness_packet_not_ready")

    envelope_ids = [str(envelope.get("local_runner_envelope_id")) for envelope in envelopes]
    duplicate_envelope_ids = sorted(
        envelope_id
        for envelope_id, count in Counter(envelope_ids).items()
        if count > 1
    )
    for envelope_id in duplicate_envelope_ids:
        blockers.append(f"duplicate_local_runner_envelope_id:{envelope_id}")

    for index, envelope in enumerate(envelopes, start=1):
        blockers.extend(_envelope_blockers(envelope, index=index))

    plan_records = [
        _screening_plan_record(envelope, index=index)
        for index, envelope in enumerate(envelopes, start=1)
    ]

    region_counts = Counter(record["region"] for record in plan_records)
    asset_class_counts = Counter(record["asset_class"] for record in plan_records)
    preset_counts = Counter(record["behavior_preset_id"] for record in plan_records)
    timeframe_counts = Counter(record["timeframe"] for record in plan_records)

    plan_ready = not blockers

    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "input_path": input_path.as_posix(),
        "authority_boundaries": {
            "screening_plan_only": True,
            "not_alpha_authority": True,
            "not_trade_signal_generation": True,
            "not_data_fetching": True,
            "not_screening_execution": True,
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
            "screening_validation_forbidden": True,
            "paper_shadow_live_forbidden": True,
            "broker_risk_execution_forbidden": True,
        },
        "summary": {
            "screening_dry_run_plan_ready": plan_ready,
            "envelope_count": len(envelopes),
            "screening_plan_count": len(plan_records),
            "blocker_count": len(blockers),
            "duplicate_local_runner_envelope_id_count": len(duplicate_envelope_ids),
            "screening_executed": False,
            "validation_executed": False,
            "execution_performed": False,
            "subprocess_called": False,
            "network_called": False,
            "run_research_called": False,
            "campaign_launcher_called": False,
            "safe_to_execute_research": False,
            "final_recommendation": (
                "screening_dry_run_plan_ready_not_executed"
                if plan_ready
                else "screening_dry_run_plan_blocked"
            ),
            "operator_summary": (
                "Controlled screening dry-run plan is materialized as logs-only records. "
                "No screening, validation, subprocess, network, run_research, "
                "campaign_launcher, paper/shadow/live, broker, or risk authority was invoked."
                if plan_ready
                else "Controlled screening dry-run plan has blockers and must not be used."
            ),
            "region_counts": dict(sorted(region_counts.items())),
            "asset_class_counts": dict(sorted(asset_class_counts.items())),
            "preset_counts": dict(sorted(preset_counts.items())),
            "timeframe_counts": dict(sorted(timeframe_counts.items())),
        },
        "blockers": blockers,
        "screening_dry_run_plan_records": plan_records,
    }


def render_operator_summary(packet: dict[str, Any]) -> str:
    summary = packet["summary"]
    lines = [
        "# QRE Controlled Subset Screening Dry-Run Plan",
        "",
        f"- {summary['operator_summary']}",
        "",
        "## Current Status",
        "",
        f"- screening_dry_run_plan_ready: {summary['screening_dry_run_plan_ready']}",
        f"- envelope_count: {summary['envelope_count']}",
        f"- screening_plan_count: {summary['screening_plan_count']}",
        f"- blocker_count: {summary['blocker_count']}",
        f"- screening_executed: {summary['screening_executed']}",
        f"- validation_executed: {summary['validation_executed']}",
        f"- execution_performed: {summary['execution_performed']}",
        f"- subprocess_called: {summary['subprocess_called']}",
        f"- network_called: {summary['network_called']}",
        f"- run_research_called: {summary['run_research_called']}",
        f"- campaign_launcher_called: {summary['campaign_launcher_called']}",
        f"- safe_to_execute_research: {summary['safe_to_execute_research']}",
        f"- final_recommendation: {summary['final_recommendation']}",
        "",
        "## Region Counts",
        "",
    ]
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
            "- This module only materializes screening dry-run plan records.",
            "- It does not execute screening, validation, subprocess, network, run_research, campaign_launcher, paper/shadow/live, broker execution, risk changes, queue mutation, candidate promotion, strategy registration, or preset mutation.",
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
        description="Build screening dry-run plan from controlled subset local runner envelopes."
    )
    parser.add_argument("--input", default=DEFAULT_INPUT_PATH.as_posix())
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)

    packet = build_screening_dry_run_plan(Path(args.input))
    if args.write:
        packet["_artifact_paths"] = write_outputs(packet)

    print(json.dumps(packet, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())