from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from research import qre_failure_to_action_mapper as failure_mapper
from research import qre_preregistered_multiwindow_evidence_run as campaign_run


SCHEMA_VERSION: Final[str] = "1.0"
REPORT_KIND: Final[str] = "qre_multiwindow_evidence_closure"
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_multiwindow_evidence_closure")
LATEST_NAME: Final[str] = "latest.json"
SUMMARY_NAME: Final[str] = "operator_summary.md"
WRITE_PREFIX: Final[str] = "logs/qre_multiwindow_evidence_closure/"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _unique_in_order(values: Sequence[Any]) -> list[str]:
    return list(dict.fromkeys(_text(value) for value in values if _text(value)))


def compute_multiwindow_closure_hash(report: Mapping[str, Any]) -> str:
    canonical = {
        "schema_version": report.get("schema_version", SCHEMA_VERSION),
        "report_kind": report.get("report_kind", REPORT_KIND),
        "closure_status": report.get("closure_status", ""),
        "campaign_ref": report.get("campaign_ref", ""),
        "sampling_plan_ref": report.get("sampling_plan_ref", ""),
        "accepted_lineage_count": int(report.get("accepted_lineage_count", 0) or 0),
        "accepted_oos_count": int(report.get("accepted_oos_count", 0) or 0),
        "evidence_complete_count": int(report.get("evidence_complete_count", 0) or 0),
        "hypothesis_disposition": report.get("hypothesis_disposition", ""),
        "blockers_cleared": list(report.get("blockers_cleared", [])),
        "blockers_remaining": list(report.get("blockers_remaining", [])),
        "reason_records": list(report.get("reason_records", [])),
        "recommended_next_action": report.get("recommended_next_action", ""),
        "authority": dict(report.get("authority", {})),
    }
    raw = json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _reason_record(*, record_id: str, reason_code: str, evidence_refs: Sequence[str], message: str) -> dict[str, Any]:
    return {
        "record_id": record_id,
        "record_family": "multiwindow_evidence_closure",
        "reason_codes": [reason_code],
        "evidence_refs": list(evidence_refs),
        "message": message,
    }


