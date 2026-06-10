"""Dry-run candidate planner for a controlled-discovery subset.

This module turns a validated controlled-discovery subset adapter packet into
candidate-plan records. It is intentionally planner-only: it does not run
screening, validation, campaigns, broker execution, paper/shadow/live, or mutate
research_latest.json / strategy_matrix.csv.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Final


SCHEMA_VERSION: Final[str] = "1.0"
REPORT_KIND: Final[str] = "qre_controlled_subset_candidate_plan"

DEFAULT_INPUT_PATH: Final[Path] = Path("logs/qre_controlled_discovery_subset_adapter/latest.json")
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_controlled_subset_candidate_plan")

FORBIDDEN_ASSET_CLASSES: Final[set[str]] = {"crypto", "crypto_legacy"}
REQUIRED_PACKET_FIELDS: Final[tuple[str, ...]] = (
    "report_kind",
    "summary",
    "rows",
)
REQUIRED_ROW_FIELDS: Final[tuple[str, ...]] = (
    "subset_sequence_number",
    "instrument_symbol",
    "asset_class",
    "region",
    "behavior_preset_id",
    "timeframe",
    "classification",
    "mapping_status",
    "source_identity_status",
)


class CandidatePlanError(RuntimeError):
    """Raised when a subset packet cannot be converted into a safe dry-run plan."""


def _read_json(path: Path) -> Any:
    if not path.exists():
        raise CandidatePlanError(f"input packet does not exist: {path.as_posix()}")
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _require_packet(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise CandidatePlanError("input packet must be a JSON object")
    missing = [
        field
        for field in REQUIRED_PACKET_FIELDS
        if payload.get(field) in (None, "", [])
    ]
    if missing:
        raise CandidatePlanError("input packet missing required fields: " + ",".join(missing))
    return payload


def _as_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows_payload = payload.get("rows")
    if not isinstance(rows_payload, list):
        raise CandidatePlanError("input packet rows must be a list")
    rows: list[dict[str, Any]] = []
    for index, row in enumerate(rows_payload, start=1):
        if not isinstance(row, dict):
            raise CandidatePlanError(f"input packet row {index} is not an object")
        rows.append(row)
    return rows


def _packet_is_ready(payload: dict[str, Any]) -> bool:
    summary = payload.get("summary")
    if not isinstance(summary, dict):
        return False
    return (
        summary.get("subset_adapter_ready") is True
        and int(summary.get("validation_blocker_count") or 0) == 0
        and summary.get("safe_to_execute_research") is False
    )


def _row_blockers(row: dict[str, Any], *, index: int) -> list[str]:
    blockers: list[str] = []
    for field in REQUIRED_ROW_FIELDS:
        if row.get(field) in (None, "", []):
            blockers.append(f"missing_required_field:{field}")

    asset_class = str(row.get("asset_class") or "").lower()
    symbol = str(row.get("instrument_symbol") or "")

    if asset_class in FORBIDDEN_ASSET_CLASSES:
        blockers.append(f"forbidden_asset_class:{asset_class}")
    if "-USD" in symbol.upper() or symbol.upper() in {"BTC", "ETH", "SOL", "DOGE", "XRP"}:
        blockers.append("crypto_symbol_marker_detected")

    if str(row.get("classification")) != "executable":
        blockers.append("classification_not_executable")
    if str(row.get("mapping_status")) != "ready":
        blockers.append("mapping_status_not_ready")
    if str(row.get("source_identity_status")) != "provider_symbol_verified":
        blockers.append("source_identity_not_provider_verified")

    for field in (
        "execution_allowed",
        "campaign_launch_allowed",
        "paper_activation_allowed",
        "shadow_activation_allowed",
        "live_activation_allowed",
    ):
        if bool(row.get(field, False)):
            blockers.append(f"{field}_true")

    return [f"row_{index}:{blocker}" for blocker in blockers]


def _candidate_id(row: dict[str, Any]) -> str:
    symbol = str(row.get("instrument_symbol"))
    preset = str(row.get("behavior_preset_id"))
    timeframe = str(row.get("timeframe"))
    return f"qre-dryrun::{symbol}::{preset}::{timeframe}"


def _candidate_record(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "candidate_plan_id": _candidate_id(row),
        "subset_sequence_number": row.get("subset_sequence_number"),
        "source_sequence_number": row.get("source_sequence_number"),
        "instrument_symbol": str(row.get("instrument_symbol")),
        "asset_class": str(row.get("asset_class")),
        "region": str(row.get("region")),
        "behavior_preset_id": str(row.get("behavior_preset_id")),
        "timeframe": str(row.get("timeframe")),
        "classification": str(row.get("classification")),
        "mapping_status": str(row.get("mapping_status")),
        "source_identity_status": str(row.get("source_identity_status")),
        "primary_data_provider_symbol": row.get("primary_data_provider_symbol"),
        "provider_symbol_status": row.get("provider_symbol_status"),
        "plan_status": "planned_not_executed",
        "not_alpha_claim": True,
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


def build_candidate_plan(input_path: Path = DEFAULT_INPUT_PATH) -> dict[str, Any]:
    packet = _require_packet(_read_json(input_path))
    rows = _as_rows(packet)

    validation_blockers: list[str] = []
    if packet.get("report_kind") != "qre_controlled_discovery_subset_adapter":
        validation_blockers.append("input_report_kind_not_subset_adapter")
    if not _packet_is_ready(packet):
        validation_blockers.append("input_subset_adapter_not_ready_for_operator_review")

    for index, row in enumerate(rows, start=1):
        validation_blockers.extend(_row_blockers(row, index=index))

    candidate_records = [_candidate_record(row) for row in rows]
    candidate_ids = [str(row["candidate_plan_id"]) for row in candidate_records]
    duplicate_candidate_ids = sorted(
        candidate_id
        for candidate_id, count in Counter(candidate_ids).items()
        if count > 1
    )
    for candidate_id in duplicate_candidate_ids:
        validation_blockers.append(f"duplicate_candidate_plan_id:{candidate_id}")

    region_counts = Counter(str(row["region"]) for row in candidate_records)
    asset_class_counts = Counter(str(row["asset_class"]) for row in candidate_records)
    preset_counts = Counter(str(row["behavior_preset_id"]) for row in candidate_records)
    timeframe_counts = Counter(str(row["timeframe"]) for row in candidate_records)

    plan_ready = not validation_blockers

    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "input_path": input_path.as_posix(),
        "authority_boundaries": {
            "planner_is_dry_run_only": True,
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
            "candidate_plan_ready": plan_ready,
            "input_subset_row_count": len(rows),
            "candidate_plan_count": len(candidate_records),
            "validation_blocker_count": len(validation_blockers),
            "duplicate_candidate_plan_id_count": len(duplicate_candidate_ids),
            "safe_to_execute_research": False,
            "screening_allowed": False,
            "validation_allowed": False,
            "final_recommendation": (
                "candidate_plan_ready_for_operator_review_not_execution"
                if plan_ready
                else "candidate_plan_blocked_for_operator_review"
            ),
            "operator_summary": (
                "Controlled subset candidate plan is a dry-run, logs-only planning artifact. "
                "It does not authorize screening, validation, campaigns, paper/shadow/live, "
                "broker execution, candidate promotion, or strategy/preset mutation."
                if plan_ready
                else "Controlled subset candidate plan has blockers and must not be used."
            ),
            "region_counts": dict(sorted(region_counts.items())),
            "asset_class_counts": dict(sorted(asset_class_counts.items())),
            "preset_counts": dict(sorted(preset_counts.items())),
            "timeframe_counts": dict(sorted(timeframe_counts.items())),
        },
        "validation_blockers": validation_blockers,
        "candidate_plan_records": candidate_records,
    }


def render_operator_summary(packet: dict[str, Any]) -> str:
    summary = packet["summary"]
    lines = [
        "# QRE Controlled Subset Candidate Plan",
        "",
        f"- {summary['operator_summary']}",
        "",
        "## Current Status",
        "",
        f"- candidate_plan_ready: {summary['candidate_plan_ready']}",
        f"- input_subset_row_count: {summary['input_subset_row_count']}",
        f"- candidate_plan_count: {summary['candidate_plan_count']}",
        f"- validation_blocker_count: {summary['validation_blocker_count']}",
        f"- duplicate_candidate_plan_id_count: {summary['duplicate_candidate_plan_id_count']}",
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

    lines.extend(["", "## Preset Counts", ""])
    for key, value in summary["preset_counts"].items():
        lines.append(f"- {key}: {value}")

    if packet["validation_blockers"]:
        lines.extend(["", "## Validation Blockers", ""])
        for blocker in packet["validation_blockers"]:
            lines.append(f"- {blocker}")

    lines.extend(
        [
            "",
            "## Authority Boundary",
            "",
            "- This plan is dry-run operator-review context only.",
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
        description="Build a dry-run candidate plan from a controlled-discovery subset packet."
    )
    parser.add_argument("--input", default=DEFAULT_INPUT_PATH.as_posix())
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)

    packet = build_candidate_plan(Path(args.input))
    if args.write:
        packet["_artifact_paths"] = write_outputs(packet)

    print(json.dumps(packet, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())