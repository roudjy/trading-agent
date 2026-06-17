from __future__ import annotations

import argparse
import json
import os
import subprocess
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
SAFE_REPORT_ONLY_COMMANDS: Final[tuple[str, ...]] = (
    "python -m research.qre_guarded_alias_bounded_generation_cascade --write",
    "python -m research.qre_guarded_preset_timeframe_alias_policy --write",
    "python -m research.qre_bounded_first_batch_generation_decision --write",
    "python -m research.qre_bounded_aapl_nvda_current_basket_generation_discovery --write",
)
SAFE_PREFLIGHT_COMMANDS: Final[tuple[str, ...]] = ()
APPROVAL_REQUIRED_GENERATION_COMMANDS: Final[tuple[str, ...]] = (
    "python -m research.controlled_discovery_grid --symbols AAPL,NVDA --preset trend_pullback_continuation_daily_v1 --timeframe daily_v1",
    "python -m research.controlled_validation --symbols AAPL,NVDA --preset trend_pullback_continuation_daily_v1 --timeframe daily_v1",
)
FORBIDDEN_COMMAND_FRAGMENTS: Final[dict[str, str]] = {
    "campaign_launcher": "forbidden_mutation",
    "run_campaign": "forbidden_mutation",
    "campaign_queue": "forbidden_mutation",
    "campaign_registry": "forbidden_mutation",
    "paper": "forbidden_trading",
    "shadow": "forbidden_trading",
    "live": "forbidden_trading",
    "broker": "forbidden_trading",
    "risk": "forbidden_trading",
    "execution": "forbidden_trading",
    "strategy synthesis": "forbidden_mutation",
    "strategy registration": "forbidden_mutation",
    "candidate promotion": "forbidden_mutation",
    "provider fetch": "forbidden_external_fetch",
    "provider activation": "forbidden_external_fetch",
    "external data fetch": "forbidden_external_fetch",
}
PROTECTED_PATHS: Final[tuple[str, ...]] = ("research/research_latest.json", "research/strategy_matrix.csv")
STATUS_IGNORE_PREFIXES: Final[tuple[str, ...]] = ("logs/", ".tmp/")
STATUS_IGNORE_EXACT: Final[frozenset[str]] = frozenset({"pr_body.md"})


def _table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    head = "| " + " | ".join(headers) + " |"
    divider = "| " + " | ".join(["---"] * len(headers)) + " |"
    body = ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join([head, divider, *body])


def classify_command_envelope(command: str) -> dict[str, Any]:
    normalized = " ".join(str(command or "").split())
    lowered = normalized.lower()
    if normalized in SAFE_REPORT_ONLY_COMMANDS:
        return {
            "command": normalized,
            "classification": "safe_report_only",
            "operator_approval_required": False,
            "auto_run_allowed": False,
        }
    if normalized in SAFE_PREFLIGHT_COMMANDS:
        return {
            "command": normalized,
            "classification": "safe_preflight_only",
            "operator_approval_required": False,
            "auto_run_allowed": False,
        }
    if normalized in APPROVAL_REQUIRED_GENERATION_COMMANDS or "controlled_discovery_grid" in lowered or "controlled_validation" in lowered:
        return {
            "command": normalized,
            "classification": "approval_required_generation",
            "operator_approval_required": True,
            "auto_run_allowed": False,
        }
    for fragment, classification in FORBIDDEN_COMMAND_FRAGMENTS.items():
        if fragment in lowered:
            return {
                "command": normalized,
                "classification": classification,
                "operator_approval_required": True,
                "auto_run_allowed": False,
            }
    return {
        "command": normalized,
        "classification": "unknown_requires_operator_review",
        "operator_approval_required": True,
        "auto_run_allowed": False,
    }


def _git_status_paths(repo_root: Path) -> list[str]:
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo_root,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    except OSError:
        return []
    if result.returncode != 0:
        return []
    paths: list[str] = []
    for line in result.stdout.splitlines():
        if len(line) < 4:
            continue
        candidate = line[3:].strip()
        if " -> " in candidate:
            candidate = candidate.split(" -> ", 1)[1].strip()
        candidate = candidate.replace("\\", "/")
        if candidate:
            paths.append(candidate)
    return paths