def build_multiwindow_evidence_closure(campaign_report: Mapping[str, Any]) -> dict[str, Any]:
    window_results = list(campaign_report.get("window_results") or [])
    accepted_lineage_count = int(campaign_report.get("accepted_lineage_count") or 0)
    accepted_oos_count = int(campaign_report.get("accepted_oos_count") or 0)
    campaign_outcome = _text(campaign_report.get("campaign_outcome"))
    positive_oos_trade_count_total = int(campaign_report.get("positive_oos_trade_count_total") or 0)
    null_control_payload = campaign_report.get("null_control_results") if isinstance(campaign_report.get("null_control_results"), Mapping) else {}
    null_control_status = _text(null_control_payload.get("status"))
    reason_records: list[dict[str, Any]] = []
    blockers_cleared: list[str] = []
    blockers_remaining: list[str] = []

    if accepted_lineage_count > 0:
        blockers_cleared.append("campaign_lineage_missing")
        reason_records.append(
            _reason_record(
                record_id="rr_multiwindow_lineage_present",
                reason_code="accepted_lineage_present",
                evidence_refs=[_text(campaign_report.get("campaign_id"))],
                message="Verifier-acceptable structured lineage exists for the preregistered campaign scope.",
            )
        )
    else:
        blockers_remaining.append("campaign_lineage_missing")

    if accepted_oos_count > 0:
        blockers_cleared.append("no_oos_evidence")
    else:
        blockers_remaining.append("no_oos_evidence")

    if not window_results:
        closure_status = "blocked_incomplete_campaign"
        hypothesis_disposition = "not_evaluated"
        recommended_next_action = "route_to_operator_review"
        reason_records.append(
            _reason_record(
                record_id="rr_multiwindow_missing_windows",
                reason_code="missing_window_results",
                evidence_refs=[],
                message="The preregistered campaign did not execute any windows.",
            )
        )
    elif null_control_status == "controls_failed":
        closure_status = "null_control_failed"
        hypothesis_disposition = "fail_closed_rejected"
        recommended_next_action = "reject_hypothesis"
        reason_records.append(
            _reason_record(
                record_id="rr_multiwindow_null_control_failed",
                reason_code="null_control_failed",
                evidence_refs=[],
                message="Null/control requirements failed, so completion is blocked fail-closed.",
            )
        )
    elif null_control_status in {"controls_not_run", "controls_incomplete", ""}:
        closure_status = "blocked_missing_null_controls"
        hypothesis_disposition = "insufficient_for_completion"
        recommended_next_action = _text(null_control_payload.get("recommended_next_action")) or "materialize_missing_preregistered_controls"
        blockers_remaining.append("null_controls_incomplete")
        reason_records.append(
            _reason_record(
                record_id="rr_multiwindow_null_control_incomplete",
                reason_code="null_controls_incomplete",
                evidence_refs=[_text(campaign_report.get("campaign_id"))],
                message="Preregistered null/control requirements are still incomplete, so evidence completion remains blocked.",
            )
        )
    elif campaign_outcome == "accepted_multiwindow_oos_evidence" and accepted_lineage_count > 0 and accepted_oos_count > 0:
        closure_status = "evidence_complete"
        hypothesis_disposition = "supported_for_evidence_review"
        recommended_next_action = "route_to_operator_review"
        reason_records.append(
            _reason_record(
                record_id="rr_multiwindow_evidence_complete",
                reason_code="evidence_complete",
                evidence_refs=[_text(campaign_report.get("campaign_id"))],
                message="Accepted lineage and OOS evidence satisfied the preregistered multi-window criteria.",
            )
        )
    elif campaign_outcome in {"partial_oos_evidence", "regime_specific_evidence_only"} or accepted_oos_count > 0:
        closure_status = "evidence_partial"
        hypothesis_disposition = "insufficient_for_completion"
        recommended_next_action = "route_to_operator_review"
        reason_records.append(
            _reason_record(
                record_id="rr_multiwindow_partial",
                reason_code="evidence_partial",
                evidence_refs=[_text(campaign_report.get("campaign_id"))],
                message="Some accepted OOS evidence exists, but the preregistered completion criteria were not met.",
            )
        )
    elif campaign_outcome == "all_windows_non_positive_trade_count":
        closure_status = "all_windows_no_oos_trades"
        hypothesis_disposition = "fail_closed_rejected"
        recommended_next_action = failure_mapper.map_failure_to_action(
            failure_class="all_preregistered_windows_failed"
        )["recommended_action"]
        reason_records.append(
            _reason_record(
                record_id="rr_multiwindow_all_zero",
                reason_code="all_windows_non_positive_trade_count",
                evidence_refs=[_text(campaign_report.get("campaign_id"))],
                message="Every preregistered window completed with non-positive OOS trade count.",
            )
        )
    elif campaign_outcome == "insufficient_total_oos_trades":
        closure_status = "insufficient_total_oos_trades"
        hypothesis_disposition = "fail_closed_rejected"
        recommended_next_action = failure_mapper.map_failure_to_action(
            failure_class="insufficient_trades_across_windows"
        )["recommended_action"]
        reason_records.append(
            _reason_record(
                record_id="rr_multiwindow_insufficient_trades",
                reason_code="insufficient_trades_across_windows",
                evidence_refs=[_text(campaign_report.get("campaign_id"))],
                message="Preregistered windows ran, but total OOS trades remained below the minimum requirement.",
            )
        )
    elif campaign_outcome in {"hypothesis_not_supported", "blocked_safety_check", "blocked_source", "blocked_approval"}:
        closure_status = "hypothesis_not_supported" if campaign_outcome == "hypothesis_not_supported" else "operator_review_required"
        hypothesis_disposition = "fail_closed_rejected" if campaign_outcome == "hypothesis_not_supported" else "operator_review_required"
        recommended_next_action = "route_to_operator_review" if campaign_outcome != "hypothesis_not_supported" else "reject_hypothesis"
        reason_records.append(
            _reason_record(
                record_id="rr_multiwindow_campaign_blocked",
                reason_code=campaign_outcome or "campaign_blocked",
                evidence_refs=[_text(campaign_report.get("campaign_id"))],
                message="The multi-window campaign did not produce acceptable OOS evidence for the preregistered scope.",
            )
        )
    else:
        closure_status = "operator_review_required"
        hypothesis_disposition = "operator_review_required"
        recommended_next_action = "route_to_operator_review"

    if accepted_oos_count == 0 and "no_oos_evidence" not in blockers_remaining:
        blockers_remaining.append("no_oos_evidence")

    report = {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "closure_status": closure_status,
        "campaign_ref": _text(campaign_report.get("campaign_id")),
        "sampling_plan_ref": _text(campaign_report.get("sampling_plan_id")),
        "accepted_lineage_count": accepted_lineage_count,
        "accepted_oos_count": accepted_oos_count,
        "evidence_complete_count": 1 if closure_status == "evidence_complete" else 0,
        "hypothesis_disposition": hypothesis_disposition,
        "blockers_cleared": _unique_in_order(blockers_cleared),
        "blockers_remaining": _unique_in_order(blockers_remaining),
        "reason_records": reason_records,
        "recommended_next_action": recommended_next_action,
        "authority": {
            "non_authoritative": False,
            "can_promote_candidate": False,
            "can_activate_deployment": False,
            "evidence_authority": "closure_summary_only",
        },
        "campaign_outcome": campaign_outcome,
        "positive_oos_trade_count_total": positive_oos_trade_count_total,
    }
    report["hash"] = compute_multiwindow_closure_hash(report)
    return report


