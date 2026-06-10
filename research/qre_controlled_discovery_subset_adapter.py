"""Read-only adapter for a bounded controlled-discovery executable subset.

This module converts a previously selected executable discovery-grid subset
into an operator-review request packet. It does not run research execution,
launch campaigns, mutate queues, register strategies, or authorize
paper/shadow/live trading.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Final


SCHEMA_VERSION: Final[str] = "1.0"
REPORT_KIND: Final[str] = "qre_controlled_discovery_subset_adapter"

DEFAULT_INPUT_PATH: Final[Path] = Path(
    "logs/qre_controlled_discovery_grid_inspection/safe_executable_subset.json"
)
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_controlled_discovery_subset_adapter")

ALLOWED_ASSET_CLASSES: Final[set[str]] = {"equity", "etf", "fundamental_equity", "index"}
FORBIDDEN_ASSET_CLASSES: Final[set[str]] = {"crypto", "crypto_legacy"}
REQUIRED_ROW_FIELDS: Final[tuple[str, ...]] = (
    "instrument_symbol",
    "asset_class",
    "region",
    "behavior_preset_id",
    "timeframe",
    "classification",
    "mapping_status",
    "source_identity_status",
)


class SubsetAdapterError(RuntimeError):
    """Raised when a controlled-discovery subset is unsafe or malformed."""


def _read_json(path: Path) -> Any:
    if not path.exists():
        raise SubsetAdapterError(f"input subset does not exist: {path.as_posix()}")
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _as_rows(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, list):
        raise SubsetAdapterError("input subset must be a JSON array")
    rows: list[dict[str, Any]] = []
    for index, row in enumerate(payload, start=1):
        if not isinstance(row, dict):
            raise SubsetAdapterError(f"subset row {index} is not an object")
        rows.append(row)
    return rows


def _missing_fields(row: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    for field in REQUIRED_ROW_FIELDS:
        value = row.get(field)
        if value in (None, "", []):
            missing.append(field)
    return missing


def _validate_row(row: dict[str, Any], *, index: int) -> list[str]:
    blockers: list[str] = []

    missing = _missing_fields(row)
    if missing:
        blockers.append("missing_required_fields:" + ",".join(sorted(missing)))

    asset_class = str(row.get("asset_class") or "").lower()
    if asset_class in FORBIDDEN_ASSET_CLASSES:
        blockers.append(f"forbidden_asset_class:{asset_class}")
    if asset_class and asset_class not in ALLOWED_ASSET_CLASSES:
        blockers.append(f"unsupported_asset_class:{asset_class}")

    if str(row.get("classification")) != "executable":
        blockers.append("classification_not_executable")
    if str(row.get("mapping_status")) != "ready":
        blockers.append("mapping_status_not_ready")
    if str(row.get("source_identity_status")) != "provider_symbol_verified":
        blockers.append("source_identity_not_provider_verified")

    for activation_field in (
        "paper_activation_allowed",
        "shadow_activation_allowed",
        "live_activation_allowed",
    ):
        if bool(row.get(activation_field, False)):
            blockers.append(f"{activation_field}_true")

    symbol = str(row.get("instrument_symbol") or "")
    if "-USD" in symbol.upper() or symbol.upper() in {"BTC", "ETH", "SOL", "DOGE", "XRP"}:
        blockers.append("crypto_symbol_marker_detected")

    if blockers:
        return [f"row_{index}:{blocker}" for blocker in blockers]
    return []


def _normalized_row(row: dict[str, Any], *, index: int) -> dict[str, Any]:
    return {
        "subset_sequence_number": index,
        "source_sequence_number": row.get("sequence_number"),
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
        "blocker_class": row.get("blocker_class"),
        "explanation": row.get("explanation"),
        "not_alpha_claim": True,
        "paper_activation_allowed": False,
        "shadow_activation_allowed": False,
        "live_activation_allowed": False,
        "execution_allowed": False,
        "campaign_launch_allowed": False,
        "candidate_promotion_allowed": False,
    }


def build_subset_adapter_packet(input_path: Path = DEFAULT_INPUT_PATH) -> dict[str, Any]:
    rows = _as_rows(_read_json(input_path))

    validation_blockers: list[str] = []
    for index, row in enumerate(rows, start=1):
        validation_blockers.extend(_validate_row(row, index=index))

    normalized_rows = [
        _normalized_row(row, index=index)
        for index, row in enumerate(rows, start=1)
    ]

    safe_to_execute_research = False
    subset_safe_for_operator_review = not validation_blockers

    region_counts = Counter(row["region"] for row in normalized_rows)
    asset_class_counts = Counter(row["asset_class"] for row in normalized_rows)
    preset_counts = Counter(row["behavior_preset_id"] for row in normalized_rows)

    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "input_path": input_path.as_posix(),
        "authority_boundaries": {
            "adapter_is_read_only": True,
            "not_alpha_authority": True,
            "not_trade_signal_generation": True,
            "not_data_fetching": True,
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
            "read_only": True,
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
            "paper_shadow_live_forbidden": True,
            "broker_risk_execution_forbidden": True,
        },
        "summary": {
            "subset_adapter_ready": subset_safe_for_operator_review,
            "subset_row_count": len(normalized_rows),
            "validation_blocker_count": len(validation_blockers),
            "safe_to_execute_research": safe_to_execute_research,
            "final_recommendation": (
                "subset_ready_for_operator_review_not_execution"
                if subset_safe_for_operator_review
                else "subset_blocked_for_operator_review"
            ),
            "operator_summary": (
                "Controlled discovery subset is validated as a bounded, non-crypto, "
                "read-only operator-review packet. It does not authorize research "
                "execution, campaigns, paper/shadow/live, broker execution, or risk changes."
                if subset_safe_for_operator_review
                else "Controlled discovery subset has validation blockers and must not be used."
            ),
            "region_counts": dict(sorted(region_counts.items())),
            "asset_class_counts": dict(sorted(asset_class_counts.items())),
            "preset_counts": dict(sorted(preset_counts.items())),
        },
        "validation_blockers": validation_blockers,
        "rows": normalized_rows,
    }


def render_operator_summary(packet: dict[str, Any]) -> str:
    summary = packet["summary"]
    lines = [
        "# QRE Controlled Discovery Subset Adapter",
        "",
        f"- {summary['operator_summary']}",
        "",
        "## Current Status",
        "",
        f"- subset_adapter_ready: {summary['subset_adapter_ready']}",
        f"- subset_row_count: {summary['subset_row_count']}",
        f"- validation_blocker_count: {summary['validation_blocker_count']}",
        f"- safe_to_execute_research: {summary['safe_to_execute_research']}",
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
            "- This packet is operator-review context only.",
            "- It does not launch research, campaigns, paper/shadow/live, broker execution, risk changes, queue mutation, candidate promotion, strategy registration, or preset mutation.",
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
        description="Build a read-only controlled-discovery subset operator packet."
    )
    parser.add_argument("--input", default=DEFAULT_INPUT_PATH.as_posix())
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)

    packet = build_subset_adapter_packet(Path(args.input))
    if args.write:
        packet["_artifact_paths"] = write_outputs(packet)

    print(json.dumps(packet, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())