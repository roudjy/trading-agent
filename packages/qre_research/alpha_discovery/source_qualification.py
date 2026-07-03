from __future__ import annotations

from pathlib import Path
from typing import Any

from research.external_intelligence.source_manifest_registry import build_source_manifest_registry

from .contracts import content_id

SOURCE_SMOKE_ONLY = "SOURCE_SMOKE_ONLY"
SOURCE_SCREENING_ELIGIBLE = "SOURCE_SCREENING_ELIGIBLE"
SOURCE_VALIDATION_ELIGIBLE = "SOURCE_VALIDATION_ELIGIBLE"
SOURCE_BLOCKED = "SOURCE_BLOCKED"


def _registry_rows() -> dict[str, dict[str, Any]]:
    registry = build_source_manifest_registry()
    rows = registry.get("rows") or []
    resolved: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        for key in (row.get("source_id"), row.get("provider_id"), row.get("source_name")):
            if key:
                resolved[str(key).lower()] = dict(row)
    return resolved


def reconcile_source_policy(*, repo_root: Path, dataset_catalog: dict[str, Any]) -> dict[str, Any]:
    del repo_root
    rows = _registry_rows()
    yfinance = rows.get("yfinance") or rows.get("yahoo_finance_yfinance_manifest") or {}
    current_status = str(yfinance.get("source_status") or "unknown")
    cause = "GLOBAL_VERSUS_CAMPAIGN_SCOPE"
    if current_status == "manual_research_only":
        cause = "MANUAL_RESEARCH_ONLY_BY_DESIGN"
    payload = {
        "schema_version": "1.0",
        "report_kind": "qre_source_policy_reconciliation",
        "historical_yfinance_status": "campaign_scoped_quality_ready",
        "current_yfinance_status": current_status,
        "exact_cause": cause,
        "policy_versions": {
            "historical_campaign_scope": "campaign_scoped_quality_ready",
            "current_global_scope": current_status,
        },
        "scoped_override": True,
        "bug_or_intentional_change": "intentional_global_authority_ceiling" if current_status == "manual_research_only" else "unknown",
        "transition_record": {
            "previous_policy": "campaign_scoped_quality_ready",
            "new_policy": current_status,
            "scope": "provider_global_authority_overrides_campaign_scoped_readiness",
            "promotion_ceiling": SOURCE_SMOKE_ONLY if current_status == "manual_research_only" else SOURCE_BLOCKED,
        },
        "content_identity": content_id("qsp", {"status": current_status, "datasets": len(dataset_catalog.get("datasets") or [])}),
    }
    return payload


def qualify_datasets(*, dataset_catalog: dict[str, Any], policy_reconciliation: dict[str, Any]) -> dict[str, Any]:
    rows = []
    current_status = str(policy_reconciliation.get("current_yfinance_status") or "unknown")
    for dataset in dataset_catalog.get("datasets") or []:
        if not isinstance(dataset, dict):
            continue
        quality = dict(dataset.get("quality_summary") or {})
        integrity = dict(dataset.get("integrity_summary") or {})
        allowed_tier = SOURCE_BLOCKED
        reason_codes = []
        if integrity.get("conflicting_row_count"):
            reason_codes.append("unresolved_conflicting_bars")
        if integrity.get("impossible_bar_density"):
            reason_codes.append("impossible_bar_density")
        if current_status == "manual_research_only":
            reason_codes.append("global_policy_ceiling_manual_research_only")
            allowed_tier = SOURCE_BLOCKED
        elif quality.get("effective_research_quality_status") == "ready" and not reason_codes:
            allowed_tier = SOURCE_SCREENING_ELIGIBLE
        rows.append(
            {
                "qualification_id": content_id("qdsq", {"dataset_id": dataset.get("dataset_id"), "tier": allowed_tier}),
                "source_id": dataset.get("source_id"),
                "source_policy_version": policy_reconciliation.get("content_identity"),
                "dataset_id": dataset.get("dataset_id"),
                "dataset_fingerprint": dataset.get("dataset_fingerprint"),
                "instrument_ids": dataset.get("instrument_ids"),
                "timeframe": dataset.get("timeframe"),
                "period": {"start": dataset.get("start"), "end": dataset.get("end")},
                "retrieval_timestamp": None,
                "query_parameters": {},
                "adjustment_policy": "UNKNOWN",
                "timezone_policy": "UTC_NORMALIZED",
                "raw_row_count": integrity.get("raw_row_count", dataset.get("row_count", 0)),
                "unique_bar_count": integrity.get("unique_bar_count", dataset.get("row_count", 0)),
                "expected_bar_count": integrity.get("expected_bar_count"),
                "coverage_ratio": integrity.get("coverage_ratio"),
                "missing_bar_count": integrity.get("missing_bar_count", 0),
                "duplicate_bar_count": integrity.get("exact_duplicate_row_count", 0),
                "conflicting_bar_count": integrity.get("conflicting_row_count", 0),
                "OHLC_validity": "VALID" if not reason_codes else "BLOCKED",
                "volume_validity": "VALID",
                "timestamp_validity": "VALID" if not integrity.get("invalid_row_count") else "BLOCKED",
                "session_validity": "UNKNOWN",
                "identity_validity": dict(dataset.get("identity_summary") or {}).get("instrument_identity_status", "unknown"),
                "corporate_action_validity": dict(dataset.get("corporate_action_summary") or {}).get("status", "UNKNOWN"),
                "reproducibility_status": "IMMUTABLE_CACHED_SNAPSHOT",
                "cross_source_agreement_status": "NOT_AVAILABLE",
                "revision_risk": "MANUAL_RESEARCH_ONLY_SOURCE",
                "allowed_evidence_tier": allowed_tier,
                "expiry_or_refresh_policy": "refresh_on_new_catalog_materialization",
                "reason_codes": tuple(reason_codes),
                "content_identity": content_id("qdsqc", {"dataset_id": dataset.get("dataset_id"), "reasons": reason_codes}),
            }
        )
    payload = {
        "schema_version": "1.0",
        "report_kind": "qre_dataset_source_qualification",
        "rows": rows,
        "content_identity": content_id("qdsqset", rows),
    }
    return payload

