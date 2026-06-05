from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


SUMMARY_FILENAME = "summary_latest.v1.json"
OPERATOR_SUMMARY_FILENAME = "operator_summary.md"
RESULTS_FILENAME = "combination_results.v1.jsonl"
OOS_EVIDENCE_OUTCOME = "sufficient_oos_evidence"
UNKNOWN_REQUIRES_ARTIFACT_INSPECTION = "unknown_requires_artifact_inspection"


def _table(headers: list[str], rows: list[list[str]]) -> str:
    head = "| " + " | ".join(headers) + " |"
    divider = "| " + " | ".join(["---"] * len(headers)) + " |"
    body = ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join([head, divider, *body])


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text:
            continue
        payload = json.loads(text)
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def _latest_result_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    latest_by_sequence: dict[int, dict[str, Any]] = {}
    ordered_sequences: list[int] = []
    for row in rows:
        sequence_number = int(row.get("sequence_number") or 0)
        if sequence_number not in latest_by_sequence:
            ordered_sequences.append(sequence_number)
        latest_by_sequence[sequence_number] = row
    return [latest_by_sequence[sequence] for sequence in ordered_sequences]


def _group_counts(rows: list[dict[str, Any]], field: str) -> list[dict[str, Any]]:
    counts: defaultdict[str, int] = defaultdict(int)
    for row in rows:
        counts[str(row.get(field) or "unknown")] += 1
    return [
        {"value": key, "count": counts[key]}
        for key in sorted(counts)
    ]


def _top_rows(
    rows: list[dict[str, Any]],
    *,
    predicate: Any,
) -> list[dict[str, Any]]:
    selected = [row for row in rows if predicate(row)]
    selected.sort(
        key=lambda row: (
            float(row.get("oos_trades") or 0),
            float(row.get("trades_total") or 0),
            -int(row.get("sequence_number") or 0),
        ),
        reverse=True,
    )
    return [
        {
            "sequence_number": int(row.get("sequence_number") or 0),
            "instrument_symbol": str(row.get("instrument_symbol") or ""),
            "behavior_preset_id": str(row.get("behavior_preset_id") or ""),
            "trades_total": row.get("trades_total"),
            "oos_trades": row.get("oos_trades"),
            "criteria_status": row.get("criteria_status"),
        }
        for row in selected[:10]
    ]


def _coerce_number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _criteria_failure_classes(criteria_status: Any) -> list[str]:
    if criteria_status is None:
        return []
    classes: list[str] = []
    for token in str(criteria_status).split(","):
        item = token.strip()
        if not item:
            continue
        if item in {"promotion_allowed", "criteria_passed"}:
            continue
        classes.append(item)
    return classes


def _metric_consistency_diagnostics(row: dict[str, Any]) -> dict[str, Any]:
    trades_total = _coerce_number(row.get("trades_total"))
    oos_trades = _coerce_number(row.get("oos_trades"))
    hd_trades = _coerce_number(row.get("hd_trades"))
    warnings: list[str] = []
    status = "consistent"
    consistency = "consistent"
    if trades_total is None and (oos_trades is not None or hd_trades is not None):
        warnings.append("missing_total_trade_metric")
        status = "inconsistent"
        consistency = "missing_total_trade_metric"
    elif (
        trades_total is not None
        and oos_trades is not None
        and hd_trades is not None
        and (oos_trades + hd_trades) > trades_total + 0.5
    ):
        warnings.append("oos_hd_exceeds_trades_total")
        status = "inconsistent"
        consistency = "oos_hd_exceeds_trades_total"
    elif trades_total is not None and oos_trades is not None and oos_trades > trades_total + 0.5:
        warnings.append("oos_trades_exceeds_trades_total")
        status = "inconsistent"
        consistency = "oos_trades_exceeds_trades_total"
    elif trades_total is not None and hd_trades is not None and hd_trades > trades_total + 0.5:
        warnings.append("hd_trades_exceeds_trades_total")
        status = "inconsistent"
        consistency = "hd_trades_exceeds_trades_total"

    return {
        "trades_total": trades_total,
        "oos_trades": oos_trades,
        "hd_trades": hd_trades,
        "trades_total_vs_oos_hd_consistency": consistency,
        "metric_consistency_status": status,
        "metric_consistency_warnings": warnings,
    }


def _artifact_status(row: dict[str, Any]) -> str:
    artifact_paths = row.get("artifact_paths")
    has_artifact_paths = isinstance(artifact_paths, dict) and bool(artifact_paths)
    has_result_path = bool(str(row.get("result_path") or "").strip())
    if has_artifact_paths or has_result_path:
        return "artifacts_present"
    return "missing_artifacts"


