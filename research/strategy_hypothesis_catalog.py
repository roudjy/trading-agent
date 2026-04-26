"""Strategy hypothesis catalog (v3.15.3, strict validation v3.15.4).

First-class artifact-backed registry of strategy hypotheses with a
closed status enum. The v3.15.2 Campaign Operating Layer reads this
catalog through ``research.campaign_policy`` to decide which hypotheses
are eligible for autonomous campaign spawning.

Invariant (v3.15.4): at least one hypothesis carries
``status="active_discovery"`` and every active_discovery hypothesis is
fully wired (executable registry strategy, bounded grid, non-empty
eligible_campaign_types, canonical failure modes). Other statuses are
visible-but-not-spawned (``planned``), explicitly blocked
(``disabled``), or enrichment-only (``diagnostic``); none of those may
declare campaign eligibility.

Cross-module preset-bridge validation
(:func:`validate_active_discovery_preset_bridges`) is invoked
explicitly by the orchestrator at startup; it is NOT run at module
import to keep the catalog ↔ presets layering one-directional.

Layer rules:
- This module is pure configuration + payload assembly. It does not
  resolve strategy factories, run features, or touch sidecar IO beyond
  the canonical ``write_sidecar_atomic`` helper.
- The ``family`` field on each hypothesis bridges to the
  ``strategy_family`` column of ``research.registry.STRATEGIES``.
  Executable hypotheses (``active_discovery``) MUST map to at least one
  enabled registry strategy. Metadata-only statuses (``planned``,
  ``disabled``, ``diagnostic``) MAY have no executable strategy yet.
- The artifact ``research/strategy_hypothesis_catalog_latest.v1.json``
  is adjacent to (never spliced into) the frozen v3.5+ contracts
  ``research_latest.json`` and ``strategy_matrix.csv``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Final, Literal

from research._sidecar_io import (
    require_schema_version,
    write_sidecar_atomic,
)
from research.campaign_os_artifacts import build_pin_block
from research.registry import STRATEGIES
from research.strategy_failure_taxonomy import CANONICAL_FAILURE_CODES


CATALOG_SCHEMA_VERSION: Final[str] = "1.0"
HYPOTHESIS_CATALOG_VERSION: Final[str] = "v0.1"

CATALOG_ARTIFACT_PATH: Final[Path] = Path(
    "research/strategy_hypothesis_catalog_latest.v1.json"
)


HypothesisStatus = Literal["active_discovery", "planned", "disabled", "diagnostic"]
CLOSED_STATUSES: Final[tuple[str, ...]] = (
    "active_discovery",
    "planned",
    "disabled",
    "diagnostic",
)

# Statuses that the campaign policy may consider for *alpha* spawning.
# Diagnostic hypotheses are enrichment-only by design.
ALPHA_ELIGIBLE_STATUSES: Final[tuple[str, ...]] = ("active_discovery",)

# Hard ceiling on default_parameter_grid size for active_discovery
# hypotheses. AGENTS.md mandates max 3 parameters; with conservative
# 2-value sweeps that is 8 combos, so 16 is a comfortable upper bound
# that still rules out brute-force search.
_MAX_DEFAULT_GRID_COMBOS: Final[int] = 16

# Cost classes a hypothesis may declare. Closed vocabulary so the
# campaign-budget layer can reason over it without parsing free text.
HypothesisCostClass = Literal["low", "medium", "high"]
COST_CLASSES: Final[tuple[str, ...]] = ("low", "medium", "high")


# Families that the catalog may carry without a backing executable
# entry in research.registry.STRATEGIES. These are deliberately
# metadata-only branchpoints (regime diagnostics, planned strategies,
# disabled branchpoint). v3.15.4: removed
# ``volatility_compression_breakout`` (now executable / active_discovery);
# added ``multi_asset_trend_sleeve`` and ``cross_sectional_momentum``
# (planned-tier, executable wiring deferred to follow-up branches).
_METADATA_ONLY_FAMILIES: Final[frozenset[str]] = frozenset({
    "regime_diagnostics",
    "atr_adaptive_trend",
    "dynamic_pairs",
    "multi_asset_trend_sleeve",
    "cross_sectional_momentum",
})


@dataclass(frozen=True)
class StrategyHypothesis:
    """One row of the hypothesis catalog.

    Fields mirror the v3.15.3 spec §5.1 schema. ``policy_metadata`` is
    a small open dict reserved for keys the campaign policy reads
    directly (e.g. ``max_active_discovery``); kept as a plain dict
    to avoid pinning a sub-schema before behaviour stabilizes.
    """

    hypothesis_id: str
    strategy_family: str
    status: HypothesisStatus
    description: str
    feature_dependencies: tuple[str, ...]
    parameter_schema: dict[str, dict[str, str]]
    default_parameter_grid: tuple[dict[str, Any], ...]
    eligible_campaign_types: tuple[str, ...]
    expected_failure_modes: tuple[str, ...]
    baseline_reference: str | None
    cost_class: HypothesisCostClass
    policy_metadata: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return {
            "hypothesis_id": self.hypothesis_id,
            "strategy_family": self.strategy_family,
            "status": self.status,
            "description": self.description,
            "feature_dependencies": list(self.feature_dependencies),
            "parameter_schema": {
                key: dict(spec) for key, spec in self.parameter_schema.items()
            },
            "default_parameter_grid": [
                dict(combo) for combo in self.default_parameter_grid
            ],
            "eligible_campaign_types": list(self.eligible_campaign_types),
            "expected_failure_modes": list(self.expected_failure_modes),
            "baseline_reference": self.baseline_reference,
            "cost_class": self.cost_class,
            "policy_metadata": dict(self.policy_metadata),
        }


# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------

STRATEGY_HYPOTHESIS_CATALOG: Final[tuple[StrategyHypothesis, ...]] = (
    StrategyHypothesis(
        hypothesis_id="trend_pullback_v1",
        strategy_family="trend_pullback",
        status="active_discovery",
        description=(
            "In een gevestigde trend leveren tijdelijke pullbacks naar of "
            "onder een korte EMA betere entries dan late breakout-entries. "
            "Long-only baseline; signal flat zodra trend breekt of pullback "
            "resolveert."
        ),
        feature_dependencies=(
            "ema_fast",
            "ema_slow",
            "rolling_volatility",
            "pullback_distance",
        ),
        parameter_schema={
            "ema_fast_window": {"type": "int"},
            "ema_slow_window": {"type": "int"},
            "entry_k": {"type": "float"},
        },
        default_parameter_grid=(
            {"ema_fast_window": 10, "ema_slow_window": 50, "entry_k": 0.5},
            {"ema_fast_window": 10, "ema_slow_window": 50, "entry_k": 1.0},
            {"ema_fast_window": 10, "ema_slow_window": 100, "entry_k": 0.5},
            {"ema_fast_window": 10, "ema_slow_window": 100, "entry_k": 1.0},
            {"ema_fast_window": 20, "ema_slow_window": 50, "entry_k": 0.5},
            {"ema_fast_window": 20, "ema_slow_window": 50, "entry_k": 1.0},
            {"ema_fast_window": 20, "ema_slow_window": 100, "entry_k": 0.5},
            {"ema_fast_window": 20, "ema_slow_window": 100, "entry_k": 1.0},
        ),
        eligible_campaign_types=(
            "daily_primary",
            "survivor_confirmation",
            "weekly_retest",
        ),
        expected_failure_modes=(
            "insufficient_trades",
            "cost_fragile",
            "parameter_fragile",
            "asset_singleton",
            "oos_collapse",
            "no_baseline_edge",
        ),
        baseline_reference="ema_trend_baseline",
        cost_class="medium",
        policy_metadata={"max_active_discovery": True},
    ),
    StrategyHypothesis(
        hypothesis_id="regime_diagnostics_v1",
        strategy_family="regime_diagnostics",
        status="diagnostic",
        description=(
            "Regime diagnostics blijven enrichment-only: per-candidate "
            "tagging en sidecar-uitvoer, nooit signaal-filter of trade "
            "gating. Geen alpha-campaigns; alleen explicit diagnostische "
            "campagne types mogen ze raadplegen."
        ),
        feature_dependencies=(),
        parameter_schema={},
        default_parameter_grid=(),
        eligible_campaign_types=(),
        expected_failure_modes=(),
        baseline_reference=None,
        cost_class="low",
        policy_metadata={"max_active_discovery": False},
    ),
    StrategyHypothesis(
        hypothesis_id="atr_adaptive_trend_v0",
        strategy_family="atr_adaptive_trend",
        status="planned",
        description=(
            "Trend-anchor met ATR-genormaliseerde move filter. Metadata "
            "only in v3.15.3; geen executable strategy of preset."
        ),
        feature_dependencies=(
            "trend_anchor",
            "atr",
            "normalized_trend_move",
        ),
        parameter_schema={},
        default_parameter_grid=(),
        eligible_campaign_types=(),
        expected_failure_modes=(
            "insufficient_trades",
            "cost_fragile",
            "parameter_fragile",
            "no_baseline_edge",
        ),
        baseline_reference=None,
        cost_class="medium",
        policy_metadata={"max_active_discovery": False},
    ),
    StrategyHypothesis(
        hypothesis_id="volatility_compression_breakout_v0",
        strategy_family="volatility_compression_breakout",
        status="active_discovery",
        description=(
            "v3.15.4 second controlled active_discovery: long-only "
            "range-breakout entry uit een prior compressed-vol regime "
            "(compression_ratio[t-1] < threshold AND close[t] > "
            "rolling_high_previous[t]). Flat op opposite-side breakdown "
            "of compression release. Bridges naar de "
            "volatility_compression_breakout family in research.registry; "
            "v0 id behouden (geen destructieve rename) want geen "
            "historische evidence-ledger entries onder v0."
        ),
        feature_dependencies=(
            "atr_short",
            "atr_long",
            "compression_ratio",
            "rolling_high_previous",
            "rolling_low_previous",
        ),
        parameter_schema={
            "atr_short_window": {"type": "int"},
            "atr_long_window": {"type": "int"},
            "compression_threshold": {"type": "float"},
        },
        default_parameter_grid=(
            {"atr_short_window": 5, "atr_long_window": 20, "compression_threshold": 0.5},
            {"atr_short_window": 5, "atr_long_window": 20, "compression_threshold": 0.7},
            {"atr_short_window": 5, "atr_long_window": 50, "compression_threshold": 0.5},
            {"atr_short_window": 5, "atr_long_window": 50, "compression_threshold": 0.7},
            {"atr_short_window": 10, "atr_long_window": 20, "compression_threshold": 0.5},
            {"atr_short_window": 10, "atr_long_window": 20, "compression_threshold": 0.7},
            {"atr_short_window": 10, "atr_long_window": 50, "compression_threshold": 0.5},
            {"atr_short_window": 10, "atr_long_window": 50, "compression_threshold": 0.7},
        ),
        eligible_campaign_types=(
            "daily_primary",
            "survivor_confirmation",
            "weekly_retest",
        ),
        expected_failure_modes=(
            "insufficient_trades",
            "cost_fragile",
            "parameter_fragile",
            "overtrading",
            "no_baseline_edge",
        ),
        baseline_reference="ema_trend_baseline",
        cost_class="medium",
        policy_metadata={"max_active_discovery": True},
    ),
    StrategyHypothesis(
        hypothesis_id="multi_asset_trend_sleeve_v0",
        strategy_family="multi_asset_trend_sleeve",
        status="planned",
        description=(
            "Sleeve-aggregated trend signaal over een multi-asset "
            "basket (geen hidden single-asset dominance). Executable "
            "wiring deferred — requires portfolio-level sleeve execution "
            "layer (out of scope v3.15.4). Catalog-metadata-only in "
            "v3.15.4 als expliciet branchpoint; geen registry alias om "
            "misleidende family-labels te vermijden."
        ),
        feature_dependencies=(
            "ema_fast",
            "ema_slow",
        ),
        parameter_schema={},
        default_parameter_grid=(),
        eligible_campaign_types=(),
        expected_failure_modes=(
            "insufficient_trades",
            "cost_fragile",
            "parameter_fragile",
            "asset_singleton",
            "no_baseline_edge",
        ),
        baseline_reference=None,
        cost_class="medium",
        policy_metadata={"max_active_discovery": False},
    ),
    StrategyHypothesis(
        hypothesis_id="cross_sectional_momentum_v0",
        strategy_family="cross_sectional_momentum",
        status="planned",
        description=(
            "Cross-sectional rank momentum: per rebalance window de "
            "top-k assets long en/of bottom-k short, ranking exclusief "
            "huidige bar. Executable wiring deferred — requires "
            "cross-sectional rank infrastructure (rank_returns + "
            "multi-asset universe ranking primitive; out of scope "
            "v3.15.4). Catalog-metadata-only in v3.15.4."
        ),
        feature_dependencies=(
            "lookback_returns",
            "rank_returns",
        ),
        parameter_schema={},
        default_parameter_grid=(),
        eligible_campaign_types=(),
        expected_failure_modes=(
            "insufficient_trades",
            "cost_fragile",
            "parameter_fragile",
            "asset_singleton",
            "no_baseline_edge",
        ),
        baseline_reference=None,
        cost_class="medium",
        policy_metadata={"max_active_discovery": False},
    ),
    StrategyHypothesis(
        hypothesis_id="dynamic_pairs_v0",
        strategy_family="dynamic_pairs",
        status="disabled",
        description=(
            "Expliciet branchpoint: dynamic pairs blijven disabled tot "
            "een v3.x ADR de fitted-feature multi-asset uitbreiding + "
            "pair-universe selectiebeleid vastlegt. Geen discovery enqueue, "
            "geen executable strategy."
        ),
        feature_dependencies=(
            "rolling_beta",
            "spread",
            "spread_zscore",
            "pair_stability",
        ),
        parameter_schema={},
        default_parameter_grid=(),
        eligible_campaign_types=(),
        expected_failure_modes=(
            "asset_singleton",
            "liquidity_sensitive",
            "parameter_fragile",
            "no_baseline_edge",
        ),
        baseline_reference=None,
        cost_class="high",
        policy_metadata={"max_active_discovery": False},
    ),
)


# ---------------------------------------------------------------------------
# Validation (runs at import time)
# ---------------------------------------------------------------------------


class HypothesisCatalogError(RuntimeError):
    """Raised when the catalog violates a hard invariant."""


def _validate_catalog(catalog: tuple[StrategyHypothesis, ...]) -> None:
    """Enforce v3.15.4 strict catalog invariants (structural, import-time).

    1. Every status is in ``CLOSED_STATUSES``.
    2. Every cost_class is in ``COST_CLASSES``.
    3. Hypothesis ids are unique.
    4. Strategy families are unique within the catalog.
    5. ``active_discovery`` count is at least 1.
    6. For each ``active_discovery`` hypothesis (see
       :func:`_assert_active_discovery_strict` for full detail):
       a. family bridges to >= 1 enabled registry strategy
       b. family is NOT in ``_METADATA_ONLY_FAMILIES``
       c. ``default_parameter_grid`` is non-empty AND
          <= ``_MAX_DEFAULT_GRID_COMBOS``
       d. ``eligible_campaign_types`` is non-empty
       e. ``parameter_schema`` is non-empty
       f. every grid combo's keys are a subset of parameter_schema keys
    7. ``expected_failure_modes`` ⊆ ``CANONICAL_FAILURE_CODES`` (every
       hypothesis, regardless of status — declaring a non-canonical
       code is always wrong).
    8. Non-active hypotheses MUST declare empty
       ``eligible_campaign_types`` (no dead-eligibility noise).
    9. Non-active hypotheses whose family is NOT in
       ``_METADATA_ONLY_FAMILIES`` MUST bridge to a registry entry.

    Cross-module bridge to the preset layer is enforced separately by
    :func:`validate_active_discovery_preset_bridges`, called by the
    orchestrator at startup, NOT at module import.
    """
    seen_ids: set[str] = set()
    seen_families: set[str] = set()
    active_discovery_count = 0
    for hyp in catalog:
        if hyp.status not in CLOSED_STATUSES:
            raise HypothesisCatalogError(
                f"hypothesis {hyp.hypothesis_id!r} has invalid status "
                f"{hyp.status!r}; allowed={CLOSED_STATUSES}"
            )
        if hyp.cost_class not in COST_CLASSES:
            raise HypothesisCatalogError(
                f"hypothesis {hyp.hypothesis_id!r} has invalid cost_class "
                f"{hyp.cost_class!r}; allowed={COST_CLASSES}"
            )
        if hyp.hypothesis_id in seen_ids:
            raise HypothesisCatalogError(
                f"duplicate hypothesis_id {hyp.hypothesis_id!r}"
            )
        if hyp.strategy_family in seen_families:
            raise HypothesisCatalogError(
                f"duplicate strategy_family {hyp.strategy_family!r}"
            )
        seen_ids.add(hyp.hypothesis_id)
        seen_families.add(hyp.strategy_family)

        for code in hyp.expected_failure_modes:
            if code not in CANONICAL_FAILURE_CODES:
                raise HypothesisCatalogError(
                    f"hypothesis {hyp.hypothesis_id!r} declares "
                    f"non-canonical failure code {code!r}; canonical="
                    f"{sorted(CANONICAL_FAILURE_CODES)}"
                )

        if hyp.status == "active_discovery":
            active_discovery_count += 1
            _assert_active_discovery_strict(hyp)
        else:
            if hyp.eligible_campaign_types:
                raise HypothesisCatalogError(
                    f"hypothesis {hyp.hypothesis_id!r} status "
                    f"{hyp.status!r} declares "
                    f"eligible_campaign_types="
                    f"{hyp.eligible_campaign_types!r}; "
                    f"only active_discovery may be eligible"
                )
            if hyp.strategy_family not in _METADATA_ONLY_FAMILIES:
                if not _family_in_registry(hyp.strategy_family):
                    raise HypothesisCatalogError(
                        f"hypothesis {hyp.hypothesis_id!r} family "
                        f"{hyp.strategy_family!r} is neither registered "
                        f"nor in the metadata-only allowlist "
                        f"{sorted(_METADATA_ONLY_FAMILIES)}"
                    )
    if active_discovery_count < 1:
        raise HypothesisCatalogError(
            f"at least one active_discovery hypothesis required; "
            f"got {active_discovery_count}"
        )


def _family_in_registry(strategy_family: str) -> bool:
    return any(
        s.get("strategy_family") == strategy_family for s in STRATEGIES
    )


def _assert_active_discovery_strict(hyp: StrategyHypothesis) -> None:
    """Strict per-hypothesis checks for ``active_discovery`` rows.

    See ``_validate_catalog`` rule 6 for the full set; the function
    raises :class:`HypothesisCatalogError` on the first violation.
    """
    matches = [
        s for s in STRATEGIES
        if s.get("strategy_family") == hyp.strategy_family
        and s.get("enabled", True)
    ]
    if not matches:
        raise HypothesisCatalogError(
            f"active_discovery hypothesis {hyp.hypothesis_id!r} "
            f"family {hyp.strategy_family!r} has no enabled registry "
            f"strategy"
        )
    if hyp.strategy_family in _METADATA_ONLY_FAMILIES:
        raise HypothesisCatalogError(
            f"active_discovery hypothesis {hyp.hypothesis_id!r} "
            f"family {hyp.strategy_family!r} is in the metadata-only "
            f"allowlist {sorted(_METADATA_ONLY_FAMILIES)}; promote the "
            f"family out of the allowlist before activating"
        )
    if not hyp.default_parameter_grid:
        raise HypothesisCatalogError(
            f"active_discovery hypothesis {hyp.hypothesis_id!r} has "
            f"empty default_parameter_grid"
        )
    if len(hyp.default_parameter_grid) > _MAX_DEFAULT_GRID_COMBOS:
        raise HypothesisCatalogError(
            f"active_discovery hypothesis {hyp.hypothesis_id!r} "
            f"default_parameter_grid has "
            f"{len(hyp.default_parameter_grid)} combos; max is "
            f"{_MAX_DEFAULT_GRID_COMBOS}"
        )
    if not hyp.eligible_campaign_types:
        raise HypothesisCatalogError(
            f"active_discovery hypothesis {hyp.hypothesis_id!r} has "
            f"empty eligible_campaign_types"
        )
    if not hyp.parameter_schema:
        raise HypothesisCatalogError(
            f"active_discovery hypothesis {hyp.hypothesis_id!r} has "
            f"empty parameter_schema"
        )
    schema_keys = set(hyp.parameter_schema.keys())
    for combo in hyp.default_parameter_grid:
        unknown = set(combo.keys()) - schema_keys
        if unknown:
            raise HypothesisCatalogError(
                f"active_discovery hypothesis {hyp.hypothesis_id!r} "
                f"grid combo references unknown parameter keys "
                f"{sorted(unknown)}; schema keys={sorted(schema_keys)}"
            )


def validate_active_discovery_preset_bridges(
    *,
    catalog: tuple[StrategyHypothesis, ...] = STRATEGY_HYPOTHESIS_CATALOG,
) -> None:
    """Cross-module bridge: every active_discovery has a stable preset.

    For each ``active_discovery`` hypothesis verifies that:

    - at least one preset declares ``hypothesis_id == hyp.hypothesis_id``
      AND ``status="stable"`` AND ``enabled=True``;
    - that preset's bundle resolves to >= 1 enabled registry strategy
      via :func:`research.presets.resolve_preset_bundle`.

    Raises :class:`HypothesisCatalogError` with a ``bridge:`` message
    prefix on the first violation. Imports ``research.presets`` lazily
    so the catalog module's import path stays independent of the
    preset layer.

    Called explicitly by ``research.run_research`` at startup; NOT
    invoked at module import.
    """
    from research.presets import PRESETS, resolve_preset_bundle

    by_hypothesis_id: dict[str, list[Any]] = {}
    for preset in PRESETS:
        if preset.hypothesis_id is None:
            continue
        by_hypothesis_id.setdefault(preset.hypothesis_id, []).append(preset)

    for hyp in catalog:
        if hyp.status != "active_discovery":
            continue
        bound = by_hypothesis_id.get(hyp.hypothesis_id) or []
        stable_enabled = [
            p for p in bound if p.status == "stable" and p.enabled
        ]
        if not stable_enabled:
            # Surface every preset that *did* bind via hypothesis_id but
            # failed the stable+enabled gate, so an operator can see at
            # a glance whether the binding is missing entirely or merely
            # disqualified by a status / enabled flip.
            disqualified = [
                f"{p.name!r}(status={p.status!r},enabled={p.enabled})"
                for p in bound
            ]
            disqualified_part = (
                f"; bound-but-disqualified={disqualified}"
                if disqualified
                else "; no presets bind via hypothesis_id at all"
            )
            raise HypothesisCatalogError(
                f"bridge: active_discovery hypothesis "
                f"{hyp.hypothesis_id!r} (strategy_family="
                f"{hyp.strategy_family!r}) has no stable+enabled preset "
                f"binding via hypothesis_id"
                f"{disqualified_part}"
            )
        for preset in stable_enabled:
            resolved = resolve_preset_bundle(preset)
            if not resolved:
                raise HypothesisCatalogError(
                    f"bridge: preset {preset.name!r} bound to "
                    f"hypothesis {hyp.hypothesis_id!r} (strategy_family="
                    f"{hyp.strategy_family!r}) resolves to zero enabled "
                    f"registry strategies; bundle={list(preset.bundle)}"
                )


_validate_catalog(STRATEGY_HYPOTHESIS_CATALOG)


# ---------------------------------------------------------------------------
# Public lookups
# ---------------------------------------------------------------------------


def get_by_id(
    hypothesis_id: str,
    *,
    catalog: tuple[StrategyHypothesis, ...] = STRATEGY_HYPOTHESIS_CATALOG,
) -> StrategyHypothesis:
    for hyp in catalog:
        if hyp.hypothesis_id == hypothesis_id:
            return hyp
    raise KeyError(
        f"unknown hypothesis_id {hypothesis_id!r}; known="
        f"{[h.hypothesis_id for h in catalog]}"
    )


def get_by_family(
    strategy_family: str,
    *,
    catalog: tuple[StrategyHypothesis, ...] = STRATEGY_HYPOTHESIS_CATALOG,
) -> StrategyHypothesis:
    for hyp in catalog:
        if hyp.strategy_family == strategy_family:
            return hyp
    raise KeyError(
        f"no hypothesis registered for strategy_family "
        f"{strategy_family!r}; known="
        f"{[h.strategy_family for h in catalog]}"
    )


def list_active_discovery(
    *,
    catalog: tuple[StrategyHypothesis, ...] = STRATEGY_HYPOTHESIS_CATALOG,
) -> list[StrategyHypothesis]:
    return [h for h in catalog if h.status == "active_discovery"]


def list_by_status(
    status: HypothesisStatus,
    *,
    catalog: tuple[StrategyHypothesis, ...] = STRATEGY_HYPOTHESIS_CATALOG,
) -> list[StrategyHypothesis]:
    return [h for h in catalog if h.status == status]


# ---------------------------------------------------------------------------
# Sidecar payload + writer
# ---------------------------------------------------------------------------


def build_catalog_payload(
    *,
    generated_at_utc: datetime,
    git_revision: str | None,
    run_id: str | None = None,
    catalog: tuple[StrategyHypothesis, ...] = STRATEGY_HYPOTHESIS_CATALOG,
) -> dict[str, Any]:
    """Return the canonical catalog payload ready for atomic write.

    The payload carries the campaign-os pin block (``schema_version``,
    ``live_eligible=False``, ...) plus the catalog-specific
    ``hypothesis_catalog_version`` and the deterministic-ordered
    ``hypotheses`` list (sorted by ``hypothesis_id``).
    """
    pin = build_pin_block(
        schema_version=CATALOG_SCHEMA_VERSION,
        generated_at_utc=generated_at_utc,
        git_revision=git_revision,
        run_id=run_id,
    )
    hypotheses_payload = [
        hyp.to_payload()
        for hyp in sorted(catalog, key=lambda h: h.hypothesis_id)
    ]
    payload = dict(pin)
    payload["hypothesis_catalog_version"] = HYPOTHESIS_CATALOG_VERSION
    payload["hypotheses"] = hypotheses_payload
    return payload


def write_catalog_sidecar(
    *,
    generated_at_utc: datetime,
    git_revision: str | None,
    run_id: str | None = None,
    path: Path = CATALOG_ARTIFACT_PATH,
) -> Path:
    payload = build_catalog_payload(
        generated_at_utc=generated_at_utc,
        git_revision=git_revision,
        run_id=run_id,
    )
    require_schema_version(payload, CATALOG_SCHEMA_VERSION)
    write_sidecar_atomic(path, payload)
    return path


__all__ = [
    "ALPHA_ELIGIBLE_STATUSES",
    "CATALOG_ARTIFACT_PATH",
    "CATALOG_SCHEMA_VERSION",
    "CLOSED_STATUSES",
    "COST_CLASSES",
    "HYPOTHESIS_CATALOG_VERSION",
    "HypothesisCatalogError",
    "HypothesisCostClass",
    "HypothesisStatus",
    "STRATEGY_HYPOTHESIS_CATALOG",
    "StrategyHypothesis",
    "build_catalog_payload",
    "get_by_family",
    "get_by_id",
    "list_active_discovery",
    "list_by_status",
    "validate_active_discovery_preset_bridges",
    "write_catalog_sidecar",
]
