from __future__ import annotations

from pathlib import Path
from typing import Any

from .contracts import ExperimentContract, UniversePlan, content_id

UNIVERSE_SINGLE_INSTRUMENT = "SINGLE_INSTRUMENT"
UNIVERSE_STATIC_MULTI_ASSET = "STATIC_MULTI_ASSET"
UNIVERSE_POINT_IN_TIME_INDEX = "POINT_IN_TIME_INDEX"
UNIVERSE_LIQUIDITY_FILTERED = "LIQUIDITY_FILTERED"
UNIVERSE_CROSS_SECTIONAL_PANEL = "CROSS_SECTIONAL_PANEL"
UNIVERSE_PAIR_OR_RELATIVE_VALUE = "PAIR_OR_RELATIVE_VALUE"
UNIVERSE_CAPABILITY_BLOCKED = "UNIVERSE_CAPABILITY_BLOCKED"


def _classify_universe(experiment: ExperimentContract) -> str:
    universe = str(experiment.universe_spec or "").lower()
    if "single_asset" in universe or "single_instrument" in universe:
        return UNIVERSE_SINGLE_INSTRUMENT
    if "cross_section" in universe:
        return UNIVERSE_CROSS_SECTIONAL_PANEL
    if "pair" in universe or "relative" in universe:
        return UNIVERSE_PAIR_OR_RELATIVE_VALUE
    if "index" in universe:
        return UNIVERSE_POINT_IN_TIME_INDEX
    if "multi" in universe:
        return UNIVERSE_STATIC_MULTI_ASSET
    return UNIVERSE_SINGLE_INSTRUMENT


def plan_universe(
    *,
    repo_root: Path,
    experiment: ExperimentContract,
    catalog: dict[str, Any],
    max_assets: int = 20,
) -> UniversePlan:
    del repo_root
    datasets = [dict(row) for row in catalog.get("datasets") or [] if isinstance(row, dict)]
    universe_type = _classify_universe(experiment)
    requested_assets = [str(experiment.universe_spec)]
    pit_required = universe_type in {UNIVERSE_POINT_IN_TIME_INDEX, UNIVERSE_CROSS_SECTIONAL_PANEL, UNIVERSE_PAIR_OR_RELATIVE_VALUE}
    pit_status = "PIT_NOT_REQUIRED"
    final_decision = "UNIVERSE_READY"
    excluded_assets: list[dict[str, str]] = []
    resolved_assets: list[str] = []

    if universe_type == UNIVERSE_SINGLE_INSTRUMENT:
        eligible = [
            row for row in datasets
            if str(row.get("timeframe") or "") == str(experiment.timeframe or "")
            and str(row.get("identity_summary", {}).get("instrument_identity_status") or "") == "ready"
        ]
        eligible = sorted(
            eligible,
            key=lambda row: (
                0 if str(row.get("quality_summary", {}).get("effective_research_quality_status") or "") == "ready" else 1,
                -int(row.get("row_count") or 0),
                str(row.get("dataset_id") or ""),
            ),
        )
        if eligible:
            resolved_assets = [str(eligible[0].get("instrument_ids", ["unknown"])[0])]
        else:
            final_decision = UNIVERSE_CAPABILITY_BLOCKED
    elif pit_required:
        pit_status = "PIT_UNAVAILABLE"
        final_decision = UNIVERSE_CAPABILITY_BLOCKED
        excluded_assets.append({"asset": str(experiment.universe_spec), "reason": "PIT_UNAVAILABLE"})
    else:
        final_decision = UNIVERSE_CAPABILITY_BLOCKED

    return UniversePlan(
        universe_plan_id=content_id(
            "qup",
            {"experiment_id": experiment.experiment_id, "universe_spec": experiment.universe_spec, "type": universe_type},
        ),
        experiment_id=experiment.experiment_id,
        universe_type=universe_type,
        canonical_universe_id=str(experiment.universe_spec),
        selection_date=str(catalog.get("summary", {}).get("generated_at_utc") or "current_catalog"),
        membership_effective_dates=(),
        requested_assets=tuple(requested_assets),
        resolved_assets=tuple(resolved_assets[:max_assets]),
        excluded_assets=tuple(excluded_assets),
        exclusion_reasons=tuple(sorted({str(item["reason"]) for item in excluded_assets})),
        minimum_assets=1,
        target_assets=min(max_assets, 1 if universe_type == UNIVERSE_SINGLE_INSTRUMENT else max_assets),
        liquidity_requirements="baseline_corpus_liquid_only",
        identity_requirements="resolved_identity",
        point_in_time_required=pit_required,
        point_in_time_status=pit_status,
        sector_or_group_metadata_required=universe_type in {UNIVERSE_CROSS_SECTIONAL_PANEL, UNIVERSE_PAIR_OR_RELATIVE_VALUE},
        corporate_actions_required=False,
        session_calendar_required=True,
        survivorship_bias_status="PIT_NOT_REQUIRED" if not pit_required else "PIT_UNAVAILABLE",
        selection_bias_status="CONTROLLED" if resolved_assets else "BLOCKED",
        final_universe_decision=final_decision,
        content_identity=content_id("qupc", {"resolved_assets": resolved_assets, "pit_status": pit_status, "decision": final_decision}),
    )


__all__ = [
    "UNIVERSE_CAPABILITY_BLOCKED",
    "UNIVERSE_CROSS_SECTIONAL_PANEL",
    "UNIVERSE_LIQUIDITY_FILTERED",
    "UNIVERSE_PAIR_OR_RELATIVE_VALUE",
    "UNIVERSE_POINT_IN_TIME_INDEX",
    "UNIVERSE_SINGLE_INSTRUMENT",
    "UNIVERSE_STATIC_MULTI_ASSET",
    "plan_universe",
]
