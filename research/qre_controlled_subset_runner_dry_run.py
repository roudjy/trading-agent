"""Runner dry-run intent adapter for controlled subset candidates.

This module converts a candidate feasibility report into runner dry-run intent
records. It deliberately does not call run_research, campaign_launcher,
screening, validation, broker execution, paper/shadow/live, or mutate
research_latest.json / strategy_matrix.csv.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Final


SCHEMA_VERSION: Final[str] = "1.0"
REPORT_KIND: Final[str] = "qre_controlled_subset_runner_dry_run"

DEFAULT_INPUT_PATH: Final[Path] = Path("logs/qre_controlled_subset_candidate_feasibility/latest.json")
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_controlled_subset_runner_dry_run")


class RunnerDryRunError(RuntimeError):
    """Raised when runner dry-run input cannot be read."""


def _read_json(path: Path) -> Any:
    if not path.exists():
        raise RunnerDryRunError(f"feasibility report does not exist: {path.as_posix()}")
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _require_packet(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise RunnerDryRunError("feasibility input must be a JSON object")
    return payload


def _records(payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw_records = payload.get("feasibility_records")
    if not isinstance(raw_records, list):
        raise RunnerDryRunError("feasibility_records must be a list")
    records: list[dict[str, Any]] = []
    for index, record in enumerate(raw_records, start=1):
        if not isinstance(record, dict):
            raise RunnerDryRunError(f"feasibility_records[{index}] is not an object")
        records.append(record)
    return records


def _feasibility_ready(payload: dict[str, Any]) -> bool:
    summary = payload.get("summary")
    if not isinstance(summary, dict):
        return False
    return (
        payload.get("report_kind") == "qre_controlled_subset_candidate_feasibility"
        and summary.get("feasibility_report_ready") is True
        and summary.get("runner_design_ready") is True
        and int(summary.get("hard_blocker_count") or 0) == 0
        and summary.get("safe_to_execute_research") is False
        and summary.get("screening_allowed") is False
        and summary.get("validation_allowed") is False
    )


def _intent_blockers(record: dict[str, Any], *, index: int) -> list[str]:
    blockers: list[str] = []

    for field in (
        "candidate_plan_id",
        "instrument_symbol",
        "asset_class",
        "region",
        "behavior_preset_id",
        "timeframe",
        "primary_data_provider_symbol",
        "feasibility_status",
    ):
        if record.get(field) in (None, "", []):
            blockers.append(f"missing_required_field:{field}")

    if record.get("safe_for_runner_dry_run_design") is not True:
        blockers.append("not_safe_for_runner_dry_run_design")
    if record.get("required_runner_inputs_present") is not True:
        blockers.append("required_runner_inputs_not_present")

    if bool(record.get("screening_allowed", False)):
        blockers.append("screening_allowed_true")
    if bool(record.get("validation_allowed", False)):
        blockers.append("validation_allowed_true")
    if bool(record.get("execution_allowed", False)):
        blockers.append("execution_allowed_true")
    if bool(record.get("campaign_launch_allowed", False)):
        blockers.append("campaign_launch_allowed_true")
    if bool(record.get("paper_activation_allowed", False)):
        blockers.append("paper_activation_allowed_true")
    if bool(record.get("shadow_activation_allowed", False)):
        blockers.append("shadow_activation_allowed_true")
    if bool(record.get("live_activation_allowed", False)):
        blockers.append("live_activation_allowed_true")

    return [f"record_{index}:{blocker}" for blocker in blockers]


def _runner_intent(record: dict[str, Any]) -> dict[str, Any]:
    candidate_plan_id = str(record.get("candidate_plan_id"))
    return {
        "runner_dry_run_intent_id": f"runner-dryrun::{candidate_plan_id}",
        "candidate_plan_id": candidate_plan_id,
        "instrument_symbol": str(record.get("instrument_symbol")),
        "asset_class": str(record.get("asset_class")),
        "region": str(record.get("region")),
        "behavior_preset_id": str(record.get("behavior_preset_id")),
        "timeframe": str(record.get("timeframe")),
        "primary_data_provider_symbol": str(record.get("primary_data_provider_symbol")),
        "intent_status": "runner_dry_run_intent_materialized_not_executed",
        "expected_runner_mode": "dry_run_no_subprocess_no_mutation",
        "not_alpha_claim": True,
        "run_research_called": False,
        "campaign_launcher_called": False,
        "screening_called": False,
        "validation_called": False,
        "network_allowed": False,
        "external_data_allowed": False,
        "screening_allowed": False,
        "validation_allowed": False,
        "execution_allowed": False,
        "campaign_launch_allowed": False,
        "candidate_promotion_allowed": False,
        "paper_activation_allowed": False,
        "shadow_activation_allowed": False,
        "live_activation_allowed": False,
        "expected_artifact_scope": "logs_only",
    }


def build_runner_dry_run_packet(input_path: Path = DEFAULT_INPUT_PATH) -> dict[str, Any]:
    packet = _require_packet(_read_json(input_path))
    records = _records(packet)

    blockers: list[str] = []
    if not _feasibility_ready(packet):
        blockers.append("input_feasibility_report_not_ready")

    for index, record in enumerate(records, start=1):
        blockers.extend(_intent_blockers(record, index=index))

    intents = [_runner_intent(record) for record in records]
    packet_ready = not blockers

    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "input_path": input_path.as_posix(),
        "authority_boundaries": {
            "runner_adapter_is_dry_run_only": True,
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
            "does_not_call_run_research": True,
            "does_not_call_campaign_launcher": True,
            "does_not_mutate_research_latest": True,
            "does_not_mutate_strategy_matrix": True,
        },
        "safety_invariants": {
            "writes_logs_only": True,
            "uses_network": False,
            "uses_external_data": False,
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
            "runner_dry_run_packet_ready": packet_ready,
            "runner_dry_run_intent_count": len(intents),
            "blocker_count": len(blockers),
            "safe_to_execute_research": False,
            "screening_allowed": False,
            "validation_allowed": False,
            "run_research_called": False,
            "campaign_launcher_called": False,
            "final_recommendation": (
                "runner_dry_run_intents_ready_not_executed"
                if packet_ready
                else "runner_dry_run_intents_blocked"
            ),
            "operator_summary": (
                "Runner dry-run intents are materialized as logs-only records. "
                "No runner, screening, validation, campaign launcher, network, "
                "paper/shadow/live, broker, or risk authority was invoked."
                if packet_ready
                else "Runner dry-run intents have blockers and must not be used."
            ),
        },
        "blockers": blockers,
        "runner_dry_run_intents": intents,
    }


def render_operator_summary(packet: dict[str, Any]) -> str:
    summary = packet["summary"]
    lines = [
        "# QRE Controlled Subset Runner Dry-Run",
        "",
        f"- {summary['operator_summary']}",
        "",
        "## Current Status",
        "",
        f"- runner_dry_run_packet_ready: {summary['runner_dry_run_packet_ready']}",
        f"- runner_dry_run_intent_count: {summary['runner_dry_run_intent_count']}",
        f"- blocker_count: {summary['blocker_count']}",
        f"- safe_to_execute_research: {summary['safe_to_execute_research']}",
        f"- screening_allowed: {summary['screening_allowed']}",
        f"- validation_allowed: {summary['validation_allowed']}",
        f"- run_research_called: {summary['run_research_called']}",
        f"- campaign_launcher_called: {summary['campaign_launcher_called']}",
        f"- final_recommendation: {summary['final_recommendation']}",
    ]

    if packet["blockers"]:
        lines.extend(["", "## Blockers", ""])
        for blocker in packet["blockers"]:
            lines.append(f"- {blocker}")

    lines.extend(
        [
            "",
            "## Authority Boundary",
            "",
            "- This is a runner dry-run intent packet only.",
            "- It does not call run_research, campaign_launcher, screening, validation, paper/shadow/live, broker execution, risk changes, queue mutation, candidate promotion, strategy registration, or preset mutation.",
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
        description="Build runner dry-run intent packet from controlled subset feasibility."
    )
    parser.add_argument("--input", default=DEFAULT_INPUT_PATH.as_posix())
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)

    packet = build_runner_dry_run_packet(Path(args.input))
    if args.write:
        packet["_artifact_paths"] = write_outputs(packet)

    print(json.dumps(packet, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())