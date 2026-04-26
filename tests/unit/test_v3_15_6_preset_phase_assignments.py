"""v3.15.6 — exact screening_phase mapping per preset (§6)."""

from __future__ import annotations

import pytest

from research.presets import PRESETS


EXPECTED_PHASE_BY_NAME: dict[str, str] = {
    "trend_equities_4h_baseline": "promotion_grade",
    "pairs_equities_daily_baseline": "promotion_grade",
    "trend_regime_filtered_equities_4h": "promotion_grade",
    "trend_pullback_crypto_1h": "exploratory",
    "vol_compression_breakout_crypto_1h": "exploratory",
    "crypto_diagnostic_1h": "exploratory",
}


@pytest.mark.parametrize(
    "preset_name,expected_phase",
    sorted(EXPECTED_PHASE_BY_NAME.items()),
)
def test_preset_screening_phase_matches_v3_15_6_mapping(
    preset_name: str, expected_phase: str
) -> None:
    matches = [p for p in PRESETS if p.name == preset_name]
    assert matches, f"preset {preset_name!r} not found in catalog"
    preset = matches[0]
    assert preset.screening_phase == expected_phase, (
        f"{preset_name}: screening_phase={preset.screening_phase!r}, "
        f"expected {expected_phase!r}"
    )


def test_all_current_presets_are_covered_by_mapping():
    actual_names = {p.name for p in PRESETS}
    expected_names = set(EXPECTED_PHASE_BY_NAME.keys())
    assert actual_names == expected_names, (
        "v3.15.6 mapping drift: catalog and expected mapping must agree."
    )
