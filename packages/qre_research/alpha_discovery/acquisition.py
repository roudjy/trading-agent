from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from packages.qre_data.dataset_catalog import materialize_data_truth
from research.external_intelligence.source_manifest_registry import build_source_manifest_registry

from .contracts import (
    AcquisitionPlan,
    CoverageAssessment,
    DataRequirement,
    UniversePlan,
    content_id,
)


def _parse_history_span(value: str) -> int:
    text = str(value or "").strip().lower()
    if text.endswith("d") and text[:-1].isdigit():
        return int(text[:-1])
    return 0


def _source_registry() -> dict[str, dict[str, Any]]:
    payload = build_source_manifest_registry()
    rows = payload.get("rows") or []
    registry: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        for key in (row.get("source_id"), row.get("provider_id"), row.get("source_name")):
            if key:
                registry[str(key).lower()] = dict(row)
    registry["yfinance"] = registry.get("yahoo_finance_yfinance_manifest", {})
    return registry


def assess_coverage(
    *,
    repo_root: Path,
    requirement: DataRequirement,
    universe_plan: UniversePlan,
    catalog: dict[str, Any],
) -> CoverageAssessment:
    del repo_root
    datasets = [dict(row) for row in catalog.get("datasets") or [] if isinstance(row, dict)]
    instrument = universe_plan.resolved_assets[0] if universe_plan.resolved_assets else ""
    candidates = [
        row for row in datasets
        if str(row.get("timeframe") or "") == requirement.base_timeframe
        and (not instrument or instrument in tuple(row.get("instrument_ids") or ()))
    ]
    candidates = sorted(
        candidates,
        key=lambda row: (
            0 if str(row.get("quality_summary", {}).get("effective_research_quality_status") or "") == "ready" else 1,
            -int(row.get("row_count") or 0),
            str(row.get("dataset_id") or ""),
        ),
    )
    if not candidates:
        return CoverageAssessment(
            coverage_assessment_id=content_id("qcov", {"requirement_id": requirement.requirement_id, "decision": "EXTERNAL_DATA_BOUNDARY"}),
            requirement_id=requirement.requirement_id,
            universe_plan_id=requirement.universe_plan_id,
            decision="EXTERNAL_DATA_BOUNDARY",
            rows=(),
            highest_admissible_tier="COMPILER_ONLY",
            content_identity=content_id("qcovc", "empty_coverage"),
        )

    selected = candidates[0]
    span_days = int(selected.get("coverage_summary", {}).get("span_days") or 0)
    required_days = _parse_history_span(requirement.required_history_span)
    quality = str(selected.get("quality_summary", {}).get("effective_research_quality_status") or "blocked")
    identity = str(selected.get("identity_summary", {}).get("instrument_identity_status") or "ambiguous")
    pit = str(selected.get("PIT_summary", {}).get("status") or "PIT_NOT_REQUIRED")
    missing = "none"
    decision = "COVERAGE_READY"
    reasons: list[str] = []
    if quality != "ready":
        decision = "SOURCE_QUALITY_BLOCKED"
        reasons.append("source_quality_not_research_ready")
    elif identity != "ready":
        decision = "IDENTITY_BLOCKED"
        reasons.append("identity_not_resolved")
    elif universe_plan.point_in_time_required and pit != "PIT_READY":
        decision = "PIT_BLOCKED"
        reasons.append("pit_not_available")
    elif span_days < required_days:
        decision = "COVERAGE_PARTIAL_NOT_FETCHABLE"
        missing = f"{required_days - span_days}d_missing"
        reasons.append("history_gap_detected")
    rows = (
        {
            "instrument": instrument or str(selected.get("instrument_ids", ["unknown"])[0]),
            "timeframe": requirement.base_timeframe,
            "available_start": selected.get("start"),
            "available_end": selected.get("end"),
            "complete_bar_end": selected.get("complete_bar_end"),
            "row_count": selected.get("row_count"),
            "missing_ranges": [] if missing == "none" else [missing],
            "duplicate_ranges": [],
            "invalid_ranges": [],
            "quality_blockers": [] if quality == "ready" else ["source_quality_not_research_ready"],
            "identity_blockers": [] if identity == "ready" else ["identity_not_resolved"],
            "PIT_blockers": [] if pit in {"PIT_READY", "PIT_NOT_REQUIRED"} else ["pit_not_available"],
            "corporate_action_blockers": [],
            "session_blockers": [],
            "window_capacity": selected.get("window_capacity", {}),
            "estimated_activity": max(int(selected.get("row_count") or 0) // 40, 0),
            "decision": decision,
            "dataset_id": selected.get("dataset_id"),
            "dataset_path": (selected.get("partition_refs") or [""])[0],
            "reason_codes": reasons,
        },
    )
    return CoverageAssessment(
        coverage_assessment_id=content_id("qcov", {"requirement_id": requirement.requirement_id, "dataset_id": selected.get("dataset_id"), "decision": decision}),
        requirement_id=requirement.requirement_id,
        universe_plan_id=requirement.universe_plan_id,
        decision=decision,
        rows=rows,
        highest_admissible_tier=str(selected.get("highest_admissible_tier") or "COMPILER_ONLY"),
        content_identity=content_id("qcovc", rows),
    )


def plan_acquisition(
    *,
    requirement: DataRequirement,
    coverage: CoverageAssessment,
) -> AcquisitionPlan:
    registry = _source_registry()
    selected_source = "yfinance"
    source_row = registry.get(selected_source, {})
    source_status = str(source_row.get("source_status") or "").lower()
    policy_status = str(source_row.get("license_policy_status") or "").upper()
    approved = source_status == "quality_gated" and policy_status == "PASS"
    external_boundary = None
    decision = "APPROVED_SOURCE_SELECTED"
    if coverage.decision == "SOURCE_QUALITY_BLOCKED":
        decision = "NO_APPROVED_SOURCE"
        external_boundary = "STOPPED_SOURCE_QUALITY_BOUNDARY"
    elif coverage.decision == "IDENTITY_BLOCKED":
        decision = "NO_APPROVED_SOURCE"
        external_boundary = "STOPPED_IDENTITY_BOUNDARY"
    elif coverage.decision == "PIT_BLOCKED":
        decision = "NO_APPROVED_SOURCE"
        external_boundary = "STOPPED_PIT_BOUNDARY"
    elif not approved:
        decision = "NO_APPROVED_SOURCE"
        external_boundary = "STOPPED_PROVIDER_BOUNDARY"
    row = coverage.rows[0] if coverage.rows else {}
    return AcquisitionPlan(
        acquisition_plan_id=content_id("qap", {"requirement_id": requirement.requirement_id, "decision": decision}),
        requirement_id=requirement.requirement_id,
        source_ids=(selected_source,),
        instrument_ids=requirement.resolved_instrument_ids,
        base_timeframe=requirement.base_timeframe,
        start=requirement.required_history_start,
        end=requirement.required_history_end,
        expected_rows=max(requirement.minimum_rows_per_asset * max(requirement.minimum_assets, 1), requirement.minimum_rows),
        incremental=bool(coverage.decision == "COVERAGE_PARTIAL_FETCHABLE"),
        backfill=bool(coverage.decision == "COVERAGE_PARTIAL_FETCHABLE"),
        resample_targets=requirement.required_timeframes,
        corporate_action_actions=(),
        identity_actions=() if coverage.decision != "IDENTITY_BLOCKED" else ("resolve_identity",),
        quality_checks=("timestamp_monotonicity", "ohlc_consistency", "deduplicate_rows"),
        request_batches=(),
        rate_limit_budget=100,
        retry_budget=2,
        estimated_bytes=0,
        estimated_calls=0,
        expected_unlock=coverage.highest_admissible_tier,
        source_selection_decision=decision,
        external_boundary=external_boundary,
        reason_codes=tuple(row.get("reason_codes") or ()),
        content_identity=content_id("qapc", {"decision": decision, "coverage": coverage.coverage_assessment_id}),
    )


def execute_acquisition_once(
    *,
    repo_root: Path,
    plan: AcquisitionPlan,
) -> dict[str, Any]:
    telemetry = {
        "provider_calls": 0,
        "provider_calls_avoided": int(plan.estimated_calls or 0),
        "rows_downloaded": 0,
        "rows_reused": 0,
        "rows_rejected": 0,
        "incomplete_bars_excluded": 0,
        "duplicates_rejected": 0,
        "gaps_detected": 0,
        "partial_failures": 0,
        "atomic_commit": True,
        "fingerprints_before": [],
        "fingerprints_after": [],
        "external_boundary": plan.external_boundary,
        "source_selection_decision": plan.source_selection_decision,
        "content_identity": content_id("qing", {"plan": plan.acquisition_plan_id, "boundary": plan.external_boundary}),
    }
    refreshed = materialize_data_truth(repo_root)
    telemetry["rows_reused"] = sum(int(row.get("row_count") or 0) for row in refreshed["catalog"]["datasets"])
    telemetry["cache_hit_rate"] = 1.0
    return telemetry


def throughput_snapshot(
    *,
    catalog: dict[str, Any],
    telemetry: dict[str, Any],
) -> dict[str, Any]:
    datasets = [dict(row) for row in catalog.get("datasets") or [] if isinstance(row, dict)]
    row_total = sum(int(row.get("row_count") or 0) for row in datasets)
    tier_counts = Counter(str(row.get("highest_admissible_tier") or "") for row in datasets)
    return {
        "catalog_datasets_discovered": len(datasets),
        "physical_files_discovered": int(catalog.get("summary", {}).get("files_scanned") or 0),
        "manifest_references": int(catalog.get("summary", {}).get("files_scanned") or 0),
        "missing_files": int(catalog.get("summary", {}).get("missing_referenced_files") or 0),
        "orphaned_files": int(catalog.get("summary", {}).get("orphaned_files") or 0),
        "stale_manifests": int(catalog.get("summary", {}).get("stale_manifests") or 0),
        "duplicate_bytes_avoided": 0,
        "cache_hit_rate": telemetry.get("cache_hit_rate", 1.0),
        "rows_reused": telemetry.get("rows_reused", row_total),
        "rows_downloaded": telemetry.get("rows_downloaded", 0),
        "API_calls": telemetry.get("provider_calls", 0),
        "API_calls_avoided": telemetry.get("provider_calls_avoided", 0),
        "bytes_downloaded": telemetry.get("estimated_bytes", 0),
        "assets_made_ready": len({asset for row in datasets for asset in row.get("instrument_ids", [])}),
        "timeframes_made_ready": len({str(row.get("timeframe") or "") for row in datasets}),
        "history_span_gained": 0,
        "OOS_capacity_gained": int(tier_counts.get("LOCKED_OOS_VALIDATION", 0)),
        "source_failures": 1 if telemetry.get("external_boundary") == "STOPPED_SOURCE_QUALITY_BOUNDARY" else 0,
        "identity_failures": 1 if telemetry.get("external_boundary") == "STOPPED_IDENTITY_BOUNDARY" else 0,
        "quality_failures": 1 if telemetry.get("external_boundary") == "STOPPED_SOURCE_QUALITY_BOUNDARY" else 0,
        "time_to_evidence_ready_dataset": None,
        "compute_spent_on_ingestion": 0,
    }


__all__ = [
    "assess_coverage",
    "execute_acquisition_once",
    "plan_acquisition",
    "throughput_snapshot",
]
