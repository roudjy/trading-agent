from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from research import qre_local_grid_artifact_refresh as local_grid_refresh
from research import qre_pre_shadow_paper_research_readiness as pre_shadow_readiness


REPORT_KIND: Final[str] = "qre_targeted_readiness_rerun"
SCHEMA_VERSION: Final[str] = "1.0"
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_targeted_readiness_rerun")
LATEST_NAME: Final[str] = "latest.json"
OPERATOR_SUMMARY_NAME: Final[str] = "operator_summary.md"
WRITE_PREFIX: Final[str] = "logs/qre_targeted_readiness_rerun/"
PERSISTED_READINESS_PATH: Final[Path] = Path("logs/qre_pre_shadow_paper_research_readiness/latest.json")


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


def _metric(summary: Mapping[str, Any], key: str, default: Any) -> Any:
    return summary.get(key, default)


def _delta_rows(
    persisted: Mapping[str, Any],
    current: Mapping[str, Any],
) -> list[dict[str, Any]]:
    keys = [
        "readiness_state",
        "final_recommendation",
        "source_readiness_linked",
        "candidate_blockers_explainable",
        "oos_blockers_explainable",
        "routing_evidence_backed",
        "sampling_evidence_backed",
        "trusted_loop_maturity_state",
    ]
    rows: list[dict[str, Any]] = []
    for key in keys:
        before = _metric(persisted, key, None)
        after = _metric(current, key, None)
        rows.append(
            {
                "metric": key,
                "before": before,
                "after": after,
                "changed": before != after,
            }
        )
    return rows


def _focus_rows(
    current_report: Mapping[str, Any],
    grid_refresh: Mapping[str, Any],
) -> list[dict[str, Any]]:
    current_summary = current_report.get("summary") if isinstance(current_report, Mapping) else {}
    current_supporting = (
        current_report.get("supporting_reports") if isinstance(current_report, Mapping) else {}
    )
    coverage = current_supporting.get("coverage") if isinstance(current_supporting, Mapping) else {}
    source_cache = (
        current_supporting.get("source_cache_materialization")
        if isinstance(current_supporting, Mapping)
        else {}
    )
    grid_summary = grid_refresh.get("summary") if isinstance(grid_refresh, Mapping) else {}
    focus_rows: list[dict[str, Any]] = []

    if bool(grid_summary.get("missing_local_grid_artifacts")):
        focus_rows.append(
            {
                "focus_area": "controlled_grid_artifacts",
                "current_status": "blocked_missing_local_artifacts",
                "exact_next_action": "restore_or_copy_grid_run_artifacts",
                "blocking_reason": "missing_local_grid_artifacts",
                "operator_explanation": (
                    "Local readiness cannot move past grid evidence blockers until controlled-grid artifacts exist locally."
                ),
            }
        )
    if not bool(current_summary.get("candidate_blockers_explainable")):
        focus_rows.append(
            {
                "focus_area": "candidate_blocker_explainability",
                "current_status": "incomplete",
                "exact_next_action": "close_candidate_blocker_gaps",
                "blocking_reason": "candidate_blockers_not_fully_explainable",
                "operator_explanation": (
                    "Candidate blocker explanations remain incomplete in the current local readiness pass."
                ),
            }
        )
    if not bool(current_summary.get("source_readiness_linked")):
        missing = list(source_cache.get("missing_sidecars") or [])
        present_not_ready = list(source_cache.get("present_not_ready_sidecars") or [])
        blocking_reason = (
            "missing_source_cache_sidecars"
            if missing
            else "source_cache_sidecars_present_not_ready"
            if present_not_ready
            else "source_ready_basket_pct_zero"
        )
        focus_rows.append(
            {
                "focus_area": "source_cache_linkage",
                "current_status": "not_linked",
                "exact_next_action": "restore_or_harden_source_cache_sidecars",
                "blocking_reason": blocking_reason,
                "operator_explanation": (
                    "Source/cache linkage is still not sufficient for readiness, even after the local read-only refresh."
                ),
            }
        )
    if int(coverage.get("screening_evidence_rows_total") or 0) == 0:
        focus_rows.append(
            {
                "focus_area": "screening_and_oos_evidence",
                "current_status": "grid_evidence_not_visible",
                "exact_next_action": "rerun_readiness_after_grid_restoration",
                "blocking_reason": "screening_evidence_rows_total_zero",
                "operator_explanation": (
                    "No grid-backed screening evidence is currently visible to readiness in this local checkout."
                ),
            }
        )
    return focus_rows


