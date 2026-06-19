from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any, Final, Literal

from research import qre_bounded_validation_approval_gate as approval_gate
from research import qre_sampling_plan as sampling_plan


CampaignStatus = Literal[
    "campaign_ready_preregistered_context",
    "blocked_invalid_sampling_plan",
    "blocked_invalid_approval",
    "blocked_external_fetch_not_allowed",
    "blocked_output_path_not_allowlisted",
    "blocked_outcome_based_window_selection",
]

SCHEMA_VERSION: Final[str] = "1.0"
REPORT_KIND: Final[str] = "qre_preregistered_multiwindow_validation"
NON_AUTHORITATIVE: Final[bool] = True
CAN_AUTHORIZE_EXECUTION: Final[bool] = False
CAN_CLEAR_EVIDENCE_BLOCKERS: Final[bool] = False
CAN_PROMOTE_CANDIDATE: Final[bool] = False
EVIDENCE_AUTHORITY: Final[str] = "context_only"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _unique_in_order(values: Sequence[Any]) -> list[str]:
    return list(dict.fromkeys(_text(value) for value in values if _text(value)))


def _request_from_approval(approval_manifest: Mapping[str, Any]) -> dict[str, Any]:
    scope = approval_manifest.get("scope") if isinstance(approval_manifest.get("scope"), Mapping) else {}
    return {
        "request_id": f"preregistered-multiwindow-{_text(approval_manifest.get('approval_id'))}",
        "symbols": list(scope.get("symbols") or approval_manifest.get("symbols") or []),
        "preset_id": _text(scope.get("preset_id") or approval_manifest.get("preset_id")),
        "timeframe": _text(scope.get("timeframe") or approval_manifest.get("timeframe")),
        "approval_ref": _text(approval_manifest.get("approval_id")),
        "allowed_output_paths": list(approval_manifest.get("allowed_output_paths") or []),
        "forbidden_capabilities": list(approval_manifest.get("forbidden_capabilities") or []),
        "required_artifact_types": [
            "structured_lineage_artifact",
            "structured_oos_artifact",
        ],
    }


