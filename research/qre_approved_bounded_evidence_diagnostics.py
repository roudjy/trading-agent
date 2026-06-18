from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Final


REPORT_KIND: Final[str] = "qre_approved_bounded_evidence_diagnostics"
SCHEMA_VERSION: Final[str] = "1.0"
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_approved_bounded_evidence_diagnostics")
LATEST_NAME: Final[str] = "latest.json"
OPERATOR_SUMMARY_NAME: Final[str] = "operator_summary.md"
WRITE_PREFIX: Final[str] = "logs/qre_approved_bounded_evidence_diagnostics/"
DEFAULT_APPROVAL_PATH: Final[Path] = Path(
    "research/operator_approvals/qre_bounded_validation_approval_first_batch.v1.json"
)
DEFAULT_APPROVED_RUN_PATH: Final[Path] = Path(
    "logs/qre_bounded_current_basket_generation_runner/approved_bounded_validation_execution/latest.json"
)
DEFAULT_VERIFIER_PATH: Final[Path] = Path(
    "logs/qre_bounded_generation_artifact_acceptance_verifier/latest.json"
)
DEFAULT_CLOSURE_PATH: Final[Path] = Path("logs/qre_evidence_complete_basket_closure/latest.json")
TIMEFRAME_ALIASES: Final[dict[str, tuple[str, ...]]] = {
    "daily_v1": ("daily_v1", "1d"),
    "1d": ("1d", "daily_v1"),
}


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _text(value: Any) -> str:
    return str(value or "").strip()


def _text_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [text for item in value if (text := _text(item))]


def _timeframe_equivalent(lhs: str, rhs_values: list[str]) -> bool:
    if not rhs_values:
        return False
    aliases = set(TIMEFRAME_ALIASES.get(lhs, (lhs,)))
    return bool(aliases.intersection(rhs_values))


def compute_diagnostics_hash(report: dict[str, Any]) -> str:
    canonical = {
        "schema_version": report.get("schema_version", SCHEMA_VERSION),
        "report_kind": report.get("report_kind", REPORT_KIND),
        "approved_scope": report.get("approved_scope", {}),
        "lineage_accepted_count": report.get("lineage_accepted_count", 0),
        "lineage_scope_keys": report.get("lineage_scope_keys", []),
        "closure_scope_keys": report.get("closure_scope_keys", []),
        "lineage_scope_match": report.get("lineage_scope_match", False),
        "unmatched_lineage_reasons": report.get("unmatched_lineage_reasons", []),
        "accepted_oos_count": report.get("accepted_oos_count", 0),
        "rejected_oos_count": report.get("rejected_oos_count", 0),
        "exact_oos_rejection_reasons": report.get("exact_oos_rejection_reasons", []),
        "recommended_next_action": report.get("recommended_next_action", ""),
        "diagnostic_statuses": report.get("diagnostic_statuses", []),
    }
    raw = json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _accepted_verifier_row(verifier_payload: dict[str, Any]) -> dict[str, Any] | None:
    rows = verifier_payload.get("rows")
    if not isinstance(rows, list):
        return None
    for row in rows:
        if isinstance(row, dict) and row.get("relative_path") == "logs/qre_controlled_validation_adapter_results/latest.json":
            return row
    return None


def _lineage_scope_key(record: dict[str, Any]) -> str:
    return "|".join(
        [
            _text(record.get("candidate_id")),
            _text(record.get("preset_id")),
            _text(record.get("timeframe")),
            _text(record.get("request_ref")),
        ]
    )


def _closure_scope_key(row: dict[str, Any]) -> str:
    timeframes = row.get("failure_action", {}).get("timeframes") if isinstance(row.get("failure_action"), dict) else []
    if not isinstance(timeframes, list):
        timeframes = []
    timeframe = _text(timeframes[0]) if timeframes else ""
    return "|".join(
        [
            _text(row.get("candidate_id")),
            _text(row.get("preset_id")),
            timeframe,
            "",
        ]
    )


