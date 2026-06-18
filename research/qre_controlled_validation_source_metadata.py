from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any, Final, Literal


MetadataStatus = Literal[
    "metadata_complete",
    "missing_candidate_id",
    "missing_campaign_or_generation_id",
    "missing_source_artifact_ref",
    "missing_oos_window",
    "missing_oos_metrics",
    "missing_cost_slippage_refs",
    "missing_validation_status",
    "missing_reason_records",
    "unrecoverable_context_only_source",
    "unrecoverable_stdout_only_source",
    "unrecoverable_legacy_alias_only_source",
]

REPORT_KIND: Final[str] = "qre_controlled_validation_source_metadata"
SCHEMA_VERSION: Final[str] = "1.0"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return value
    return ()


def _unique_in_order(values: Sequence[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _status_from_reasons(reasons: Sequence[str]) -> MetadataStatus:
    ordered: tuple[tuple[str, MetadataStatus], ...] = (
        ("unrecoverable_context_only_source", "unrecoverable_context_only_source"),
        ("unrecoverable_stdout_only_source", "unrecoverable_stdout_only_source"),
        ("unrecoverable_legacy_alias_only_source", "unrecoverable_legacy_alias_only_source"),
        ("missing_candidate_id", "missing_candidate_id"),
        ("missing_campaign_or_generation_id", "missing_campaign_or_generation_id"),
        ("missing_source_artifact_ref", "missing_source_artifact_ref"),
        ("missing_oos_window", "missing_oos_window"),
        ("missing_oos_metrics", "missing_oos_metrics"),
        ("missing_cost_slippage_refs", "missing_cost_slippage_refs"),
        ("missing_validation_status", "missing_validation_status"),
        ("missing_reason_records", "missing_reason_records"),
    )
    for reason, status in ordered:
        if reason in reasons:
            return status
    return "metadata_complete"


def compute_source_metadata_hash(payload: Mapping[str, Any]) -> str:
    canonical = {
        "schema_version": payload.get("schema_version", SCHEMA_VERSION),
        "report_kind": payload.get("report_kind", REPORT_KIND),
        "source_ref": payload.get("source_ref", ""),
        "source_type": payload.get("source_type", ""),
        "metadata_status": payload.get("metadata_status", ""),
        "reasons": list(payload.get("reasons", [])),
        "lineage_record_count": int(payload.get("lineage_record_count", 0) or 0),
        "oos_record_count": int(payload.get("oos_record_count", 0) or 0),
    }
    blob = json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def build_controlled_validation_source_metadata(
    source: Mapping[str, Any] | None,
) -> dict[str, Any]:
    source = _mapping(source)
    source_type = _text(source.get("source_type"))
    source_ref = _text(source.get("source_ref"))
    reasons: list[str] = []
    if source_type == "context_only" or _text(source.get("source_authority")) == "context_only":
        reasons.append("unrecoverable_context_only_source")
    elif source_type == "stdout_only":
        reasons.append("unrecoverable_stdout_only_source")
    elif source_type == "legacy_alias_only":
        reasons.append("unrecoverable_legacy_alias_only_source")
    if not source_ref:
        reasons.append("missing_source_artifact_ref")

    lineage_records = [item for item in _sequence(source.get("lineage_records")) if isinstance(item, Mapping)]
    oos_records = [item for item in _sequence(source.get("oos_records")) if isinstance(item, Mapping)]

    for record in lineage_records:
        if not _text(record.get("candidate_id")):
            reasons.append("missing_candidate_id")
        if not (
            _text(record.get("campaign_id"))
            or _text(record.get("generation_run_id"))
            or _text(record.get("controlled_generation_id"))
            or _text(record.get("grid_run_id"))
        ):
            reasons.append("missing_campaign_or_generation_id")
        if not _sequence(record.get("reason_record_refs")):
            reasons.append("missing_reason_records")
        if not _text(record.get("validation_status")):
            reasons.append("missing_validation_status")

    for record in oos_records:
        if not _text(record.get("candidate_id")):
            reasons.append("missing_candidate_id")
        window = _mapping(record.get("oos_window"))
        if not _text(window.get("start")) or not _text(window.get("end")):
            reasons.append("missing_oos_window")
        if not _mapping(record.get("oos_metric_fields")):
            reasons.append("missing_oos_metrics")
        if not _sequence(record.get("cost_slippage_assumption_refs")):
            reasons.append("missing_cost_slippage_refs")
        if not _sequence(record.get("reason_record_refs")):
            reasons.append("missing_reason_records")
        if not _text(record.get("validation_status")):
            reasons.append("missing_validation_status")

    reasons = _unique_in_order(reasons)
    report = {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "source_ref": source_ref,
        "source_type": source_type,
        "metadata_status": _status_from_reasons(reasons),
        "reasons": reasons,
        "lineage_record_count": len(lineage_records),
        "oos_record_count": len(oos_records),
    }
    report["hash"] = compute_source_metadata_hash(report)
    return report


def validate_source_metadata(report: Mapping[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []
    if not _text(report.get("metadata_status")):
        reasons.append("missing_metadata_status")
    computed_hash = compute_source_metadata_hash(report)
    if _text(report.get("hash")) and _text(report.get("hash")) != computed_hash:
        reasons.append("hash_mismatch")
    return {
        "valid": not reasons,
        "rejection_reasons": reasons,
        "hash": computed_hash,
        "schema_version": SCHEMA_VERSION,
    }