def compute_campaign_hash(report: Mapping[str, Any]) -> str:
    canonical = {
        "schema_version": report.get("schema_version", SCHEMA_VERSION),
        "report_kind": report.get("report_kind", REPORT_KIND),
        "campaign_id": report.get("campaign_id", ""),
        "sampling_plan_ref": report.get("sampling_plan_ref", ""),
        "sampling_plan_hash": report.get("sampling_plan_hash", ""),
        "approval_ref": report.get("approval_ref", ""),
        "window_run_specs": list(report.get("window_run_specs", [])),
        "regime_run_specs": list(report.get("regime_run_specs", [])),
        "execution_order": list(report.get("execution_order", [])),
        "stopping_rules": list(report.get("stopping_rules", [])),
        "acceptance_rules": list(report.get("acceptance_rules", [])),
        "rejection_rules": list(report.get("rejection_rules", [])),
        "status": report.get("status", ""),
        "authority": dict(report.get("authority", {})),
    }
    blob = json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def build_preregistered_multiwindow_validation(
    *,
    sampling_plan_payload: Mapping[str, Any],
    approval_manifest: Mapping[str, Any],
    local_source_ref: str,
    minimum_required_windows: int,
    minimum_total_oos_trades: int,
    per_window_minimum_oos_trades: int,
    null_control_requirements: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    sampling_validation = sampling_plan.validate_sampling_plan(sampling_plan_payload)
    request = _request_from_approval(approval_manifest)
    gate = approval_gate.build_bounded_validation_approval_gate(
        {
            "approval_id": _text(approval_manifest.get("approval_id")),
            "approved_by": _text(approval_manifest.get("approved_by")),
            "approved_at_utc": _text(approval_manifest.get("approved_at_utc")),
            "expires_at_utc": _text(approval_manifest.get("expiry_utc") or approval_manifest.get("expires_at_utc")),
            "symbols": list((approval_manifest.get("scope") or {}).get("symbols") or approval_manifest.get("symbols") or []),
            "preset_id": _text((approval_manifest.get("scope") or {}).get("preset_id") or approval_manifest.get("preset_id")),
            "timeframe": _text((approval_manifest.get("scope") or {}).get("timeframe") or approval_manifest.get("timeframe")),
            "allowed_command_class": _text(approval_manifest.get("allowed_command_class")),
            "allowed_output_paths": list(approval_manifest.get("allowed_output_paths") or []),
            "forbidden_capabilities": list(approval_manifest.get("forbidden_capabilities") or []),
            "dry_run_allowed": bool(approval_manifest.get("dry_run_allowed", False)),
            "real_run_allowed": bool(approval_manifest.get("real_run_allowed", False)),
            "external_fetch_allowed": bool(approval_manifest.get("external_fetch_allowed", False)),
            "evidence_acceptance_allowed": bool(approval_manifest.get("evidence_acceptance_allowed", False)),
        },
        request,
        evaluated_at_utc=_text(approval_manifest.get("approved_at_utc")),
        requested_external_fetch=False,
        require_real_run=True,
        require_evidence_acceptance=True,
    )
    blocked_reasons: list[str] = []
    status: CampaignStatus = "campaign_ready_preregistered_context"
    if sampling_validation["valid"] is not True or _text(sampling_plan_payload.get("status")) != "sampling_plan_ready_context_only":
        status = "blocked_invalid_sampling_plan"
        blocked_reasons.extend(list(sampling_validation.get("rejection_reasons") or []))
        blocked_reasons.extend(_unique_in_order(sampling_plan_payload.get("blocked_reasons") or []))
    elif gate["approval_gate_status"] != "approval_valid_for_bounded_validation":
        status = "blocked_invalid_approval"
        blocked_reasons.extend(list(gate.get("rejection_reasons") or []))
    elif bool(approval_manifest.get("external_fetch_allowed", False)):
        status = "blocked_external_fetch_not_allowed"
        blocked_reasons.append("external_fetch_must_remain_false")
    elif any("output_path_not_allowlisted" in reason for reason in gate.get("rejection_reasons") or []):
        status = "blocked_output_path_not_allowlisted"
        blocked_reasons.extend(list(gate.get("rejection_reasons") or []))
    elif any(
        "profit" in _text(rule).lower() or "sharpe" in _text(rule).lower()
        for rule in sampling_plan_payload.get("selection_policy", "")
    ):
        status = "blocked_outcome_based_window_selection"
        blocked_reasons.append("outcome_based_window_selection")

    windows = list(sampling_plan_payload.get("window_definitions") or [])
    symbols = list(request.get("symbols") or [])
    window_run_specs = [
        {
            "window_id": _text(window.get("window_id")),
            "bounded_input_window": dict(window.get("bounded_input_window") or {}),
            "oos_window": dict(window.get("oos_window") or {}),
            "regime_label": _text(window.get("regime_label")) or "unclassified",
            "symbols": symbols,
            "preset_id": request["preset_id"],
            "timeframe": request["timeframe"],
            "source_data_ref": local_source_ref,
            "locked": bool(window.get("locked", False)),
        }
        for window in windows
    ]
    regime_counts = Counter(_text(window.get("regime_label")) or "unclassified" for window in windows)
    regime_run_specs = [
        {"regime_label": regime_label, "window_count": count}
        for regime_label, count in sorted(regime_counts.items())
    ]
    report = {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "campaign_id": "qmwv_"
        + hashlib.sha256(
            json.dumps(
                {
                    "sampling_plan_id": sampling_plan_payload.get("sampling_plan_id"),
                    "approval_id": approval_manifest.get("approval_id"),
                    "symbols": symbols,
                    "window_ids": [_text(window.get("window_id")) for window in windows],
                },
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
            ).encode("utf-8")
        ).hexdigest()[:16],
        "sampling_plan_ref": _text(sampling_plan_payload.get("sampling_plan_id")),
        "sampling_plan_hash": _text(sampling_plan_payload.get("hash")),
        "approval_ref": _text(approval_manifest.get("approval_id")),
        "approval_gate": gate,
        "window_run_specs": window_run_specs,
        "regime_run_specs": regime_run_specs,
        "execution_order": [_text(window.get("window_id")) for window in windows],
        "stopping_rules": [
            "execute_all_preregistered_windows_in_order",
            "do_not_stop_early_for_positive_results",
            "do_not_add_windows_after_execution_starts",
            "stop_on_approval_expiry_or_safety_failure",
            "stop_if_external_fetch_becomes_required_without_approval",
        ],
        "acceptance_rules": [
            f"minimum_required_windows:{int(minimum_required_windows)}",
            f"minimum_total_oos_trades:{int(minimum_total_oos_trades)}",
            f"per_window_minimum_oos_trades:{int(per_window_minimum_oos_trades)}",
            "accepted_oos_requires_positive_trade_count_and_complete_structured_fields",
            "null_control_must_pass_for_evidence_complete",
        ],
        "rejection_rules": [
            "not_supported_across_preregistered_windows",
            "insufficient_total_oos_trades",
            "null_control_failed",
            "blocked_incomplete_evidence",
            "operator_review_required",
        ],
        "null_control_requirements": [dict(item) for item in null_control_requirements],
        "minimum_required_windows": int(minimum_required_windows),
        "minimum_total_oos_trades": int(minimum_total_oos_trades),
        "per_window_minimum_oos_trades": int(per_window_minimum_oos_trades),
        "local_source_ref": local_source_ref,
        "authority": {
            "non_authoritative": NON_AUTHORITATIVE,
            "can_authorize_execution": CAN_AUTHORIZE_EXECUTION,
            "can_clear_evidence_blockers": CAN_CLEAR_EVIDENCE_BLOCKERS,
            "can_promote_candidate": CAN_PROMOTE_CANDIDATE,
            "evidence_authority": EVIDENCE_AUTHORITY,
        },
        "status": status,
        "blocked_reasons": _unique_in_order(blocked_reasons),
    }
    report["hash"] = compute_campaign_hash(report)
    return report
