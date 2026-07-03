from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from packages.qre_data.dataset_catalog import materialize_data_truth

from .acquisition import assess_coverage, plan_acquisition
from .contracts import (
    EXECUTION_TIER_COMPILER_ONLY,
    EXECUTION_TIER_EMPIRICAL_SCREENING,
    EXECUTION_TIER_EXECUTOR_SMOKE,
    EXECUTION_TIER_LOCKED_OOS_VALIDATION,
    AcquisitionPlan,
    CoverageAssessment,
    CoverageDecision,
    DataRequirement,
    ExperimentContract,
    UniversePlan,
    content_id,
)

TIER_ORDER = {
    EXECUTION_TIER_COMPILER_ONLY: 0,
    EXECUTION_TIER_EXECUTOR_SMOKE: 1,
    EXECUTION_TIER_EMPIRICAL_SCREENING: 2,
    EXECUTION_TIER_LOCKED_OOS_VALIDATION: 3,
}


def _parse_ts(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _span_days(start: Any, end: Any) -> int:
    start_ts = _parse_ts(start)
    end_ts = _parse_ts(end)
    if start_ts is None or end_ts is None:
        return 0
    return max((end_ts - start_ts).days, 0)


def _history_span_for_tier(tier: str, timeframe: str) -> str:
    if tier == EXECUTION_TIER_EXECUTOR_SMOKE:
        return "5d"
    if timeframe == "1h":
        return "120d"
    if timeframe == "4h":
        return "365d"
    return "90d"


def _min_rows_for_tier(tier: str, timeframe: str) -> int:
    if tier == EXECUTION_TIER_EXECUTOR_SMOKE:
        return 5
    if timeframe == "1h":
        return 500
    if timeframe == "4h":
        return 250
    return 90


def _load_selected_frame(repo_root: Path, dataset_row: dict[str, Any]) -> pd.DataFrame | None:
    partitions = [str(item) for item in dataset_row.get("partition_refs") or [] if item]
    if not partitions:
        return None
    frames: list[pd.DataFrame] = []
    for rel_path in partitions:
        path = repo_root / rel_path
        if not path.is_file():
            continue
        frame = pd.read_parquet(path)
        if "timestamp_utc" in frame.columns:
            frame = frame.copy()
            frame["timestamp_utc"] = pd.to_datetime(frame["timestamp_utc"], utc=True)
        frames.append(frame)
    if not frames:
        return None
    combined = pd.concat(frames, ignore_index=True)
    if "timestamp_utc" in combined.columns:
        combined = combined.sort_values("timestamp_utc").drop_duplicates(subset=["timestamp_utc"], keep="last")
        combined = combined.set_index("timestamp_utc")
    return combined


def build_data_requirement(contract: ExperimentContract, universe_plan: UniversePlan) -> DataRequirement:
    requested_tier = contract.requested_execution_tier
    minimum_rows = _min_rows_for_tier(requested_tier, contract.timeframe)
    minimum_validation_rows = 0 if requested_tier == EXECUTION_TIER_EXECUTOR_SMOKE else max(minimum_rows // 4, 20)
    minimum_locked_oos_rows = 0 if requested_tier != EXECUTION_TIER_LOCKED_OOS_VALIDATION else max(minimum_rows // 4, 20)
    minimum_expected_trades = 1 if requested_tier == EXECUTION_TIER_EXECUTOR_SMOKE else 3
    minimum_locked_oos_activity = 0 if requested_tier != EXECUTION_TIER_LOCKED_OOS_VALIDATION else 2
    history_span = _history_span_for_tier(requested_tier, contract.timeframe)
    return DataRequirement(
        requirement_id=content_id(
            "qdr",
            {"experiment_id": contract.experiment_id, "timeframe": contract.timeframe, "tier": requested_tier},
        ),
        experiment_id=contract.experiment_id,
        universe_plan_id=universe_plan.universe_plan_id,
        universe_selector=contract.universe_spec,
        resolved_instrument_ids=universe_plan.resolved_assets,
        instrument_requirements=universe_plan.resolved_assets,
        timeframe=contract.timeframe,
        base_timeframe=contract.timeframe,
        required_timeframes=(contract.timeframe,),
        required_fields=contract.required_data_fields,
        required_history_start="derived_from_catalog",
        required_history_end="latest_complete_bar",
        required_history_span=history_span,
        minimum_rows=minimum_rows,
        minimum_rows_per_asset=minimum_rows,
        minimum_assets=max(universe_plan.minimum_assets, 1),
        target_assets=max(universe_plan.target_assets, 1),
        minimum_common_history=history_span,
        requested_execution_tier=requested_tier,
        minimum_history_span=history_span,
        minimum_expected_signals=minimum_expected_trades,
        minimum_expected_trades=minimum_expected_trades,
        minimum_validation_rows=minimum_validation_rows,
        minimum_locked_oos_rows=minimum_locked_oos_rows,
        minimum_locked_oos_activity=minimum_locked_oos_activity,
        validation_requirement=contract.validation_policy,
        locked_oos_requirement=contract.locked_OOS_policy,
        embargo_requirement=contract.embargo_policy,
        warmup_requirement=contract.warmup_policy,
        required_source_quality="quality_gated",
        required_identity_status="resolved",
        required_cost_model=contract.transaction_cost_model,
        required_slippage_model=contract.slippage_model,
        point_in_time_requirement="point_in_time_rows_only" if universe_plan.point_in_time_required else "not_required",
        corporate_action_requirement="not_applicable_or_canonical",
        session_calendar_requirement="canonical_session_calendar_if_available",
        PIT_requirement=universe_plan.point_in_time_status,
        cost_data_requirement=contract.transaction_cost_model,
        slippage_data_requirement=contract.slippage_model,
        regime_context_requirement="experiment_declared_regime_scope",
        quality_policy="quality_ready_only",
        identity_policy="identity_resolved_only",
        preferred_sources=("market_repository",),
        content_identity=content_id(
            "qdrp",
            {"timeframe": contract.timeframe, "universe": contract.universe_spec, "tier": requested_tier, "universe_plan_id": universe_plan.universe_plan_id},
        ),
    )


def _coverage_to_decision(
    *,
    repo_root: Path,
    requirement: DataRequirement,
    coverage: CoverageAssessment,
    catalog: dict[str, Any],
) -> CoverageDecision:
    datasets = {str(row.get("dataset_id") or ""): dict(row) for row in catalog.get("datasets") or [] if isinstance(row, dict)}
    selected_row = dict(coverage.rows[0]) if coverage.rows else {}
    dataset_row = datasets.get(str(selected_row.get("dataset_id") or ""), {})
    frame = _load_selected_frame(repo_root, dataset_row) if dataset_row else None
    admissible_tier = str(dataset_row.get("highest_admissible_tier") or EXECUTION_TIER_COMPILER_ONLY)
    if coverage.decision == "SOURCE_QUALITY_BLOCKED":
        admissible_tier = EXECUTION_TIER_EXECUTOR_SMOKE
    selected_data = {
        "selected_row": selected_row,
        "dataset_id": dataset_row.get("dataset_id"),
        "data_path": str((dataset_row.get("partition_refs") or [""])[0]),
        "row_count": int(dataset_row.get("row_count") or 0),
        "history_span_days": _span_days(dataset_row.get("start"), dataset_row.get("end")),
        "frame": frame,
        "dataset_partition_count": len(tuple(dataset_row.get("partition_refs") or ())),
        "row_integrity_status": str(dataset_row.get("quality_summary", {}).get("row_integrity_status") or "unknown"),
        "cache_integrity_status": "ready" if dataset_row else "blocked",
        "source_quality_status": str(dataset_row.get("quality_summary", {}).get("source_quality_status") or "unknown"),
        "source_identity_status": str(dataset_row.get("identity_summary", {}).get("source_identity_status") or "ambiguous"),
        "campaign_scoped_quality_status": str(dataset_row.get("quality_summary", {}).get("campaign_scoped_quality_status") or "unknown"),
        "effective_research_quality_status": str(dataset_row.get("quality_summary", {}).get("effective_research_quality_status") or "unknown"),
        "validation_rows": int(max(int(dataset_row.get("row_count") or 0) // 5, 0)),
        "locked_oos_rows": int(max(int(dataset_row.get("row_count") or 0) // 10, 0)),
        "estimated_activity": int(max(int(dataset_row.get("row_count") or 0) // 40, 0)),
        "window_capacity": dict(dataset_row.get("window_capacity", {})),
    }
    reason_codes = tuple(str(item) for item in selected_row.get("reason_codes") or ())
    decision = "CACHE_READY" if dataset_row else "FETCH_REQUIRED"
    approved_fetch = coverage.decision in {"COVERAGE_PARTIAL_FETCHABLE", "EXTERNAL_DATA_BOUNDARY"}
    return CoverageDecision(
        decision=decision,
        coverage_decision=coverage.decision,
        requested_execution_tier=requirement.requested_execution_tier,
        admissible_execution_tier=admissible_tier,
        tier_downgrade_reasons=reason_codes,
        reason_codes=reason_codes,
        selected_data=selected_data,
        approved_fetch=approved_fetch,
        dataset_inventory=tuple(dict(row) for row in catalog.get("datasets") or [] if isinstance(row, dict)),
        content_identity=content_id(
            "qdc",
            {
                "coverage": coverage.coverage_assessment_id,
                "dataset_id": dataset_row.get("dataset_id"),
                "admissible_tier": admissible_tier,
            },
        ),
    )


def resolve_data_plan(
    repo_root: Path,
    requirement: DataRequirement,
    *,
    universe_plan: UniversePlan,
) -> tuple[CoverageDecision, CoverageAssessment, AcquisitionPlan, dict[str, Any], UniversePlan]:
    truth = materialize_data_truth(repo_root)
    catalog = truth["catalog"]
    resolved_universe = universe_plan
    coverage = assess_coverage(repo_root=repo_root, requirement=requirement, universe_plan=resolved_universe, catalog=catalog)
    acquisition = plan_acquisition(requirement=requirement, coverage=coverage)
    decision = _coverage_to_decision(repo_root=repo_root, requirement=requirement, coverage=coverage, catalog=catalog)
    return decision, coverage, acquisition, truth, resolved_universe


__all__ = [
    "build_data_requirement",
    "resolve_data_plan",
]
