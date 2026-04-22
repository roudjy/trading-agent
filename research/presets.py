"""Research presets — first-class run configurations for v3.10.

A preset is a frozen bundle of (universe, timeframe, strategy-bundle,
screening mode, cost mode) that the ``researchctl`` CLI, the Flask
preset API, and the systemd-timer all feed into ``run_research.py``.
Presets are the v3.10 replacement for the copy-paste loop between
terminal / Claude / GPT.

Layer boundaries:

- This module is pure configuration. It imports from
  ``research.registry`` (the strategy source-of-truth) for
  validation, but NEVER introduces new strategy registrations. A
  preset that names a strategy which is not yet in the registry is
  surfaced as ``status="planned"`` with a ``backlog_reason`` so the
  UI can render it and the scheduler can skip it.
- Presets do not touch the frozen ``ROW_SCHEMA`` /
  ``JSON_*_SCHEMA`` tuples in ``research/results.py``. New
  per-run metadata lands in a separate sidecar
  (``research/run_meta_latest.v1.json``) owned by
  ``research.run_state``.
- ``diagnostic_only`` / ``excluded_from_candidate_promotion`` /
  ``excluded_from_daily_scheduler`` are hard flags honoured by the
  promotion layer and the scheduler unit. The safe default on
  missing metadata is "excluded" — a diagnostic run must never be
  silently promoted (see ADR-011 §9).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from research.registry import STRATEGIES


ScreeningMode = Literal["strict", "lenient", "diagnostic"]
CostMode = Literal["realistic", "zero", "stress"]
PresetStatus = Literal["stable", "planned", "diagnostic", "not_executable"]


@dataclass(frozen=True)
class ResearchPreset:
    """Frozen preset descriptor consumed by CLI / API / scheduler."""

    name: str
    hypothesis: str
    universe: tuple[str, ...]
    timeframe: str
    bundle: tuple[str, ...]
    screening_mode: ScreeningMode = "strict"
    cost_mode: CostMode = "realistic"
    status: PresetStatus = "stable"
    enabled: bool = True
    diagnostic_only: bool = False
    excluded_from_daily_scheduler: bool = False
    excluded_from_candidate_promotion: bool = False
    regime_filter: str | None = None
    regime_modes: tuple[str, ...] = field(default_factory=tuple)
    optional_bundle: tuple[str, ...] = field(default_factory=tuple)
    backlog_reason: str | None = None


# ---------------------------------------------------------------------------
# Preset catalog
# ---------------------------------------------------------------------------

_TREND_EQUITIES_UNIVERSE: tuple[str, ...] = (
    "NVDA", "AMD", "ASML", "MSFT", "META", "AMZN", "TSM",
)

_PAIRS_EQUITIES_UNIVERSE: tuple[str, ...] = (
    "NVDA/AMD", "META/GOOGL", "AAPL/MSFT",
)

_CRYPTO_DIAGNOSTIC_UNIVERSE: tuple[str, ...] = (
    "BTC-EUR", "ETH-EUR",
)


PRESETS: tuple[ResearchPreset, ...] = (
    ResearchPreset(
        name="trend_equities_4h_baseline",
        hypothesis=(
            "Twee orthogonale trendstrategieen (SMA crossover + breakout "
            "momentum) capturen persistent directional moves op 4h equities "
            "zonder management-varianten. Doel: een stabiele daily default "
            "zonder strategie-explosie."
        ),
        universe=_TREND_EQUITIES_UNIVERSE,
        timeframe="4h",
        bundle=("sma_crossover", "breakout_momentum"),
        optional_bundle=("trend_pullback",),
        screening_mode="strict",
        cost_mode="realistic",
        status="stable",
        enabled=True,
    ),
    ResearchPreset(
        name="pairs_equities_daily_baseline",
        hypothesis=(
            "Equity-paren via z-score spread mean reversion. Requires OLS "
            "hedge ratio + multi-reference_asset support die niet in v3.10 "
            "scope zit (pairs_zscore is v3.6 scope-lock met fixed "
            "hedge_ratio=1.0 en reference_asset=ETH-EUR)."
        ),
        universe=_PAIRS_EQUITIES_UNIVERSE,
        timeframe="1d",
        bundle=("pairs_zscore",),
        screening_mode="strict",
        cost_mode="realistic",
        status="planned",
        enabled=False,
        backlog_reason=(
            "v3.11 equity-pairs ADR required: OLS hedge ratio + "
            "multi-reference_asset. See ADR-011 \u00a77."
        ),
    ),
    ResearchPreset(
        name="trend_regime_filtered_equities_4h",
        hypothesis=(
            "Zelfde trendbundel als preset 1 maar onder een regime-filter "
            "(trend_only + low_vol_only afgeleid van bollinger_regime). "
            "Diagnostisch: verbetert regimefiltering de trendstrategieen? "
            "Bollinger mean-reversion is NIET primair in deze preset."
        ),
        universe=_TREND_EQUITIES_UNIVERSE,
        timeframe="4h",
        bundle=("sma_crossover", "breakout_momentum"),
        regime_filter="bollinger_regime_derived",
        regime_modes=("trend_only", "low_vol_only"),
        screening_mode="strict",
        cost_mode="realistic",
        status="stable",
        enabled=True,
    ),
    ResearchPreset(
        name="crypto_diagnostic_1h",
        hypothesis=(
            "Crypto 1h intraday MR is diagnostisch, niet primaire alpha-"
            "richting (orchestrator_brief). Preset loopt om rejection "
            "patronen te observeren; mag nooit promoten of auto-scheduled "
            "draaien."
        ),
        universe=_CRYPTO_DIAGNOSTIC_UNIVERSE,
        timeframe="1h",
        bundle=("rsi", "bollinger_mr"),
        screening_mode="diagnostic",
        cost_mode="stress",
        status="diagnostic",
        enabled=True,
        diagnostic_only=True,
        excluded_from_daily_scheduler=True,
        excluded_from_candidate_promotion=True,
    ),
)


_DEFAULT_DAILY_PRESET = "trend_equities_4h_baseline"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def list_presets() -> list[ResearchPreset]:
    return list(PRESETS)


def get_preset(name: str) -> ResearchPreset:
    for preset in PRESETS:
        if preset.name == name:
            return preset
    known = ", ".join(p.name for p in PRESETS)
    raise KeyError(f"unknown preset {name!r}; known: {known}")


def default_daily_preset() -> ResearchPreset:
    """Preset used by the systemd-timer on the VPS."""
    return get_preset(_DEFAULT_DAILY_PRESET)


def resolve_preset_bundle(preset: ResearchPreset) -> list[dict]:
    """Return the registry entries for the preset bundle.

    Bundle names that are not in the registry are silently dropped (the
    preset still carries them for UI surfacing; the resolver only returns
    executable entries). Disabled presets always return an empty list so
    no accidental execution can happen.
    """
    if not preset.enabled:
        return []
    known_by_name = {strategy["name"]: strategy for strategy in STRATEGIES}
    resolved: list[dict] = []
    for entry_name in preset.bundle:
        if entry_name in known_by_name:
            resolved.append(known_by_name[entry_name])
    return resolved


def validate_preset(preset: ResearchPreset) -> list[str]:
    """Return a list of issues; empty list means the preset is executable."""
    issues: list[str] = []
    if not preset.enabled:
        if preset.backlog_reason is None:
            issues.append("disabled preset must carry a backlog_reason")
        return issues

    known = {strategy["name"] for strategy in STRATEGIES}
    missing = [name for name in preset.bundle if name not in known]
    if missing:
        issues.append(
            f"bundle references unknown strategies: {sorted(missing)}"
        )
    resolved = resolve_preset_bundle(preset)
    if not resolved:
        issues.append("bundle has no executable strategies after resolution")

    # Pair identifiers (NVDA/AMD) only make sense for pairs strategies.
    pair_entries = [a for a in preset.universe if "/" in a]
    if pair_entries and "pairs_zscore" not in preset.bundle:
        issues.append(
            "universe contains pair identifiers but bundle does not include "
            "pairs_zscore"
        )

    if preset.diagnostic_only and not preset.excluded_from_candidate_promotion:
        issues.append(
            "diagnostic_only preset must also set "
            "excluded_from_candidate_promotion"
        )
    return issues


def daily_schedulable_presets() -> list[ResearchPreset]:
    """Presets the systemd-timer is allowed to fire."""
    return [
        preset
        for preset in PRESETS
        if preset.enabled and not preset.excluded_from_daily_scheduler
    ]


def preset_to_card(preset: ResearchPreset) -> dict:
    """Flatten a preset into a JSON-safe card for the UI."""
    return {
        "name": preset.name,
        "hypothesis": preset.hypothesis,
        "universe": list(preset.universe),
        "timeframe": preset.timeframe,
        "bundle": list(preset.bundle),
        "optional_bundle": list(preset.optional_bundle),
        "screening_mode": preset.screening_mode,
        "cost_mode": preset.cost_mode,
        "status": preset.status,
        "enabled": preset.enabled,
        "diagnostic_only": preset.diagnostic_only,
        "excluded_from_daily_scheduler": preset.excluded_from_daily_scheduler,
        "excluded_from_candidate_promotion": preset.excluded_from_candidate_promotion,
        "regime_filter": preset.regime_filter,
        "regime_modes": list(preset.regime_modes),
        "backlog_reason": preset.backlog_reason,
    }


__all__ = [
    "CostMode",
    "PRESETS",
    "PresetStatus",
    "ResearchPreset",
    "ScreeningMode",
    "daily_schedulable_presets",
    "default_daily_preset",
    "get_preset",
    "list_presets",
    "preset_to_card",
    "resolve_preset_bundle",
    "validate_preset",
]
