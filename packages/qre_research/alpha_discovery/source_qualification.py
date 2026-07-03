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

SCREENING_REQUIRED_FIELDS = (
    "dataset_snapshot_id",
    "source_id",
    "instrument_ids",
    "timeframe",
    "fingerprint",
    "logical_dataset_family_id",
    "acquisition_batch_ids",
    "unique_bar_count",
    "expected_bar_count",
    "coverage_ratio",
    "missing_bar_count",
    "conflicting_row_count",
    "invalid_row_count",
    "start",
    "end",
    "history_span",
    "minimum_required_history",
    "minimum_required_rows",
    "activity_estimate",
    "validation_capacity",
    "adjustment_policy",
    "timezone_policy",
    "session_policy",
    "source_policy_version",
    "qualification_policy_version",
)


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
    for field in SCREENING_REQUIRED_FIELDS:
        value = snapshot.get(field)
        if value is None or value == "" or value == () or value == []:
            reasons.append(f"qualification_metric_missing:{field}")
    if snapshot.get("expected_bar_count") is None:
        reasons.append("qualification_metric_missing:expected_bar_count")
    if snapshot.get("coverage_ratio") is None:
        reasons.append("qualification_metric_missing:coverage_ratio")
    if int(snapshot.get("unique_bar_count") or 0) < 90:
        reasons.append("insufficient_unique_history")
    coverage_ratio = snapshot.get("coverage_ratio")
    if coverage_ratio is not None and not (0.0 <= float(coverage_ratio) <= 1.0):
        reasons.append("invalid_coverage_ratio")
    elif coverage_ratio is not None and float(coverage_ratio) < 0.9:
        reasons.append("excess_missing_bars")
    if int(snapshot.get("expected_bar_count") or 0) and int(snapshot.get("unique_bar_count") or 0) > int(snapshot.get("expected_bar_count") or 0):
        reasons.append("impossible_bar_density")
    if not snapshot.get("fingerprint"):
        reasons.append("immutable_fingerprint_missing")
    if not snapshot.get("history_start") or not snapshot.get("history_end") or not snapshot.get("history_span"):
        reasons.append("qualification_metric_missing:history_span")
    return reasons


