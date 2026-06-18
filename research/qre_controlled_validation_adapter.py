"""Controlled validation adapter for bounded evidence.

The adapter is read-only and fail-closed. It normalizes a bounded request
plus an explicitly supplied structured validation source into candidate
lineage/OOS records, but it does not invent identifiers, fetch data,
execute campaigns, or treat adapter output as proof by itself.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from typing import Any, Final, Literal

from research.qre_bounded_basket_request import (
    ALLOWED_OUTPUT_ROOTS,
    BoundedBasketRequest,
)
from research import qre_controlled_validation_source_metadata as source_metadata


AdapterStatus = Literal[
    "adapter_ready",
    "no_safe_controlled_validation_source",
    "blocked_invalid_bounded_request",
    "blocked_missing_approval_ref",
    "blocked_forbidden_capability",
    "blocked_output_path_not_allowlisted",
    "blocked_source_not_structured",
    "blocked_missing_candidate_id",
    "blocked_missing_campaign_or_generation_id",
    "blocked_missing_oos_window",
    "blocked_missing_oos_metrics",
    "blocked_missing_cost_slippage_refs",
    "rejected_context_only_source",
    "rejected_stdout_only_source",
    "rejected_legacy_alias_only_source",
    "accepted_structured_evidence",
]

ADAPTER_SCHEMA_VERSION: Final[str] = "1.0"
REPORT_KIND: Final[str] = "qre_controlled_validation_adapter"
NON_AUTHORITATIVE_FLAG: Final[bool] = True
EVIDENCE_AUTHORITY: Final[str] = "adapter_context_until_verifier_acceptance"
CAN_AUTHORIZE_EXECUTION: Final[bool] = False
CAN_PROMOTE_CANDIDATE: Final[bool] = False
FORBIDDEN_CAPABILITY_MARKERS: Final[tuple[str, ...]] = (
    "strategy_synthesis",
    "strategy_registration",
    "candidate_promotion",
    "paper_shadow_live",
    "broker_risk_execution",
    "execution",
    "order",
    "capital_allocation",
    "external_data_fetch",
    "frozen_contract_mutation",
)
STRUCTURED_SOURCE_TYPES: Final[frozenset[str]] = frozenset(
    {"structured_controlled_validation", "accepted_structured_validation"}
)


def _unique_in_order(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(str(value) for value in values if str(value).strip()))


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _as_sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return value
    return ()


def _normalized_request_payload(request: BoundedBasketRequest | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(request, BoundedBasketRequest):
        return request.to_payload()
    return dict(request)


def _request_or_error(
    request: BoundedBasketRequest | Mapping[str, Any],
) -> tuple[BoundedBasketRequest | None, AdapterStatus | None, tuple[str, ...]]:
    payload = _normalized_request_payload(request)
    if not str(payload.get("approval_ref") or "").strip():
        return None, "blocked_missing_approval_ref", ("missing_approval_ref",)
    try:
        bounded_request = BoundedBasketRequest.from_payload(payload)
    except ValueError as exc:
        message = str(exc)
        if "forbidden_capabilities_present" in message:
            return None, "blocked_forbidden_capability", ("forbidden_capability",)
        if "path_violation" in message:
            return None, "blocked_output_path_not_allowlisted", ("output_path_not_allowlisted",)
        if "missing_approval_ref" in message:
            return None, "blocked_missing_approval_ref", ("missing_approval_ref",)
        return None, "blocked_invalid_bounded_request", (message,)
    forbidden_hits = tuple(
        capability
        for capability in bounded_request.forbidden_capabilities
        if any(marker in capability.lower() for marker in FORBIDDEN_CAPABILITY_MARKERS)
    )
    if forbidden_hits:
        return None, "blocked_forbidden_capability", (
            *(f"forbidden_capability:{item}" for item in forbidden_hits),
        )
    disallowed_paths = tuple(
        path
        for path in bounded_request.allowed_output_paths
        if not any(path.startswith(root) for root in ALLOWED_OUTPUT_ROOTS)
    )
    if disallowed_paths:
        return None, "blocked_output_path_not_allowlisted", (
            *(f"output_path_not_allowlisted:{path}" for path in disallowed_paths),
        )
    return bounded_request, None, ()


def _source_status(
    source: Mapping[str, Any] | None,
) -> tuple[AdapterStatus | None, tuple[str, ...]]:
    if not source:
        return "no_safe_controlled_validation_source", ("no_safe_controlled_validation_source",)
    source_type = str(source.get("source_type") or "").strip()
    source_authority = str(source.get("source_authority") or "").strip()
    if source_type == "context_only" or source_authority == "context_only":
        return "rejected_context_only_source", ("context_only_source_rejected",)
    if source_type == "stdout_only":
        return "rejected_stdout_only_source", ("stdout_only_source_rejected",)
    if source_type == "legacy_alias_only":
        return "rejected_legacy_alias_only_source", ("legacy_alias_only_source_rejected",)
    if source_type not in STRUCTURED_SOURCE_TYPES:
        return "blocked_source_not_structured", ("source_not_structured",)
    return None, ()


def _lineage_candidate(
    *,
    bounded_request: BoundedBasketRequest,
    source_ref: str,
    record: Mapping[str, Any],
) -> tuple[dict[str, Any], tuple[str, ...]]:
    candidate_id = str(record.get("candidate_id") or "").strip()
    campaign_id = str(record.get("campaign_id") or "").strip()
    generation_id = str(
        record.get("generation_run_id")
        or record.get("controlled_generation_id")
        or record.get("grid_run_id")
        or ""
    ).strip()
    rejection_reasons: list[str] = []
    if not candidate_id:
        rejection_reasons.append("missing_candidate_id")
    if not campaign_id and not generation_id:
        rejection_reasons.append("missing_campaign_or_generation_id")
    accepted = not rejection_reasons
    return (
        {
            "artifact_type": "structured_lineage_candidate",
            "request_id": bounded_request.request_id,
            "candidate_id": candidate_id,
            "campaign_id": campaign_id,
            "generation_id": generation_id,
            "preset_id": bounded_request.preset_id,
            "timeframe": bounded_request.timeframe,
            "source_ref": source_ref,
            "reason_record_refs": list(_unique_in_order(record.get("reason_record_refs") or ())),
            "accepted_by_adapter": accepted,
            "accepted_for_campaign_lineage": accepted,
            "rejection_reasons": rejection_reasons,
        },
        tuple(rejection_reasons),
    )


def _oos_candidate(
    *,
    bounded_request: BoundedBasketRequest,
    source_ref: str,
    record: Mapping[str, Any],
) -> tuple[dict[str, Any], tuple[str, ...]]:
    candidate_id = str(record.get("candidate_id") or "").strip()
    oos_window = _as_mapping(record.get("oos_window"))
    metrics = _as_mapping(record.get("oos_metric_fields"))
    cost_refs = _as_sequence(record.get("cost_slippage_assumption_refs"))
    rejection_reasons: list[str] = []
    if not candidate_id:
        rejection_reasons.append("missing_candidate_id")
    if not str(oos_window.get("start") or "").strip() or not str(oos_window.get("end") or "").strip():
        rejection_reasons.append("missing_oos_window")
    if not metrics:
        rejection_reasons.append("missing_oos_metrics")
    if not cost_refs:
        rejection_reasons.append("missing_cost_slippage_refs")
    accepted = not rejection_reasons
    return (
        {
            "artifact_type": "structured_oos_candidate",
            "request_id": bounded_request.request_id,
            "candidate_id": candidate_id,
            "preset_id": bounded_request.preset_id,
            "timeframe": bounded_request.timeframe,
            "source_ref": source_ref,
            "oos_window": dict(oos_window),
            "oos_metric_fields": dict(metrics),
            "cost_slippage_assumption_refs": list(_unique_in_order(cost_refs)),
            "reason_record_refs": list(_unique_in_order(record.get("reason_record_refs") or ())),
            "accepted_by_adapter": accepted,
            "accepted_for_oos_evidence": accepted,
            "rejection_reasons": rejection_reasons,
        },
        tuple(rejection_reasons),
    )


def _status_from_rejections(
    *,
    accepted_lineage_count: int,
    accepted_oos_count: int,
    rejection_reasons: Sequence[str],
) -> AdapterStatus:
    if accepted_lineage_count > 0 and accepted_oos_count > 0 and not rejection_reasons:
        return "accepted_structured_evidence"
    ordered: tuple[tuple[str, AdapterStatus], ...] = (
        ("missing_candidate_id", "blocked_missing_candidate_id"),
        ("missing_campaign_or_generation_id", "blocked_missing_campaign_or_generation_id"),
        ("missing_oos_window", "blocked_missing_oos_window"),
        ("missing_oos_metrics", "blocked_missing_oos_metrics"),
        ("missing_cost_slippage_refs", "blocked_missing_cost_slippage_refs"),
    )
    for reason, status in ordered:
        if reason in rejection_reasons:
            return status
    return "adapter_ready"


def _canonicalize_result(result: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": result.get("schema_version", ADAPTER_SCHEMA_VERSION),
        "report_kind": result.get("report_kind", REPORT_KIND),
        "adapter_status": result.get("adapter_status"),
        "request_ref": result.get("request_ref"),
        "controlled_validation_source_ref": result.get("controlled_validation_source_ref"),
        "lineage_candidate_refs": list(result.get("lineage_candidate_refs", [])),
        "oos_candidate_refs": list(result.get("oos_candidate_refs", [])),
        "accepted_lineage_count": int(result.get("accepted_lineage_count", 0) or 0),
        "accepted_oos_count": int(result.get("accepted_oos_count", 0) or 0),
        "rejected_reasons": list(result.get("rejected_reasons", [])),
        "can_clear_blockers": bool(result.get("can_clear_blockers", False)),
        "non_authoritative": bool(result.get("non_authoritative", NON_AUTHORITATIVE_FLAG)),
        "evidence_authority": result.get("evidence_authority", EVIDENCE_AUTHORITY),
        "can_authorize_execution": bool(result.get("can_authorize_execution", CAN_AUTHORIZE_EXECUTION)),
        "can_promote_candidate": bool(result.get("can_promote_candidate", CAN_PROMOTE_CANDIDATE)),
    }


def compute_adapter_hash(payload: Mapping[str, Any]) -> str:
    canonical = _canonicalize_result(payload)
    blob = json.dumps(canonical, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return hashlib.sha256(blob).hexdigest()


def _finalize(result: dict[str, Any]) -> dict[str, Any]:
    result["rejected_reasons"] = list(_unique_in_order(result.get("rejected_reasons") or ()))
    result["lineage_candidate_refs"] = list(_unique_in_order(result.get("lineage_candidate_refs") or ()))
    result["oos_candidate_refs"] = list(_unique_in_order(result.get("oos_candidate_refs") or ()))
    result["hash"] = compute_adapter_hash(result)
    return result


def build_controlled_validation_adapter_result(
    request: BoundedBasketRequest | Mapping[str, Any],
    *,
    controlled_validation_source: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    bounded_request, request_status, request_reasons = _request_or_error(request)
    if bounded_request is None:
        return _finalize(
            {
                "schema_version": ADAPTER_SCHEMA_VERSION,
                "report_kind": REPORT_KIND,
                "adapter_status": request_status,
                "request_ref": str(_as_mapping(request).get("request_id") or ""),
                "controlled_validation_source_ref": "",
                "lineage_candidate_refs": [],
                "oos_candidate_refs": [],
                "accepted_lineage_count": 0,
                "accepted_oos_count": 0,
                "rejected_reasons": list(request_reasons),
                "can_clear_blockers": False,
                "non_authoritative": NON_AUTHORITATIVE_FLAG,
                "evidence_authority": EVIDENCE_AUTHORITY,
                "can_authorize_execution": CAN_AUTHORIZE_EXECUTION,
                "can_promote_candidate": CAN_PROMOTE_CANDIDATE,
                "lineage_candidates": [],
                "oos_candidates": [],
            }
        )

    source_status, source_reasons = _source_status(controlled_validation_source)
    source = _as_mapping(controlled_validation_source)
    metadata_report = source_metadata.build_controlled_validation_source_metadata(source)
    source_ref = str(source.get("source_ref") or "").strip()
    if source_status is not None:
        return _finalize(
            {
                "schema_version": ADAPTER_SCHEMA_VERSION,
                "report_kind": REPORT_KIND,
                "adapter_status": source_status,
                "request_ref": bounded_request.request_id,
                "controlled_validation_source_ref": source_ref,
                "lineage_candidate_refs": [],
                "oos_candidate_refs": [],
                "accepted_lineage_count": 0,
                "accepted_oos_count": 0,
                "rejected_reasons": list(source_reasons),
                "can_clear_blockers": False,
                "non_authoritative": NON_AUTHORITATIVE_FLAG,
                "evidence_authority": EVIDENCE_AUTHORITY,
                "can_authorize_execution": CAN_AUTHORIZE_EXECUTION,
                "can_promote_candidate": CAN_PROMOTE_CANDIDATE,
                "source_metadata_status": metadata_report["metadata_status"],
                "source_metadata_reasons": list(metadata_report["reasons"]),
                "lineage_candidates": [],
                "oos_candidates": [],
            }
        )

    lineage_candidates: list[dict[str, Any]] = []
    oos_candidates: list[dict[str, Any]] = []
    rejected_reasons: list[str] = []
    for record in _as_sequence(source.get("lineage_records")):
        candidate, reasons = _lineage_candidate(
            bounded_request=bounded_request,
            source_ref=source_ref,
            record=_as_mapping(record),
        )
        lineage_candidates.append(candidate)
        rejected_reasons.extend(reasons)
    for record in _as_sequence(source.get("oos_records")):
        candidate, reasons = _oos_candidate(
            bounded_request=bounded_request,
            source_ref=source_ref,
            record=_as_mapping(record),
        )
        oos_candidates.append(candidate)
        rejected_reasons.extend(reasons)

    accepted_lineage_count = sum(1 for item in lineage_candidates if item["accepted_by_adapter"])
    accepted_oos_count = sum(1 for item in oos_candidates if item["accepted_by_adapter"])
    status = _status_from_rejections(
        accepted_lineage_count=accepted_lineage_count,
        accepted_oos_count=accepted_oos_count,
        rejection_reasons=rejected_reasons,
    )
    can_clear_blockers = status == "accepted_structured_evidence"
    return _finalize(
        {
            "schema_version": ADAPTER_SCHEMA_VERSION,
            "report_kind": REPORT_KIND,
            "adapter_status": status,
            "request_ref": bounded_request.request_id,
            "controlled_validation_source_ref": source_ref,
            "lineage_candidate_refs": [
                f"{source_ref}#lineage:{item['candidate_id']}"
                for item in lineage_candidates
                if item["accepted_by_adapter"]
            ],
            "oos_candidate_refs": [
                f"{source_ref}#oos:{item['candidate_id']}"
                for item in oos_candidates
                if item["accepted_by_adapter"]
            ],
            "accepted_lineage_count": accepted_lineage_count,
            "accepted_oos_count": accepted_oos_count,
            "rejected_reasons": rejected_reasons,
            "can_clear_blockers": can_clear_blockers,
            "non_authoritative": NON_AUTHORITATIVE_FLAG,
            "evidence_authority": EVIDENCE_AUTHORITY,
            "can_authorize_execution": CAN_AUTHORIZE_EXECUTION,
            "can_promote_candidate": CAN_PROMOTE_CANDIDATE,
            "source_metadata_status": metadata_report["metadata_status"],
            "source_metadata_reasons": list(metadata_report["reasons"]),
            "lineage_candidates": lineage_candidates,
            "oos_candidates": oos_candidates,
        }
    )


def validate_adapter_result(result: Mapping[str, Any]) -> dict[str, Any]:
    rejection_reasons: list[str] = []
    canonical = _canonicalize_result(result)
    if canonical["can_clear_blockers"] and (
        canonical["accepted_lineage_count"] <= 0 or canonical["accepted_oos_count"] <= 0
    ):
        rejection_reasons.append("can_clear_blockers_requires_accepted_lineage_and_oos")
    if canonical["non_authoritative"] is not True:
        rejection_reasons.append("non_authoritative_must_be_true")
    if canonical["can_authorize_execution"] is not False:
        rejection_reasons.append("can_authorize_execution_must_be_false")
    if canonical["can_promote_candidate"] is not False:
        rejection_reasons.append("can_promote_candidate_must_be_false")
    if canonical["can_clear_blockers"] and canonical["adapter_status"] != "accepted_structured_evidence":
        rejection_reasons.append("can_clear_blockers_requires_accepted_structured_evidence_status")
    computed_hash = compute_adapter_hash(result)
    if str(result.get("hash") or "") and str(result.get("hash")) != computed_hash:
        rejection_reasons.append("hash_mismatch")
    return {
        "valid": not rejection_reasons,
        "rejection_reasons": list(_unique_in_order(rejection_reasons)),
        "hash": computed_hash,
        "schema_version": ADAPTER_SCHEMA_VERSION,
    }
