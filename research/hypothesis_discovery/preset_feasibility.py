"""Preset feasibility for proposal-only Hypothesis Discovery."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from research.presets import PRESETS, ResearchPreset, resolve_preset_bundle


SCHEMA_VERSION: Final[int] = 1
MODULE_VERSION: Final[str] = "v3.15.19-minimal-2026-05-21"


@dataclass(frozen=True)
class PresetFeasibility:
    hypothesis_id: str
    feasible: bool
    preset_names: tuple[str, ...]
    preset_feasibility_ref: str
    reason_codes: tuple[str, ...]

    def to_payload(self) -> dict[str, object]:
        return {
            "schema_version": SCHEMA_VERSION,
            "hypothesis_id": self.hypothesis_id,
            "feasible": self.feasible,
            "preset_names": list(self.preset_names),
            "preset_feasibility_ref": self.preset_feasibility_ref,
            "reason_codes": list(self.reason_codes),
        }


def _is_feasible_preset(preset: ResearchPreset) -> bool:
    return (
        preset.enabled
        and preset.status == "stable"
        and not preset.diagnostic_only
        and bool(resolve_preset_bundle(preset))
    )


def evaluate_preset_feasibility(
    hypothesis_id: str,
    *,
    presets: tuple[ResearchPreset, ...] = PRESETS,
) -> PresetFeasibility:
    bound = [
        p for p in presets
        if p.hypothesis_id == hypothesis_id and _is_feasible_preset(p)
    ]
    names = tuple(sorted(p.name for p in bound))
    if names:
        ref = "preset:" + ",".join(names)
        return PresetFeasibility(
            hypothesis_id=hypothesis_id,
            feasible=True,
            preset_names=names,
            preset_feasibility_ref=ref,
            reason_codes=("preset_stable_enabled", "bundle_resolves"),
        )
    return PresetFeasibility(
        hypothesis_id=hypothesis_id,
        feasible=False,
        preset_names=(),
        preset_feasibility_ref="preset:none",
        reason_codes=("no_stable_enabled_preset",),
    )


def preset_feasibility_payload(
    hypothesis_ids: tuple[str, ...],
    *,
    presets: tuple[ResearchPreset, ...] = PRESETS,
) -> dict[str, object]:
    rows = [
        evaluate_preset_feasibility(hid, presets=presets).to_payload()
        for hid in sorted(hypothesis_ids)
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "items": rows,
    }
