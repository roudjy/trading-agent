from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Any, Final

import reporting.qre_executable_hypothesis_identity_bridge_diagnostics as bridge
import reporting.qre_selection_route_validation_flow as validation_flow

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[1]

SCHEMA_VERSION: Final[int] = 1
REPORT_KIND: Final[str] = "qre_selection_closed_loop_preflight"

OUTPUT_ARTIFACT_RELATIVE_PATH: Final[str] = "logs/qre_selection_closed_loop_preflight/latest.json"
ARTIFACT_LATEST: Final[Path] = REPO_ROOT / OUTPUT_ARTIFACT_RELATIVE_PATH


def _utcnow() -> str:
    return dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _counts(snapshot: dict[str, Any]) -> dict[str, Any]:
    counts = snapshot.get("counts")
    return counts if isinstance(counts, dict) else {}


def _bridge_summary(snapshot: dict[str, Any]) -> dict[str, Any]:
    bridge_payload = snapshot.get("bridge")
    return bridge_payload if isinstance(bridge_payload, dict) else {}


def _base_snapshot(
    *,
    generated_at_utc: str,
    flow_snapshot: dict[str, Any],
    bridge_snapshot: dict[str, Any],
) -> dict[str, Any]:
    flow_counts = _counts(flow_snapshot)
    bridge_payload = _bridge_summary(bridge_snapshot)

    flow_ready = int(flow_counts.get("selection_validation_flow_ready", 0) or 0)
    request_ready = int(flow_counts.get("request_ready_for_operator_review", 0) or 0)
    dry_run_ready = int(flow_counts.get("dry_run_ready", 0) or 0)

    legacy_regeneration_expected = bool(bridge_payload.get("regeneration_linkage_expected"))
    legacy_deterministic_mapping_possible = bool(
        bridge_payload.get("deterministic_mapping_possible")
    )
    legacy_primary_blocker = bridge_payload.get("primary_blocker")

    selection_route_ready = flow_ready > 0 and request_ready > 0 and dry_run_ready > 0

    controlled_regeneration_can_be_considered = (
        selection_route_ready
        and not legacy_regeneration_expected
        and not legacy_deterministic_mapping_possible
    )

    return {
        "report_kind": REPORT_KIND,
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": generated_at_utc,
        "safe_to_execute": False,
        "eligible_for_direct_execution": False,
        "read_only": True,
        "launches_subprocess": False,
        "launches_codex": False,
        "mutates_research_artifacts": False,
        "mutates_strategy_or_preset": False,
        "mutates_campaign_queue": False,
        "mutates_paper_shadow_live_runtime": False,
        "writes_seed_jsonl": False,
        "writes_generated_seed_jsonl": False,
        "writes_research_action_queue": False,
        "writes_development_work_queue": False,
        "selection_route": {
            "ready": selection_route_ready,
            "counts": flow_counts,
            "final_recommendation": flow_snapshot.get("final_recommendation"),
        },
        "legacy_bridge": {
            "regeneration_linkage_expected": legacy_regeneration_expected,
            "deterministic_mapping_possible": legacy_deterministic_mapping_possible,
            "primary_blocker": legacy_primary_blocker,
            "final_recommendation": bridge_snapshot.get("final_recommendation"),
        },
        "controlled_regeneration_preflight": {
            "can_be_considered": controlled_regeneration_can_be_considered,
            "requires_operator_approval": True,
            "requires_backup_plan": True,
            "requires_explicit_regeneration_flag": True,
            "reason_codes": [
                *(
                    ["selection_route_validation_flow_ready"]
                    if selection_route_ready
                    else ["selection_route_validation_flow_not_ready"]
                ),
                *(
                    ["legacy_bridge_still_blocked_but_bypassed_by_selection_route"]
                    if legacy_primary_blocker
                    else []
                ),
                "controlled_regeneration_not_executed_by_preflight",
            ],
        },
        "validation_warnings": [
            *list(flow_snapshot.get("validation_warnings") or []),
            *list(bridge_snapshot.get("validation_warnings") or []),
        ],
        "final_recommendation": (
            "selection_route_ready_controlled_regeneration_can_be_considered"
            if controlled_regeneration_can_be_considered
            else "selection_route_preflight_blocked"
        ),
    }


def collect_snapshot(
    *,
    flow_snapshot: dict[str, Any] | None = None,
    bridge_snapshot: dict[str, Any] | None = None,
    profile_name: str | None = None,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    generated = generated_at_utc or _utcnow()
    active_flow = flow_snapshot or validation_flow.collect_snapshot(
        profile_name=profile_name,
        generated_at_utc=generated,
    )
    active_bridge = bridge_snapshot or bridge.collect_snapshot(generated_at_utc=generated)

    return _base_snapshot(
        generated_at_utc=generated,
        flow_snapshot=active_flow,
        bridge_snapshot=active_bridge,
    )


def write_outputs(snapshot: dict[str, Any], *, output_path: Path | None = None) -> Path:
    target = output_path or ARTIFACT_LATEST
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return target


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--indent", type=int, default=2)
    parser.add_argument("--frozen-utc")
    parser.add_argument("--profile")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    snapshot = collect_snapshot(
        profile_name=args.profile,
        generated_at_utc=args.frozen_utc,
    )
    if not args.no_write:
        write_outputs(snapshot)
    print(json.dumps(snapshot, indent=args.indent, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
