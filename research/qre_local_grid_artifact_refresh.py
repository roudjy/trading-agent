from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final


REPORT_KIND: Final[str] = "qre_local_grid_artifact_refresh"
SCHEMA_VERSION: Final[str] = "1.0"
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_local_grid_artifact_refresh")
LATEST_NAME: Final[str] = "latest.json"
OPERATOR_SUMMARY_NAME: Final[str] = "operator_summary.md"
WRITE_PREFIX: Final[str] = "logs/qre_local_grid_artifact_refresh/"
GRID_RUNS_DIR: Final[Path] = Path("research/controlled_discovery_grid_runs")
MATERIALIZATION_PATH: Final[Path] = Path(
    "logs/qre_discovery_basket_grid_evidence_materialization/latest.json"
)
LINEAGE_BRIDGE_PATH: Final[Path] = Path(
    "logs/qre_grid_candidate_campaign_lineage_bridge/latest.json"
)


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    head = "| " + " | ".join(headers) + " |"
    divider = "| " + " | ".join(["---"] * len(headers)) + " |"
    body = ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join([head, divider, *body])


def _grid_directory_summary(repo_root: Path) -> dict[str, Any]:
    path = repo_root / GRID_RUNS_DIR
    if not path.exists():
        return {
            "path": GRID_RUNS_DIR.as_posix(),
            "directory_status": "missing",
            "run_count": 0,
            "run_ids": [],
            "latest_run_id": None,
        }
    if not path.is_dir():
        return {
            "path": GRID_RUNS_DIR.as_posix(),
            "directory_status": "invalid",
            "run_count": 0,
            "run_ids": [],
            "latest_run_id": None,
        }
    run_dirs = sorted(child.name for child in path.iterdir() if child.is_dir())
    return {
        "path": GRID_RUNS_DIR.as_posix(),
        "directory_status": "present",
        "run_count": len(run_dirs),
        "run_ids": run_dirs,
        "latest_run_id": run_dirs[-1] if run_dirs else None,
    }


