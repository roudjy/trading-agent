from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from research import qre_basket_evidence_recovery_plan as recovery_plan


REPORT_KIND: Final[str] = "qre_basket_next_action_queue"
SCHEMA_VERSION: Final[str] = "1.0"
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_basket_next_action_queue")
LATEST_NAME: Final[str] = "latest.json"
OPERATOR_SUMMARY_NAME: Final[str] = "operator_summary.md"
WRITE_PREFIX: Final[str] = "logs/qre_basket_next_action_queue/"


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


def _blocker_rows(report: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = report.get("blocker_rows")
    if not isinstance(rows, list):
        return []
    return [dict(row) for row in rows if isinstance(row, Mapping)]


def build_basket_next_action_queue(
    *,
    repo_root: Path = Path("."),
    max_candidates: int = 15,
) -> dict[str, Any]:
    report = recovery_plan.build_basket_evidence_recovery_plan(
        repo_root=repo_root,
        max_candidates=max_candidates,
    )
    blocker_rows = _blocker_rows(report)
    queue_rows: list[dict[str, Any]] = []
    for row in blocker_rows:
        queue_rows.append(
            {
                "candidate_id": row.get("candidate_id"),
                "symbol": row.get("symbol"),
                "region": row.get("region"),
                "asset_class": row.get("asset_class"),
                "preset_id": row.get("preset_id"),
                "hypothesis_id": row.get("hypothesis_id"),
                "blocker_code": row.get("blocker_code"),
                "blocker_family": row.get("blocker_family"),
                "current_status": row.get("current_status"),
                "exact_next_action": row.get("exact_next_action"),
                "required_artifact": row.get("required_artifact"),
                "safe_action_type": row.get("safe_action_type"),
                "allowed_to_auto_run": False,
                "blocked_by_identity": bool(row.get("blocked_by_identity")),
                "blocked_by_source_cache": bool(row.get("blocked_by_source_cache")),
                "blocked_by_lineage": bool(row.get("blocked_by_lineage")),
                "blocked_by_screening": bool(row.get("blocked_by_screening")),
                "blocked_by_oos": bool(row.get("blocked_by_oos")),
                "evidence_refs": list(row.get("potential_clear_refs") or []),
                "reason_record_refs": dict(row.get("reason_record_refs") or {}),
                "operator_explanation": str(row.get("operator_explanation") or ""),
            }
        )
    queue_rows.sort(
        key=lambda row: (
            str(row.get("symbol") or ""),
            str(row.get("preset_id") or ""),
            str(row.get("blocker_code") or ""),
        )
    )
    action_counts = Counter(str(row["exact_next_action"]) for row in queue_rows)
    blocker_counts = Counter(str(row["blocker_code"]) for row in queue_rows)
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "summary": {
            "row_count": len(queue_rows),
            "blocker_counts": dict(sorted(blocker_counts.items())),
            "exact_next_action_counts": dict(sorted(action_counts.items())),
            "operator_summary": (
                "Deterministic next-action queue enumerates every remaining basket blocker "
                "as a read-only operator review item."
            ),
            "final_recommendation": "basket_next_action_queue_ready" if queue_rows else "basket_next_action_queue_missing",
        },
        "rows": queue_rows,
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
    rows = report.get("rows") if isinstance(report.get("rows"), list) else []
    count_table = _table(
        ["Field", "Count"],
        [
            ["rows", str(summary.get("row_count") or 0)],
            ["collect_screening_evidence", str(summary.get("exact_next_action_counts", {}).get("collect_screening_evidence") or 0)],
            ["collect_oos_evidence", str(summary.get("exact_next_action_counts", {}).get("collect_oos_evidence") or 0)],
            ["expand_basket_coverage", str(summary.get("exact_next_action_counts", {}).get("expand_basket_coverage") or 0)],
            ["materialize_lineage_from_existing_artifacts", str(summary.get("exact_next_action_counts", {}).get("materialize_lineage_from_existing_artifacts") or 0)],
            ["require_identity_resolution", str(summary.get("exact_next_action_counts", {}).get("require_identity_resolution") or 0)],
        ],
    )
    row_table = _table(
        ["Symbol", "Blocker", "Action", "Artifact", "Auto-run"],
        [
            [
                str(row.get("symbol") or ""),
                str(row.get("blocker_code") or ""),
                str(row.get("exact_next_action") or ""),
                str(row.get("required_artifact") or ""),
                str(bool(row.get("allowed_to_auto_run"))).lower(),
            ]
            for row in rows
        ],
    )
    return "\n".join(
        [
            "# QRE Basket Next-Action Queue",
            "",
            "## 1. Korte conclusie",
            f"- {summary.get('operator_summary') or ''}",
            "",
            "## 2. Action counts",
            count_table,
            "",
            "## 3. Queue rows",
            row_table,
        ]
    )


def _validate_write_target(path: Path) -> None:
    if WRITE_PREFIX not in path.as_posix():
        raise ValueError(f"qre_basket_next_action_queue: refusing write outside allowlist: {path!r}")


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
        prog="python -m research.qre_basket_next_action_queue",
        description="Build the read-only basket next-action queue.",
    )
    parser.add_argument("--max-candidates", type=int, default=15)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    report = build_basket_next_action_queue(max_candidates=args.max_candidates)
    if args.write:
        report["_artifact_paths"] = write_outputs(report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
