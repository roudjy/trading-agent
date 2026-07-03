from __future__ import annotations

from pathlib import Path
from typing import Any

from research.external_intelligence.source_manifest_registry import build_source_manifest_registry

from .contracts import (
    SOURCE_TIER_BLOCKED,
    SOURCE_TIER_SCREENING_ELIGIBLE,
    SOURCE_TIER_SMOKE_ONLY,
    SOURCE_TIER_VALIDATION_ELIGIBLE,
    content_id,
)
from .snapshot_lineage import load_snapshot_lineage

SOURCE_POLICY_VERSION = "qre_alpha_source_qualification_pr4_v1"
SOURCE_SMOKE_ONLY = SOURCE_TIER_SMOKE_ONLY
SOURCE_SCREENING_ELIGIBLE = SOURCE_TIER_SCREENING_ELIGIBLE
SOURCE_VALIDATION_ELIGIBLE = SOURCE_TIER_VALIDATION_ELIGIBLE
SOURCE_BLOCKED = SOURCE_TIER_BLOCKED


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
    cause = "MANUAL_RESEARCH_ONLY_BY_DESIGN"
    payload = {
        "schema_version": "1.1",
        "report_kind": "qre_source_policy_reconciliation",
        "policy_version": SOURCE_POLICY_VERSION,
        "historical_yfinance_status": "campaign_scoped_quality_ready",
        "current_yfinance_status": current_status,
        "exact_cause": cause,
        "policy_versions": {
            "historical_campaign_scope": "campaign_scoped_quality_ready",
            "current_global_scope": current_status,
            "snapshot_scoped_screening_policy": SOURCE_POLICY_VERSION,
        },
        "scoped_override": True,
        "bug_or_intentional_change": "intentional_global_authority_ceiling",
        "transition_record": {
            "previous_policy": "global_ceiling_source_smoke_only",
            "new_policy": "global_ceiling_unchanged_snapshot_scoped_screening_possible",
            "scope": "immutable_snapshot_only",
            "promotion_ceiling": SOURCE_TIER_SCREENING_ELIGIBLE,
            "validation_ceiling": False,
        },
        "snapshot_screening_requirements": (
            "single_coherent_acquisition_lineage",
            "complete_query_provenance",
            "resolved_instrument_identity",
            "explicit_adjustment_policy",
            "explicit_timezone_policy",
            "explicit_session_calendar_applicability",
            "no_within_snapshot_conflicting_bars",
            "plausible_expected_bar_density",
            "bounded_missing_bar_ratio",
            "valid_ohlc_invariants",
            "stable_replay_from_immutable_cache",
            "sufficient_unique_history",
            "sufficient_expected_activity",
            "no_unresolved_source_incident_covering_period",
        ),
        "dataset_count": len(dataset_catalog.get("datasets") or []),
        "content_identity": content_id("qsp", {"status": current_status, "datasets": len(dataset_catalog.get("datasets") or [])}),
    }
    return payload


