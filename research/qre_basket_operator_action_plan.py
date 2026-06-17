from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from research import qre_basket_lineage_recovery_diagnostics as lineage_diag
from research import qre_basket_next_action_queue as next_action_queue
from research import qre_first_batch_evidence_recovery_cascade as first_batch_cascade
from research import qre_first_batch_evidence_recovery_readiness as first_batch_readiness


REPORT_KIND: Final[str] = "qre_basket_operator_action_plan"
SCHEMA_VERSION: Final[str] = "1.0"
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_basket_operator_action_plan")
LATEST_NAME: Final[str] = "latest.json"
OPERATOR_SUMMARY_NAME: Final[str] = "operator_summary.md"
WRITE_PREFIX: Final[str] = "logs/qre_basket_operator_action_plan/"

SAFE_COMMANDS: Final[tuple[str, ...]] = (
    "python -m research.qre_basket_evidence_density_materialization --write",
    "python -m research.qre_basket_lineage_recovery_diagnostics --write",
    "python -m research.qre_basket_evidence_recovery_plan --write",
    "python -m research.qre_basket_next_action_queue --write",
    "python -m research.qre_evidence_complete_basket_closure --write",
    "python -m research.qre_trusted_loop_review_packet --write",
    "python -m research.qre_first_batch_evidence_recovery_readiness --write",
    "python -m research.qre_first_batch_evidence_recovery_cascade --write",
)
NOT_ALLOWED_COMMANDS: Final[tuple[str, ...]] = (
    "any campaign mutation command",
    "any paper/shadow/live activation command",
    "any broker/risk/execution command",
    "any strategy synthesis or registration command",
)


def _table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    head = "| " + " | ".join(headers) + " |"
    divider = "| " + " | ".join(["---"] * len(headers)) + " |"
    body = ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join([head, divider, *body])