def _source_identity_blocker(row: dict[str, Any]) -> str | None:
    blocker_class = str(row.get("source_identity_blocker_class") or "").strip()
    if blocker_class:
        return blocker_class
    source_identity_status = str(row.get("source_identity_status") or "").strip()
    provider_symbol_status = str(row.get("provider_symbol_status") or "").strip()
    if source_identity_status == "missing_provider_symbol":
        return "source_identity_missing_provider_symbol"
    if provider_symbol_status == "candidate_alias_requires_verification":
        return "source_identity_candidate_alias_unverified"
    if provider_symbol_status == "provider_lookup_failed":
        return "source_identity_provider_lookup_failed"
    return None


def _derive_row_diagnostics(row: dict[str, Any]) -> dict[str, Any]:
    diagnostic = dict(row)
    metric = _metric_consistency_diagnostics(row)
    diagnostic.update(metric)
    diagnostic["criteria_failure_classes"] = _criteria_failure_classes(
        row.get("criteria_status")
    )
    diagnostic["artifact_status"] = _artifact_status(row)
    diagnostic["source_identity_blocker_class"] = _source_identity_blocker(row)

    blocker_class = str(row.get("blocker_class") or "").strip()
    outcome_class = str(row.get("outcome_class") or "unknown").strip() or "unknown"
    promotion_candidate = bool(row.get("promotion_candidate"))
    oos_blocker = None
    if outcome_class == OOS_EVIDENCE_OUTCOME and not promotion_candidate:
        if metric["metric_consistency_status"] != "consistent":
            oos_blocker = "oos_evidence_metric_inconsistent"
        elif blocker_class == "degenerate_no_survivors":
            oos_blocker = "oos_evidence_degenerate_no_survivors"
        elif diagnostic["artifact_status"] == "missing_artifacts":
            oos_blocker = "oos_evidence_missing_artifacts"
        elif diagnostic["criteria_failure_classes"]:
            oos_blocker = "oos_evidence_no_promotion_due_to_criteria"
        elif blocker_class:
            oos_blocker = "oos_evidence_quality_failed"
        else:
            oos_blocker = "oos_evidence_unknown_reason"
    diagnostic["oos_evidence_blocker_class"] = oos_blocker
    diagnostic["primary_blocker"] = (
        oos_blocker
        or blocker_class
        or diagnostic["source_identity_blocker_class"]
        or UNKNOWN_REQUIRES_ARTIFACT_INSPECTION
    )
    diagnostic["follow_up"] = (
        "inspect_metric_consistency"
        if oos_blocker == "oos_evidence_metric_inconsistent"
        else "review_criteria_failures"
        if oos_blocker == "oos_evidence_no_promotion_due_to_criteria"
        else "inspect_missing_artifacts"
        if oos_blocker == "oos_evidence_missing_artifacts"
        else "resolve_source_identity"
        if diagnostic["source_identity_blocker_class"]
        else UNKNOWN_REQUIRES_ARTIFACT_INSPECTION
        if outcome_class == "unknown"
        else "bounded_follow_up"
    )

    derived_outcome_class = outcome_class
    if outcome_class == "unknown":
        if str(row.get("status") or "") == "execution_integration_deferred":
            derived_outcome_class = "unknown"
        elif diagnostic["source_identity_blocker_class"]:
            derived_outcome_class = diagnostic["source_identity_blocker_class"]
        elif blocker_class and blocker_class not in {
            "execution_integration_deferred",
            "controlled_validation_failed",
            "unknown_execution_error",
        }:
            derived_outcome_class = blocker_class
        else:
            derived_outcome_class = UNKNOWN_REQUIRES_ARTIFACT_INSPECTION
    diagnostic["derived_outcome_class"] = derived_outcome_class
    diagnostic["safe_to_promote"] = False if outcome_class == OOS_EVIDENCE_OUTCOME else bool(
        row.get("safe_to_promote")
    )
    diagnostic["near_pass"] = False if outcome_class == OOS_EVIDENCE_OUTCOME else bool(
        row.get("near_pass")
    )
    diagnostic["promotion_candidate"] = False if outcome_class == OOS_EVIDENCE_OUTCOME else promotion_candidate
    return diagnostic


def _diagnostic_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [_derive_row_diagnostics(row) for row in rows]