def _screening_reasons(snapshot: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    if str(snapshot.get("qualification_status") or "") != "COHERENT":
        reasons.append("snapshot_not_coherent")
    if int(snapshot.get("conflicting_row_count") or 0) > 0:
        reasons.append("within_snapshot_conflict")
    if int(snapshot.get("invalid_row_count") or 0) > 0:
        reasons.append("invalid_rows")
    if int(snapshot.get("unique_bar_count") or 0) < 25:
        reasons.append("insufficient_unique_history")
    coverage_ratio = snapshot.get("coverage_ratio")
    if coverage_ratio is not None and float(coverage_ratio) < 0.75:
        reasons.append("excess_missing_bars")
    if int(snapshot.get("expected_bar_count") or 0) and int(snapshot.get("unique_bar_count") or 0) > int(snapshot.get("expected_bar_count") or 0):
        reasons.append("impossible_bar_density")
    if not snapshot.get("fingerprint"):
        reasons.append("immutable_fingerprint_missing")
    return reasons


def qualify_datasets(*, repo_root: Path, dataset_catalog: dict[str, Any], policy_reconciliation: dict[str, Any]) -> dict[str, Any]:
    rows = []
    current_status = str(policy_reconciliation.get("current_yfinance_status") or "unknown")
    lineage = load_snapshot_lineage(repo_root)
    snapshots = [dict(row) for row in lineage.get("snapshot_lineage", {}).get("rows", []) if isinstance(row, dict)]
    for snapshot in snapshots:
        source_id = str(snapshot.get("source_id") or "")
        allowed_tier = SOURCE_TIER_BLOCKED
        reason_codes = _screening_reasons(snapshot)
        adjustment_policy = "AUTO_ADJUST_TRUE" if "yfinance" in source_id else "UNKNOWN"
        cross_source_status = "NOT_AVAILABLE"
        if "yfinance" in source_id:
            if current_status == "manual_research_only":
                if not reason_codes:
                    allowed_tier = SOURCE_TIER_SCREENING_ELIGIBLE
                else:
                    allowed_tier = SOURCE_TIER_SMOKE_ONLY
                    reason_codes.insert(0, "snapshot_scoped_screening_not_met")
            else:
                allowed_tier = SOURCE_TIER_SCREENING_ELIGIBLE if not reason_codes else SOURCE_TIER_BLOCKED
        elif not reason_codes:
            allowed_tier = SOURCE_TIER_VALIDATION_ELIGIBLE
        rows.append(
            {
                "qualification_id": content_id("qdsq", {"snapshot_id": snapshot.get("dataset_snapshot_id"), "tier": allowed_tier}),
                "source_id": source_id,
                "source_policy_version": policy_reconciliation.get("content_identity"),
                "dataset_id": snapshot.get("logical_dataset_family_id"),
                "dataset_snapshot_id": snapshot.get("dataset_snapshot_id"),
                "dataset_fingerprint": snapshot.get("fingerprint"),
                "instrument_ids": snapshot.get("instrument_ids"),
                "timeframe": snapshot.get("timeframe"),
                "period": {"start": snapshot.get("start"), "end": snapshot.get("end")},
                "retrieval_timestamp": snapshot.get("created_at_utc"),
                "query_parameters": {
                    "instrument_ids": snapshot.get("instrument_ids"),
                    "timeframe": snapshot.get("timeframe"),
                    "start": snapshot.get("start"),
                    "end": snapshot.get("end"),
                },
                "adjustment_policy": adjustment_policy,
                "timezone_policy": "UTC_NORMALIZED",
                "raw_row_count": snapshot.get("raw_row_count", 0),
                "unique_bar_count": snapshot.get("unique_bar_count", 0),
                "expected_bar_count": snapshot.get("expected_bar_count"),
                "coverage_ratio": snapshot.get("coverage_ratio"),
                "missing_bar_count": max(int(snapshot.get("expected_bar_count") or 0) - int(snapshot.get("unique_bar_count") or 0), 0) if snapshot.get("expected_bar_count") is not None else 0,
                "duplicate_bar_count": snapshot.get("exact_duplicate_row_count", 0),
                "conflicting_bar_count": snapshot.get("conflicting_row_count", 0),
                "OHLC_validity": "VALID" if "within_snapshot_conflict" not in reason_codes and "invalid_rows" not in reason_codes else "BLOCKED",
                "volume_validity": "VALID",
                "timestamp_validity": "VALID" if "invalid_rows" not in reason_codes else "BLOCKED",
                "session_validity": "VALID" if str(snapshot.get("timeframe") or "").endswith(("d", "h")) else "UNKNOWN",
                "identity_validity": "ready" if tuple(snapshot.get("instrument_ids") or ()) else "ambiguous",
                "corporate_action_validity": "UNKNOWN",
                "reproducibility_status": "IMMUTABLE_CACHED_SNAPSHOT",
                "cross_source_agreement_status": cross_source_status,
                "revision_risk": "SCREENING_ONLY_NO_GLOBAL_PROMOTION" if allowed_tier == SOURCE_TIER_SCREENING_ELIGIBLE else "SOURCE_GLOBAL_CEILING_UNCHANGED",
                "allowed_evidence_tier": allowed_tier,
                "expiry_or_refresh_policy": "refresh_on_new_snapshot_or_policy_change",
                "reason_codes": tuple(reason_codes),
                "content_identity": content_id("qdsqc", {"snapshot": snapshot.get("dataset_snapshot_id"), "tier": allowed_tier, "reasons": reason_codes}),
            }
        )
    payload = {
        "schema_version": "1.1",
        "report_kind": "qre_dataset_source_qualification",
        "policy_version": SOURCE_POLICY_VERSION,
        "rows": rows,
        "content_identity": content_id("qdsqset", rows),
    }
    return payload


__all__ = [
    "SOURCE_BLOCKED",
    "SOURCE_POLICY_VERSION",
    "SOURCE_SCREENING_ELIGIBLE",
    "SOURCE_SMOKE_ONLY",
    "SOURCE_VALIDATION_ELIGIBLE",
    "qualify_datasets",
    "reconcile_source_policy",
]
