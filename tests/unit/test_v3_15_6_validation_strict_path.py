"""v3.15.6 — strict validation mode raises PresetValidationError.

Strict-mode contract (``QRE_STRICT_PRESET_VALIDATION=1``):
- Invalid ``screening_phase`` raises ``PresetValidationError``.
- The exception is NOT a ``DegenerateResearchRunError``; the
  v3.15.5 launcher therefore classifies the rc=1 outcome as
  ``technical_failure``, not ``degenerate_no_survivors``.
"""

from __future__ import annotations

import pytest

from research.empty_run_reporting import DegenerateResearchRunError
from research.presets import ResearchPreset
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
    return ResearchPreset(
        name="x_strict",
        hypothesis="h",
        universe=("A",),
        timeframe="1d",
        bundle=(),
        screening_phase="not_a_phase",  # type: ignore[arg-type]
        enabled=False,
        backlog_reason="t",
        rationale="r",
        expected_behavior="e",
        falsification=("f",),
    )


def test_strict_mode_raises_preset_validation_error(monkeypatch):
    monkeypatch.setenv("QRE_STRICT_PRESET_VALIDATION", "1")
    p = _bad_preset()
    tracker = _FakeTracker()
    with pytest.raises(PresetValidationError):
        _enforce_preset_validation(p, tracker)


def test_preset_validation_error_is_not_degenerate(monkeypatch):
    """v3.15.6 invariant: strict-mode failure must classify as
    technical_failure downstream, never degenerate or
    research_rejection.
    """
    monkeypatch.setenv("QRE_STRICT_PRESET_VALIDATION", "1")
    p = _bad_preset()
    tracker = _FakeTracker()
    with pytest.raises(PresetValidationError) as excinfo:
        _enforce_preset_validation(p, tracker)
    # Class hierarchy guard: PresetValidationError must not be
    # a (sub)class of DegenerateResearchRunError.
    assert not isinstance(excinfo.value, DegenerateResearchRunError)
    assert not issubclass(PresetValidationError, DegenerateResearchRunError)


def test_strict_mode_emits_warning_event_before_raising(monkeypatch):
    """Tracker event still fires before the exception so operators
    get observability even when the runner aborts.
    """
    monkeypatch.setenv("QRE_STRICT_PRESET_VALIDATION", "1")
    p = _bad_preset()
    tracker = _FakeTracker()
    with pytest.raises(PresetValidationError):
        _enforce_preset_validation(p, tracker)
    phase_events = [
        (n, kw) for n, kw in tracker.events
        if n == "preset_validation_warning"
        and "screening_phase_invalid" in str(kw.get("issue", ""))
    ]
    assert phase_events, (
        f"expected at least one preset_validation_warning event before "
        f"strict-raise, got: {tracker.events}"
    )
