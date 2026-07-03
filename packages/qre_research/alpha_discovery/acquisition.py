from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from data.contracts import Instrument
from data.repository import DataUnavailableError, MarketRepository
from packages.qre_data.dataset_catalog import materialize_data_truth

from .contracts import (
    EXECUTION_TIER_COMPILER_ONLY,
    EXECUTION_TIER_EMPIRICAL_SCREENING,
    EXECUTION_TIER_EXECUTOR_SMOKE,
    EXECUTION_TIER_LOCKED_OOS_VALIDATION,
    SOURCE_TIER_SMOKE_ONLY,
    SOURCE_TIER_SCREENING_ELIGIBLE,
    AcquisitionPlan,
    CoverageAssessment,
    DatasetSnapshot,
    DataRequirement,
    ScreeningSlippageModel,
    SourceResolution,
    UniversePlan,
    content_id,
)
from .snapshot_lineage import append_snapshot_row, coherent_snapshots, load_snapshot_lineage, materialize_snapshot_lineage
from .source_resolution import resolve_source


def _parse_history_span(value: str) -> int:
    text = str(value or "").strip().lower()
    if text.endswith("d") and text[:-1].isdigit():
        return int(text[:-1])
    return 0


def _guess_asset_class(symbol: str) -> str:
    text = str(symbol or "").upper()
    return "crypto" if "-EUR" in text or "-USD" in text or text.startswith(("BTC", "ETH", "SOL", "XRP", "DOGE")) else "equity"


def _quote_ccy(symbol: str) -> str:
    text = str(symbol or "").upper()
    if text.endswith("-EUR"):
        return "EUR"
    return "USD"


def _screening_slippage_model(*, symbol: str, timeframe: str) -> ScreeningSlippageModel:
    model = ScreeningSlippageModel(
        slippage_model_id=content_id("qslip", {"symbol": symbol, "timeframe": timeframe}),
        asset_class=_guess_asset_class(symbol),
        timeframe=timeframe,
        liquidity_proxy="bar_range_and_turnover_proxy",
        spread_or_range_proxy="high_low_range_proxy",
        minimum_slippage_floor_bps=5.0 if timeframe == "1d" else 8.0,
        turnover_dependency="higher_turnover_higher_slippage",
        stress_multiplier=1.5,
        applicability="empirical_screening_only",
        limitations=("proxy_not_realized_execution", "validation_may_require_stronger_model"),
        content_identity=content_id("qslipc", {"symbol": symbol, "timeframe": timeframe}),
    )
    return model