def _validate_write_target(path: Path) -> None:
    if WRITE_PREFIX not in path.as_posix():
        raise ValueError(f"{REPORT_KIND}: refusing write outside allowlist: {path!r}")


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path.as_posix()}")
    return payload


def write_outputs(report: Mapping[str, Any], *, repo_root: Path = Path(".")) -> dict[str, str]:
    base = repo_root / DEFAULT_OUTPUT_DIR
    base.mkdir(parents=True, exist_ok=True)
    latest = base / LATEST_NAME
    summary_path = base / SUMMARY_NAME
    for target in (latest, summary_path):
        _validate_write_target(target)
    tmp_json = latest.with_suffix(latest.suffix + ".tmp")
    tmp_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp_json, latest)
    tmp_md = summary_path.with_suffix(summary_path.suffix + ".tmp")
    tmp_md.write_text(
        "\n".join(
            [
                "# QRE Multi-Window Evidence Closure",
                "",
                f"- closure_status: {report.get('closure_status', '')}",
                f"- accepted_lineage_count: {report.get('accepted_lineage_count', 0)}",
                f"- accepted_oos_count: {report.get('accepted_oos_count', 0)}",
                f"- evidence_complete_count: {report.get('evidence_complete_count', 0)}",
                f"- hypothesis_disposition: {report.get('hypothesis_disposition', '')}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    os.replace(tmp_md, summary_path)
    return {
        "latest": latest.relative_to(repo_root).as_posix(),
        "operator_summary": summary_path.relative_to(repo_root).as_posix(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m research.qre_multiwindow_evidence_closure",
        description="Finalize the preregistered multi-window evidence campaign.",
    )
    parser.add_argument(
        "--campaign-file",
        default="logs/qre_preregistered_multiwindow_evidence_run/latest.json",
    )
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    report = build_multiwindow_evidence_closure(_read_json(Path(args.campaign_file)))
    if args.write:
        report["_artifact_paths"] = write_outputs(report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
