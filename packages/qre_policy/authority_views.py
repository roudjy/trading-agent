"""Derived read-only authority views (ADR-014 section E).

Pure derivations over the canonical authorities defined in ADR-014 section A.
This module does not introduce a new authority; it exposes formal predicates
that distinguish concepts that operators and downstream code would otherwise
conflate.

Authority sources (read-only, never mutated):

- ``research.registry.STRATEGIES``: canonical for "this strategy exists as
  code" / ``enabled``.
- ``research.presets.PRESETS``: canonical for "this strategy is bundled in
  some enabled preset". Driven via ``bundle`` and ``optional_bundle`` fields,
  gated by ``preset.enabled``.
- ``research.strategy_hypothesis_catalog.STRATEGY_HYPOTHESIS_CATALOG``:
  canonical for "this strategy backs an active research hypothesis". Bridged
  via the strategy's ``strategy_family``.

Layer rules:

- No IO; no mutation; no caching beyond function scope.
- No artifact writes.
- No decision-path side effects: this module is observability / diagnostics
  only. Decision logic in ``research.promotion``, ``research.campaign_policy``,
  ``research.campaign_funnel_policy``, ``research.falsification``, and
  ``research.paper_readiness`` must not consume these views.
- No imports from runtime orchestration modules (``run_research``,
  ``campaign_launcher``, ``runtime``, ``screening_runtime``,
  ``candidate_pipeline``).

See ``docs/adr/ADR-014-truth-authority-settlement.md`` for the canonical
authority mapping.
"""

from __future__ import annotations

from typing import Final

from research.presets import PRESETS
from research.registry import STRATEGIES
from research.strategy_hypothesis_catalog import (
    ALPHA_ELIGIBLE_STATUSES,
    STRATEGY_HYPOTHESIS_CATALOG,
)


# Hard pin per ADR-014 section E. Live trading remains gated by the no-live
# governance envelope through v3.17 regardless of any strategy-level
# configuration. Mirrors the paper-readiness invariant.
_LIVE_ELIGIBLE_PIN: Final[bool] = False


def _registry_row(strategy_name: str) -> dict | None:
    for row in STRATEGIES:
        if row.get("name") == strategy_name:
            return row
    return None


def _is_registered(strategy_name: str) -> bool:
    return _registry_row(strategy_name) is not None


def _is_enabled(strategy_name: str) -> bool:
    row = _registry_row(strategy_name)
    if row is None:
        return False
    return bool(row.get("enabled", False))


def bundle_active(strategy_name: str) -> bool:
    """Return whether ``strategy_name`` is bundled in an enabled preset.

    Derived from ``research.presets.PRESETS``. Says nothing about whether the
    strategy is registered or executable; for that, query the registry
    directly.

    Per ADR-014 section E, ``enabled=True`` in the registry does not imply
    ``bundle_active=True``. The registered-but-bundle-inert strategies
    ``bollinger_regime``, ``trend_pullback_tp_sl``, and
    ``zscore_mean_reversion`` are the canonical example.
    """
    for preset in PRESETS:
        if not getattr(preset, "enabled", False):
            continue
        if strategy_name in preset.bundle:
            return True
        if strategy_name in preset.optional_bundle:
            return True
    return False


def active_discovery(strategy_name: str) -> bool:
    """Return whether a strategy bridges to an active discovery hypothesis.

    Per ADR-014 section A, the catalog is canonical for hypothesis status.
    Legacy or non-bridged strategies return ``False`` when no
    ``active_discovery`` hypothesis carries their strategy family.
    """
    row = _registry_row(strategy_name)
    if row is None:
        return False
    family = row.get("strategy_family")
    if not family:
        return False
    for hypothesis in STRATEGY_HYPOTHESIS_CATALOG:
        if hypothesis.strategy_family != family:
            continue
        if hypothesis.status in ALPHA_ELIGIBLE_STATUSES:
            return True
    return False


def live_eligible(strategy_name: str) -> bool:
    """Return the no-live governance pin for the given strategy name."""
    del strategy_name
    return _LIVE_ELIGIBLE_PIN


def render_authority_summary(strategy_name: str) -> str:
    """Return a one-line operator-readable derived authority summary."""

    def _yn(value: bool) -> str:
        return "Y" if value else "N"

    return (
        f"{strategy_name}: "
        f"registered={_yn(_is_registered(strategy_name))} "
        f"enabled={_yn(_is_enabled(strategy_name))} "
        f"bundle_active={_yn(bundle_active(strategy_name))} "
        f"active_discovery={_yn(active_discovery(strategy_name))} "
        f"live_eligible={_yn(live_eligible(strategy_name))}"
    )


__all__ = [
    "bundle_active",
    "active_discovery",
    "live_eligible",
    "render_authority_summary",
]
