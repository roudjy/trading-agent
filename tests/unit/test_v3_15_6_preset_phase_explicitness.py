"""v3.15.6 — AST guard: every ResearchPreset(...) call sets screening_phase=.

The dataclass default ``promotion_grade`` is only a safety net for
newly-added presets that forget the keyword. ALL existing presets
MUST set ``screening_phase`` explicitly. This test parses
``research/presets.py`` and walks every ``ResearchPreset(...)``
call to verify the keyword is present.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest


PRESETS_PY = Path("research/presets.py")


def _research_preset_calls() -> list[ast.Call]:
    tree = ast.parse(PRESETS_PY.read_text(encoding="utf-8"))
    calls: list[ast.Call] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                and node.func.id == "ResearchPreset":
            calls.append(node)
    return calls


def test_at_least_six_preset_constructions_present():
    """Sanity: catalog has at least the 6 known presets."""
    calls = _research_preset_calls()
    assert len(calls) >= 6, (
        f"expected >= 6 ResearchPreset(...) calls in presets.py, found {len(calls)}"
    )


def test_every_research_preset_call_has_screening_phase_keyword():
    calls = _research_preset_calls()
    offenders: list[tuple[int, list[str]]] = []
    for call in calls:
        kw_names = {kw.arg for kw in call.keywords if kw.arg is not None}
        if "screening_phase" not in kw_names:
            offenders.append((call.lineno, sorted(kw_names)))
    assert offenders == [], (
        "v3.15.6 explicitness violated — ResearchPreset(...) calls "
        "missing screening_phase= keyword:\n"
        + "\n".join(f"  line {lno}: keys={kws}" for lno, kws in offenders)
    )