def _candidate_rows(report: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = report.get("rows")
    if not isinstance(rows, list):
        return []
    return [dict(row) for row in rows if isinstance(row, Mapping)]


def build_basket_operator_action_plan(
    *,
    repo_root: Path = Path("."),
    max_candidates: int = 15,
) -> dict[str, Any]:
    queue_report = next_action_queue.build_basket_next_action_queue(
        repo_root=repo_root,
        max_candidates=max_candidates,
    )
    readiness_report = first_batch_readiness.build_first_batch_evidence_recovery_readiness(
        repo_root=repo_root,
        max_candidates=max_candidates,
    )
    cascade_report = first_batch_cascade.build_first_batch_evidence_recovery_cascade(
        repo_root=repo_root,
        max_candidates=max_candidates,
    )
    lineage_report = lineage_diag.build_basket_lineage_recovery_diagnostics(
        repo_root=repo_root,
        max_candidates=max_candidates,
    )
    queue_rows = _candidate_rows(queue_report)
    lineage_rows = {
        str(row.get("candidate_id") or ""): dict(row)
        for row in _candidate_rows(lineage_report)
    }

    top_candidates = [
        row
        for row in queue_rows
        if str(row.get("symbol") or "") in {"AAPL", "NVDA"}
    ]
    top_candidates.sort(
        key=lambda row: (
            int(row.get("priority_rank") or 99),
            -int(row.get("candidate_score") or 0),
            str(row.get("blocker_code") or ""),
        )
    )
    first_batch_rows = top_candidates[:4] if top_candidates else queue_rows[:4]
    first_batch_symbols = list(dict.fromkeys(str(row.get("symbol") or "") for row in first_batch_rows))
    targeted_blockers = Counter(str(row.get("blocker_code") or "") for row in first_batch_rows)
    top_actions = list(dict.fromkeys(str(row.get("exact_next_action") or "") for row in first_batch_rows))
    expected_blocker_impact = {
        blocker: count
        for blocker, count in sorted(targeted_blockers.items())
    }
    blocked_by_identity = any(bool(row.get("blocked_by_identity")) for row in first_batch_rows)
    blocked_by_source_cache = any(bool(row.get("blocked_by_source_cache")) for row in first_batch_rows)
    blocked_by_lineage = any(bool(row.get("blocked_by_lineage")) for row in first_batch_rows)
    blocked_by_screening = any(bool(row.get("blocked_by_screening")) for row in first_batch_rows)
    blocked_by_oos = any(bool(row.get("blocked_by_oos")) for row in first_batch_rows)
    if blocked_by_identity:
        first_batch_name = "identity_review"
    elif blocked_by_lineage and not blocked_by_source_cache:
        first_batch_name = "lineage_repair"
    elif blocked_by_source_cache:
        first_batch_name = "source_cache_repair"
    elif blocked_by_screening or blocked_by_oos:
        first_batch_name = "evidence_collection"
    else:
        first_batch_name = "operator_review"

    report_rows = [
        {
            "candidate_id": row.get("candidate_id"),
            "symbol": row.get("symbol"),
            "region": row.get("region"),
            "asset_class": row.get("asset_class"),
            "preset_id": row.get("preset_id"),
            "hypothesis_id": row.get("hypothesis_id"),
            "priority_rank": row.get("priority_rank"),
            "priority_bucket": row.get("priority_bucket"),
            "exact_next_action": row.get("exact_next_action"),
            "recommended_batch": row.get("recommended_batch"),
            "candidate_score": row.get("candidate_score"),
            "lineage_proof_status": row.get("lineage_proof_status"),
            "campaign_lineage_proof_status": row.get("campaign_lineage_proof_status"),
            "allowed_command_template": row.get("allowed_command_template"),
            "requires_operator_review": True,
            "safe_action_type": row.get("safe_action_type"),
            "exact_blocker": row.get("blocker_code"),
            "blocker_family": row.get("blocker_family"),
            "operator_explanation": row.get("operator_explanation"),
            "lineage_diagnostic": lineage_rows.get(str(row.get("candidate_id") or ""), {}),
        }
        for row in first_batch_rows
    ]

    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "summary": {
            "recommended_first_batch": first_batch_name,
            "first_batch_candidate_symbols": first_batch_symbols,
            "top_candidates": first_batch_symbols,
            "top_actions": top_actions,
            "blockers_targeted": dict(expected_blocker_impact),
            "safe_command_count": len(SAFE_COMMANDS),
            "commands_not_allowed_count": len(NOT_ALLOWED_COMMANDS),
            "first_batch_readiness_artifact": "logs/qre_first_batch_evidence_recovery_readiness/latest.json",
            "first_batch_readiness_available": str(readiness_report.get("report_kind") or "") == "qre_first_batch_evidence_recovery_readiness",
            "first_batch_recovery_cascade_artifact": "logs/qre_first_batch_evidence_recovery_cascade/latest.json",
            "first_batch_recovery_cascade_available": str(cascade_report.get("report_kind") or "") == "qre_first_batch_evidence_recovery_cascade",
            "first_batch_recovery_cascade_result": str(cascade_report.get("overall_result") or ""),
            "first_batch_recovery_cascade_top_blocker": str(
                (cascade_report.get("first_batch_summary") or {}).get("current_top_blocker") or ""
            ),
            "final_recommendation": "basket_operator_action_plan_ready" if queue_rows else "basket_operator_action_plan_missing",
            "operator_summary": (
                "Read-only operator action plan groups the closest evidence recovery steps into a bounded first batch "
                "without granting any execution authority."
            ),
        },
        "first_batch": report_rows,
        "safe_commands_to_run_manually": list(SAFE_COMMANDS),
        "commands_not_allowed": list(NOT_ALLOWED_COMMANDS),
        "stop_conditions": [
            "Do not run any command that mutates campaigns, queues, or strategy registration.",
            "Do not use paper/shadow/live, broker, risk, or execution paths.",
            "Do not claim evidence completeness unless the closure packet proves it from local artifacts.",
            "Do not clear ASMI identity blocking without deterministic local proof.",
        ],
        "required_follow_up_reports": [
            "python -m research.qre_basket_evidence_density_materialization --write",
            "python -m research.qre_basket_lineage_recovery_diagnostics --write",
            "python -m research.qre_basket_evidence_recovery_plan --write",
            "python -m research.qre_basket_next_action_queue --write",
            "python -m research.qre_evidence_complete_basket_closure --write",
            "python -m research.qre_trusted_loop_review_packet --write",
            "python -m research.qre_first_batch_evidence_recovery_readiness --write",
            "python -m research.qre_first_batch_evidence_recovery_cascade --write",
        ],
        "expected_rerun_sequence": [
            "materialize_density",
            "diagnose_lineage",
            "refresh_first_batch_readiness",
            "refresh_first_batch_recovery_cascade",
            "refresh_recovery_plan",
            "refresh_next_action_queue",
            "refresh_closure",
            "refresh_trusted_loop",
        ],
        "safety_invariants": {
            "read_only": True,
            "mutates_campaigns": False,
            "mutates_queues": False,
            "mutates_frozen_contracts": False,
            "paper_shadow_live_forbidden": True,
            "broker_risk_execution_forbidden": True,
            "promotion_forbidden": True,
        },
    }


