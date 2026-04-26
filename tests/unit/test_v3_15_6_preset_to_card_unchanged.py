"""v3.15.6 — preset_to_card API surface byte-identical pre-v3.15.6.

Spec §8.1 picks Optie B: do NOT add ``screening_phase`` to
``preset_to_card``. Frontend snapshot tests must continue to
pass. This test pins:

- The set of keys returned by ``preset_to_card`` is exactly the
  pre-v3.15.6 expected set.
- Legacy ``screening_mode`` IS in that set.
- New ``screening_phase`` is NOT in that set.
"""

from __future__ import annotations

from research.presets import PRESETS, preset_to_card


# Pre-v3.15.6 frozen key set. Adding ``screening_phase`` here would
# change the dashboard / frontend API surface; the v3.15.6 plan
# forbids that.
EXPECTED_KEYS: frozenset[str] = frozenset({
    "name",
    "hypothesis",
    "universe",
    "timeframe",
    "bundle",
    "optional_bundle",
    "screening_mode",
    "cost_mode",
    "status",
    "enabled",
    "diagnostic_only",
    "excluded_from_daily_scheduler",
    "excluded_from_candidate_promotion",
    "regime_filter",
    "regime_modes",
    "backlog_reason",
    "preset_class",
    "rationale",
    "expected_behavior",
    "falsification",
    "enablement_criteria",
    "decision",
})


def test_preset_to_card_keys_are_byte_identical_pre_v3_15_6():
    for preset in PRESETS:
        actual = set(preset_to_card(preset).keys())
        assert actual == EXPECTED_KEYS, (
            f"v3.15.6 forbids changing preset_to_card surface. "
            f"{preset.name}: extra={actual - EXPECTED_KEYS}, "
            f"missing={EXPECTED_KEYS - actual}"
        )


def test_legacy_screening_mode_still_in_card():
    preset = PRESETS[0]
    card = preset_to_card(preset)
    assert "screening_mode" in card


def test_new_screening_phase_NOT_in_card():
    preset = PRESETS[0]
    card = preset_to_card(preset)
    assert "screening_phase" not in card, (
        "v3.15.6 plan §8.1 (Optie B): preset_to_card must NOT carry "
        "screening_phase to keep the frontend API surface byte-"
        "identical."
    )
