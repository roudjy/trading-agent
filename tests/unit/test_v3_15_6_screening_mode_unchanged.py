"""v3.15.6 — guard: legacy screening_mode is unchanged.

Pre-v3.15.6 every preset's ``screening_mode`` value is part of an
implicit contract (visible via the dashboard API + CLI). v3.15.6
must not mutate this. The legacy ``ScreeningMode`` Literal must also
remain exactly ``("strict", "lenient", "diagnostic")`` — any
extension would be a separate decision.
"""

from __future__ import annotations

import pytest

from research.presets import PRESETS, ScreeningMode


EXPECTED_LEGACY_SCREENING_MODE: dict[str, str] = {
    "trend_equities_4h_baseline": "strict",
    "pairs_equities_daily_baseline": "strict",
    "trend_regime_filtered_equities_4h": "strict",
    "trend_pullback_crypto_1h": "strict",
    "vol_compression_breakout_crypto_1h": "strict",
    "crypto_diagnostic_1h": "diagnostic",
}


def test_screening_mode_literal_is_byte_identical():
    assert ScreeningMode.__args__ == ("strict", "lenient", "diagnostic")


@pytest.mark.parametrize(
    "preset_name,expected_mode",
    sorted(EXPECTED_LEGACY_SCREENING_MODE.items()),
)
def test_preset_screening_mode_unchanged(preset_name: str, expected_mode: str) -> None:
    matches = [p for p in PRESETS if p.name == preset_name]
    assert matches
    assert matches[0].screening_mode == expected_mode, (
        f"v3.15.6 invariant violated: {preset_name}.screening_mode "
        f"changed to {matches[0].screening_mode!r} (expected {expected_mode!r})."
    )


def test_screening_mode_and_screening_phase_are_distinct_fields():
    """Adjacent fields with similar names; pin that they coexist."""
    preset = PRESETS[0]
    assert hasattr(preset, "screening_mode")
    assert hasattr(preset, "screening_phase")
    # They are not aliases.
    assert preset.screening_mode != preset.screening_phase or \
        preset.screening_mode == "promotion_grade"  # impossible by Literal sets