def build_approved_bounded_evidence_diagnostics(
    *,
    repo_root: Path = Path("."),
    approval_path: Path = DEFAULT_APPROVAL_PATH,
    approved_run_path: Path = DEFAULT_APPROVED_RUN_PATH,
    verifier_path: Path = DEFAULT_VERIFIER_PATH,
    closure_path: Path = DEFAULT_CLOSURE_PATH,
) -> dict[str, Any]:
    approval_payload = _read_json(repo_root / approval_path)
    approved_run_payload = _read_json(repo_root / approved_run_path)
    verifier_payload = _read_json(repo_root / verifier_path)
    closure_payload = _read_json(repo_root / closure_path)
    statuses: list[str] = []

    if approved_run_payload is None:
        statuses.append("blocked_missing_approved_run_artifacts")
    if verifier_payload is None:
        statuses.append("blocked_missing_verifier_output")
    if closure_payload is None:
        statuses.append("blocked_missing_closure_output")

    if statuses:
        report = {
            "schema_version": SCHEMA_VERSION,
            "report_kind": REPORT_KIND,
            "approved_scope": {},
            "lineage_accepted_count": 0,
            "lineage_scope_keys": [],
            "closure_scope_keys": [],
            "lineage_scope_match": False,
            "unmatched_lineage_reasons": list(statuses),
            "accepted_oos_count": 0,
            "rejected_oos_count": 0,
            "exact_oos_rejection_reasons": [],
            "oos_trade_count": [],
            "oos_window": [],
            "oos_metrics_presence": False,
            "cost_slippage_refs_presence": False,
            "source_artifact_ref": "",
            "closure_blockers_before_after": [],
            "blocker_clearance_eligibility": False,
            "recommended_next_action": "no_safe_next_action",
            "diagnostic_statuses": list(statuses),
        }
        report["hash"] = compute_diagnostics_hash(report)
        return report

    approval_scope = approval_payload.get("scope") if isinstance(approval_payload, dict) else {}
    if not isinstance(approval_scope, dict):
        approval_scope = {}
    verifier_row = _accepted_verifier_row(verifier_payload or {})
    closure_rows = closure_payload.get("rows") if isinstance(closure_payload, dict) else []
    if not isinstance(closure_rows, list):
        closure_rows = []

    approved_candidates = {
        _text(symbol).upper()
        for symbol in approval_scope.get("symbols", [])
        if _text(symbol)
    }
    filtered_closure_rows = [
        row
        for row in closure_rows
        if isinstance(row, dict) and _text(row.get("symbol")).upper() in approved_candidates
    ]

    lineage_records = [
        dict(record)
        for record in (verifier_row.get("accepted_lineage_records") if isinstance(verifier_row, dict) else [])
        if isinstance(record, dict)
    ]
    accepted_oos_records = [
        dict(record)
        for record in (verifier_row.get("accepted_oos_records") if isinstance(verifier_row, dict) else [])
        if isinstance(record, dict)
    ]
    lineage_scope_keys = [_lineage_scope_key(record) for record in lineage_records]
    closure_scope_keys = [_closure_scope_key(row) for row in filtered_closure_rows]

    unmatched_lineage_reasons: list[str] = []
    lineage_scope_match = True
    for record in lineage_records:
        matching_row = None
        for row in filtered_closure_rows:
            if _text(record.get("candidate_id")) != _text(row.get("candidate_id")):
                continue
            if _text(record.get("preset_id")) != _text(row.get("preset_id")):
                continue
            row_timeframes = []
            failure_action = row.get("failure_action")
            if isinstance(failure_action, dict):
                row_timeframes = [value for value in failure_action.get("timeframes", []) if _text(value)]
            if _text(record.get("timeframe")) in row_timeframes:
                matching_row = row
                break
            if _timeframe_equivalent(_text(record.get("timeframe")), row_timeframes):
                unmatched_lineage_reasons.append("timeframe_alias_mismatch_between_verifier_and_closure")
                matching_row = row
                break
        if matching_row is None:
            lineage_scope_match = False
            unmatched_lineage_reasons.append("no_exact_closure_scope_match_for_accepted_lineage")
        elif "campaign_lineage_missing" in _text_list(matching_row.get("exact_blockers")):
            statuses.append("lineage_accepted_but_closure_not_cleared")

    exact_oos_rejection_reasons = _text_list(verifier_row.get("oos_rejection_reasons") if isinstance(verifier_row, dict) else [])
    dedup_oos_reasons = list(dict.fromkeys(exact_oos_rejection_reasons))
    if "non_positive_oos_trade_count" in dedup_oos_reasons:
        statuses.append("oos_rejected_non_positive_trade_count")
        statuses.append("approved_source_has_no_oos_trades")
    if "missing_oos_window" in dedup_oos_reasons:
        statuses.append("oos_rejected_missing_window")
    if "missing_oos_metrics" in dedup_oos_reasons:
        statuses.append("oos_rejected_missing_metrics")
    if "missing_cost_slippage_refs" in dedup_oos_reasons:
        statuses.append("oos_rejected_missing_cost_slippage_refs")
    if unmatched_lineage_reasons:
        statuses.append("lineage_accepted_but_scope_mismatch")

    oos_trade_count: list[int | float] = []
    oos_window: list[dict[str, Any]] = []
    oos_metrics_presence = False
    cost_slippage_refs_presence = False
    source_artifact_ref = ""
    source_payload = approved_run_payload.get("source_payload") if isinstance(approved_run_payload, dict) else {}
    if isinstance(source_payload, dict):
        source_artifact_ref = _text(source_payload.get("source_ref"))
        oos_records = source_payload.get("oos_records")
        if isinstance(oos_records, list):
            for record in oos_records:
                if not isinstance(record, dict):
                    continue
                metrics = record.get("oos_metric_fields")
                if isinstance(metrics, dict):
                    oos_metrics_presence = True
                    if "oos_trade_count" in metrics:
                        oos_trade_count.append(metrics.get("oos_trade_count"))  # type: ignore[arg-type]
                cost_slippage_refs = record.get("cost_slippage_assumption_refs")
                if isinstance(cost_slippage_refs, list) and any(_text(item) for item in cost_slippage_refs):
                    cost_slippage_refs_presence = True
                window = record.get("oos_window")
                if isinstance(window, dict):
                    oos_window.append(dict(window))

    closure_blockers_before_after: list[dict[str, Any]] = []
    blocker_clearance_eligibility = bool(lineage_records) and bool(accepted_oos_records)
    for row in filtered_closure_rows:
        exact_blockers = _text_list(row.get("exact_blockers"))
        closure_blockers_before_after.append(
            {
                "candidate_id": _text(row.get("candidate_id")),
                "symbol": _text(row.get("symbol")),
                "blockers_after": exact_blockers,
                "campaign_lineage_missing_present": "campaign_lineage_missing" in exact_blockers,
                "no_oos_evidence_present": "no_oos_evidence" in exact_blockers,
            }
        )

    if "approved_source_has_no_oos_trades" in statuses:
        recommended_next_action = "approved_source_has_no_oos_trades"
    elif "lineage_accepted_but_scope_mismatch" in statuses or "lineage_accepted_but_closure_not_cleared" in statuses:
        recommended_next_action = "fix_accepted_lineage_closure_scope"
    elif "oos_rejected_missing_window" in statuses or "oos_rejected_missing_metrics" in statuses or "oos_rejected_missing_cost_slippage_refs" in statuses:
        recommended_next_action = "repair_oos_window_metrics_cost_mapping"
    else:
        recommended_next_action = "no_safe_next_action"

    report = {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "approved_scope": {
            "approval_id": _text(approval_payload.get("approval_id") if isinstance(approval_payload, dict) else ""),
            "symbols": sorted(approved_candidates),
            "preset_id": _text(approval_scope.get("preset_id")),
            "timeframe": _text(approval_scope.get("timeframe")),
            "external_fetch_allowed": bool(approval_payload.get("external_fetch_allowed")) if isinstance(approval_payload, dict) else False,
        },
        "lineage_accepted_count": len(lineage_records),
        "lineage_scope_keys": lineage_scope_keys,
        "closure_scope_keys": closure_scope_keys,
        "lineage_scope_match": lineage_scope_match and not unmatched_lineage_reasons,
        "unmatched_lineage_reasons": list(dict.fromkeys(unmatched_lineage_reasons)),
        "accepted_oos_count": len(accepted_oos_records),
        "rejected_oos_count": len(exact_oos_rejection_reasons),
        "exact_oos_rejection_reasons": dedup_oos_reasons,
        "oos_trade_count": oos_trade_count,
        "oos_window": oos_window,
        "oos_metrics_presence": oos_metrics_presence,
        "cost_slippage_refs_presence": cost_slippage_refs_presence,
        "source_artifact_ref": source_artifact_ref,
        "closure_blockers_before_after": closure_blockers_before_after,
        "blocker_clearance_eligibility": blocker_clearance_eligibility,
        "recommended_next_action": recommended_next_action,
        "diagnostic_statuses": list(dict.fromkeys(["diagnostics_ready", *statuses])),
    }
    report["hash"] = compute_diagnostics_hash(report)
    return report