def _top_oos_follow_up_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    selected = [
        row
        for row in rows
        if str(row.get("outcome_class") or "") == OOS_EVIDENCE_OUTCOME
        and not bool(row.get("promotion_candidate"))
    ]
    selected.sort(
        key=lambda row: (
            0 if row.get("metric_consistency_status") == "consistent" else 1,
            len(row.get("criteria_failure_classes") or []),
            1 if row.get("source_identity_blocker_class") else 0,
            -(row.get("trades_total") or 0.0),
            -(row.get("oos_trades") or 0.0),
            int(row.get("sequence_number") or 0),
        )
    )
    top_rows: list[dict[str, Any]] = []
    for row in selected[:10]:
        top_rows.append(
            {
                "sequence_number": int(row.get("sequence_number") or 0),
                "instrument_symbol": str(row.get("instrument_symbol") or ""),
                "behavior_preset_id": str(row.get("behavior_preset_id") or ""),
                "promotion_candidate": False,
                "near_pass": False,
                "safe_to_promote": False,
                "primary_blocker": row.get("primary_blocker"),
                "criteria_failure_classes": row.get("criteria_failure_classes"),
                "metric_consistency_status": row.get("metric_consistency_status"),
                "follow_up": row.get("follow_up"),
                "trades_total": row.get("trades_total"),
                "oos_trades": row.get("oos_trades"),
                "hd_trades": row.get("hd_trades"),
                "source_identity_blocker_class": row.get("source_identity_blocker_class"),
            }
        )
    return top_rows


def build_summary(
    *,
    run_dir: Path,
    results: list[dict[str, Any]],
    total_planned: int | None = None,
) -> dict[str, Any]:
    latest_results = _latest_result_rows(results)
    diagnostic_rows = _diagnostic_rows(latest_results)
    blocker_counter = Counter(
        str(row.get("blocker_class") or "unknown") for row in diagnostic_rows
    )
    outcome_counter = Counter(
        str(row.get("derived_outcome_class") or "unknown") for row in diagnostic_rows
    )
    status_counter = Counter(str(row.get("status") or "unknown") for row in diagnostic_rows)
    oos_blocker_counter = Counter(
        str(row.get("oos_evidence_blocker_class") or "none") for row in diagnostic_rows
    )

    deferred_count = status_counter.get("execution_integration_deferred", 0)
    summary = {
        "report_kind": "qre_controlled_discovery_grid_analysis",
        "run_dir": run_dir.as_posix(),
        "result_count": len(diagnostic_rows),
        "counts": {
            "total_combinations_planned": int(total_planned or len(diagnostic_rows)),
            "total_attempted": len(diagnostic_rows),
            "total_completed": status_counter.get("completed", 0),
            "total_skipped": status_counter.get("skipped", 0)
            + status_counter.get("skipped_invalid_metadata", 0)
            + status_counter.get("blocked_by_safety", 0),
            "total_failed": status_counter.get("failed", 0),
            "execution_integration_deferred": deferred_count,
            "insufficient_trades": blocker_counter.get("insufficient_trades", 0),
            "no_oos_evidence": blocker_counter.get("no_oos_evidence", 0),
            "criteria_win_rate_failed": blocker_counter.get("criteria_win_rate_failed", 0),
            "criteria_trades_per_maand_failed": blocker_counter.get(
                "criteria_trades_per_maand_failed", 0
            ),
            "criteria_consistentie_failed": blocker_counter.get(
                "criteria_consistentie_failed", 0
            ),
            "data_coverage_blocker": blocker_counter.get("data_coverage_blocker", 0),
            "sufficient_oos_evidence": sum(
                1
                for row in diagnostic_rows
                if str(row.get("outcome_class") or "") == OOS_EVIDENCE_OUTCOME
            ),
            "oos_evidence_quality_failed": oos_blocker_counter.get(
                "oos_evidence_quality_failed", 0
            ),
            "oos_evidence_metric_inconsistent": oos_blocker_counter.get(
                "oos_evidence_metric_inconsistent", 0
            ),
            "oos_evidence_no_promotion_due_to_criteria": oos_blocker_counter.get(
                "oos_evidence_no_promotion_due_to_criteria", 0
            ),
            "oos_evidence_degenerate_no_survivors": oos_blocker_counter.get(
                "oos_evidence_degenerate_no_survivors", 0
            ),
            "oos_evidence_missing_artifacts": oos_blocker_counter.get(
                "oos_evidence_missing_artifacts", 0
            ),
            "oos_evidence_unknown_reason": oos_blocker_counter.get(
                "oos_evidence_unknown_reason", 0
            ),
            "near_pass": outcome_counter.get("near_pass", 0),
            "promotion_candidate": outcome_counter.get("promotion_candidate", 0),
            "unknown": outcome_counter.get("unknown", 0),
            "total_unknown": outcome_counter.get("unknown", 0),
        },
        "by_region": _group_counts(diagnostic_rows, "region"),
        "by_asset": _group_counts(diagnostic_rows, "instrument_symbol"),
        "by_behavior_preset": _group_counts(diagnostic_rows, "behavior_preset_id"),
        "by_outcome_class": _group_counts(diagnostic_rows, "derived_outcome_class"),
        "by_blocker_class": _group_counts(diagnostic_rows, "blocker_class"),
        "by_oos_evidence_blocker_class": _group_counts(
            [row for row in diagnostic_rows if row.get("oos_evidence_blocker_class")],
            "oos_evidence_blocker_class",
        ),
        "top_near_pass": _top_rows(
            diagnostic_rows,
            predicate=lambda row: bool(row.get("near_pass")),
        ),
        "top_promotion_candidates": _top_rows(
            diagnostic_rows,
            predicate=lambda row: bool(row.get("promotion_candidate")),
        ),
        "sufficient_oos_evidence_blockers": [
            {
                "sequence_number": int(row.get("sequence_number") or 0),
                "instrument_symbol": str(row.get("instrument_symbol") or ""),
                "behavior_preset_id": str(row.get("behavior_preset_id") or ""),
                "oos_trades": row.get("oos_trades"),
                "hd_trades": row.get("hd_trades"),
                "trades_total": row.get("trades_total"),
                "promotion_candidate": False,
                "primary_blocker": row.get("primary_blocker"),
                "criteria_failure_classes": row.get("criteria_failure_classes"),
                "metric_consistency_status": row.get("metric_consistency_status"),
                "metric_consistency_warnings": row.get("metric_consistency_warnings"),
                "follow_up": row.get("follow_up"),
            }
            for row in diagnostic_rows
            if row.get("oos_evidence_blocker_class")
        ],
        "top_oos_follow_up_diagnostics": _top_oos_follow_up_rows(diagnostic_rows),
        "next_action": "DEFER_EXECUTION_INTEGRATION"
        if deferred_count
        else "MERGE_AND_RUN_ON_VPS",
    }
    return summary


