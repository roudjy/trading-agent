"""v3.15.6 — ScreeningPhase Literal type + dataclass default.

Pins the canonical vocabulary and the safety-net default. ``standard``
is intentionally part of the Literal even though no current preset
uses it (reserved for the future research middle layer).
"""

from __future__ import annotations

from dataclasses import fields

from research.presets import (
    PRESETS,
    ResearchPreset,
    ScreeningPhase,
    validate_preset,
)


def test_screening_phase_literal_has_exact_three_values():
    assert ScreeningPhase.__args__ == ("exploratory", "standard", "promotion_grade")


def test_screening_phase_dataclass_default_is_promotion_grade():
    field_map = {f.name: f for f in fields(ResearchPreset)}
    assert field_map["screening_phase"].default == "promotion_grade"


def test_standard_is_valid_even_though_no_current_preset_uses_it():
    """v3.15.6: ``standard`` must validate cleanly for the future."""
    preset = PRESETS[0].__class__(
        name="x",
        hypothesis="",
        universe=(),
        timeframe="1d",
        bundle=(),
        enabled=False,
        backlog_reason="reserved",
        screening_phase="standard",
    )
    issues = validate_preset(preset)
    phase_issues = [i for i in issues if "screening_phase" in i]
    assert phase_issues == []


def test_no_current_preset_uses_standard():
    """Documents that ``standard`` is reserved; if this fails the
    plan §6 mapping should be revisited.
    """
    standards = [p.name for p in PRESETS if p.screening_phase == "standard"]
    assert standards == []