def assess_coverage(
    *,
    repo_root: Path,
    requirement: DataRequirement,
    universe_plan: UniversePlan,
    catalog: dict[str, Any],
) -> CoverageAssessment:
    lineage = load_snapshot_lineage(repo_root)
    source_resolution = resolve_source(
        repo_root=repo_root,
        requirement=requirement,
        target_source_tier=SOURCE_TIER_SCREENING_ELIGIBLE if requirement.requested_execution_tier != EXECUTION_TIER_EXECUTOR_SMOKE else "SOURCE_SMOKE_ONLY",
    )
    instrument = universe_plan.resolved_assets[0] if universe_plan.resolved_assets else ""
    snapshot_rows = [
        row
        for row in coherent_snapshots(lineage)
        if str(row.get("timeframe") or "") == requirement.base_timeframe
        and (not instrument or instrument in tuple(row.get("instrument_ids") or ()))
    ]
    if not snapshot_rows:
        for dataset in catalog.get("datasets") or []:
            if not isinstance(dataset, dict):
                continue
            if str(dataset.get("timeframe") or "") != requirement.base_timeframe:
                continue
            instrument_ids = tuple(str(value) for value in dataset.get("instrument_ids") or ())
            if instrument and instrument not in instrument_ids:
                continue
            integrity = dataset.get("integrity_summary") or {}
            snapshot_rows.append(
                {
                    "logical_dataset_family_id": dataset.get("dataset_id"),
                    "dataset_snapshot_id": dataset.get("dataset_snapshot_id") or dataset.get("dataset_id"),
                    "instrument_ids": instrument_ids,
                    "timeframe": dataset.get("timeframe"),
                    "start": dataset.get("start"),
                    "end": dataset.get("end"),
                    "raw_row_count": int(integrity.get("raw_row_count", dataset.get("row_count", 0)) or 0),
                    "unique_bar_count": int(integrity.get("unique_bar_count", dataset.get("row_count", 0)) or 0),
                    "expected_bar_count": integrity.get("expected_bar_count"),
                    "coverage_ratio": integrity.get("coverage_ratio"),
                    "overlapping_row_count": int(integrity.get("overlapping_row_count", 0) or 0),
                    "conflicting_row_count": int(integrity.get("conflicting_row_count", 0) or 0),
                    "qualification_status": "COHERENT"
                    if str((dataset.get("quality_summary") or {}).get("effective_research_quality_status") or "").lower() == "ready"
                    else "BLOCKED",
                    "partition_refs": tuple(dataset.get("partition_refs") or ()),
                    "allowed_source_tier": SOURCE_TIER_SMOKE_ONLY,
                }
            )
    if not snapshot_rows:
        return CoverageAssessment(
            coverage_assessment_id=content_id("qcov", {"requirement_id": requirement.requirement_id, "decision": "EXTERNAL_DATA_BOUNDARY"}),
            requirement_id=requirement.requirement_id,
            universe_plan_id=requirement.universe_plan_id,
            decision="EXTERNAL_DATA_BOUNDARY",
            rows=(),
            highest_admissible_tier=EXECUTION_TIER_COMPILER_ONLY,
            content_identity=content_id("qcovc", "empty_snapshot_coverage"),
        )

    selected = snapshot_rows[0]
    required_days = _parse_history_span(requirement.required_history_span)
    expected = int(selected.get("expected_bar_count") or 0)
    unique_bars = int(selected.get("unique_bar_count") or 0)
    quality = "ready" if str(selected.get("qualification_status") or "") == "COHERENT" else "blocked"
    source_tier = str(selected.get("allowed_source_tier") or source_resolution.current_source_tier)
    span_days = 0
    try:
        start = datetime.fromisoformat(str(selected.get("start") or "").replace("Z", "+00:00"))
        end = datetime.fromisoformat(str(selected.get("end") or "").replace("Z", "+00:00"))
        span_days = max((end - start).days, 0)
    except ValueError:
        span_days = 0
    decision = "COVERAGE_READY"
    reasons: list[str] = []
    if int(selected.get("conflicting_row_count") or 0) > 0:
        decision = "SOURCE_QUALITY_BLOCKED"
        reasons.append("conflicting_snapshot_bars")
    elif source_tier not in {SOURCE_TIER_SCREENING_ELIGIBLE, "SOURCE_VALIDATION_ELIGIBLE"} and requirement.requested_execution_tier != EXECUTION_TIER_EXECUTOR_SMOKE:
        decision = "SOURCE_QUALITY_BLOCKED"
        reasons.append("source_tier_below_screening")
    elif quality != "ready":
        decision = "SOURCE_QUALITY_BLOCKED"
        reasons.append("snapshot_not_coherent")
    elif span_days < required_days:
        decision = "COVERAGE_PARTIAL_FETCHABLE"
        reasons.append("history_gap_detected")
    rows = (
        {
            "instrument": instrument or str(selected.get("instrument_ids", ["unknown"])[0]),
            "timeframe": requirement.base_timeframe,
            "available_start": selected.get("start"),
            "available_end": selected.get("end"),
            "complete_bar_end": selected.get("end"),
            "row_count": unique_bars,
            "raw_row_count": int(selected.get("raw_row_count") or unique_bars),
            "unique_bar_count": unique_bars,
            "overlapping_row_count": int(selected.get("overlapping_row_count") or 0),
            "conflicting_row_count": int(selected.get("conflicting_row_count") or 0),
            "expected_bar_count": expected or None,
            "missing_ranges": [] if decision != "COVERAGE_PARTIAL_FETCHABLE" else [f"{max(required_days - span_days, 0)}d_missing"],
            "duplicate_ranges": [],
            "invalid_ranges": [],
            "quality_blockers": [] if decision != "SOURCE_QUALITY_BLOCKED" else reasons,
            "identity_blockers": [],
            "PIT_blockers": [],
            "corporate_action_blockers": [],
            "session_blockers": [],
            "window_capacity": {},
            "estimated_activity": max(unique_bars // 40, 0),
            "decision": decision,
            "dataset_id": selected.get("logical_dataset_family_id"),
            "dataset_snapshot_id": selected.get("dataset_snapshot_id"),
            "dataset_path": (selected.get("partition_refs") or [""])[0],
            "source_tier": source_tier,
            "reason_codes": reasons,
        },
    )
    highest_tier = EXECUTION_TIER_EXECUTOR_SMOKE
    if source_tier in {SOURCE_TIER_SCREENING_ELIGIBLE, "SOURCE_VALIDATION_ELIGIBLE"}:
        highest_tier = EXECUTION_TIER_EMPIRICAL_SCREENING
        if unique_bars >= max(requirement.minimum_locked_oos_rows + requirement.minimum_validation_rows + requirement.minimum_rows_per_asset, requirement.minimum_rows):
            highest_tier = EXECUTION_TIER_LOCKED_OOS_VALIDATION
    return CoverageAssessment(
        coverage_assessment_id=content_id("qcov", {"requirement_id": requirement.requirement_id, "snapshot": selected.get("dataset_snapshot_id"), "decision": decision}),
        requirement_id=requirement.requirement_id,
        universe_plan_id=requirement.universe_plan_id,
        decision=decision,
        rows=rows,
        highest_admissible_tier=highest_tier,
        content_identity=content_id("qcovc", rows),
    )


def plan_acquisition(
    *,
    repo_root: Path,
    requirement: DataRequirement,
    coverage: CoverageAssessment,
) -> tuple[AcquisitionPlan, SourceResolution]:
    target_tier = SOURCE_TIER_SCREENING_ELIGIBLE if requirement.requested_execution_tier != EXECUTION_TIER_EXECUTOR_SMOKE else "SOURCE_SMOKE_ONLY"
    resolution = resolve_source(repo_root=repo_root, requirement=requirement, target_source_tier=target_tier)
    row = coverage.rows[0] if coverage.rows else {}
    external_boundary = None
    decision = "APPROVED_SOURCE_SELECTED"
    if resolution.credential_requirements:
        decision = "NO_APPROVED_SOURCE"
        external_boundary = "STOPPED_CREDENTIAL_BOUNDARY"
    elif resolution.license_requirements:
        decision = "NO_APPROVED_SOURCE"
        external_boundary = "STOPPED_LICENSE_BOUNDARY"
    elif coverage.decision == "SOURCE_QUALITY_BLOCKED":
        decision = "NO_APPROVED_SOURCE"
        external_boundary = "STOPPED_SOURCE_CERTIFICATION_BOUNDARY"
    elif coverage.decision == "IDENTITY_BLOCKED":
        decision = "NO_APPROVED_SOURCE"
        external_boundary = "STOPPED_IDENTITY_BOUNDARY"
    elif coverage.decision == "PIT_BLOCKED":
        decision = "NO_APPROVED_SOURCE"
        external_boundary = "STOPPED_PIT_BOUNDARY"
    elif not resolution.selected_source:
        decision = "NO_APPROVED_SOURCE"
        external_boundary = "STOPPED_EXTERNAL_PROVIDER_BOUNDARY"

    request_batches = ()
    if coverage.decision in {"COVERAGE_PARTIAL_FETCHABLE", "EXTERNAL_DATA_BOUNDARY"} and resolution.selected_source:
        request_batches = (
            {
                "source_id": resolution.selected_source,
                "instrument_ids": list(requirement.resolved_instrument_ids),
                "timeframe": requirement.base_timeframe,
                "start": requirement.required_history_start,
                "end": requirement.required_history_end,
            },
        )

    plan = AcquisitionPlan(
        acquisition_plan_id=content_id("qap", {"requirement_id": requirement.requirement_id, "decision": decision, "source": resolution.selected_source}),
        requirement_id=requirement.requirement_id,
        source_ids=(resolution.selected_source,) if resolution.selected_source else (),
        instrument_ids=requirement.resolved_instrument_ids,
        base_timeframe=requirement.base_timeframe,
        start=requirement.required_history_start,
        end=requirement.required_history_end,
        expected_rows=max(requirement.minimum_rows_per_asset * max(requirement.minimum_assets, 1), requirement.minimum_rows),
        incremental=bool(coverage.decision == "COVERAGE_PARTIAL_FETCHABLE"),
        backfill=bool(coverage.decision in {"COVERAGE_PARTIAL_FETCHABLE", "EXTERNAL_DATA_BOUNDARY"}),
        resample_targets=requirement.required_timeframes,
        corporate_action_actions=(),
        identity_actions=() if coverage.decision != "IDENTITY_BLOCKED" else ("resolve_identity",),
        quality_checks=("timestamp_monotonicity", "ohlc_consistency", "deduplicate_rows", "unique_bar_integrity"),
        request_batches=request_batches,
        rate_limit_budget=100,
        retry_budget=2,
        estimated_bytes=max(int(plan_rows := max(requirement.minimum_rows, requirement.minimum_rows_per_asset)) * 128, 0),
        estimated_calls=max(len(request_batches), 0),
        expected_unlock=coverage.highest_admissible_tier,
        source_selection_decision=decision,
        external_boundary=external_boundary,
        reason_codes=tuple(dict.fromkeys(tuple(row.get("reason_codes") or ()) + resolution.unresolved_blockers)),
        content_identity=content_id("qapc", {"decision": decision, "coverage": coverage.coverage_assessment_id, "resolution": resolution.content_identity}),
    )
    return plan, resolution


def execute_acquisition_once(
    *,
    repo_root: Path,
    plan: AcquisitionPlan,
) -> dict[str, Any]:
    telemetry = {
        "provider_calls": 0,
        "provider_calls_avoided": 0,
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
    before = load_snapshot_lineage(repo_root)["snapshot_lineage"]
    telemetry["fingerprints_before"] = [str(row.get("fingerprint") or "") for row in before.get("rows", []) if isinstance(row, dict)]
    if plan.external_boundary:
        refreshed = materialize_data_truth(repo_root, force_refresh=False)
        telemetry["rows_reused"] = sum(int(row.get("row_count") or 0) for row in refreshed["catalog"]["datasets"])
        telemetry["provider_calls_avoided"] = int(plan.estimated_calls or 0)
        return telemetry

    repository = MarketRepository()
    now = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    for symbol in plan.instrument_ids[:20]:
        history_days = 120 if str(plan.base_timeframe) == "1h" else 180
        start_utc = now - timedelta(days=history_days)
        try:
            response = repository.get_bars(
                instrument=Instrument(
                    id=str(symbol),
                    asset_class=_guess_asset_class(symbol),
                    venue="UNKNOWN",
                    native_symbol=str(symbol),
                    quote_ccy=_quote_ccy(symbol),
                ),
                interval=plan.base_timeframe,
                start_utc=start_utc,
                end_utc=now,
            )
            frame = response.frame
            telemetry["provider_calls"] += 1
            telemetry["rows_downloaded"] += int(len(frame))
            if not frame.empty:
                cache_path = repository._cache_path(  # type: ignore[attr-defined]
                    "yfinance",
                    str(symbol),
                    plan.base_timeframe,
                    start_utc,
                    now,
                )
                snapshot = DatasetSnapshot(
                    dataset_snapshot_id=content_id("qdsnap", {"path": cache_path.as_posix(), "symbol": symbol, "timeframe": plan.base_timeframe}),
                    logical_dataset_family_id=f"yfinance|{symbol}|{plan.base_timeframe}",
                    acquisition_batch_ids=(content_id("qdbatch", {"path": cache_path.as_posix(), "symbol": symbol}),),
                    parent_snapshot_id=None,
                    instrument_ids=(str(symbol),),
                    timeframe=plan.base_timeframe,
                    start=frame.index.min().tz_localize("UTC").isoformat().replace("+00:00", "Z") if frame.index.tz is None else frame.index.min().tz_convert("UTC").isoformat().replace("+00:00", "Z"),
                    end=frame.index.max().tz_localize("UTC").isoformat().replace("+00:00", "Z") if frame.index.tz is None else frame.index.max().tz_convert("UTC").isoformat().replace("+00:00", "Z"),
                    unique_bar_count=int(len(frame)),
                    raw_row_count=int(len(frame)),
                    exact_duplicate_row_count=0,
                    overlapping_row_count=0,
                    conflicting_row_count=0,
                    invalid_row_count=0,
                    expected_bar_count=None,
                    coverage_ratio=1.0,
                    fingerprint=content_id("qdfetch", {"symbol": symbol, "timeframe": plan.base_timeframe, "rows": int(len(frame)), "start": str(frame.index.min()), "end": str(frame.index.max())}),
                    source_id="yfinance",
                    source_policy_version="snapshot_scoped_screening_pr4_v1",
                    qualification_status="COHERENT",
                    immutable=True,
                    created_at_utc=_to_utc(now),
                    partition_refs=(cache_path.as_posix().replace("\\", "/"),),
                    compatibility_status="ROOT",
                    lineage_depth=0,
                    content_identity=content_id("qdsnaprow", {"path": cache_path.as_posix(), "rows": int(len(frame))}),
                )
                append_snapshot_row(repo_root, snapshot)
        except DataUnavailableError:
            telemetry["partial_failures"] += 1
    refreshed_truth = materialize_data_truth(repo_root, force_refresh=False)
    refreshed_lineage = load_snapshot_lineage(repo_root)["snapshot_lineage"]
    telemetry["fingerprints_after"] = [str(row.get("fingerprint") or "") for row in refreshed_lineage.get("rows", []) if isinstance(row, dict)]
    telemetry["rows_reused"] = sum(int(row.get("row_count") or 0) for row in refreshed_truth["catalog"]["datasets"])
    telemetry["provider_calls_avoided"] = max(int(plan.estimated_calls or 0) - int(telemetry["provider_calls"]), 0)
    telemetry["cache_hit_rate"] = 1.0 if telemetry["provider_calls"] == 0 else 0.0
    return telemetry


def _to_utc(value: datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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
        "OOS_capacity_gained": int(tier_counts.get(EXECUTION_TIER_LOCKED_OOS_VALIDATION, 0)),
        "source_failures": 1 if telemetry.get("external_boundary") == "STOPPED_SOURCE_CERTIFICATION_BOUNDARY" else 0,
        "identity_failures": 1 if telemetry.get("external_boundary") == "STOPPED_IDENTITY_BOUNDARY" else 0,
        "quality_failures": 1 if telemetry.get("external_boundary") == "STOPPED_SOURCE_CERTIFICATION_BOUNDARY" else 0,
        "time_to_evidence_ready_dataset": None,
        "compute_spent_on_ingestion": 0,
    }


__all__ = [
    "assess_coverage",
    "execute_acquisition_once",
    "plan_acquisition",
    "throughput_snapshot",
    "_screening_slippage_model",
]
