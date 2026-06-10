"""Local runner harness for controlled subset dry-run intents.

This module consumes runner dry-run intents and materializes local execution
envelopes. It deliberately does not call run_research, campaign_launcher,
screening, validation, subprocesses, network, broker execution, paper/shadow/live,
or mutate research_latest.json / strategy_matrix.csv.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Final


SCHEMA_VERSION: Final[str] = "1.0"
REPORT_KIND: Final[str] = "qre_controlled_subset_local_runner_harness"

DEFAULT_INPUT_PATH: Final[Path] = Path("logs/qre_controlled_subset_runner_dry_run/latest.json")
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_controlled_subset_local_runner_harness")

FORBIDDEN_ASSET_CLASSES: Final[set[str]] = {"crypto", "crypto_legacy"}
REQUIRED_INTENT_FIELDS: Final[tuple[str, ...]] = (
    "runner_dry_run_intent_id",
    "candidate_plan_id",
    "instrument_symbol",
    "asset_class",
    "region",
    "behavior_preset_id",
    "timeframe",
    "primary_data_provider_symbol",
    "intent_status",
    "expected_runner_mode",
)


class LocalRunnerHarnessError(RuntimeError):
    """Raised when local runner harness input cannot be read."""


def _read_json(path: Path) -> Any:
    if not path.exists():
        raise LocalRunnerHarnessError(f"runner dry-run packet does not exist: {path.as_posix()}")
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _require_packet(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise LocalRunnerHarnessError("runner dry-run input must be a JSON object")
    return payload


def _intents(payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw_intents = payload.get("runner_dry_run_intents")
    if not isinstance(raw_intents, list):
        raise LocalRunnerHarnessError("runner_dry_run_intents must be a list")
    intents: list[dict[str, Any]] = []
    for index, intent in enumerate(raw_intents, start=1):
        if not isinstance(intent, dict):
            raise LocalRunnerHarnessError(f"runner_dry_run_intents[{index}] is not an object")
        intents.append(intent)
    return intents


def _input_packet_ready(payload: dict[str, Any]) -> bool:
    summary = payload.get("summary")
    if not isinstance(summary, dict):
        return False
    return (
        payload.get("report_kind") == "qre_controlled_subset_runner_dry_run"
        and summary.get("runner_dry_run_packet_ready") is True
        and int(summary.get("blocker_count") or 0) == 0
        and summary.get("safe_to_execute_research") is False
        and summary.get("screening_allowed") is False
        and summary.get("validation_allowed") is False
        and summary.get("run_research_called") is False
        and summary.get("campaign_launcher_called") is False
    )


def _intent_blockers(intent: dict[str, Any], *, index: int) -> list[str]:
    blockers: list[str] = []

    for field in REQUIRED_INTENT_FIELDS:
        if intent.get(field) in (None, "", []):
            blockers.append(f"missing_required_field:{field}")

    symbol = str(intent.get("instrument_symbol") or "")
    asset_class = str(intent.get("asset_class") or "").lower()

    if asset_class in FORBIDDEN_ASSET_CLASSES:
        blockers.append(f"forbidden_asset_class:{asset_class}")
    if "-USD" in symbol.upper() or symbol.upper() in {"BTC", "ETH", "SOL", "DOGE", "XRP"}:
        blockers.append("crypto_symbol_marker_detected")

    if str(intent.get("intent_status")) != "runner_dry_run_intent_materialized_not_executed":
        blockers.append("intent_status_not_materialized_not_executed")
    if str(intent.get("expected_runner_mode")) != "dry_run_no_subprocess_no_mutation":
        blockers.append("unexpected_runner_mode")

    for field in (
        "run_research_called",
        "campaign_launcher_called",
        "screening_called",
        "validation_called",
        "network_allowed",
        "external_data_allowed",
        "screening_allowed",
        "validation_allowed",
        "execution_allowed",
        "campaign_launch_allowed",
        "candidate_promotion_allowed",
        "paper_activation_allowed",
        "shadow_activation_allowed",
        "live_activation_allowed",
    ):
        if bool(intent.get(field, False)):
            blockers.append(f"{field}_true")

    return [f"intent_{index}:{blocker}" for blocker in blockers]


def _envelope(intent: dict[str, Any], *, index: int) -> dict[str, Any]:
    runner_intent_id = str(intent.get("runner_dry_run_intent_id"))
    return {
        "envelope_sequence_number": index,
        "local_runner_envelope_id": f"local-harness::{runner_intent_id}",
        "runner_dry_run_intent_id": runner_intent_id,
        "candidate_plan_id": str(intent.get("candidate_plan_id")),
        "instrument_symbol": str(intent.get("instrument_symbol")),
        "asset_class": str(intent.get("asset_class")),
        "region": str(intent.get("region")),
        "behavior_preset_id": str(intent.get("behavior_preset_id")),
        "timeframe": str(intent.get("timeframe")),
        "primary_data_provider_symbol": str(intent.get("primary_data_provider_symbol")),
        "envelope_status": "local_harness_envelope_materialized_not_executed",
        "execution_performed": False,
        "subprocess_called": False,
        "network_called": False,
        "run_research_called": False,
        "campaign_launcher_called": False,
        "screening_called": False,
        "validation_called": False,
        "candidate_registry_mutated": False,
        "campaign_artifacts_mutated": False,
        "queue_mutated": False,
        "strategy_registered": False,
        "preset_mutated": False,
        "research_latest_mutated": False,
        "strategy_matrix_mutated": False,
        "paper_activation_allowed": False,
        "shadow_activation_allowed": False,
        "live_activation_allowed": False,
        "broker_execution_allowed": False,
        "risk_authority_allowed": False,
        "expected_artifact_scope": "logs_only",
        "not_alpha_claim": True,
    }


def build_local_runner_harness_packet(input_path: Path = DEFAULT_INPUT_PATH) -> dict[str, Any]:
    packet = _require_packet(_read_json(input_path))
    intents = _intents(packet)

    blockers: list[str] = []
    if not _input_packet_ready(packet):
        blockers.append("input_runner_dry_run_packet_not_ready")

    intent_ids = [str(intent.get("runner_dry_run_intent_id")) for intent in intents]
    duplicate_intent_ids = sorted(
        intent_id
        for intent_id, count in Counter(intent_ids).items()
        if count > 1
    )
    for intent_id in duplicate_intent_ids:
        blockers.append(f"duplicate_runner_dry_run_intent_id:{intent_id}")

    for index, intent in enumerate(intents, start=1):
        blockers.extend(_intent_blockers(intent, index=index))

    envelopes = [_envelope(intent, index=index) for index, intent in enumerate(intents, start=1)]

    region_counts = Counter(envelope["region"] for envelope in envelopes)
    asset_class_counts = Counter(envelope["asset_class"] for envelope in envelopes)
    preset_counts = Counter(envelope["behavior_preset_id"] for envelope in envelopes)
    timeframe_counts = Counter(envelope["timeframe"] for envelope in envelopes)

    harness_ready = not blockers

    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "input_path": input_path.as_posix(),
        "authority_boundaries": {
            "local_harness_is_dry_run_only": True,
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
            "local_runner_harness_ready": harness_ready,
            "intent_count": len(intents),
            "envelope_count": len(envelopes),
            "blocker_count": len(blockers),
            "duplicate_runner_dry_run_intent_id_count": len(duplicate_intent_ids),
            "execution_performed": False,
            "subprocess_called": False,
            "network_called": False,
            "run_research_called": False,
            "campaign_launcher_called": False,
            "screening_called": False,
            "validation_called": False,
            "safe_to_execute_research": False,
            "screening_allowed": False,
            "validation_allowed": False,
            "final_recommendation": (
                "local_runner_harness_ready_not_executed"
                if harness_ready
                else "local_runner_harness_blocked"
            ),
            "operator_summary": (
                "Local runner harness envelopes are materialized as logs-only records. "
                "No subprocess, network, run_research, campaign_launcher, screening, "
                "validation, paper/shadow/live, broker, or risk authority was invoked."
                if harness_ready
                else "Local runner harness has blockers and must not be used."
            ),
            "region_counts": dict(sorted(region_counts.items())),
            "asset_class_counts": dict(sorted(asset_class_counts.items())),
            "preset_counts": dict(sorted(preset_counts.items())),
            "timeframe_counts": dict(sorted(timeframe_counts.items())),
        },
        "blockers": blockers,
        "local_runner_envelopes": envelopes,
    }


def render_operator_summary(packet: dict[str, Any]) -> str:
    summary = packet["summary"]
    lines = [
        "# QRE Controlled Subset Local Runner Harness",
        "",
        f"- {summary['operator_summary']}",
        "",
        "## Current Status",
        "",
        f"- local_runner_harness_ready: {summary['local_runner_harness_ready']}",
        f"- intent_count: {summary['intent_count']}",
        f"- envelope_count: {summary['envelope_count']}",
        f"- blocker_count: {summary['blocker_count']}",
        f"- execution_performed: {summary['execution_performed']}",
        f"- subprocess_called: {summary['subprocess_called']}",
        f"- network_called: {summary['network_called']}",
        f"- run_research_called: {summary['run_research_called']}",
        f"- campaign_launcher_called: {summary['campaign_launcher_called']}",
        f"- screening_called: {summary['screening_called']}",
        f"- validation_called: {summary['validation_called']}",
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
            "- This local runner harness only materializes dry-run envelopes.",
            "- It does not call subprocess, network, run_research, campaign_launcher, screening, validation, paper/shadow/live, broker execution, risk changes, queue mutation, candidate promotion, strategy registration, or preset mutation.",
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
        description="Build local runner harness envelopes from controlled subset dry-run intents."
    )
    parser.add_argument("--input", default=DEFAULT_INPUT_PATH.as_posix())
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)

    packet = build_local_runner_harness_packet(Path(args.input))
    if args.write:
        packet["_artifact_paths"] = write_outputs(packet)

    print(json.dumps(packet, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())