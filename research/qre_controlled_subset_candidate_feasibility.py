"""Feasibility report for the controlled subset candidate plan.

This module validates whether a dry-run candidate plan has enough explicit
metadata to design a bounded runner dry-run. It does not execute screening,
validation, campaigns, paper/shadow/live, broker execution, or mutate
research_latest.json / strategy_matrix.csv.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Final


SCHEMA_VERSION: Final[str] = "1.0"
REPORT_KIND: Final[str] = "qre_controlled_subset_candidate_feasibility"

DEFAULT_INPUT_PATH: Final[Path] = Path("logs/qre_controlled_subset_candidate_plan/latest.json")
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_controlled_subset_candidate_feasibility")

FORBIDDEN_ASSET_CLASSES: Final[set[str]] = {"crypto", "crypto_legacy"}
REQUIRED_RECORD_FIELDS: Final[tuple[str, ...]] = (
    "candidate_plan_id",
    "instrument_symbol",
    "asset_class",
    "region",
    "behavior_preset_id",
    "timeframe",
    "classification",
    "mapping_status",
    "source_identity_status",
    "primary_data_provider_symbol",
    "plan_status",
)


class CandidateFeasibilityError(RuntimeError):
    """Raised when candidate feasibility input cannot be read."""


def _read_json(path: Path) -> Any:
    if not path.exists():
        raise CandidateFeasibilityError(f"candidate plan does not exist: {path.as_posix()}")
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _require_packet(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise CandidateFeasibilityError("candidate plan input must be a JSON object")
    return payload


def _records(payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw_records = payload.get("candidate_plan_records")
    if not isinstance(raw_records, list):
        raise CandidateFeasibilityError("candidate_plan_records must be a list")
    records: list[dict[str, Any]] = []
    for index, record in enumerate(raw_records, start=1):
        if not isinstance(record, dict):
            raise CandidateFeasibilityError(f"candidate_plan_records[{index}] is not an object")
        records.append(record)
    return records


def _candidate_plan_ready(payload: dict[str, Any]) -> bool:
    summary = payload.get("summary")
    if not isinstance(summary, dict):
        return False
    return (
        payload.get("report_kind") == "qre_controlled_subset_candidate_plan"
        and summary.get("candidate_plan_ready") is True
        and int(summary.get("validation_blocker_count") or 0) == 0
        and summary.get("safe_to_execute_research") is False
        and summary.get("screening_allowed") is False
        and summary.get("validation_allowed") is False
    )


def _record_blockers(record: dict[str, Any], *, index: int) -> list[str]:
    blockers: list[str] = []

    for field in REQUIRED_RECORD_FIELDS:
        if record.get(field) in (None, "", []):
            blockers.append(f"missing_required_field:{field}")

    symbol = str(record.get("instrument_symbol") or "")
    asset_class = str(record.get("asset_class") or "").lower()

    if asset_class in FORBIDDEN_ASSET_CLASSES:
        blockers.append(f"forbidden_asset_class:{asset_class}")
    if "-USD" in symbol.upper() or symbol.upper() in {"BTC", "ETH", "SOL", "DOGE", "XRP"}:
        blockers.append("crypto_symbol_marker_detected")

    if str(record.get("classification")) != "executable":
        blockers.append("classification_not_executable")
    if str(record.get("mapping_status")) != "ready":
        blockers.append("mapping_status_not_ready")
    if str(record.get("source_identity_status")) != "provider_symbol_verified":
        blockers.append("source_identity_not_provider_verified")
    if str(record.get("plan_status")) != "planned_not_executed":
        blockers.append("plan_status_not_planned_not_executed")

    for field in (
        "screening_allowed",
        "validation_allowed",
        "execution_allowed",
        "campaign_launch_allowed",
        "candidate_promotion_allowed",
        "paper_activation_allowed",
        "shadow_activation_allowed",
        "live_activation_allowed",
    ):
        if bool(record.get(field, False)):
            blockers.append(f"{field}_true")

    return [f"record_{index}:{blocker}" for blocker in blockers]


def _feasibility_record(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "candidate_plan_id": str(record.get("candidate_plan_id")),
        "instrument_symbol": str(record.get("instrument_symbol")),
        "asset_class": str(record.get("asset_class")),
        "region": str(record.get("region")),
        "behavior_preset_id": str(record.get("behavior_preset_id")),
        "timeframe": str(record.get("timeframe")),
        "primary_data_provider_symbol": str(record.get("primary_data_provider_symbol")),
        "source_identity_status": str(record.get("source_identity_status")),
        "provider_symbol_status": record.get("provider_symbol_status"),
        "feasibility_status": "runner_dry_run_design_ready",
        "required_runner_inputs_present": True,
        "missing_runner_inputs": [],
        "safe_for_runner_dry_run_design": True,
        "safe_to_execute_research": False,
        "screening_allowed": False,
        "validation_allowed": False,
        "execution_allowed": False,
        "campaign_launch_allowed": False,
        "paper_activation_allowed": False,
        "shadow_activation_allowed": False,
        "live_activation_allowed": False,
    }


def build_feasibility_report(input_path: Path = DEFAULT_INPUT_PATH) -> dict[str, Any]:
    packet = _require_packet(_read_json(input_path))
    records = _records(packet)

    hard_blockers: list[str] = []
    if not _candidate_plan_ready(packet):
        hard_blockers.append("input_candidate_plan_not_ready")

    candidate_ids = [str(record.get("candidate_plan_id")) for record in records]
    duplicate_ids = sorted(
        candidate_id
        for candidate_id, count in Counter(candidate_ids).items()
        if count > 1
    )
    for candidate_id in duplicate_ids:
        hard_blockers.append(f"duplicate_candidate_plan_id:{candidate_id}")

    for index, record in enumerate(records, start=1):
        hard_blockers.extend(_record_blockers(record, index=index))

    feasibility_records = [_feasibility_record(record) for record in records]
    region_counts = Counter(record["region"] for record in feasibility_records)
    asset_class_counts = Counter(record["asset_class"] for record in feasibility_records)
    preset_counts = Counter(record["behavior_preset_id"] for record in feasibility_records)
    timeframe_counts = Counter(record["timeframe"] for record in feasibility_records)

    report_ready = not hard_blockers

    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "input_path": input_path.as_posix(),
        "authority_boundaries": {
            "feasibility_report_only": True,
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
            "does_not_mutate_research_latest": True,
            "does_not_mutate_strategy_matrix": True,
        },
        "safety_invariants": {
            "read_only_input": True,
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
            "feasibility_report_ready": report_ready,
            "candidate_count": len(feasibility_records),
            "hard_blocker_count": len(hard_blockers),
            "duplicate_candidate_plan_id_count": len(duplicate_ids),
            "runner_design_ready": report_ready,
            "safe_to_execute_research": False,
            "screening_allowed": False,
            "validation_allowed": False,
            "final_recommendation": (
                "runner_dry_run_design_ready_not_execution"
                if report_ready
                else "runner_dry_run_design_blocked"
            ),
            "operator_summary": (
                "Controlled subset candidates have complete dry-run runner-design metadata. "
                "This report does not authorize screening, validation, campaigns, "
                "paper/shadow/live, broker execution, or risk changes."
                if report_ready
                else "Controlled subset candidate feasibility has hard blockers."
            ),
            "region_counts": dict(sorted(region_counts.items())),
            "asset_class_counts": dict(sorted(asset_class_counts.items())),
            "preset_counts": dict(sorted(preset_counts.items())),
            "timeframe_counts": dict(sorted(timeframe_counts.items())),
        },
        "hard_blockers": hard_blockers,
        "feasibility_records": feasibility_records,
    }


def render_operator_summary(packet: dict[str, Any]) -> str:
    summary = packet["summary"]
    lines = [
        "# QRE Controlled Subset Candidate Feasibility",
        "",
        f"- {summary['operator_summary']}",
        "",
        "## Current Status",
        "",
        f"- feasibility_report_ready: {summary['feasibility_report_ready']}",
        f"- candidate_count: {summary['candidate_count']}",
        f"- hard_blocker_count: {summary['hard_blocker_count']}",
        f"- duplicate_candidate_plan_id_count: {summary['duplicate_candidate_plan_id_count']}",
        f"- runner_design_ready: {summary['runner_design_ready']}",
        f"- safe_to_execute_research: {summary['safe_to_execute_research']}",
        f"- screening_allowed: {summary['screening_allowed']}",
        f"- validation_allowed: {summary['validation_allowed']}",
        f"- final_recommendation: {summary['final_recommendation']}",
        "",
        "## Region Counts",
        "",
    ]
    for key, value in summary["region_counts"].items():
        lines.append(f"- {key}: {value}")

    if packet["hard_blockers"]:
        lines.extend(["", "## Hard Blockers", ""])
        for blocker in packet["hard_blockers"]:
            lines.append(f"- {blocker}")

    lines.extend(
        [
            "",
            "## Authority Boundary",
            "",
            "- This report is feasibility context only.",
            "- It does not run screening, validation, campaigns, paper/shadow/live, broker execution, risk changes, queue mutation, candidate promotion, strategy registration, or preset mutation.",
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
        description="Build controlled subset candidate feasibility report."
    )
    parser.add_argument("--input", default=DEFAULT_INPUT_PATH.as_posix())
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)

    packet = build_feasibility_report(Path(args.input))
    if args.write:
        packet["_artifact_paths"] = write_outputs(packet)

    print(json.dumps(packet, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())