from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from research import qre_real_basket_evidence_coverage as evidence_coverage


REPORT_KIND: Final[str] = "qre_evidence_complete_basket_closure"
SCHEMA_VERSION: Final[str] = "1.0"
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_evidence_complete_basket_closure")
LATEST_NAME: Final[str] = "latest.json"
OPERATOR_SUMMARY_NAME: Final[str] = "operator_summary.md"
WRITE_PREFIX: Final[str] = "logs/qre_evidence_complete_basket_closure/"


CHECKLIST_ORDER: Final[tuple[tuple[str, str], ...]] = (
    ("source_identity_ready", "source_identity_ready"),
    ("source_quality_ready", "source_quality_ready"),
    ("cache_ready", "cache_ready"),
    ("screening_evidence_present", "screening_evidence_present"),
    ("oos_evidence_known", "oos_evidence_known"),
    ("campaign_lineage_present", "campaign_lineage_present"),
    ("candidate_lineage_present", "candidate_lineage_present"),
)


def _table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    head = "| " + " | ".join(headers) + " |"
    divider = "| " + " | ".join(["---"] * len(headers)) + " |"
    body = ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join([head, divider, *body])


def _row_closure(row: Mapping[str, Any]) -> dict[str, Any]:
    flags = row.get("evidence_presence")
    if not isinstance(flags, Mapping):
        flags = {}
    missing_taxonomy = list(row.get("missing_evidence_taxonomy") or [])
    checklist = [
        {
            "check_id": check_id,
            "passed": bool(flags.get(flag_key)),
        }
        for check_id, flag_key in CHECKLIST_ORDER
    ]
    unknown_like = [value for value in missing_taxonomy if "unknown" in str(value)]
    if str(row.get("evidence_completeness_status") or "") == "complete" and not missing_taxonomy:
        closure_status = "evidence_complete"
        exact_next_action = "keep_fail_closed"
        operator_explanation = (
            f"{row.get('symbol')} has a closed evidence-complete checklist for the current non-execution phase."
        )
    else:
        closure_status = "blocked_not_evidence_complete"
        if "source_identity_blocked" in missing_taxonomy:
            exact_next_action = "require_identity_resolution"
        elif any(
            blocker in missing_taxonomy
            for blocker in (
                "source_quality_rows_missing",
                "source_quality_not_ready",
                "cache_coverage_missing",
                "cache_coverage_not_ready",
            )
        ):
            exact_next_action = "restore_or_harden_source_cache_sidecars"
        elif any(
            blocker in missing_taxonomy
            for blocker in ("screening_evidence_missing", "oos_evidence_missing", "oos_evidence_unknown")
        ):
            exact_next_action = "restore_or_run_grid_artifacts"
        elif any(
            blocker in missing_taxonomy
            for blocker in ("campaign_lineage_missing", "candidate_lineage_missing")
        ):
            exact_next_action = "close_lineage_gaps"
        else:
            exact_next_action = "keep_fail_closed"
        operator_explanation = (
            f"{row.get('symbol')} is not evidence-complete because the exact blockers are: "
            + ", ".join(missing_taxonomy or ["none_recorded_fail_closed"])
            + "."
        )
    return {
        "candidate_id": row.get("candidate_id"),
        "symbol": row.get("symbol"),
        "preset_id": row.get("preset_id"),
        "diagnosis_class": row.get("diagnosis_class"),
        "evidence_completeness_score_pct": int(row.get("evidence_completeness_score_pct") or 0),
        "evidence_completeness_status": row.get("evidence_completeness_status"),
        "closure_status": closure_status,
        "checklist": checklist,
        "exact_blockers": missing_taxonomy,
        "unknown_blockers": unknown_like,
        "unknown_blocker_count": len(unknown_like),
        "follow_up": row.get("follow_up"),
        "exact_next_action": exact_next_action,
        "operator_explanation": operator_explanation,
    }


