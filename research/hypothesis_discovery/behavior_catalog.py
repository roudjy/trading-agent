"""Behavior-first catalog for minimal Hypothesis Discovery.

This is a closed, hand-authored bridge from market behaviors to the
existing strategy families. It intentionally does not register new
strategies and does not infer families from free text.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final


SCHEMA_VERSION: Final[int] = 1
MODULE_VERSION: Final[str] = "v3.15.19-minimal-2026-05-21"

BEHAVIOR_FAMILIES: Final[tuple[str, ...]] = (
    "trend_pullback",
    "volatility_breakout",
)


@dataclass(frozen=True)
class BehaviorDescriptor:
    behavior_family: str
    market_behavior: str
    strategy_family: str
    required_features: tuple[str, ...]
    required_diagnostics: tuple[str, ...]
    required_null_model: str

    def to_payload(self) -> dict[str, object]:
        return {
            "schema_version": SCHEMA_VERSION,
            "behavior_family": self.behavior_family,
            "market_behavior": self.market_behavior,
            "strategy_family": self.strategy_family,
            "required_features": list(self.required_features),
            "required_diagnostics": list(self.required_diagnostics),
            "required_null_model": self.required_null_model,
        }


_CATALOG: Final[tuple[BehaviorDescriptor, ...]] = (
    BehaviorDescriptor(
        behavior_family="trend_pullback",
        market_behavior=(
            "temporary pullback inside an established directional trend"
        ),
        strategy_family="trend_pullback",
        required_features=(
            "ema_fast",
            "ema_slow",
            "rolling_volatility",
            "pullback_distance",
        ),
        required_diagnostics=(
            "null_model",
            "tail_asymmetry",
            "entropy_structure",
        ),
        required_null_model="shuffle_returns",
    ),
    BehaviorDescriptor(
        behavior_family="volatility_breakout",
        market_behavior=(
            "range breakout following a compressed-volatility regime"
        ),
        strategy_family="volatility_compression_breakout",
        required_features=(
            "atr_short",
            "atr_long",
            "compression_ratio",
            "rolling_high_previous",
            "rolling_low_previous",
        ),
        required_diagnostics=(
            "null_model",
            "tail_asymmetry",
            "entropy_structure",
        ),
        required_null_model="shuffle_returns",
    ),
)


def list_behaviors() -> list[BehaviorDescriptor]:
    return list(_CATALOG)


def get_behavior(strategy_family: str) -> BehaviorDescriptor:
    for behavior in _CATALOG:
        if behavior.strategy_family == strategy_family:
            return behavior
    known = [b.strategy_family for b in _CATALOG]
    raise KeyError(
        f"no behavior descriptor for strategy_family {strategy_family!r}; "
        f"known={known}"
    )


def behavior_catalog_payload() -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "behavior_families": list(BEHAVIOR_FAMILIES),
        "behaviors": [
            behavior.to_payload()
            for behavior in sorted(_CATALOG, key=lambda b: b.behavior_family)
        ],
    }
