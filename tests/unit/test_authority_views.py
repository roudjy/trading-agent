"""Unit tests for ``research.authority_views`` (ADR-014 §E).

Pins the derived-truth table for the registered strategies:

- ``bundle_active`` reflects ``research.presets.PRESETS`` membership
  (across ``bundle`` and ``optional_bundle``) gated by the preset's
  ``enabled`` flag. The three registered-but-bundle-inert strategies
  (``bollinger_regime``, ``trend_pullback_tp_sl``,
  ``zscore_mean_reversion``) are the canonical
  ``enabled=True`` ∧ ``bundle_active=False`` case (audit §8.6 / E1).
- ``active_discovery`` is True only when the strategy's
  ``strategy_family`` matches a hypothesis with
  ``status="active_discovery"`` in the catalog. Legacy
  ``trend_pullback`` / ``trend_pullback_tp_sl`` (registered with
  ``strategy_family="trend_following"``) MUST return False — they are
  intentionally NOT bridged to the v3.15.3 active_discovery row.
- ``live_eligible`` is hard-pinned to ``False`` for every registered
  strategy through the no-live governance envelope (ADR-014 §E).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from research.authority_views import (
    active_discovery,
    bundle_active,
    live_eligible,
    render_authority_summary,
)
from research.registry import STRATEGIES


# ---------------------------------------------------------------------------
# bundle_active truth table (ADR-014 §E + audit §4.1 / §4.2)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name,expected",
    [
        # Registered-but-bundle-inert (the audit's "misleading" finding).
        ("bollinger_regime", False),
        ("trend_pullback_tp_sl", False),
        ("zscore_mean_reversion", False),
        # pairs_zscore is bundled only in pairs_equities_daily_baseline,
        # but that preset is enabled=False → not bundle_active.
        ("pairs_zscore", False),
        # Bundle-active in enabled presets.
        ("sma_crossover", True),  # trend_equities_4h_baseline + filtered
        ("breakout_momentum", True),
        ("trend_pullback_v1", True),  # trend_pullback_crypto_1h
        ("volatility_compression_breakout", True),
        ("rsi", True),  # crypto_diagnostic_1h
        ("bollinger_mr", True),  # crypto_diagnostic_1h
        # Legacy trend_pullback is in optional_bundle of an enabled preset.
        ("trend_pullback", True),
        # Unknown strategy → False.
        ("nonexistent_strategy", False),
    ],
)
def test_bundle_active_truth_table(name: str, expected: bool) -> None:
    assert bundle_active(name) is expected


# ---------------------------------------------------------------------------
# active_discovery truth table (ADR-014 §A + audit §3.4)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name,expected",
    [
        # Two thin v3.15.3 / v3.15.4 active_discovery strategies.
        ("trend_pullback_v1", True),
        ("volatility_compression_breakout", True),
        # Legacy trend_pullback / trend_pullback_tp_sl carry
        # strategy_family="trend_following" — explicitly NOT bridged.
        ("trend_pullback", False),
        ("trend_pullback_tp_sl", False),
        # Mean-reversion strategies have no active_discovery hypothesis.
        ("rsi", False),
        ("bollinger_mr", False),
        ("bollinger_regime", False),
        ("zscore_mean_reversion", False),
        # SMA crossover and breakout_momentum carry strategy_family="trend_following"
        # — no active_discovery hypothesis on that family.
        ("sma_crossover", False),
        ("breakout_momentum", False),
        # Pairs zscore: stat_arb family has no active_discovery hypothesis.
        ("pairs_zscore", False),
        # Unknown strategy → False.
        ("nonexistent_strategy", False),
    ],
)
def test_active_discovery_truth_table(name: str, expected: bool) -> None:
    assert active_discovery(name) is expected


# ---------------------------------------------------------------------------
# live_eligible hard pin
# ---------------------------------------------------------------------------


def test_live_eligible_false_for_every_registered_strategy() -> None:
    for row in STRATEGIES:
        assert live_eligible(row["name"]) is False


def test_live_eligible_false_for_unknown_strategy() -> None:
    assert live_eligible("nonexistent_strategy") is False


# ---------------------------------------------------------------------------
# render_authority_summary smoke
# ---------------------------------------------------------------------------


def test_render_summary_format_for_known_strategy() -> None:
    summary = render_authority_summary("zscore_mean_reversion")
    assert summary == (
        "zscore_mean_reversion: registered=Y enabled=Y bundle_active=N "
        "active_discovery=N live_eligible=N"
    )


def test_render_summary_format_for_unknown_strategy() -> None:
    summary = render_authority_summary("nonexistent_strategy")
    assert summary == (
        "nonexistent_strategy: registered=N enabled=N bundle_active=N "
        "active_discovery=N live_eligible=N"
    )


# ---------------------------------------------------------------------------
# Forbidden-import guard (ADR-014 §B / Plan §D1)
# ---------------------------------------------------------------------------


_FORBIDDEN_IMPORT_PREFIXES = (
    "research.run_research",
    "research.campaign_launcher",
    "research.runtime",
    "research.screening_runtime",
    "research.candidate_pipeline",
    "research.authority_trace",
    "research.promotion",
    "research.campaign_policy",
    "research.campaign_funnel_policy",
    "research.falsification",
    "research.falsification_reporting",
    "research.candidate_lifecycle",
    "research.paper_readiness",
)


def _imported_modules(source_path: Path) -> list[str]:
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    out: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module is not None:
                out.append(node.module)
    return out


def test_authority_views_does_not_import_forbidden_modules() -> None:
    module_path = (
        Path(__file__).resolve().parents[2] / "research" / "authority_views.py"
    )
    imported = _imported_modules(module_path)
    for forbidden in _FORBIDDEN_IMPORT_PREFIXES:
        for name in imported:
            assert not name.startswith(forbidden), (
                f"authority_views.py must not import {name} — "
                f"forbidden prefix {forbidden}"
            )
