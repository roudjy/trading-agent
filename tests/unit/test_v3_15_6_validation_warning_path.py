"""v3.15.6 — default validation mode emits warning, run continues.

The default-mode contract (no QRE_STRICT_PRESET_VALIDATION env var):
- Constructing ``ResearchPreset(..., screening_phase="bad")`` must
  succeed (Literal is static-only).
- ``validate_preset(preset)`` must return a list containing
  ``screening_phase_invalid: <value>``.
- ``_enforce_preset_validation(preset, tracker)`` must emit a
  ``preset_validation_warning`` tracker event for the issue and
  must NOT raise.
"""

from __future__ import annotations

import pytest

from research.presets import ResearchPreset, validate_preset
from research.run_research import (
    PresetValidationError,
    _enforce_preset_validation,
)


class _FakeTracker:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    def emit_event(self, name: str, **kwargs) -> None:
        self.events.append((name, kwargs))


def _bad_preset() -> ResearchPreset:
    # rationale/expected_behavior/falsification non-empty so we only
    # surface the screening_phase_invalid issue, not the v3.11
    # hypothesis-metadata noise.
    return ResearchPreset(
        name="x_bad_phase",
        hypothesis="placeholder",
        universe=("AAA",),
        timeframe="1d",
        bundle=(),  # empty bundle is acceptable for this test
        screening_phase="not_a_phase",  # type: ignore[arg-type]
        enabled=False,
        backlog_reason="for-test",
        rationale="r",
        expected_behavior="e",
        falsification=("f",),
    )


def test_construct_invalid_phase_succeeds_at_runtime():
    """Literal is static-only; runtime construction is not blocked."""
    p = _bad_preset()
    assert p.screening_phase == "not_a_phase"


def test_validate_preset_returns_screening_phase_invalid_issue():
    p = _bad_preset()
    issues = validate_preset(p)
    matches = [i for i in issues if i.startswith("screening_phase_invalid:")]
    assert matches, f"expected screening_phase_invalid issue, got: {issues}"


def test_default_mode_emits_warning_event_for_screening_phase(monkeypatch):
    """Without QRE_STRICT_PRESET_VALIDATION, the invalid phase
    surfaces as a tracker event but the run continues.
    """
    monkeypatch.delenv("QRE_STRICT_PRESET_VALIDATION", raising=False)
    p = _bad_preset()
    tracker = _FakeTracker()
    _enforce_preset_validation(p, tracker)
    phase_events = [
        (n, kw) for n, kw in tracker.events
        if n == "preset_validation_warning"
        and "screening_phase_invalid" in str(kw.get("issue", ""))
    ]
    assert phase_events, (
        f"expected preset_validation_warning event for screening_phase_invalid, "
        f"got: {tracker.events}"
    )


def test_default_mode_never_raises_preset_validation_error(monkeypatch):
    monkeypatch.delenv("QRE_STRICT_PRESET_VALIDATION", raising=False)
    p = _bad_preset()
    tracker = _FakeTracker()
    try:
        _enforce_preset_validation(p, tracker)
    except PresetValidationError:
        pytest.fail("default mode must not raise PresetValidationError")
