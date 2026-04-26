"""v3.15.6 — researchctl dry-run listing surfaces screening_phase.

Source-level guard: the CLI dry-run card includes ``screening_phase``
next to the legacy ``screening_mode``. Both keys present, additive
only. If implementation runs into fragile snapshot tests, this
test should be reviewed for fallback to Optie B (CLI ungewijzigd).
"""

from __future__ import annotations

import inspect
from pathlib import Path

import researchctl


def test_researchctl_dry_run_card_includes_screening_phase():
    """Source-level guard. The dry-run card dict literal must
    include ``"screening_phase": preset.screening_phase``.
    """
    src = Path("researchctl.py").read_text(encoding="utf-8")
    assert '"screening_phase": preset.screening_phase' in src, (
        "researchctl.py dry-run card must include 'screening_phase' "
        "next to 'screening_mode' for operator visibility."
    )


def test_researchctl_dry_run_card_keeps_screening_mode():
    src = Path("researchctl.py").read_text(encoding="utf-8")
    assert '"screening_mode": preset.screening_mode' in src, (
        "Legacy 'screening_mode' must remain in the dry-run card."
    )