def render_operator_summary(report: Mapping[str, Any]) -> str:
    summary = report.get("summary") or {}
    rows = report.get("first_batch") if isinstance(report.get("first_batch"), list) else []
    batch_table = _table(
        ["Symbol", "Priority", "Batch", "Action", "Allowed command"],
        [
            [
                str(row.get("symbol") or ""),
                str(row.get("priority_bucket") or ""),
                str(row.get("recommended_batch") or ""),
                str(row.get("exact_next_action") or ""),
                str(row.get("allowed_command_template") or ""),
            ]
            for row in rows
        ],
    )
    return "\n".join(
        [
            "# QRE Basket Operator Action Plan",
            "",
            "## 1. Korte conclusie",
            f"- {summary.get('operator_summary') or ''}",
            "",
            "## 2. Recommended first batch",
            _table(
                ["Field", "Value"],
                [
                    ["recommended_first_batch", str(summary.get("recommended_first_batch") or "")],
                    ["top_candidates", ", ".join(str(item) for item in summary.get("top_candidates") or []) or "none"],
                    ["top_actions", ", ".join(str(item) for item in summary.get("top_actions") or []) or "none"],
                    ["cascade_result", str(summary.get("first_batch_recovery_cascade_result") or "")],
                    ["cascade_top_blocker", str(summary.get("first_batch_recovery_cascade_top_blocker") or "")],
                ],
            ),
            "",
            "## 3. First batch rows",
            batch_table,
            "",
            "## 4. Safe commands",
            "\n".join(f"- `{item}`" for item in report.get("safe_commands_to_run_manually") or []),
            "",
            "## 5. Commands not allowed",
            "\n".join(f"- {item}" for item in report.get("commands_not_allowed") or []),
        ]
    )


def _validate_write_target(path: Path) -> None:
    if WRITE_PREFIX not in path.as_posix():
        raise ValueError(
            f"qre_basket_operator_action_plan: refusing write outside allowlist: {path!r}"
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
    tmp_summary = summary_path.with_suffix(summary_path.suffix + ".tmp")
    tmp_summary.write_text(render_operator_summary(report) + "\n", encoding="utf-8")
    os.replace(tmp_summary, summary_path)
    return {
        "latest": latest.relative_to(repo_root).as_posix(),
        "operator_summary": summary_path.relative_to(repo_root).as_posix(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m research.qre_basket_operator_action_plan",
        description="Build the read-only basket operator action plan.",
    )
    parser.add_argument("--max-candidates", type=int, default=15)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    report = build_basket_operator_action_plan(max_candidates=args.max_candidates)
    if args.write:
        report["_artifact_paths"] = write_outputs(report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
