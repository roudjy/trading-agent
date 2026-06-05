"""Execution adapter for controlled discovery grid rows.

This module maps a planned discovery-grid combination onto a bounded,
single-asset research preset override that can be executed through the
existing ``research.run_research`` path. Unsupported behavior families
do not raise as normal control flow; they return a deterministic
``skipped`` blocker result instead.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final

from research.presets import ResearchPreset
from research.production_discovery_catalog import list_presets


REQUIRED_GRID_FIELDS: Final[tuple[str, ...]] = (
    "sequence_number",
    "instrument_symbol",
    "canonical_instrument_id",
    "region",
    "asset_class",
    "behavior_preset_id",
    "hypothesis_id",
    "timeframe",
)

BLOCKER_UNSUPPORTED_MAPPING: Final[str] = "unsupported_grid_to_validation_mapping"
BLOCKER_MISSING_METADATA: Final[str] = "missing_validation_input"
BLOCKER_SAFETY_VIOLATION: Final[str] = "blocked_by_safety"
BLOCKER_REGION_MISMATCH: Final[str] = "preset_region_constraint_mismatch"
BLOCKER_ASSET_CLASS_MISMATCH: Final[str] = "preset_asset_class_constraint_mismatch"


@dataclass(frozen=True)
class ExecutionTemplate:
    behavior_preset_id: str
    preset_reference: str
    bundle: tuple[str, ...]
    screening_phase: str
    executable_hypothesis_id: str | None
    executable: bool
    supported_asset_classes: tuple[str, ...]
    supported_regions: tuple[str, ...]
    unsupported_reason: str | None = None


@dataclass(frozen=True)
class GridExecutionMapping:
    status: str
    blocker_class: str | None
    validation_campaign_id: str
    strategy_or_preset_reference: str | None
    asset_symbol: str
    timeframe: str | None
    hypothesis_id: str | None
    run_label: str
    output_subdir: str
    safety_flags: dict[str, bool]
    mapping_notes: tuple[str, ...]
    preset_override: ResearchPreset | None

    def to_payload(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "blocker_class": self.blocker_class,
            "validation_campaign_id": self.validation_campaign_id,
            "strategy_or_preset_reference": self.strategy_or_preset_reference,
            "asset_symbol": self.asset_symbol,
            "timeframe": self.timeframe,
            "hypothesis_id": self.hypothesis_id,
            "run_label": self.run_label,
            "output_subdir": self.output_subdir,
            "safety_flags": dict(self.safety_flags),
            "mapping_notes": list(self.mapping_notes),
        }


_CATALOG_PRESET_BY_ID: Final[dict[str, dict[str, Any]]] = {
    str(preset.to_payload()["preset_id"]): preset.to_payload()
    for preset in list_presets()
}

_EXECUTION_TEMPLATES: Final[dict[str, ExecutionTemplate]] = {
    "trend_continuation_daily_v1": ExecutionTemplate(
        behavior_preset_id="trend_continuation_daily_v1",
        preset_reference="trend_equities_4h_baseline",
        bundle=("sma_crossover", "breakout_momentum"),
        screening_phase="exploratory",
        executable_hypothesis_id=None,
        executable=True,
        supported_asset_classes=("equity", "etf"),
        supported_regions=("NL/EU", "US", "Asia/proxies", "ETFs/context"),
    ),
    "trend_pullback_continuation_daily_v1": ExecutionTemplate(
        behavior_preset_id="trend_pullback_continuation_daily_v1",
        preset_reference="trend_pullback_equities_4h",
        bundle=("trend_pullback_v1",),
        screening_phase="exploratory",
        executable_hypothesis_id="trend_pullback_v1",
        executable=True,
        supported_asset_classes=("equity",),
        supported_regions=("NL/EU", "US", "Asia/proxies"),
    ),
    "vol_compression_breakout_daily_v1": ExecutionTemplate(
        behavior_preset_id="vol_compression_breakout_daily_v1",
        preset_reference="vol_compression_breakout_crypto_1h",
        bundle=("volatility_compression_breakout",),
        screening_phase="exploratory",
        executable_hypothesis_id="volatility_compression_breakout_v0",
        executable=True,
        supported_asset_classes=("equity", "etf"),
        supported_regions=("NL/EU", "US", "Asia/proxies", "ETFs/context"),
    ),
    "vol_compression_breakout_4h_v1": ExecutionTemplate(
        behavior_preset_id="vol_compression_breakout_4h_v1",
        preset_reference="vol_compression_breakout_crypto_4h",
        bundle=("volatility_compression_breakout",),
        screening_phase="exploratory",
        executable_hypothesis_id="volatility_compression_breakout_v0",
        executable=True,
        supported_asset_classes=("equity", "etf"),
        supported_regions=("US", "ETFs/context"),
    ),
    "relative_strength_vs_sector_daily_v1": ExecutionTemplate(
        behavior_preset_id="relative_strength_vs_sector_daily_v1",
        preset_reference=None,
        bundle=(),
        screening_phase="exploratory",
        executable_hypothesis_id=None,
        executable=False,
        supported_asset_classes=("equity",),
        supported_regions=("NL/EU", "US"),
        unsupported_reason="preset_not_executable",
    ),
    "relative_strength_vs_region_daily_v1": ExecutionTemplate(
        behavior_preset_id="relative_strength_vs_region_daily_v1",
        preset_reference=None,
        bundle=(),
        screening_phase="exploratory",
        executable_hypothesis_id=None,
        executable=False,
        supported_asset_classes=("equity", "etf"),
        supported_regions=("NL/EU", "US", "Asia/proxies", "ETFs/context"),
        unsupported_reason="preset_not_executable",
    ),
    "post_shock_stabilization_daily_v1": ExecutionTemplate(
        behavior_preset_id="post_shock_stabilization_daily_v1",
        preset_reference=None,
        bundle=(),
        screening_phase="exploratory",
        executable_hypothesis_id=None,
        executable=False,
        supported_asset_classes=("equity", "etf"),
        supported_regions=("NL/EU", "US", "Asia/proxies", "ETFs/context"),
        unsupported_reason="preset_not_executable",
    ),
    "index_regime_filter_daily_v1": ExecutionTemplate(
        behavior_preset_id="index_regime_filter_daily_v1",
        preset_reference=None,
        bundle=(),
        screening_phase="exploratory",
        executable_hypothesis_id=None,
        executable=False,
        supported_asset_classes=("equity", "etf"),
        supported_regions=("NL/EU", "US", "Asia/proxies", "ETFs/context"),
        unsupported_reason="preset_not_executable",
    ),
}


def _missing_required_fields(row: dict[str, Any]) -> list[str]:
    return [field for field in REQUIRED_GRID_FIELDS if row.get(field) in (None, "", [])]


def _safety_flags(row: dict[str, Any]) -> dict[str, bool]:
    return {
        "not_alpha_claim": bool(row.get("not_alpha_claim") is True),
        "paper_activation_allowed": bool(row.get("paper_activation_allowed") is True),
        "shadow_activation_allowed": bool(row.get("shadow_activation_allowed") is True),
        "live_activation_allowed": bool(row.get("live_activation_allowed") is True),
    }


def _deterministic_ids(row: dict[str, Any]) -> tuple[str, str, str]:
    sequence = int(row["sequence_number"])
    symbol = str(row["instrument_symbol"])
    preset_id = str(row["behavior_preset_id"])
    validation_campaign_id = (
        f"qre-grid-validation-{sequence:03d}-{symbol.lower()}-{preset_id}"
    )
    run_label = f"qre_grid_seq_{sequence:03d}_{symbol}_{preset_id}"
    output_subdir = f"combination_{sequence:03d}_{symbol}_{preset_id}"
    return validation_campaign_id, run_label, output_subdir


def _preset_override_for(
    *,
    row: dict[str, Any],
    template: ExecutionTemplate,
) -> ResearchPreset:
    symbol = str(row["instrument_symbol"])
    timeframe = str(row["timeframe"])
    hypothesis_id = (
        template.executable_hypothesis_id
        if template.executable_hypothesis_id is not None
        else None
    )
    return ResearchPreset(
        name=f"qre_grid_exec__{row['sequence_number']:03d}__{symbol}__{template.behavior_preset_id}",
        hypothesis=(
            "Controlled discovery grid execution override. This is a "
            "single-asset bounded research attempt; it is not an alpha claim "
            "and grants no paper/shadow/live authority."
        ),
        universe=(symbol,),
        timeframe=timeframe,
        bundle=template.bundle,
        screening_mode="strict",
        screening_phase=template.screening_phase,  # type: ignore[arg-type]
        cost_mode="realistic",
        status="stable",
        enabled=True,
        diagnostic_only=False,
        excluded_from_daily_scheduler=True,
        excluded_from_candidate_promotion=False,
        hypothesis_id=hypothesis_id,
        preset_class="experimental",
        rationale=(
            "Bounded controlled discovery-grid execution over an existing "
            "executable strategy bundle."
        ),
        expected_behavior=(
            "Produces per-combination research evidence using the existing "
            "run_research path with a single-asset universe override."
        ),
        falsification=(
            "No executable candidates emerge for the mapped asset/timeframe.",
            "Validation evidence remains insufficient or absent.",
        ),
        enablement_criteria=(
            "not_alpha_claim remains true",
            "paper_activation_allowed remains false",
            "shadow_activation_allowed remains false",
            "live_activation_allowed remains false",
        ),
    )


def map_grid_row_to_execution(row: dict[str, Any]) -> GridExecutionMapping:
    validation_campaign_id, run_label, output_subdir = _deterministic_ids(
        {
            **row,
            "sequence_number": int(row.get("sequence_number") or 0),
            "instrument_symbol": str(row.get("instrument_symbol") or "unknown"),
            "behavior_preset_id": str(row.get("behavior_preset_id") or "unknown"),
        }
    )
    safety_flags = _safety_flags(row)
    missing = _missing_required_fields(row)
    if missing:
        return GridExecutionMapping(
            status="skipped",
            blocker_class=BLOCKER_MISSING_METADATA,
            validation_campaign_id=validation_campaign_id,
            strategy_or_preset_reference=None,
            asset_symbol=str(row.get("instrument_symbol") or ""),
            timeframe=str(row.get("timeframe") or "") or None,
            hypothesis_id=str(row.get("hypothesis_id") or "") or None,
            run_label=run_label,
            output_subdir=output_subdir,
            safety_flags=safety_flags,
            mapping_notes=tuple(f"missing_{field}" for field in missing),
            preset_override=None,
        )
    if (
        not safety_flags["not_alpha_claim"]
        or safety_flags["paper_activation_allowed"]
        or safety_flags["shadow_activation_allowed"]
        or safety_flags["live_activation_allowed"]
    ):
        return GridExecutionMapping(
            status="skipped",
            blocker_class=BLOCKER_SAFETY_VIOLATION,
            validation_campaign_id=validation_campaign_id,
            strategy_or_preset_reference=None,
            asset_symbol=str(row["instrument_symbol"]),
            timeframe=str(row["timeframe"]),
            hypothesis_id=str(row["hypothesis_id"]),
            run_label=run_label,
            output_subdir=output_subdir,
            safety_flags=safety_flags,
            mapping_notes=("grid_row_failed_safety_invariants",),
            preset_override=None,
        )

    behavior_preset_id = str(row["behavior_preset_id"])
    template = _EXECUTION_TEMPLATES.get(behavior_preset_id)
    if template is None:
        return GridExecutionMapping(
            status="skipped",
            blocker_class=BLOCKER_UNSUPPORTED_MAPPING,
            validation_campaign_id=validation_campaign_id,
            strategy_or_preset_reference=None,
            asset_symbol=str(row["instrument_symbol"]),
            timeframe=str(row["timeframe"]),
            hypothesis_id=str(row["hypothesis_id"]),
            run_label=run_label,
            output_subdir=output_subdir,
            safety_flags=safety_flags,
            mapping_notes=("unknown_behavior_preset_id",),
            preset_override=None,
        )

    asset_class = str(row["asset_class"])
    region = str(row["region"])
    if asset_class not in template.supported_asset_classes:
        return GridExecutionMapping(
            status="skipped",
            blocker_class=BLOCKER_ASSET_CLASS_MISMATCH,
            validation_campaign_id=validation_campaign_id,
            strategy_or_preset_reference=template.preset_reference,
            asset_symbol=str(row["instrument_symbol"]),
            timeframe=str(row["timeframe"]),
            hypothesis_id=str(row["hypothesis_id"]),
            run_label=run_label,
            output_subdir=output_subdir,
            safety_flags=safety_flags,
            mapping_notes=("asset_class_not_supported_by_executable_mapping",),
            preset_override=None,
        )
    if region not in template.supported_regions:
        return GridExecutionMapping(
            status="skipped",
            blocker_class=BLOCKER_REGION_MISMATCH,
            validation_campaign_id=validation_campaign_id,
            strategy_or_preset_reference=template.preset_reference,
            asset_symbol=str(row["instrument_symbol"]),
            timeframe=str(row["timeframe"]),
            hypothesis_id=str(row["hypothesis_id"]),
            run_label=run_label,
            output_subdir=output_subdir,
            safety_flags=safety_flags,
            mapping_notes=("region_not_supported_by_executable_mapping",),
            preset_override=None,
        )
    if not template.executable or template.preset_reference is None:
        return GridExecutionMapping(
            status="skipped",
            blocker_class=template.unsupported_reason or BLOCKER_UNSUPPORTED_MAPPING,
            validation_campaign_id=validation_campaign_id,
            strategy_or_preset_reference=template.preset_reference,
            asset_symbol=str(row["instrument_symbol"]),
            timeframe=str(row["timeframe"]),
            hypothesis_id=str(row["hypothesis_id"]),
            run_label=run_label,
            output_subdir=output_subdir,
            safety_flags=safety_flags,
            mapping_notes=("no_existing_executable_preset_for_behavior_family",),
            preset_override=None,
        )

    preset_override = _preset_override_for(row=row, template=template)
    catalog_preset = _CATALOG_PRESET_BY_ID.get(behavior_preset_id) or {}
    notes = [
        f"mapped_from_catalog_preset={behavior_preset_id}",
        f"strategy_or_preset_reference={template.preset_reference}",
    ]
    if catalog_preset:
        notes.append(
            f"catalog_required_data_quality={catalog_preset.get('required_data_quality')}"
        )
    return GridExecutionMapping(
        status="ready",
        blocker_class=None,
        validation_campaign_id=validation_campaign_id,
        strategy_or_preset_reference=template.preset_reference,
        asset_symbol=str(row["instrument_symbol"]),
        timeframe=str(row["timeframe"]),
        hypothesis_id=str(row["hypothesis_id"]),
        run_label=run_label,
        output_subdir=output_subdir,
        safety_flags=safety_flags,
        mapping_notes=tuple(notes),
        preset_override=preset_override,
    )