def render_operator_summary(report: dict[str, Any]) -> str:
    approved_scope = report.get("approved_scope", {})
    statuses = ", ".join(report.get("diagnostic_statuses", [])) or "none"
    return "\n".join(
        [
            "# Approved Bounded Evidence Diagnostics",
            "",
            f"- approval_id: {approved_scope.get('approval_id', '')}",
            f"- symbols: {', '.join(approved_scope.get('symbols', []))}",
            f"- preset_id: {approved_scope.get('preset_id', '')}",
            f"- timeframe: {approved_scope.get('timeframe', '')}",
            f"- lineage_accepted_count: {report.get('lineage_accepted_count', 0)}",
            f"- accepted_oos_count: {report.get('accepted_oos_count', 0)}",
            f"- lineage_scope_match: {str(bool(report.get('lineage_scope_match'))).lower()}",
            f"- exact_oos_rejection_reasons: {', '.join(report.get('exact_oos_rejection_reasons', [])) or 'none'}",
            f"- recommended_next_action: {report.get('recommended_next_action', '')}",
            f"- diagnostic_statuses: {statuses}",
            "",
        ]
    )


def _validate_write_target(path: Path) -> None:
    if WRITE_PREFIX not in path.as_posix():
        raise ValueError(f"{REPORT_KIND}: refusing write outside allowlist: {path!r}")


def write_outputs(report: dict[str, Any], *, repo_root: Path = Path("."), output_dir: Path = DEFAULT_OUTPUT_DIR) -> dict[str, str]:
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
        prog="python -m research.qre_approved_bounded_evidence_diagnostics",
        description="Explain approved bounded evidence rejection and closure scope.",
    )
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)

    report = build_approved_bounded_evidence_diagnostics()
    if args.write:
        report["_artifact_paths"] = write_outputs(report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