def render_operator_summary(summary: dict[str, Any]) -> str:
    counts = summary["counts"]
    evidence_table = _table(
        ["Field", "Count"],
        [
            ["total combinations planned", str(counts["total_combinations_planned"])],
            ["executed combinations", str(counts["total_attempted"])],
            ["total completed", str(counts["total_completed"])],
            ["total skipped", str(counts["total_skipped"])],
            ["total failed", str(counts["total_failed"])],
            ["execution integration deferred", str(counts["execution_integration_deferred"])],
            ["insufficient trades", str(counts["insufficient_trades"])],
            ["no OOS evidence", str(counts["no_oos_evidence"])],
            ["criteria win-rate failed", str(counts["criteria_win_rate_failed"])],
            [
                "criteria trades-per-month failed",
                str(counts["criteria_trades_per_maand_failed"]),
            ],
            ["criteria consistentie failed", str(counts["criteria_consistentie_failed"])],
            ["data coverage blocker", str(counts["data_coverage_blocker"])],
            ["sufficient OOS evidence", str(counts["sufficient_oos_evidence"])],
            [
                "OOS blocker: quality failed",
                str(counts["oos_evidence_quality_failed"]),
            ],
            [
                "OOS blocker: metric inconsistent",
                str(counts["oos_evidence_metric_inconsistent"]),
            ],
            [
                "OOS blocker: no promotion due to criteria",
                str(counts["oos_evidence_no_promotion_due_to_criteria"]),
            ],
            [
                "OOS blocker: degenerate no survivors",
                str(counts["oos_evidence_degenerate_no_survivors"]),
            ],
            [
                "OOS blocker: missing artifacts",
                str(counts["oos_evidence_missing_artifacts"]),
            ],
            [
                "OOS blocker: unknown reason",
                str(counts["oos_evidence_unknown_reason"]),
            ],
            ["near pass", str(counts["near_pass"])],
            ["promotion candidate", str(counts["promotion_candidate"])],
            ["unknown", str(counts["unknown"])],
        ],
    )
    region_table = _table(
        ["Region", "Count"],
        [[row["value"], str(row["count"])] for row in summary["by_region"]],
    )
    preset_table = _table(
        ["Behavior preset", "Count"],
        [[row["value"], str(row["count"])] for row in summary["by_behavior_preset"]],
    )
    oos_rows = summary["sufficient_oos_evidence_blockers"] or [
        {
            "sequence_number": "-",
            "instrument_symbol": "-",
            "behavior_preset_id": "-",
            "oos_trades": "-",
            "hd_trades": "-",
            "trades_total": "-",
            "promotion_candidate": False,
            "primary_blocker": "-",
            "criteria_failure_classes": [],
            "metric_consistency_status": "-",
            "follow_up": "-",
        }
    ]
    oos_table = _table(
        [
            "Sequence",
            "Instrument",
            "Preset",
            "OOS trades",
            "HD trades",
            "Trades total",
            "Promotion",
            "Primary blocker",
            "Criteria failures",
            "Metric consistency",
            "Follow-up",
        ],
        [
            [
                str(row["sequence_number"]),
                str(row["instrument_symbol"]),
                str(row["behavior_preset_id"]),
                str(row["oos_trades"]),
                str(row["hd_trades"]),
                str(row["trades_total"]),
                "false",
                str(row["primary_blocker"]),
                ", ".join(row["criteria_failure_classes"]) or "-",
                str(row["metric_consistency_status"]),
                str(row["follow_up"]),
            ]
            for row in oos_rows
        ],
    )
    follow_up_rows = summary["top_oos_follow_up_diagnostics"] or [
        {
            "sequence_number": "-",
            "instrument_symbol": "-",
            "behavior_preset_id": "-",
            "primary_blocker": "-",
            "criteria_failure_classes": [],
            "metric_consistency_status": "-",
            "follow_up": "-",
        }
    ]
    follow_up_table = _table(
        ["Sequence", "Instrument", "Preset", "Primary blocker", "Criteria failures", "Metric consistency", "Follow-up"],
        [
            [
                str(row["sequence_number"]),
                str(row["instrument_symbol"]),
                str(row["behavior_preset_id"]),
                str(row["primary_blocker"]),
                ", ".join(row["criteria_failure_classes"]) or "-",
                str(row["metric_consistency_status"]),
                str(row["follow_up"]),
            ]
            for row in follow_up_rows
        ],
    )
    return "\n".join(
        [
            "# QRE Controlled Discovery Grid Operator Summary",
            "",
            "## 1. Korte conclusie",
            "- This run attempted controlled discovery-grid combinations through the existing research path whenever a concrete mapping existed.",
            "- Unsupported or unsafe combinations were written as explicit skipped blockers instead of crashing the run.",
            "- Completed, skipped, and failed counts below show the real attempt distribution for this run.",
            "",
            "## 2. Outcome counts",
            evidence_table,
            "",
            "## 3. Region coverage",
            region_table,
            "",
            "## 4. Behavior preset coverage",
            preset_table,
            "",
            "## 5. Sufficient OOS evidence blocker explanation",
            oos_table,
            "",
            "## 6. Top OOS follow-up diagnostics",
            follow_up_table,
            "",
            "## 7. Next action",
            f"- NEXT_ACTION: {summary['next_action']}",
        ]
    )


