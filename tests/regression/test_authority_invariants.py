"""Regression invariants for the ADR-014 authority layer.

These tests pin the additive / no-side-effect contract of
``research.authority_views``:

- the module never writes a frozen artifact (no IO at all);
- it never imports a runtime / orchestration / decision module;
- ``live_eligible`` derives ``False`` for every registered strategy
  (the no-live governance envelope is global through v3.17);
- the existing frozen sidecar artifact paths are not touched by
  importing the views module.
"""

from __future__ import annotations

import ast
from pathlib import Path

from research.authority_views import live_eligible
from research.registry import STRATEGIES


_AUTHORITY_VIEWS_PATH = (
    Path(__file__).resolve().parents[2] / "research" / "authority_views.py"
)


# ---------------------------------------------------------------------------
# 1. Live-eligible pin holds for every registered strategy.
# ---------------------------------------------------------------------------


def test_live_eligible_pin_holds_for_every_registered_strategy() -> None:
    """ADR-014 §E + paper_readiness invariant: live_eligible is hard False."""
    for row in STRATEGIES:
        assert live_eligible(row["name"]) is False, (
            f"live_eligible({row['name']!r}) must be False under the no-live "
            f"governance envelope through v3.17."
        )


# ---------------------------------------------------------------------------
# 2. authority_views.py has no IO and no decision-path imports.
# ---------------------------------------------------------------------------


_FORBIDDEN_IMPORT_PREFIXES = (
    # Runtime / orchestration modules.
    "research.run_research",
    "research.campaign_launcher",
    "research.runtime",
    "research.screening_runtime",
    "research.candidate_pipeline",
    # Decision / policy modules — must remain pure.
    "research.promotion",
    "research.campaign_policy",
    "research.campaign_funnel_policy",
    "research.falsification",
    "research.falsification_reporting",
    "research.candidate_lifecycle",
    "research.paper_readiness",
    # Trace module (will be added in v3.15.15.11; views must not consume it).
    "research.authority_trace",
    # IO helpers — views are pure read-only.
    "research._sidecar_io",
    "research.run_state",
)


_FORBIDDEN_IO_CALL_NAMES = frozenset(
    {
        "open",
        "write",
        "write_text",
        "write_bytes",
        "write_json_atomic",
        "write_sidecar_atomic",
    }
)


def _imported_modules(tree: ast.AST) -> list[str]:
    out: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module is not None:
                out.append(node.module)
    return out


def _called_functions(tree: ast.AST) -> set[str]:
    """Collect Name and Attribute call targets from the AST."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                names.add(func.id)
            elif isinstance(func, ast.Attribute):
                names.add(func.attr)
    return names


def test_authority_views_has_no_forbidden_imports() -> None:
    tree = ast.parse(_AUTHORITY_VIEWS_PATH.read_text(encoding="utf-8"))
    imported = _imported_modules(tree)
    for name in imported:
        for forbidden in _FORBIDDEN_IMPORT_PREFIXES:
            assert not name.startswith(forbidden), (
                f"authority_views.py must not import {name} — "
                f"forbidden prefix {forbidden}"
            )


def test_authority_views_has_no_io_calls() -> None:
    tree = ast.parse(_AUTHORITY_VIEWS_PATH.read_text(encoding="utf-8"))
    called = _called_functions(tree)
    leaks = called & _FORBIDDEN_IO_CALL_NAMES
    assert leaks == set(), (
        f"authority_views.py must not call IO functions — "
        f"found: {sorted(leaks)}"
    )


# ---------------------------------------------------------------------------
# 3. Importing authority_views does not touch frozen artifact paths.
# ---------------------------------------------------------------------------


_FROZEN_ARTIFACT_FILENAMES = (
    "research_latest.json",
    "strategy_matrix.csv",
    "candidate_registry_latest.v1.json",
    "strategy_hypothesis_catalog_latest.v1.json",
    "campaign_templates_latest.v1.json",
)


def test_authority_views_source_does_not_reference_frozen_artifact_paths() -> None:
    """Static guard: the module's source must not name any frozen artifact.

    Frozen artifacts are owned by their canonical writers; views must not
    even reference their paths to avoid future drift into write paths.
    """
    source = _AUTHORITY_VIEWS_PATH.read_text(encoding="utf-8")
    for filename in _FROZEN_ARTIFACT_FILENAMES:
        assert filename not in source, (
            f"authority_views.py references frozen artifact {filename!r}; "
            f"views must remain derivation-only."
        )
