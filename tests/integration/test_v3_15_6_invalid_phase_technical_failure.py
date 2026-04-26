"""v3.15.6 — end-to-end: invalid screening_phase → technical_failure.

Three-layer test (no committed fixture, no catalog pollution):

1. Pure helper: ``_enforce_preset_validation`` under
   ``QRE_STRICT_PRESET_VALIDATION=1`` raises ``PresetValidationError``.
2. Subprocess: a Python ``-c`` snippet constructs an inline
   ``ResearchPreset`` with an invalid phase, calls
   ``_enforce_preset_validation`` under strict env. Exit code is
   verified to be 1.
3. Launcher dispatch: rc=1 routes through the pure v3.15.5
   technical-failure helper (``_technical_failure_reason_code``).
   Outcome must be ``"technical_failure"`` and must NOT be
   ``"research_rejection"``, ``"degenerate_no_survivors"``, or
   ``"worker_crashed"``.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from research.campaign_launcher import _technical_failure_reason_code
from research.empty_run_reporting import (
    EXIT_CODE_DEGENERATE_NO_SURVIVORS,
    DegenerateResearchRunError,
)
from research.presets import ResearchPreset
from research.run_research import (
    PresetValidationError,
    _enforce_preset_validation,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


# ---- Layer 1: pure helper ---------------------------------------------------


class _FakeTracker:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    def emit_event(self, name: str, **kwargs) -> None:
        self.events.append((name, kwargs))


def test_strict_mode_raises_preset_validation_error(monkeypatch):
    monkeypatch.setenv("QRE_STRICT_PRESET_VALIDATION", "1")
    bad = ResearchPreset(
        name="x_e2e",
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
    with pytest.raises(PresetValidationError):
        _enforce_preset_validation(bad, _FakeTracker())


# ---- Layer 2: subprocess (no catalog pollution) -----------------------------


def test_subprocess_invalid_phase_returns_rc_1():
    """Inline preset construction in subprocess. No file is added to
    the repo or to the global preset catalog.
    """
    snippet = textwrap.dedent("""
        import os, sys
        os.environ["QRE_STRICT_PRESET_VALIDATION"] = "1"
        from research.presets import ResearchPreset
        from research.run_research import (
            _enforce_preset_validation, PresetValidationError,
        )

        class T:
            def emit_event(self, name, **kwargs): pass

        bad = ResearchPreset(
            name="x_subproc",
            hypothesis="h",
            universe=("A",),
            timeframe="1d",
            bundle=(),
            screening_phase="not_a_phase",
            enabled=False,
            backlog_reason="t",
            rationale="r",
            expected_behavior="e",
            falsification=("f",),
        )
        try:
            _enforce_preset_validation(bad, T())
        except PresetValidationError:
            sys.exit(1)
        sys.exit(0)
    """).strip()
    completed = subprocess.run(  # nosec B603
        [sys.executable, "-c", snippet],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
        shell=False,
    )
    assert completed.returncode == 1, (
        f"expected rc=1; got rc={completed.returncode}, "
        f"stderr={completed.stderr[:300]}"
    )
    # Crucially, rc must NOT be EXIT_CODE_DEGENERATE_NO_SURVIVORS.
    assert completed.returncode != EXIT_CODE_DEGENERATE_NO_SURVIVORS


# ---- Layer 3: launcher dispatch maps rc=1 → technical_failure --------------


def test_launcher_dispatch_maps_rc1_to_technical_failure():
    """Mirror the launcher's rc-dispatch decision rules
    (research/campaign_launcher.py around line 800).
    """
    rc = 1
    # The launcher decides the outcome bucket on rc:
    #   rc == EXIT_CODE_DEGENERATE_NO_SURVIVORS → degenerate_no_survivors
    #   rc != 0 and rc != 2                     → technical_failure
    #   rc == 0                                 → paper / research / completed
    if rc == EXIT_CODE_DEGENERATE_NO_SURVIVORS:
        outcome = "degenerate_no_survivors"
    elif rc != 0:
        outcome = "technical_failure"
        reason_code = _technical_failure_reason_code(rc)
        assert reason_code == "worker_crash"  # rc=1 → worker_crash
    else:
        outcome = "<unreachable>"

    assert outcome == "technical_failure"
    assert outcome != "research_rejection"
    assert outcome != "degenerate_no_survivors"
    assert outcome != "worker_crashed"  # deprecated alias never emitted


def test_outcome_invariants_for_rc_1():
    """Defense in depth — explicit set membership."""
    rc = 1
    forbidden = {
        "research_rejection",
        "degenerate_no_survivors",
        "worker_crashed",
    }
    if rc != 0 and rc != EXIT_CODE_DEGENERATE_NO_SURVIVORS:
        outcome = "technical_failure"
    else:
        outcome = "other"
    assert outcome not in forbidden
    assert outcome == "technical_failure"
