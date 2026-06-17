from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from research import qre_real_basket_evidence_coverage as evidence_coverage
from research import qre_failure_action_from_basket as failure_action
from research import qre_reason_records_v1 as reason_records


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

KNOWN_OOS_GAP_BLOCKERS: Final[frozenset[str]] = frozenset(
    {
        "oos_evidence_missing",
        "oos_evidence_unknown",
        "no_oos_evidence",
        "insufficient_oos_evidence",
    }
)


def _index_by_candidate(rows: Sequence[Mapping[str, Any]], *, key: str = "candidate_id") -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for row in rows:
        subject_id = str(row.get(key) or "")
        if subject_id and subject_id not in indexed:
            indexed[subject_id] = dict(row)
    return indexed


def _index_reason_records(records: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for record in records:
        subject_id = str(record.get("subject_id") or "")
        if not subject_id:
            continue
        bucket = indexed.setdefault(
            subject_id,
            {"record_ids": [], "record_families": [], "reason_codes": [], "evidence_refs": []},
        )
        for field in ("record_ids", "record_families", "reason_codes", "evidence_refs"):
            values = record.get(field)
            if not isinstance(values, Sequence) or isinstance(values, str | bytes):
                continue
            for value in values:
                text = str(value or "").strip()
                if text and text not in bucket[field]:
                    bucket[field].append(text)
    return indexed


def _table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    head = "| " + " | ".join(headers) + " |"
    divider = "| " + " | ".join(["---"] * len(headers)) + " |"
    body = ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join([head, divider, *body])


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _guarded_alias_bounded_generation_snapshot(repo_root: Path) -> dict[str, Any]:
    payload = _read_json(
        repo_root / "logs" / "qre_guarded_alias_bounded_generation_cascade" / "latest.json"
    )
    if isinstance(payload, dict) and str(payload.get("report_kind") or "") == "qre_guarded_alias_bounded_generation_cascade":
        return payload
    return {"overall_result": "guarded_alias_bounded_generation_cascade_unavailable"}


def _row_closure(row: Mapping[str, Any]) -> dict[str, Any]:
    flags = row.get("evidence_presence")
    if not isinstance(flags, Mapping):
        flags = {}
    missing_taxonomy = list(row.get("missing_evidence_taxonomy") or [])
    reason_record_refs = row.get("reason_record_refs")
    if not isinstance(reason_record_refs, Mapping):
        reason_record_refs = {}
    reason_record_ids = list(reason_record_refs.get("record_ids") or [])
    reason_record_count = len(reason_record_ids)
    reason_record_present = reason_record_count > 0
    failure_action = row.get("failure_action")
    if not isinstance(failure_action, Mapping):
        failure_action = {}
    checklist = [
        {
            "check_id": check_id,
            "passed": bool(flags.get(flag_key)),
        }
        for check_id, flag_key in CHECKLIST_ORDER
    ]
    closure_criteria = {
        "evidence_complete": str(row.get("evidence_completeness_status") or "") == "complete",
        "no_missing_evidence_taxonomy": not missing_taxonomy,
        "reason_records_present": reason_record_present,
        "failure_action_present": bool(failure_action),
    }
    unknown_like = [
        value
        for value in missing_taxonomy
        if "unknown" in str(value) and str(value) not in KNOWN_OOS_GAP_BLOCKERS
    ]
    if all(closure_criteria.values()):
        closure_status = "evidence_complete"
        exact_next_action = "keep_fail_closed"
        operator_explanation = (
            f"{row.get('symbol')} has a closed evidence-complete checklist with durable reason records "
            f"for the current non-execution phase."
        )
    else:
        closure_status = "blocked_not_evidence_complete"
        exact_next_action = str(failure_action.get("recommended_action") or "keep_fail_closed")
        operator_explanation = (
            f"{row.get('symbol')} is not evidence-complete because the exact blockers are: "
            + ", ".join(missing_taxonomy or ["none_recorded_fail_closed"])
            + f"; reason_records={reason_record_count}; failure_action={exact_next_action}."
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
        "closure_criteria": closure_criteria,
        "exact_blockers": missing_taxonomy,
        "unknown_blockers": unknown_like,
        "unknown_blocker_count": len(unknown_like),
        "reason_record_count": reason_record_count,
        "reason_record_ids": reason_record_ids,
        "reason_record_families": list(reason_record_refs.get("record_families") or []),
        "reason_record_evidence_refs": list(reason_record_refs.get("evidence_refs") or []),
        "failure_action": dict(failure_action),
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
    reason_snapshot = reason_records.build_reason_records_snapshot(
        repo_root=repo_root,
        max_candidates=max_candidates,
    )
    failure_report = failure_action.build_failure_action_from_basket(
        repo_root=repo_root,
        max_candidates=max_candidates,
    )
    rows = coverage.get("rows")
    if not isinstance(rows, list):
        rows = []
    reason_rows = reason_snapshot.get("records")
    if not isinstance(reason_rows, list):
        reason_rows = []
    failure_rows = failure_report.get("rows")
    if not isinstance(failure_rows, list):
        failure_rows = []
    reason_index = _index_reason_records([row for row in reason_rows if isinstance(row, Mapping)])
    failure_index = _index_by_candidate([row for row in failure_rows if isinstance(row, Mapping)])
    guarded_report = _guarded_alias_bounded_generation_snapshot(repo_root)
    closure_rows = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        subject_id = str(row.get("candidate_id") or "")
        enriched_row = dict(row)
        enriched_row["reason_record_refs"] = dict(reason_index.get(subject_id) or {})
        enriched_row["failure_action"] = dict(failure_index.get(subject_id) or {})
        closure_rows.append(_row_closure(enriched_row))
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
    reason_record_subject_count = len(reason_index)
    reason_record_coverage_ratio = (
        round(reason_record_subject_count / len(closure_rows), 3) if closure_rows else 0.0
    )
    actionable_failure_action_count = sum(
        1 for row in failure_rows if bool((row.get("actionability") or {}).get("is_actionable"))
    )
    complete_input_rows = [
        row for row in closure_rows if str(row.get("evidence_completeness_status") or "") == "complete"
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "summary": {
            "basket_count": len(closure_rows),
            "evidence_complete_count": complete_count,
            "not_evidence_complete_count": len(closure_rows) - complete_count,
            "reason_record_subject_count": reason_record_subject_count,
            "reason_record_coverage_ratio": reason_record_coverage_ratio,
            "failure_actionable_count": actionable_failure_action_count,
            "closure_status_counts": dict(sorted(closure_counts.items())),
            "exact_blocker_counts": dict(sorted(blocker_counts.items())),
            "unknown_blocker_count": unknown_blocker_count,
            "all_complete_baskets_have_reason_records": all(
                row["closure_status"] != "evidence_complete" or row["reason_record_count"] > 0
                for row in closure_rows
            ),
            "all_input_complete_rows_have_reason_records": all(
                row["reason_record_count"] > 0 for row in complete_input_rows
            ),
            "all_non_complete_baskets_have_exact_blockers": all(
                row["closure_status"] == "evidence_complete" or len(row["exact_blockers"]) > 0
                for row in closure_rows
            ),
            "all_non_complete_baskets_have_no_unknown_blockers": all(
                row["closure_status"] == "evidence_complete" or int(row["unknown_blocker_count"]) == 0
                for row in closure_rows
            ),
            "guarded_alias_bounded_generation_cascade_result": str(guarded_report.get("overall_result") or ""),
            "final_recommendation": (
                "evidence_complete_reason_records_ready"
                if complete_count > 0
                and reason_record_subject_count > 0
                and all(
                    row["closure_status"] != "evidence_complete" or row["reason_record_count"] > 0
                    for row in closure_rows
                )
                else "no_basket_evidence_complete_reason_records_preserved"
            ),
            "operator_summary": (
                "Evidence-complete basket closure proves either that a basket is complete for the current "
                "non-execution phase with durable reason records or that every incomplete basket has an "
                "explicit blocker set with preserved negative results and bounded failure-action mapping."
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
                    ["reason_record_subject_count", str(summary.get("reason_record_subject_count") or 0)],
                    ["reason_record_coverage_ratio", str(summary.get("reason_record_coverage_ratio") or 0.0)],
                    ["failure_actionable_count", str(summary.get("failure_actionable_count") or 0)],
                    ["unknown_blocker_count", str(summary.get("unknown_blocker_count") or 0)],
                    [
                        "all_non_complete_baskets_have_exact_blockers",
                        str(summary.get("all_non_complete_baskets_have_exact_blockers") or False),
                    ],
                    [
                        "all_complete_baskets_have_reason_records",
                        str(summary.get("all_complete_baskets_have_reason_records") or False),
                    ],
                    [
                        "all_input_complete_rows_have_reason_records",
                        str(summary.get("all_input_complete_rows_have_reason_records") or False),
                    ],
                    [
                        "all_non_complete_baskets_have_no_unknown_blockers",
                        str(summary.get("all_non_complete_baskets_have_no_unknown_blockers") or False),
                    ],
                    [
                        "guarded_alias_bounded_generation_cascade_result",
                        str(summary.get("guarded_alias_bounded_generation_cascade_result") or ""),
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