def _build_preflight(repo_root: Path) -> dict[str, Any]:
    status_paths = _git_status_paths(repo_root)
    relevant_dirty_paths = [
        path
        for path in status_paths
        if not path.startswith(STATUS_IGNORE_PREFIXES)
        and path not in STATUS_IGNORE_EXACT
    ]
    blocking_reasons: list[str] = []
    if any(path in PROTECTED_PATHS for path in relevant_dirty_paths):
        blocking_reasons.append("protected_path_dirty")
    return {
        "preflight_status": "approval_packet_ready" if not blocking_reasons else "blocked_preflight",
        "blocking_preflight_reasons": blocking_reasons,
        "approval_packet_ready": not blocking_reasons,
        "auto_run_allowed": False,
        "operator_decision_required": True,
        "recommended_next_action": (
            "operator_approve_bounded_aapl_nvda_current_basket_grid_generation"
            if not blocking_reasons
            else "clear_preflight_blockers_before_operator_review"
        ),
        "repo_clean_state_required": True,
        "current_branch_main_state_required": True,
        "frozen_contract_protection_required": True,
        "protected_path_exclusion_required": True,
        "output_path_allowlist_required": True,
        "symbol_allowlist": list(FIRST_BATCH_SYMBOLS),
        "target_preset_allowlist": [TARGET_PRESET],
        "target_timeframe_allowlist": [TARGET_TIMEFRAME],
        "no_strategy_synthesis": True,
        "no_candidate_promotion": True,
        "no_paper_shadow_live": True,
        "no_broker_risk_execution": True,
        "no_external_provider_fetch": True,
        "logs_output_manifest_required": True,
        "reason_records_required": True,
        "downstream_rerun_sequence_required": True,
        "operator_approval_required": True,
    }


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
    command_candidates = [
        *SAFE_REPORT_ONLY_COMMANDS,
        *APPROVAL_REQUIRED_GENERATION_COMMANDS,
        "campaign_launcher",
        "run_campaign",
        "campaign_queue mutation",
        "campaign_registry mutation",
        "paper/shadow/live",
        "broker/risk/execution",
        "strategy synthesis",
        "strategy registration",
        "candidate promotion",
        "provider activation",
        "external data fetch",
    ]
    preflight = _build_preflight(repo_root)
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
                *SAFE_REPORT_ONLY_COMMANDS,
            ],
            "unsafe_command_candidates": [
                *APPROVAL_REQUIRED_GENERATION_COMMANDS,
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
        "command_envelope": {
            "rows": [classify_command_envelope(command) for command in command_candidates],
        },
        "preflight": preflight,
        "runbook_contract": {
            "purpose": "future_operator_approved_current_basket_generation_for_first_batch_evidence_only",
            "symbols": list(FIRST_BATCH_SYMBOLS),
            "target_preset": TARGET_PRESET,
            "target_timeframe": TARGET_TIMEFRAME,
            "approval_required": True,
            "auto_run_allowed": False,
            "expected_command_categories": [
                "safe_report_only",
                "safe_preflight_only",
                "approval_required_generation",
            ],
            "forbidden_command_categories": [
                "forbidden_mutation",
                "forbidden_trading",
                "forbidden_external_fetch",
            ],
            "required_output_artifacts": [
                "allowlisted_current_basket_generation_source_artifact",
                "structured_campaign_lineage_artifact",
                "structured_oos_validation_artifact",
                "screening_evidence_artifact",
                "generation_manifest",
                "reason_record_refs",
            ],
            "output_directory_allowlist": [
                "logs/qre_bounded_first_batch_generation_decision/",
                "logs/qre_guarded_alias_bounded_generation_cascade/",
            ],
            "forbidden_paths": [
                "research/research_latest.json",
                "research/strategy_matrix.csv",
                "paper/",
                "shadow/",
                "live/",
                "broker/",
                "risk/",
                "execution/",
            ],
            "required_reason_records": True,
            "required_manifests": True,
            "required_downstream_rerun_sequence": [
                "python -m research.qre_guarded_alias_bounded_generation_cascade --write",
                "python -m research.qre_bounded_first_batch_generation_decision --write",
                "python -m research.qre_first_batch_evidence_recovery_readiness --write",
                "python -m research.qre_basket_operator_action_plan --write",
                "python -m research.qre_basket_next_action_queue --write",
                "python -m research.qre_evidence_complete_basket_closure --write",
                "python -m research.qre_trusted_loop_review_packet --write",
            ],
            "rollback_noop_behavior": "if_any_precondition_fails_or_approval_is_missing_do_nothing_and_preserve_current_fail_closed_state",
            "stop_conditions": list((preflight or {}).get("blocking_preflight_reasons") or []) + [
                "operator_approval_missing",
                "generation_scope_expands_beyond_aapl_nvda_daily_current_preset",
            ],
        },
        "acceptance_contract": {
            "minimum_required_fields": [
                "symbol",
                "preset_id",
                "timeframe",
                "candidate_id",
                "campaign_id_or_generation_run_id",
                "grid_run_id_or_controlled_generation_id",
                "oos_metric_fields",
                "screening_evidence_fields",
                "lineage_fields",
                "validation_status",
                "artifact_timestamp",
                "source_artifact_path",
                "reason_record_refs",
                "policy_version",
                "operator_approval_id_or_manifest_ref",
            ],
            "rejection_conditions": [
                "stdout_only_traces",
                "generated_summaries_without_source_artifacts",
                "context_only_legacy_evidence",
                "missing_campaign_or_generation_identity",
                "mismatched_preset",
                "mismatched_timeframe",
                "unapproved_generation_artifacts",
                "artifacts_outside_allowlisted_paths",
            ],
            "allowlisted_paths": [
                "logs/",
                "artifacts/",
                "archived/",
                "backup/",
                "local_quarantine/",
            ],
            "forbidden_paths": [
                ".tmp/",
                "tests/fixtures/",
                "paper/",
                "shadow/",
                "live/",
                "broker/",
                "risk/",
                "execution/",
            ],
            "policy_version": SCHEMA_VERSION,
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
            "",
            "## 3. Command envelope",
            _table(
                ["Command", "Classification", "Approval", "Auto-run"],
                [
                    [
                        str(row.get("command") or ""),
                        str(row.get("classification") or ""),
                        str(bool(row.get("operator_approval_required"))).lower(),
                        str(bool(row.get("auto_run_allowed"))).lower(),
                    ]
                    for row in (report.get("command_envelope") or {}).get("rows", [])
                ],
            ),
            "",
            "## 4. Preflight",
            _table(
                ["Field", "Value"],
                [
                    ["preflight_status", str((report.get("preflight") or {}).get("preflight_status") or "")],
                    ["approval_packet_ready", str(bool((report.get("preflight") or {}).get("approval_packet_ready"))).lower()],
                    ["blocking_preflight_reasons", ",".join(str(v) for v in (report.get("preflight") or {}).get("blocking_preflight_reasons") or []) or "none"],
                    ["recommended_next_action", str((report.get("preflight") or {}).get("recommended_next_action") or "")],
                ],
            ),
            "",
            "## 5. Contracts",
            _table(
                ["Field", "Value"],
                [
                    ["runbook_approval_required", str(bool((report.get("runbook_contract") or {}).get("approval_required"))).lower()],
                    ["runbook_auto_run_allowed", str(bool((report.get("runbook_contract") or {}).get("auto_run_allowed"))).lower()],
                    ["acceptance_required_fields", str(len((report.get("acceptance_contract") or {}).get("minimum_required_fields") or []))],
                    ["acceptance_rejection_conditions", str(len((report.get("acceptance_contract") or {}).get("rejection_conditions") or []))],
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