def qualify_datasets(*, repo_root: Path | None = None, dataset_catalog: dict[str, Any], policy_reconciliation: dict[str, Any]) -> dict[str, Any]:
    rows = []
    current_status = str(policy_reconciliation.get("current_yfinance_status") or "unknown")
    snapshots: list[dict[str, Any]] = []
    snapshot_scoped_authority = False
    catalog_rows = {
        str(dataset.get("dataset_snapshot_id") or dataset.get("dataset_id") or ""): dict(dataset)
        for dataset in dataset_catalog.get("datasets") or []
        if isinstance(dataset, dict)
    }
    if repo_root is not None:
        lineage = load_snapshot_lineage(repo_root)
        snapshots = [dict(row) for row in lineage.get("snapshot_lineage", {}).get("rows", []) if isinstance(row, dict)]
        snapshot_scoped_authority = bool(snapshots)
    if not snapshots:
        for dataset in dataset_catalog.get("datasets") or []:
            if not isinstance(dataset, dict):
                continue
            integrity = dataset.get("integrity_summary") or {}
            snapshots.append(
                {
                    "dataset_snapshot_id": dataset.get("dataset_snapshot_id") or dataset.get("dataset_id"),
                    "logical_dataset_family_id": dataset.get("dataset_id"),
                    "fingerprint": dataset.get("dataset_fingerprint"),
                    "source_id": dataset.get("source_id"),
                    "instrument_ids": tuple(dataset.get("instrument_ids") or ()),
                    "timeframe": dataset.get("timeframe"),
                    "start": dataset.get("start"),
                    "end": dataset.get("end"),
                    "created_at_utc": dataset.get("provenance", {}).get("generated_at_utc"),
                    "raw_row_count": integrity.get("raw_row_count", dataset.get("row_count", 0)),
                    "unique_bar_count": integrity.get("unique_bar_count", dataset.get("row_count", 0)),
                    "expected_bar_count": integrity.get("expected_bar_count"),
                    "coverage_ratio": integrity.get("coverage_ratio"),
                    "exact_duplicate_row_count": integrity.get("exact_duplicate_row_count", 0),
                    "conflicting_row_count": integrity.get("conflicting_row_count", 0),
                    "invalid_row_count": integrity.get("invalid_row_count", 0),
                    "qualification_status": "COHERENT" if str((dataset.get("quality_summary") or {}).get("effective_research_quality_status") or "").lower() == "ready" else "BLOCKED",
                }
            )
    for snapshot in snapshots:
        dataset_key = str(snapshot.get("dataset_snapshot_id") or snapshot.get("dataset_id") or "")
        dataset = catalog_rows.get(dataset_key) or {}
        integrity = dict(dataset.get("integrity_summary") or {})
        quality = dict(dataset.get("quality_summary") or {})
        identity = dict(dataset.get("identity_summary") or {})
        snapshot.setdefault("logical_dataset_family_id", dataset.get("dataset_id"))
        snapshot.setdefault("acquisition_batch_ids", tuple(dataset.get("acquisition_batch_ids") or ()))
        snapshot.setdefault("expected_bar_count", integrity.get("expected_bar_count"))
        snapshot.setdefault("coverage_ratio", integrity.get("coverage_ratio"))
        snapshot.setdefault("missing_bar_count", max(int(snapshot.get("expected_bar_count") or 0) - int(snapshot.get("unique_bar_count") or 0), 0) if snapshot.get("expected_bar_count") is not None else None)
        snapshot.setdefault("conflicting_row_count", integrity.get("conflicting_row_count", snapshot.get("conflicting_row_count", 0)))
        snapshot.setdefault("invalid_row_count", integrity.get("invalid_row_count", snapshot.get("invalid_row_count", 0)))
        snapshot.setdefault("invalid_bar_count", snapshot.get("invalid_row_count"))
        snapshot.setdefault("adjustment_policy", dataset.get("adjustment_policy") or quality.get("adjustment_policy") or "explicit")
        snapshot.setdefault("timezone_policy", dataset.get("timezone_policy") or "UTC_NORMALIZED")
        snapshot.setdefault("session_policy", dataset.get("session_policy") or "canonical_session_calendar")
        snapshot.setdefault("history_start", snapshot.get("start") or dataset.get("start"))
        snapshot.setdefault("history_end", snapshot.get("end") or dataset.get("end"))
        snapshot.setdefault("history_span", dataset.get("history_span") or quality.get("history_span") or "derived")
        snapshot.setdefault("minimum_required_history", dataset.get("minimum_required_history") or quality.get("minimum_required_history") or "derived")
        snapshot.setdefault("minimum_required_rows", dataset.get("minimum_required_rows") or quality.get("minimum_required_rows") or 90)
        snapshot.setdefault("activity_estimate", dataset.get("activity_estimate") or integrity.get("activity_estimate") or int(snapshot.get("unique_bar_count") or 0) // 40)
        snapshot.setdefault("validation_capacity", dataset.get("validation_capacity") or integrity.get("validation_capacity") or 0)
        snapshot.setdefault("source_policy_version", dataset.get("source_policy_version") or policy_reconciliation.get("policy_version") or SOURCE_POLICY_VERSION)
        snapshot.setdefault("qualification_policy_version", dataset.get("qualification_policy_version") or SOURCE_POLICY_VERSION)
        snapshot.setdefault("instrument_identity", tuple(snapshot.get("instrument_ids") or identity.get("instrument_ids") or ()))
        snapshot.setdefault("required_expected_bar_count", snapshot.get("expected_bar_count"))
    for snapshot in snapshots:
        source_id = str(snapshot.get("source_id") or "")
        allowed_tier = SOURCE_TIER_BLOCKED
        reason_codes = list(dict.fromkeys(_screening_reasons(snapshot)))
        adjustment_policy = "AUTO_ADJUST_TRUE" if "yfinance" in source_id else "UNKNOWN"
        cross_source_status = "NOT_AVAILABLE"
        if "yfinance" in source_id:
            if current_status == "manual_research_only":
                if snapshot_scoped_authority and not reason_codes:
                    allowed_tier = SOURCE_TIER_SCREENING_ELIGIBLE
                else:
                    allowed_tier = SOURCE_TIER_BLOCKED
                    reason_codes.insert(0, "global_policy_ceiling_manual_research_only")
                    if snapshot_scoped_authority:
                        reason_codes.append("snapshot_scoped_screening_not_met")
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
                "coverage_ratio": snapshot.get("coverage_ratio") if snapshot.get("expected_bar_count") is not None else None,
                "missing_bar_count": max(int(snapshot.get("expected_bar_count") or 0) - int(snapshot.get("unique_bar_count") or 0), 0) if snapshot.get("expected_bar_count") is not None else None,
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
                "qualification_status": "COHERENT" if allowed_tier in {SOURCE_TIER_SMOKE_ONLY, SOURCE_TIER_SCREENING_ELIGIBLE, SOURCE_TIER_VALIDATION_ELIGIBLE} else "BLOCKED",
                "expiry_or_refresh_policy": "refresh_on_new_snapshot_or_policy_change",
                "reason_codes": tuple(reason_codes),
                "qualification_policy_version": snapshot.get("qualification_policy_version") or SOURCE_POLICY_VERSION,
                "qualification_epoch_id": content_id("qdqe", {"snapshot": snapshot.get("dataset_snapshot_id"), "policy": SOURCE_POLICY_VERSION, "allowed": allowed_tier}),
                "content_identity": content_id("qdsqc", {"snapshot": snapshot.get("dataset_snapshot_id"), "tier": allowed_tier, "reasons": reason_codes}),
            }
        )
    qualification_row_count = len(rows)
    logical_dataset_count = len({str(row.get("dataset_id") or "") for row in rows if str(row.get("dataset_id") or "")})
    active_snapshot_count = sum(1 for row in rows if str(row.get("qualification_status") or "") == "COHERENT")
    replayed_snapshot_count = qualification_row_count
    historical_or_superseded_count = max(replayed_snapshot_count - active_snapshot_count, 0)
    screening_eligible_count = sum(1 for row in rows if str(row.get("allowed_evidence_tier") or "") == SOURCE_TIER_SCREENING_ELIGIBLE)
    smoke_only_count = sum(1 for row in rows if str(row.get("allowed_evidence_tier") or "") == SOURCE_TIER_SMOKE_ONLY)
    blocked_count = sum(1 for row in rows if str(row.get("allowed_evidence_tier") or "") == SOURCE_TIER_BLOCKED)
    missing_expected_bar_count = sum(1 for row in rows if row.get("expected_bar_count") is None)
    missing_coverage_count = sum(1 for row in rows if row.get("coverage_ratio") is None)
    missing_history_count = sum(1 for row in rows if row.get("history_start") is None or row.get("history_end") is None or row.get("history_span") is None)
    insufficient_rows_count = sum(1 for row in rows if "insufficient_unique_history" in tuple(row.get("reason_codes") or ()))
    insufficient_activity_count = sum(1 for row in rows if "insufficient_activity" in tuple(row.get("reason_codes") or ()))
    payload = {
        "schema_version": "1.1",
        "report_kind": "qre_dataset_source_qualification",
        "policy_version": SOURCE_POLICY_VERSION,
        "qualification_set_id": content_id("qdsqsetid", rows),
        "summary": {
            "qualification_row_count": qualification_row_count,
            "physical_snapshot_count": qualification_row_count,
            "logical_dataset_count": logical_dataset_count,
            "active_snapshot_count": active_snapshot_count,
            "replayed_snapshot_count": replayed_snapshot_count,
            "historical_or_superseded_count": historical_or_superseded_count,
            "screening_eligible_count": screening_eligible_count,
            "smoke_only_count": smoke_only_count,
            "blocked_count": blocked_count,
            "missing_expected_bar_count": missing_expected_bar_count,
            "missing_coverage_count": missing_coverage_count,
            "missing_history_count": missing_history_count,
            "insufficient_rows_count": insufficient_rows_count,
            "insufficient_activity_count": insufficient_activity_count,
        },
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
