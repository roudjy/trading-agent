"""Deterministic controlled discovery grid planner for QRE.

This module materializes the full enabled instrument x enabled preset
grid from the read-only production discovery catalog. It does not
launch research execution and does not grant paper/shadow/live
authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final

from research import production_discovery_catalog as catalog


SCHEMA_VERSION: Final[int] = 1
GRID_KIND: Final[str] = "qre_controlled_discovery_grid"
PLANNED_STATUS: Final[str] = "planned"
SKIPPED_INVALID_METADATA_STATUS: Final[str] = "skipped_invalid_metadata"
BLOCKED_BY_SAFETY_STATUS: Final[str] = "blocked_by_safety"
ALLOWED_STATUSES: Final[tuple[str, ...]] = (
    PLANNED_STATUS,
    SKIPPED_INVALID_METADATA_STATUS,
    BLOCKED_BY_SAFETY_STATUS,
)

REQUIRED_ASSET_FIELDS: Final[tuple[str, ...]] = (
    "symbol",
    "canonical_instrument_id",
    "region",
    "asset_class",
    "enabled_for_discovery",
    "enabled_for_validation",
)
REQUIRED_PRESET_FIELDS: Final[tuple[str, ...]] = (
    "preset_id",
    "hypothesis_id",
    "allowed_timeframes",
    "enabled_for_discovery",
    "enabled_for_validation",
)


@dataclass(frozen=True)
class GridCombination:
    grid_id: str
    sequence_number: int
    instrument_symbol: str
    canonical_instrument_id: str
    region: str
    asset_class: str
    primary_data_provider_symbol: str | None
    provider_symbol_aliases: tuple[str, ...]
    provider_symbol_status: str
    source_identity_status: str
    source_identity_notes: str
    source_identity_blocker_class: str
    behavior_preset_id: str
    hypothesis_id: str
    timeframe: str
    enabled_for_discovery: bool
    enabled_for_validation: bool
    not_alpha_claim: bool
    paper_activation_allowed: bool
    shadow_activation_allowed: bool
    live_activation_allowed: bool
    status: str
    result_path: str | None
    blocker_class: str | None
    outcome_class: str | None
    metadata_warnings: tuple[str, ...]

    def to_payload(self) -> dict[str, Any]:
        return {
            "grid_id": self.grid_id,
            "sequence_number": self.sequence_number,
            "instrument_symbol": self.instrument_symbol,
            "canonical_instrument_id": self.canonical_instrument_id,
            "region": self.region,
            "asset_class": self.asset_class,
            "primary_data_provider_symbol": self.primary_data_provider_symbol,
            "provider_symbol_aliases": list(self.provider_symbol_aliases),
            "provider_symbol_status": self.provider_symbol_status,
            "source_identity_status": self.source_identity_status,
            "source_identity_notes": self.source_identity_notes,
            "source_identity_blocker_class": self.source_identity_blocker_class,
            "behavior_preset_id": self.behavior_preset_id,
            "hypothesis_id": self.hypothesis_id,
            "timeframe": self.timeframe,
            "enabled_for_discovery": self.enabled_for_discovery,
            "enabled_for_validation": self.enabled_for_validation,
            "not_alpha_claim": self.not_alpha_claim,
            "paper_activation_allowed": self.paper_activation_allowed,
            "shadow_activation_allowed": self.shadow_activation_allowed,
            "live_activation_allowed": self.live_activation_allowed,
            "status": self.status,
            "result_path": self.result_path,
            "blocker_class": self.blocker_class,
            "outcome_class": self.outcome_class,
            "metadata_warnings": list(self.metadata_warnings),
        }


def _payload_has_required_fields(
    payload: dict[str, Any],
    required_fields: tuple[str, ...],
) -> tuple[bool, list[str]]:
    warnings: list[str] = []
    for field in required_fields:
        value = payload.get(field)
        if value in (None, "", []):
            warnings.append(f"missing_{field}")
    return (not warnings, warnings)


def _safety_is_blocked(
    asset_payload: dict[str, Any],
    preset_payload: dict[str, Any],
) -> bool:
    return any(
        bool(source.get(flag))
        for source in (asset_payload, preset_payload)
        for flag in (
            "paper_activation_allowed",
            "shadow_activation_allowed",
            "live_activation_allowed",
        )
    )


def _combination_status(
    asset_payload: dict[str, Any],
    preset_payload: dict[str, Any],
) -> tuple[str, list[str]]:
    asset_valid, asset_warnings = _payload_has_required_fields(
        asset_payload, REQUIRED_ASSET_FIELDS
    )
    preset_valid, preset_warnings = _payload_has_required_fields(
        preset_payload, REQUIRED_PRESET_FIELDS
    )
    warnings = [*asset_warnings, *preset_warnings]
    if not asset_valid or not preset_valid:
        return SKIPPED_INVALID_METADATA_STATUS, warnings
    if _safety_is_blocked(asset_payload, preset_payload):
        return BLOCKED_BY_SAFETY_STATUS, ["discovery_grid_safety_blocked"]
    return PLANNED_STATUS, warnings


def _timeframe_for_preset(preset_payload: dict[str, Any]) -> str:
    allowed_timeframes = preset_payload.get("allowed_timeframes")
    if isinstance(allowed_timeframes, list) and allowed_timeframes:
        return str(allowed_timeframes[0])
    return "unknown"


def list_enabled_assets() -> list[dict[str, Any]]:
    assets = [
        asset.to_payload()
        for asset in catalog.list_assets()
        if asset.enabled_for_discovery and asset.enabled_for_validation
    ]
    region_order = {region: index for index, region in enumerate(catalog.REGION_ORDER)}
    return sorted(
        assets,
        key=lambda item: (
            region_order.get(str(item["region"]), len(region_order)),
            str(item["symbol"]),
        ),
    )


def list_enabled_presets() -> list[dict[str, Any]]:
    presets = [
        preset.to_payload()
        for preset in catalog.list_presets()
        if preset.enabled_for_discovery and preset.enabled_for_validation
    ]
    return sorted(presets, key=lambda item: str(item["preset_id"]))


def build_controlled_discovery_grid() -> list[dict[str, Any]]:
    combinations: list[dict[str, Any]] = []
    source_identity_by_symbol = {
        str(row["instrument_symbol"]): row for row in catalog.source_identity_diagnostics()
    }
    sequence_number = 1
    for asset_payload in list_enabled_assets():
        source_identity = source_identity_by_symbol.get(str(asset_payload["symbol"]), {})
        for preset_payload in list_enabled_presets():
            status, warnings = _combination_status(asset_payload, preset_payload)
            combination = GridCombination(
                grid_id=(
                    "qre-grid::"
                    f'{sequence_number:03d}::'
                    f'{asset_payload["symbol"]}::'
                    f'{preset_payload["preset_id"]}'
                ),
                sequence_number=sequence_number,
                instrument_symbol=str(asset_payload["symbol"]),
                canonical_instrument_id=str(asset_payload["canonical_instrument_id"]),
                region=str(asset_payload["region"]),
                asset_class=str(asset_payload["asset_class"]),
                primary_data_provider_symbol=asset_payload.get("primary_data_provider_symbol"),
                provider_symbol_aliases=tuple(
                    str(value) for value in (asset_payload.get("provider_symbol_aliases") or [])
                ),
                provider_symbol_status=str(asset_payload.get("provider_symbol_status") or "unknown"),
                source_identity_status=str(asset_payload.get("source_identity_status") or "unknown"),
                source_identity_notes=str(asset_payload.get("source_identity_notes") or ""),
                source_identity_blocker_class=str(
                    source_identity.get("source_identity_blocker_class")
                    or "source_identity_missing_provider_symbol"
                ),
                behavior_preset_id=str(preset_payload["preset_id"]),
                hypothesis_id=str(preset_payload["hypothesis_id"]),
                timeframe=_timeframe_for_preset(preset_payload),
                enabled_for_discovery=True,
                enabled_for_validation=True,
                not_alpha_claim=bool(asset_payload["not_alpha_claim"])
                and bool(preset_payload["not_alpha_claim"]),
                paper_activation_allowed=False,
                shadow_activation_allowed=False,
                live_activation_allowed=False,
                status=status,
                result_path=None,
                blocker_class="safety_blocker"
                if status == BLOCKED_BY_SAFETY_STATUS
                else "metadata_incomplete"
                if status == SKIPPED_INVALID_METADATA_STATUS
                else None,
                outcome_class="not_started",
                metadata_warnings=tuple(warnings),
            )
            combinations.append(combination.to_payload())
            sequence_number += 1
    return combinations


def controlled_discovery_grid_payload() -> dict[str, Any]:
    combinations = build_controlled_discovery_grid()
    return {
        "schema_version": SCHEMA_VERSION,
        "grid_kind": GRID_KIND,
        "read_only": True,
        "not_alpha_claim": True,
        "paper_activation_allowed": False,
        "shadow_activation_allowed": False,
        "live_activation_allowed": False,
        "instrument_count": len(list_enabled_assets()),
        "behavior_preset_count": len(list_enabled_presets()),
        "total_combinations": len(combinations),
        "combinations": combinations,
    }