def _evidence_summary(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    payload = payload if isinstance(payload, Mapping) else {}
    summary = payload.get("summary")
    if not isinstance(summary, Mapping):
        summary = {}
    return {
        "input_basket_count": int(payload.get("input_basket_count") or 0),
        "grid_runs_scanned_count": int(payload.get("grid_runs_scanned_count") or 0),
        "baskets_with_matched_grid_rows": int(payload.get("baskets_with_matched_grid_rows") or 0),
        "next_action_counts": dict(payload.get("next_action_counts") or {}),
        "closest_baskets_to_readiness": list(payload.get("closest_baskets_to_readiness") or []),
        "operator_summary": summary.get("operator_summary"),
    }


def _lineage_summary(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    payload = payload if isinstance(payload, Mapping) else {}
    summary = payload.get("summary")
    if not isinstance(summary, Mapping):
        summary = {}
    return {
        "basket_count": int(summary.get("basket_count") or 0),
        "lineage_bridge_status_counts": dict(summary.get("lineage_bridge_status_counts") or {}),
        "next_action_counts": dict(summary.get("next_action_counts") or {}),
    }


def _rows(summary: Mapping[str, Any], evidence: Mapping[str, Any], lineage: Mapping[str, Any]) -> list[dict[str, Any]]:
    grid_status = str(summary.get("directory_status") or "unknown_fail_closed")
    evidence_actions = evidence.get("next_action_counts") or {}
    lineage_actions = lineage.get("next_action_counts") or {}

    rows: list[dict[str, Any]] = [
        {
            "surface": "controlled_grid_runs_directory",
            "status": grid_status,
            "blocking_reason": (
                "grid_runs_directory_missing"
                if grid_status == "missing"
                else "grid_runs_directory_invalid"
                if grid_status == "invalid"
                else "none"
            ),
            "exact_next_action": (
                "restore_or_copy_grid_run_artifacts"
                if grid_status == "missing"
                else "repair_grid_run_directory"
                if grid_status == "invalid"
                else "keep_fail_closed"
            ),
            "operator_explanation": (
                "Local controlled discovery grid run artifacts are absent."
                if grid_status == "missing"
                else "Local controlled discovery grid run path exists but is not a valid directory."
                if grid_status == "invalid"
                else "Local controlled discovery grid run directory is present."
            ),
        },
        {
            "surface": "grid_evidence_materialization",
            "status": (
                "blocked_no_local_grid_runs"
                if int(evidence.get("grid_runs_scanned_count") or 0) == 0
                else "grid_runs_detected"
            ),
            "blocking_reason": (
                "no_grid_runs_scanned"
                if int(evidence.get("grid_runs_scanned_count") or 0) == 0
                else "none"
            ),
            "exact_next_action": (
                "run_or_restore_controlled_grid"
                if "run_controlled_discovery_grid" in evidence_actions
                else "keep_fail_closed"
            ),
            "operator_explanation": (
                "Grid evidence materialization sees no scanned local grid runs."
                if int(evidence.get("grid_runs_scanned_count") or 0) == 0
                else "Grid evidence materialization sees local grid runs."
            ),
        },
        {
            "surface": "grid_lineage_bridge",
            "status": (
                "blocked_no_grid_match"
                if "restore_or_run_grid_artifacts" in lineage_actions
                else "lineage_materialized_or_partially_visible"
            ),
            "blocking_reason": (
                "no_local_grid_match"
                if "restore_or_run_grid_artifacts" in lineage_actions
                else "none"
            ),
            "exact_next_action": (
                "restore_or_run_grid_artifacts"
                if "restore_or_run_grid_artifacts" in lineage_actions
                else "keep_fail_closed"
            ),
            "operator_explanation": (
                "Lineage bridge remains blocked because no local grid match is available."
                if "restore_or_run_grid_artifacts" in lineage_actions
                else "Lineage bridge has local grid matches to reason over."
            ),
        },
    ]
    return rows


def build_local_grid_artifact_refresh(*, repo_root: Path = Path(".")) -> dict[str, Any]:
    grid_summary = _grid_directory_summary(repo_root)
    evidence_payload = _read_json(repo_root / MATERIALIZATION_PATH)
    lineage_payload = _read_json(repo_root / LINEAGE_BRIDGE_PATH)
    evidence = _evidence_summary(evidence_payload)
    lineage = _lineage_summary(lineage_payload)
    rows = _rows(grid_summary, evidence, lineage)
    status_counts = Counter(str(row["status"]) for row in rows)
    next_action_counts = Counter(str(row["exact_next_action"]) for row in rows)
    missing_grid_runs = grid_summary["directory_status"] != "present" or int(grid_summary["run_count"]) == 0
    refresh_plan = [
        {
            "step": 1,
            "action": "locate_historical_grid_artifacts",
            "required": True,
            "manual_human_needed": True,
            "status": "pending" if missing_grid_runs else "not_required",
            "operator_explanation": (
                "Locate prior controlled discovery grid run artifacts from VPS or another governed source."
            ),
        },
        {
            "step": 2,
            "action": "copy_or_restore_grid_run_directory",
            "required": True,
            "manual_human_needed": True,
            "status": "pending" if missing_grid_runs else "not_required",
            "operator_explanation": (
                "Restore the missing research/controlled_discovery_grid_runs/ directory without editing results."
            ),
        },
        {
            "step": 3,
            "action": "rerun_materialization_and_lineage_reports",
            "required": True,
            "manual_human_needed": False,
            "status": "pending" if missing_grid_runs else "ready",
            "operator_explanation": (
                "Recompute local grid evidence and lineage reports after artifacts exist."
            ),
        },
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "summary": {
            "grid_runs_directory_status": grid_summary["directory_status"],
            "grid_run_count": int(grid_summary["run_count"]),
            "latest_grid_run_id": grid_summary["latest_run_id"],
            "grid_runs_scanned_count": int(evidence["grid_runs_scanned_count"]),
            "baskets_with_matched_grid_rows": int(evidence["baskets_with_matched_grid_rows"]),
            "lineage_basket_count": int(lineage["basket_count"]),
            "status_counts": dict(sorted(status_counts.items())),
            "next_action_counts": dict(sorted(next_action_counts.items())),
            "missing_local_grid_artifacts": missing_grid_runs,
            "operator_summary": (
                "Local controlled-grid artifact refresh is plan-only: it makes missing or stale local grid artifacts "
                "explicit and lists the governed manual steps required before readiness reports can improve."
            ),
        },
        "grid_directory": grid_summary,
        "evidence_materialization": evidence,
        "lineage_bridge": lineage,
        "rows": rows,
        "refresh_plan": refresh_plan,
        "safety_invariants": {
            "read_only": True,
            "does_not_run_grid": True,
            "does_not_mutate_grid_artifacts": True,
            "does_not_mutate_frozen_contracts": True,
            "paper_shadow_live_forbidden": True,
            "broker_risk_execution_forbidden": True,
            "promotion_forbidden": True,
        },
    }


def render_operator_summary(report: Mapping[str, Any]) -> str:
    summary = report.get("summary") or {}
    rows = report.get("rows") if isinstance(report.get("rows"), list) else []
    refresh_plan = report.get("refresh_plan") if isinstance(report.get("refresh_plan"), list) else []
    return "\n".join(
        [
            "# QRE Local Controlled Grid Artifact Refresh",
            "",
            f"- {summary.get('operator_summary') or ''}",
            "",
            "## 1. Current State",
            _table(
                ["Field", "Value"],
                [
                    ["grid_runs_directory_status", str(summary.get("grid_runs_directory_status") or "")],
                    ["grid_run_count", str(summary.get("grid_run_count") or 0)],
                    ["latest_grid_run_id", str(summary.get("latest_grid_run_id") or "")],
                    ["grid_runs_scanned_count", str(summary.get("grid_runs_scanned_count") or 0)],
                    ["baskets_with_matched_grid_rows", str(summary.get("baskets_with_matched_grid_rows") or 0)],
                    ["missing_local_grid_artifacts", str(summary.get("missing_local_grid_artifacts") or False)],
                ],
            ),
            "",
            "## 2. Blocking Surfaces",
            _table(
                ["Surface", "Status", "Next action", "Explanation"],
                [
                    [
                        str(row.get("surface") or ""),
                        str(row.get("status") or ""),
                        str(row.get("exact_next_action") or ""),
                        str(row.get("operator_explanation") or ""),
                    ]
                    for row in rows
                ],
            ),
            "",
            "## 3. Refresh Plan",
            _table(
                ["Step", "Action", "Status", "Manual human needed", "Explanation"],
                [
                    [
                        str(row.get("step") or ""),
                        str(row.get("action") or ""),
                        str(row.get("status") or ""),
                        str(row.get("manual_human_needed") or False),
                        str(row.get("operator_explanation") or ""),
                    ]
                    for row in refresh_plan
                ],
            ),
            "",
        ]
    )


def _validate_write_target(path: Path) -> None:
    if WRITE_PREFIX not in path.as_posix():
        raise ValueError(f"qre_local_grid_artifact_refresh: refusing write outside allowlist: {path!r}")


def write_outputs(report: Mapping[str, Any], *, repo_root: Path = Path(".")) -> dict[str, str]:
    base = repo_root / DEFAULT_OUTPUT_DIR
    base.mkdir(parents=True, exist_ok=True)
    latest = base / LATEST_NAME
    summary_path = base / OPERATOR_SUMMARY_NAME
    for target in (latest, summary_path):
        _validate_write_target(target)
    tmp_json = latest.with_suffix(latest.suffix + ".tmp")
    tmp_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp_json, latest)
    tmp_md = summary_path.with_suffix(summary_path.suffix + ".tmp")
    tmp_md.write_text(render_operator_summary(report), encoding="utf-8")
    os.replace(tmp_md, summary_path)
    return {
        "latest": latest.relative_to(repo_root).as_posix(),
        "operator_summary": summary_path.relative_to(repo_root).as_posix(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m research.qre_local_grid_artifact_refresh",
        description="Report local controlled-grid artifact availability and refresh plan.",
    )
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    report = build_local_grid_artifact_refresh()
    if args.write:
        report["_artifact_paths"] = write_outputs(report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