def _resolve_run_dir(input_dir: Path) -> Path:
    if (input_dir / RESULTS_FILENAME).exists():
        return input_dir
    run_dirs = sorted(
        [path for path in input_dir.iterdir() if path.is_dir()],
        key=lambda path: path.name,
    )
    if not run_dirs:
        raise FileNotFoundError(f"no run directories found under {input_dir}")
    return run_dirs[-1]


def summarize_run(
    *,
    input_dir: Path,
    write_summary: bool,
) -> dict[str, Any]:
    run_dir = _resolve_run_dir(input_dir)
    results = _load_jsonl(run_dir / RESULTS_FILENAME)
    plan_payload = None
    plan_path = run_dir / "grid_plan.v1.json"
    if plan_path.exists():
        try:
            plan_payload = json.loads(plan_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            plan_payload = None
    total_planned = (
        int(plan_payload.get("total_combinations") or 0)
        if isinstance(plan_payload, dict)
        else None
    )
    summary = build_summary(
        run_dir=run_dir,
        results=results,
        total_planned=total_planned,
    )
    if write_summary:
        (run_dir / SUMMARY_FILENAME).write_text(
            json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        (run_dir / OPERATOR_SUMMARY_FILENAME).write_text(
            render_operator_summary(summary) + "\n",
            encoding="utf-8",
        )
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m reporting.qre_controlled_discovery_grid_analysis",
        description="Summarize controlled discovery grid sidecar artifacts.",
    )
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--write-summary", action="store_true")
    args = parser.parse_args(argv)

    summary = summarize_run(
        input_dir=Path(args.input_dir),
        write_summary=bool(args.write_summary),
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
