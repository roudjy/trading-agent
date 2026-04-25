"""Strategy hypothesis catalog (v3.15.3).

First-class artifact-backed registry of strategy hypotheses with a
closed status enum. The v3.15.2 Campaign Operating Layer reads this
catalog through ``research.campaign_policy`` to decide which hypotheses
are eligible for autonomous campaign spawning.

Hard invariant: exactly ONE hypothesis carries ``status="active_discovery"``
at any time. Other statuses are visible-but-not-spawned (``planned``),
explicitly blocked (``disabled``), or enrichment-only (``diagnostic``).

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

# Cost classes a hypothesis may declare. Closed vocabulary so the
# campaign-budget layer can reason over it without parsing free text.
HypothesisCostClass = Literal["low", "medium", "high"]
COST_CLASSES: Final[tuple[str, ...]] = ("low", "medium", "high")


# Families that the catalog may carry without a backing executable
# entry in research.registry.STRATEGIES. These are deliberately
# metadata-only branchpoints (regime diagnostics, planned strategies,
# disabled branchpoint).
_METADATA_ONLY_FAMILIES: Final[frozenset[str]] = frozenset({
    "regime_diagnostics",
    "atr_adaptive_trend",
    "volatility_compression_breakout",
    "dynamic_pairs",
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
        status="planned",
        description=(
            "Volatility compression gevolgd door range-breakout entry. "
            "Metadata only in v3.15.3; geen executable strategy of preset."
        ),
        feature_dependencies=(
            "atr_short",
            "atr_long",
            "compression_ratio",
            "rolling_high_previous",
            "rolling_low_previous",
        ),
        parameter_schema={},
        default_parameter_grid=(),
        eligible_campaign_types=(),
        expected_failure_modes=(
            "insufficient_trades",
            "cost_fragile",
            "parameter_fragile",
            "overtrading",
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
    """Enforce the v3.15.3 hard invariants on the catalog.

    1. Every status is in ``CLOSED_STATUSES``.
    2. Exactly one hypothesis has ``status="active_discovery"``.
    3. Hypothesis ids are unique.
    4. Strategy families are unique within the catalog.
    5. Every executable family bridges to an enabled registry strategy
       OR is in the metadata-only allowlist.
    6. Every cost_class is in the closed COST_CLASSES vocabulary.
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
        if hyp.status == "active_discovery":
            active_discovery_count += 1
            _assert_executable_family_bridges(hyp)
        elif hyp.strategy_family not in _METADATA_ONLY_FAMILIES:
            # Non-executable hypotheses must either bridge to a registry
            # family or be on the metadata-only allowlist; otherwise they
            # are unreachable noise.
            if not _family_in_registry(hyp.strategy_family):
                raise HypothesisCatalogError(
                    f"hypothesis {hyp.hypothesis_id!r} family "
                    f"{hyp.strategy_family!r} is neither registered nor "
                    f"in the metadata-only allowlist "
                    f"{sorted(_METADATA_ONLY_FAMILIES)}"
                )
    if active_discovery_count != 1:
        raise HypothesisCatalogError(
            f"exactly one active_discovery hypothesis required; "
            f"got {active_discovery_count}"
        )


def _family_in_registry(strategy_family: str) -> bool:
    return any(
        s.get("strategy_family") == strategy_family for s in STRATEGIES
    )


def _assert_executable_family_bridges(hyp: StrategyHypothesis) -> None:
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
    "write_catalog_sidecar",
]