def build_evidence_complete_basket_closure(
    *,
    repo_root: Path = Path("."),
    max_candidates: int = 15,
) -> dict[str, Any]:
    coverage = evidence_coverage.build_real_basket_evidence_coverage(
        repo_root=repo_root,
        max_candidates=max_candidates,
    )
    rows = coverage.get("rows")
    if not isinstance(rows, list):
        rows = []
    closure_rows = [_row_closure(row) for row in rows if isinstance(row, Mapping)]
    closure_rows.sort(
        key=lambda row: (
            str(row["closure_status"]) != "evidence_complete",
            -int(row["evidence_completeness_score_pct"]),
            str(row["symbol"]),
        )
    )
    closure_counts = Counter(str(row["closure_status"]) for row in closure_rows)
    blocker_counts = Counter(
        blocker for row in closure_rows for blocker in row.get("exact_blockers", [])
    )
    unknown_blocker_count = sum(int(row["unknown_blocker_count"]) for row in closure_rows)
    complete_count = sum(1 for row in closure_rows if row["closure_status"] == "evidence_complete")
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "summary": {
            "basket_count": len(closure_rows),
            "evidence_complete_count": complete_count,
            "not_evidence_complete_count": len(closure_rows) - complete_count,
            "closure_status_counts": dict(sorted(closure_counts.items())),
            "exact_blocker_counts": dict(sorted(blocker_counts.items())),
            "unknown_blocker_count": unknown_blocker_count,
            "all_non_complete_baskets_have_exact_blockers": all(
                row["closure_status"] == "evidence_complete" or len(row["exact_blockers"]) > 0
                for row in closure_rows
            ),
            "all_non_complete_baskets_have_no_unknown_blockers": all(
                row["closure_status"] == "evidence_complete" or int(row["unknown_blocker_count"]) == 0
                for row in closure_rows
            ),
            "final_recommendation": (
                "at_least_one_basket_evidence_complete"
                if complete_count > 0
                else "no_basket_evidence_complete_exact_blockers_enumerated"
            ),
            "operator_summary": (
                "Evidence-complete basket closure proves either that a basket is complete for the current "
                "non-execution phase or that every incomplete basket has an explicit blocker set with no hidden unlock."
            ),
        },
        "rows": closure_rows,
        "safety_invariants": {
            "read_only": True,
            "does_not_mutate_campaigns": True,
            "does_not_mutate_frozen_contracts": True,
            "paper_shadow_live_forbidden": True,
            "broker_risk_execution_forbidden": True,
            "promotion_forbidden": True,
        },
    }


def render_operator_summary(report: Mapping[str, Any]) -> str:
    summary = report.get("summary") or {}
    rows = report.get("rows") if isinstance(report.get("rows"), list) else []
    return "\n".join(
        [
            "# QRE Evidence Complete Basket Closure",
            "",
            f"- {summary.get('operator_summary') or ''}",
            "",
            "## 1. Closure Summary",
            _table(
                ["Field", "Value"],
                [
                    ["basket_count", str(summary.get("basket_count") or 0)],
                    ["evidence_complete_count", str(summary.get("evidence_complete_count") or 0)],
                    ["unknown_blocker_count", str(summary.get("unknown_blocker_count") or 0)],
                    [
                        "all_non_complete_baskets_have_exact_blockers",
                        str(summary.get("all_non_complete_baskets_have_exact_blockers") or False),
                    ],
                    [
                        "all_non_complete_baskets_have_no_unknown_blockers",
                        str(summary.get("all_non_complete_baskets_have_no_unknown_blockers") or False),
                    ],
                    ["final_recommendation", str(summary.get("final_recommendation") or "")],
                ],
            ),
            "",
            "## 2. Basket Closure Rows",
            _table(
                ["Symbol", "Preset", "Status", "Score", "Next action", "Exact blockers"],
                [
                    [
                        str(row.get("symbol") or ""),
                        str(row.get("preset_id") or ""),
                        str(row.get("closure_status") or ""),
                        str(row.get("evidence_completeness_score_pct") or 0),
                        str(row.get("exact_next_action") or ""),
                        ",".join(str(value) for value in row.get("exact_blockers") or []) or "none",
                    ]
                    for row in rows
                ],
            ),
            "",
        ]
    )


def _validate_write_target(path: Path) -> None:
    if WRITE_PREFIX not in path.as_posix():
        raise ValueError(f"qre_evidence_complete_basket_closure: refusing write outside allowlist: {path!r}")


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
        prog="python -m research.qre_evidence_complete_basket_closure",
        description="Close evidence completeness per basket with exact blockers.",
    )
    parser.add_argument("--max-candidates", type=int, default=15)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    report = build_evidence_complete_basket_closure(max_candidates=args.max_candidates)
    if args.write:
        report["_artifact_paths"] = write_outputs(report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