def build_targeted_readiness_rerun(
    *,
    repo_root: Path = Path("."),
    max_candidates: int = 15,
) -> dict[str, Any]:
    persisted_payload = _read_json(repo_root / PERSISTED_READINESS_PATH) or {}
    persisted_summary = persisted_payload.get("summary")
    if not isinstance(persisted_summary, Mapping):
        persisted_summary = {}

    current_report = pre_shadow_readiness.build_pre_shadow_paper_research_readiness(
        repo_root=repo_root,
        max_candidates=max_candidates,
    )
    current_summary = current_report.get("summary")
    if not isinstance(current_summary, Mapping):
        current_summary = {}
    grid_refresh = local_grid_refresh.build_local_grid_artifact_refresh(repo_root=repo_root)
    delta_rows = _delta_rows(persisted_summary, current_summary)
    focus_rows = _focus_rows(current_report, grid_refresh)
    changed_count = sum(1 for row in delta_rows if bool(row["changed"]))
    focus_counts = Counter(str(row["blocking_reason"]) for row in focus_rows)

    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "summary": {
            "persisted_report_present": bool(persisted_payload),
            "targeted_local_refresh_executed": True,
            "changed_metric_count": changed_count,
            "focus_row_count": len(focus_rows),
            "focus_blocking_reason_counts": dict(sorted(focus_counts.items())),
            "persisted_readiness_state": persisted_summary.get("readiness_state"),
            "current_readiness_state": current_summary.get("readiness_state"),
            "persisted_final_recommendation": persisted_summary.get("final_recommendation"),
            "current_final_recommendation": current_summary.get("final_recommendation"),
            "operator_summary": (
                "Targeted readiness rerun recomputes the current local pre-shadow readiness view without running any "
                "grid campaign, then turns the delta versus the persisted report into explicit next actions."
            ),
        },
        "persisted_summary": dict(persisted_summary),
        "current_summary": dict(current_summary),
        "delta_rows": delta_rows,
        "focus_rows": focus_rows,
        "grid_refresh_summary": grid_refresh.get("summary") or {},
        "safety_invariants": {
            "read_only": True,
            "does_not_run_grid": True,
            "does_not_mutate_frozen_contracts": True,
            "paper_shadow_live_forbidden": True,
            "broker_risk_execution_forbidden": True,
            "promotion_forbidden": True,
        },
    }


def render_operator_summary(report: Mapping[str, Any]) -> str:
    summary = report.get("summary") or {}
    delta_rows = report.get("delta_rows") if isinstance(report.get("delta_rows"), list) else []
    focus_rows = report.get("focus_rows") if isinstance(report.get("focus_rows"), list) else []
    return "\n".join(
        [
            "# QRE Targeted Readiness Rerun",
            "",
            f"- {summary.get('operator_summary') or ''}",
            "",
            "## 1. Rerun Status",
            _table(
                ["Field", "Value"],
                [
                    ["persisted_report_present", str(summary.get("persisted_report_present") or False)],
                    ["targeted_local_refresh_executed", str(summary.get("targeted_local_refresh_executed") or False)],
                    ["changed_metric_count", str(summary.get("changed_metric_count") or 0)],
                    ["persisted_readiness_state", str(summary.get("persisted_readiness_state") or "")],
                    ["current_readiness_state", str(summary.get("current_readiness_state") or "")],
                ],
            ),
            "",
            "## 2. Key Deltas",
            _table(
                ["Metric", "Before", "After", "Changed"],
                [
                    [
                        str(row.get("metric") or ""),
                        str(row.get("before") or ""),
                        str(row.get("after") or ""),
                        str(row.get("changed") or False),
                    ]
                    for row in delta_rows
                ],
            ),
            "",
            "## 3. Focus Areas",
            _table(
                ["Focus area", "Status", "Next action", "Blocking reason"],
                [
                    [
                        str(row.get("focus_area") or ""),
                        str(row.get("current_status") or ""),
                        str(row.get("exact_next_action") or ""),
                        str(row.get("blocking_reason") or ""),
                    ]
                    for row in focus_rows
                ],
            ),
            "",
        ]
    )


def _validate_write_target(path: Path) -> None:
    if WRITE_PREFIX not in path.as_posix():
        raise ValueError(f"qre_targeted_readiness_rerun: refusing write outside allowlist: {path!r}")


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
        prog="python -m research.qre_targeted_readiness_rerun",
        description="Recompute local QRE readiness and report deterministic deltas.",
    )
    parser.add_argument("--max-candidates", type=int, default=15)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    report = build_targeted_readiness_rerun(max_candidates=args.max_candidates)
    if args.write:
        report["_artifact_paths"] = write_outputs(report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
