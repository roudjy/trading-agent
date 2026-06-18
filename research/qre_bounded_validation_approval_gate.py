from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any, Final, Literal


ApprovalGateStatus = Literal[
    "approval_valid_for_bounded_validation",
    "blocked_missing_approval",
    "blocked_expired_approval",
    "blocked_scope_mismatch",
    "blocked_forbidden_capability",
    "blocked_output_path_not_allowlisted",
    "blocked_real_run_not_allowed",
    "blocked_external_fetch_not_allowed",
    "blocked_evidence_acceptance_not_allowed",
]

REPORT_KIND: Final[str] = "qre_bounded_validation_approval_gate"
SCHEMA_VERSION: Final[str] = "1.0"
FORBIDDEN_CAPABILITY_MARKERS: Final[tuple[str, ...]] = (
    "strategy_synthesis",
    "strategy_registration",
    "candidate_promotion",
    "paper_shadow_live",
    "broker_risk_execution",
    "execution",
    "order",
    "capital_allocation",
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _sorted_unique_strings(values: Any, *, upper: bool = False) -> tuple[str, ...]:
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
        return ()
    normalized = []
    seen: set[str] = set()
    for value in values:
        text = _text(value)
        if upper:
            text = text.upper()
        if text and text not in seen:
            seen.add(text)
            normalized.append(text)
    return tuple(sorted(normalized))


def _has_forbidden_capability(values: Sequence[str]) -> bool:
    return any(any(marker in item.lower() for marker in FORBIDDEN_CAPABILITY_MARKERS) for item in values)


def compute_approval_gate_hash(payload: Mapping[str, Any]) -> str:
    canonical = {
        "schema_version": payload.get("schema_version", SCHEMA_VERSION),
        "report_kind": payload.get("report_kind", REPORT_KIND),
        "approval_gate_status": payload.get("approval_gate_status", ""),
        "approval_id": payload.get("approval_id", ""),
        "request_ref": payload.get("request_ref", ""),
        "symbols": list(payload.get("symbols", [])),
        "preset_id": payload.get("preset_id", ""),
        "timeframe": payload.get("timeframe", ""),
        "allowed_command_class": payload.get("allowed_command_class", ""),
        "allowed_output_paths": list(payload.get("allowed_output_paths", [])),
        "rejection_reasons": list(payload.get("rejection_reasons", [])),
        "can_execute": bool(payload.get("can_execute", False)),
    }
    blob = json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def build_bounded_validation_approval_gate(
    approval: Mapping[str, Any] | None,
    request: Mapping[str, Any] | None,
    *,
    evaluated_at_utc: str,
    requested_external_fetch: bool = False,
    require_real_run: bool = True,
    require_evidence_acceptance: bool = True,
) -> dict[str, Any]:
    approval = dict(approval or {})
    request = dict(request or {})
    request_symbols = _sorted_unique_strings(request.get("symbols"), upper=True)
    request_paths = _sorted_unique_strings(request.get("allowed_output_paths"))
    request_forbidden = _sorted_unique_strings(request.get("forbidden_capabilities"))
    rejection_reasons: list[str] = []

    if not approval:
        status: ApprovalGateStatus = "blocked_missing_approval"
        rejection_reasons.append("missing_approval")
    else:
        approval_symbols = _sorted_unique_strings(approval.get("symbols"), upper=True)
        approval_paths = _sorted_unique_strings(approval.get("allowed_output_paths"))
        approval_forbidden = _sorted_unique_strings(approval.get("forbidden_capabilities"))
        expires_at_utc = _text(approval.get("expires_at_utc"))

        if not _text(approval.get("approval_id")) or not _text(approval.get("approved_by")) or not _text(approval.get("approved_at_utc")):
            status = "blocked_missing_approval"
            rejection_reasons.append("missing_approval_fields")
        elif expires_at_utc and expires_at_utc < evaluated_at_utc:
            status = "blocked_expired_approval"
            rejection_reasons.append("approval_expired")
        elif approval_symbols != request_symbols or _text(approval.get("preset_id")) != _text(request.get("preset_id")) or _text(approval.get("timeframe")) != _text(request.get("timeframe")):
            status = "blocked_scope_mismatch"
            rejection_reasons.append("scope_mismatch")
        elif _has_forbidden_capability(approval_forbidden) or _has_forbidden_capability(request_forbidden):
            status = "blocked_forbidden_capability"
            rejection_reasons.append("forbidden_capability")
        elif request_paths and not set(request_paths).issubset(set(approval_paths)):
            status = "blocked_output_path_not_allowlisted"
            rejection_reasons.append("output_path_not_allowlisted")
        elif require_real_run and bool(approval.get("real_run_allowed")) is not True:
            status = "blocked_real_run_not_allowed"
            rejection_reasons.append("real_run_not_allowed")
        elif requested_external_fetch and bool(approval.get("external_fetch_allowed")) is not True:
            status = "blocked_external_fetch_not_allowed"
            rejection_reasons.append("external_fetch_not_allowed")
        elif require_evidence_acceptance and bool(approval.get("evidence_acceptance_allowed")) is not True:
            status = "blocked_evidence_acceptance_not_allowed"
            rejection_reasons.append("evidence_acceptance_not_allowed")
        else:
            status = "approval_valid_for_bounded_validation"

    report = {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "approval_gate_status": status,
        "approval_id": _text(approval.get("approval_id")),
        "request_ref": _text(request.get("request_id")),
        "symbols": list(request_symbols),
        "preset_id": _text(request.get("preset_id")),
        "timeframe": _text(request.get("timeframe")),
        "allowed_command_class": _text(approval.get("allowed_command_class")),
        "allowed_output_paths": list(_sorted_unique_strings(approval.get("allowed_output_paths"))),
        "rejection_reasons": rejection_reasons,
        "real_run_allowed": bool(approval.get("real_run_allowed", False)),
        "external_fetch_allowed": bool(approval.get("external_fetch_allowed", False)),
        "evidence_acceptance_allowed": bool(approval.get("evidence_acceptance_allowed", False)),
        "dry_run_allowed": bool(approval.get("dry_run_allowed", False)),
        "can_execute": status == "approval_valid_for_bounded_validation",
        "can_authorize_shadow": False,
        "can_authorize_paper": False,
        "can_authorize_live": False,
        "can_authorize_broker_risk_execution": False,
    }
    report["hash"] = compute_approval_gate_hash(report)
    return report


def validate_approval_gate_result(report: Mapping[str, Any]) -> dict[str, Any]:
    rejection_reasons: list[str] = []
    if bool(report.get("can_authorize_shadow")):
        rejection_reasons.append("shadow_authority_forbidden")
    if bool(report.get("can_authorize_paper")):
        rejection_reasons.append("paper_authority_forbidden")
    if bool(report.get("can_authorize_live")):
        rejection_reasons.append("live_authority_forbidden")
    if bool(report.get("can_authorize_broker_risk_execution")):
        rejection_reasons.append("broker_risk_execution_authority_forbidden")
    computed_hash = compute_approval_gate_hash(report)
    if _text(report.get("hash")) and _text(report.get("hash")) != computed_hash:
        rejection_reasons.append("hash_mismatch")
    return {
        "valid": not rejection_reasons,
        "rejection_reasons": rejection_reasons,
        "hash": computed_hash,
        "schema_version": SCHEMA_VERSION,
    }
