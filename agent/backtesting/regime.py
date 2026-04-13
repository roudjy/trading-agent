"""Deterministic, point-in-time-safe regime diagnostics primitives.

This module is the single source of truth for research regime feature
computation and label assignment.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

TRENDING = "trending"
NON_TRENDING = "non_trending"
HIGH_VOL = "high_vol"
LOW_VOL = "low_vol"
UNKNOWN = "unknown"

TREND_LABELS: tuple[str, ...] = (TRENDING, NON_TRENDING, UNKNOWN)
VOLATILITY_LABELS: tuple[str, ...] = (HIGH_VOL, LOW_VOL, UNKNOWN)
COMBINED_LABELS: tuple[str, ...] = (
    f"{TRENDING}|{HIGH_VOL}",
    f"{TRENDING}|{LOW_VOL}",
    f"{NON_TRENDING}|{HIGH_VOL}",
    f"{NON_TRENDING}|{LOW_VOL}",
    UNKNOWN,
)

DEFAULT_REGIME_CONFIG: dict[str, Any] = {
    "trend_lookback_bars": 20,
    "volatility_lookback_bars": 20,
    "volatility_baseline_lookback_bars": 100,
    "trend_strength_threshold": 0.5,
    "high_vol_ratio_threshold": 1.5,
}

EPSILON = 1e-12


def normalize_regime_config(config: dict[str, Any] | None) -> dict[str, Any]:
    """Normalize optional research.regime_diagnostics config."""
    raw = dict(config or {})
    normalized = dict(DEFAULT_REGIME_CONFIG)

    for key in DEFAULT_REGIME_CONFIG:
        if key in raw:
            normalized[key] = raw[key]

    for key in (
        "trend_lookback_bars",
        "volatility_lookback_bars",
        "volatility_baseline_lookback_bars",
    ):
        value = int(normalized[key])
        if value <= 0:
            raise ValueError(f"research.regime_diagnostics.{key} must be > 0, got {value!r}")
        normalized[key] = value

    for key in ("trend_strength_threshold", "high_vol_ratio_threshold"):
        value = float(normalized[key])
        if value <= 0.0:
            raise ValueError(f"research.regime_diagnostics.{key} must be > 0, got {value!r}")
        normalized[key] = value

    return normalized


def regime_definition_payload(config: dict[str, Any] | None) -> dict[str, Any]:
    """Return explicit regime definitions for sidecar lineage."""
    normalized = normalize_regime_config(config)
    return {
        "trend_regime": {
            "labels": list(TREND_LABELS),
            "method": "abs(trailing_mean(log_return_1)) / trailing_std(log_return_1)",
            "lookback_bars": normalized["trend_lookback_bars"],
            "threshold": normalized["trend_strength_threshold"],
            "point_in_time_safe": True,
        },
        "volatility_regime": {
            "labels": list(VOLATILITY_LABELS),
            "method": "trailing_realized_vol / trailing_vol_baseline",
            "lookback_bars": normalized["volatility_lookback_bars"],
            "baseline_lookback_bars": normalized["volatility_baseline_lookback_bars"],
            "high_vol_ratio_threshold": normalized["high_vol_ratio_threshold"],
            "point_in_time_safe": True,
        },
        "combined_regime": {
            "labels": list(COMBINED_LABELS),
            "method": "trend_regime + '|' + volatility_regime, else unknown",
            "point_in_time_safe": True,
        },
    }


def build_regime_frame(frame: pd.DataFrame, config: dict[str, Any] | None) -> pd.DataFrame:
    """Compute deterministic trailing regime features and labels.

    Uses only trailing windows ending at timestamp t. No future bars,
    no full-run thresholds, and no cross-asset fitting.
    """
    normalized = normalize_regime_config(config)
    close = pd.to_numeric(frame["close"], errors="coerce").astype(float)
    safe_close = close.where(close > 0.0)
    log_return_1 = np.log(safe_close).diff()

    trend_mean = log_return_1.rolling(
        window=normalized["trend_lookback_bars"],
        min_periods=normalized["trend_lookback_bars"],
    ).mean()
    trend_std = log_return_1.rolling(
        window=normalized["trend_lookback_bars"],
        min_periods=normalized["trend_lookback_bars"],
    ).std(ddof=0)
    trend_strength = trend_mean.abs() / (trend_std + EPSILON)

    realized_vol = log_return_1.rolling(
        window=normalized["volatility_lookback_bars"],
        min_periods=normalized["volatility_lookback_bars"],
    ).std(ddof=0)
    volatility_baseline = realized_vol.rolling(
        window=normalized["volatility_baseline_lookback_bars"],
        min_periods=normalized["volatility_baseline_lookback_bars"],
    ).median()

    trend_regime = pd.Series(UNKNOWN, index=frame.index, dtype="object")
    trend_valid = trend_mean.notna() & trend_std.notna()
    trend_regime.loc[trend_valid & (trend_strength >= normalized["trend_strength_threshold"])] = TRENDING
    trend_regime.loc[trend_valid & (trend_strength < normalized["trend_strength_threshold"])] = NON_TRENDING

    volatility_regime = pd.Series(UNKNOWN, index=frame.index, dtype="object")
    vol_valid = realized_vol.notna() & volatility_baseline.notna()
    baseline_zero = vol_valid & (volatility_baseline <= EPSILON)
    non_zero_baseline = vol_valid & ~baseline_zero

    volatility_regime.loc[baseline_zero & (realized_vol > EPSILON)] = HIGH_VOL
    volatility_regime.loc[baseline_zero & (realized_vol <= EPSILON)] = LOW_VOL
    volatility_ratio = realized_vol / volatility_baseline.where(volatility_baseline > EPSILON)
    volatility_regime.loc[
        non_zero_baseline & (volatility_ratio >= normalized["high_vol_ratio_threshold"])
    ] = HIGH_VOL
    volatility_regime.loc[
        non_zero_baseline & (volatility_ratio < normalized["high_vol_ratio_threshold"])
    ] = LOW_VOL

    combined_regime = pd.Series(UNKNOWN, index=frame.index, dtype="object")
    combined_valid = (trend_regime != UNKNOWN) & (volatility_regime != UNKNOWN)
    combined_regime.loc[combined_valid] = (
        trend_regime.loc[combined_valid] + "|" + volatility_regime.loc[combined_valid]
    )

    return pd.DataFrame(
        {
            "log_return_1": log_return_1,
            "trend_strength": trend_strength,
            "realized_volatility": realized_vol,
            "volatility_baseline": volatility_baseline,
            "trend_regime": trend_regime,
            "volatility_regime": volatility_regime,
            "combined_regime": combined_regime,
        },
        index=frame.index,
    )
