from __future__ import annotations

import argparse
import json
import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from research import qre_evidence_complete_basket_closure as closure
from research import qre_guarded_preset_timeframe_alias_policy as alias_policy


REPORT_KIND: Final[str] = "qre_bounded_first_batch_generation_decision"
SCHEMA_VERSION: Final[str] = "1.0"
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_bounded_first_batch_generation_decision")
LATEST_NAME: Final[str] = "latest.json"
OPERATOR_SUMMARY_NAME: Final[str] = "operator_summary.md"
WRITE_PREFIX: Final[str] = "logs/qre_bounded_first_batch_generation_decision/"
FIRST_BATCH_SYMBOLS: Final[tuple[str, ...]] = ("AAPL", "NVDA")
TARGET_PRESET: Final[str] = "trend_pullback_continuation_daily_v1"
TARGET_TIMEFRAME: Final[str] = "daily_v1"


def _table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    head = "| " + " | ".join(headers) + " |"
    divider = "| " + " | ".join(["---"] * len(headers)) + " |"
    body = ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join([head, divider, *body])


def build_bounded_first_batch_generation_decision(
    *,
    repo_root: Path = Path("."),
    max_candidates: int = 15,
) -> dict[str, Any]:
    alias_report = alias_policy.build_guarded_preset_timeframe_alias_policy(
        repo_root=repo_root,
        max_candidates=max_candidates,
    )
    closure_report = closure.build_evidence_complete_basket_closure(
        repo_root=repo_root,
        max_candidates=max_candidates,
    )
    closure_rows = closure_report.get("rows") if isinstance(closure_report.get("rows"), list) else []
    blockers_by_symbol = {
        str(row.get("symbol") or ""): list(row.get("exact_blockers") or [])
        for row in closure_rows
        if isinstance(row, Mapping)
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "summary": {
            "first_batch": list(FIRST_BATCH_SYMBOLS),
            "target_preset": TARGET_PRESET,
            "target_timeframe": TARGET_TIMEFRAME,
            "alias_policy_status": str(alias_report.get("summary", {}).get("final_recommendation") or ""),
            "operator_summary": (
                "Bounded first-batch generation decision packet prepares the exact operator-approved "
                "next step without running generation."
            ),
            "final_recommendation": "operator_approve_bounded_aapl_nvda_current_basket_grid_generation",
        },
        "decision_packet": {
            "symbols": list(FIRST_BATCH_SYMBOLS),
            "target_preset": TARGET_PRESET,
            "target_timeframe": TARGET_TIMEFRAME,
            "reason": "current_daily_first_batch_evidence_absent_and_legacy_alias_is_context_only",
            "exact_blockers_to_clear": {
                symbol: blockers_by_symbol.get(symbol, ["campaign_lineage_missing", "no_oos_evidence"])
                for symbol in FIRST_BATCH_SYMBOLS
            },
            "required_output_artifacts": [
                "allowlisted_current_basket_generation_source_artifact",
                "structured_campaign_lineage_artifact",
                "structured_oos_validation_artifact",
                "reason_record_refs",
                "generation_manifest",
            ],
            "expected_downstream_reports_to_rerun": [
                "python -m research.qre_guarded_alias_bounded_generation_cascade --write",
                "python -m research.qre_first_batch_evidence_recovery_cascade --write",
                "python -m research.qre_first_batch_evidence_recovery_readiness --write",
                "python -m research.qre_basket_operator_action_plan --write",
                "python -m research.qre_basket_next_action_queue --write",
                "python -m research.qre_evidence_complete_basket_closure --write",
                "python -m research.qre_trusted_loop_review_packet --write",
            ],
            "safe_command_candidates": [
                "python -m research.qre_guarded_alias_bounded_generation_cascade --write",
                "python -m research.qre_guarded_preset_timeframe_alias_policy --write",
                "python -m research.qre_bounded_first_batch_generation_decision --write",
            ],
            "unsafe_command_candidates": [
                "campaign_launcher",
                "run_campaign",
                "campaign_queue mutation",
                "campaign_registry mutation",
                "paper/shadow/live",
                "broker/risk/execution",
                "provider activation",
                "external data fetch",
            ],
            "operator_approval_required": True,
            "auto_run_allowed": False,
            "rollback_noop_behavior": "no_generation_run_no_campaign_state_change_no_artifact_acceptance",
            "stop_conditions": [
                "stop_if_operator_approval_is_missing",
                "stop_if_generation_would_mutate_queue_or_registry_state",
                "stop_if_generation_would_require_provider_activation_or_external_fetch",
            ],
            "allowed_output_directories": [
                "logs/qre_bounded_first_batch_generation_decision/",
                "logs/qre_guarded_alias_bounded_generation_cascade/",
            ],
            "forbidden_output_directories": [
                "research/",
                "paper/",
                "shadow/",
                "live/",
                "broker/",
                "risk/",
                "execution/",
            ],
        },
        "safety_invariants": {
            "read_only": True,
            "operator_approval_required": True,
            "auto_run_allowed": False,
            "no_actual_generation_run": True,
            "mutates_campaigns": False,
            "mutates_frozen_contracts": False,
        },
    }


def render_operator_summary(report: Mapping[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    packet = report.get("decision_packet") if isinstance(report.get("decision_packet"), Mapping) else {}
    blockers = packet.get("exact_blockers_to_clear") if isinstance(packet.get("exact_blockers_to_clear"), Mapping) else {}
    return "\n".join(
        [
            "# QRE Bounded First-Batch Generation Decision",
            "",
            "## 1. Summary",
            _table(
                ["Field", "Value"],
                [
                    ["first_batch", ", ".join(str(v) for v in summary.get("first_batch") or []) or "none"],
                    ["target_preset", str(summary.get("target_preset") or "")],
                    ["target_timeframe", str(summary.get("target_timeframe") or "")],
                    ["final_recommendation", str(summary.get("final_recommendation") or "")],
                ],
            ),
            "",
            "## 2. Blockers to clear",
            _table(
                ["Symbol", "Blockers"],
                [
                    [str(symbol), ",".join(str(v) for v in values or [])]
                    for symbol, values in blockers.items()
                ],
            ),
        ]
    )


def _validate_write_target(path: Path) -> None:
    if WRITE_PREFIX not in path.as_posix():
        raise ValueError(
            f"qre_bounded_first_batch_generation_decision: refusing write outside allowlist: {path!r}"
        )


def write_outputs(
    report: Mapping[str, Any],
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    repo_root: Path = Path("."),
) -> dict[str, str]:
    base = repo_root / output_dir
    base.mkdir(parents=True, exist_ok=True)
    latest = base / LATEST_NAME
    summary_path = base / OPERATOR_SUMMARY_NAME
    for target in (latest, summary_path):
        _validate_write_target(target)
    tmp_json = latest.with_suffix(latest.suffix + ".tmp")
    tmp_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp_json, latest)
    tmp_md = summary_path.with_suffix(summary_path.suffix + ".tmp")
    tmp_md.write_text(render_operator_summary(report) + "\n", encoding="utf-8")
    os.replace(tmp_md, summary_path)
    return {
        "latest": latest.relative_to(repo_root).as_posix(),
        "operator_summary": summary_path.relative_to(repo_root).as_posix(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m research.qre_bounded_first_batch_generation_decision",
        description="Build the bounded first-batch generation decision packet.",
    )
    parser.add_argument("--max-candidates", type=int, default=15)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    report = build_bounded_first_batch_generation_decision(max_candidates=args.max_candidates)
    if args.write:
        report["_artifact_paths"] = write_outputs(report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
