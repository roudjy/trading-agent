"""Tests for v3.15.3 ``trend_pullback_v1`` thin strategy."""

from __future__ import annotations

import numpy as np
import pandas as pd

from agent.backtesting.strategies import trend_pullback_v1_strategie
from agent.backtesting.thin_strategy import (
    FeatureRequirement,
    build_features_for,
    is_thin_strategy,
)
from research.registry import STRATEGIES, count_param_combinations


def _make_close(n: int = 220, seed: int = 7) -> pd.Series:
    rng = np.random.default_rng(seed=seed)
    walk = np.cumsum(rng.normal(0.0, 0.5, size=n)) + 100.0
    idx = pd.date_range("2026-01-01", periods=n, freq="1h")
    return pd.Series(walk, index=idx, name="close")


def test_factory_returns_thin_strategy() -> None:
    fn = trend_pullback_v1_strategie(
        ema_fast_window=10, ema_slow_window=50, entry_k=1.0
    )
    assert is_thin_strategy(fn)


def test_declares_four_feature_requirements() -> None:
    fn = trend_pullback_v1_strategie(
        ema_fast_window=10, ema_slow_window=50, entry_k=1.0
    )
    reqs: list[FeatureRequirement] = getattr(fn, "_feature_requirements")
    assert len(reqs) == 4
    aliases = sorted(r.resolved_alias() for r in reqs)
    assert aliases == sorted(
        ["ema_fast", "ema_slow", "rolling_volatility", "pullback_distance"]
    )


def test_signal_is_int_series_in_minus_one_zero_one() -> None:
    fn = trend_pullback_v1_strategie(
        ema_fast_window=10, ema_slow_window=50, entry_k=1.0
    )
    close = _make_close()
    sig = fn(close.to_frame(name="close"))
    assert isinstance(sig, pd.Series)
    assert sig.index.equals(close.index)
    assert set(sig.dropna().unique()).issubset({-1, 0, 1})


def test_long_signal_only_when_trend_up_and_pullback() -> None:
    """When fast > slow EMA and pullback is sufficiently negative, signal=1."""
    fn = trend_pullback_v1_strategie(
        ema_fast_window=5, ema_slow_window=20, entry_k=0.5
    )
    # Build a deterministic uptrend then a dip.
    n = 80
    base = np.linspace(100.0, 120.0, n)
    base[60] = 108.0  # mild dip while still above the slow EMA
    s = pd.Series(base, index=pd.RangeIndex(n), name="close").astype(float)
    sig = fn(s.to_frame(name="close"))
    # We expect at least one long entry around the dip.
    assert (sig == 1).any()


def test_flat_when_trend_breaks() -> None:
    """If ema_fast <= ema_slow at any bar the signal must be 0 there."""
    fn = trend_pullback_v1_strategie(
        ema_fast_window=5, ema_slow_window=20, entry_k=0.5
    )
    n = 100
    base = np.linspace(120.0, 80.0, n)  # downtrend so fast <= slow
    s = pd.Series(base, index=pd.RangeIndex(n), name="close").astype(float)
    sig = fn(s.to_frame(name="close"))
    # In a downtrend the strategy should have no long signals at all.
    assert (sig == 1).sum() == 0


def test_higher_entry_k_produces_fewer_signals_monotonicity() -> None:
    """Stricter entry_k must not yield strictly more long signals."""
    close = _make_close().astype(float)
    df = close.to_frame(name="close")
    f_lo = trend_pullback_v1_strategie(
        ema_fast_window=10, ema_slow_window=50, entry_k=0.5
    )
    f_hi = trend_pullback_v1_strategie(
        ema_fast_window=10, ema_slow_window=50, entry_k=1.0
    )
    sig_lo = f_lo(df)
    sig_hi = f_hi(df)
    assert (sig_hi == 1).sum() <= (sig_lo == 1).sum()


def test_invalid_parameters_yield_flat_signal() -> None:
    """Defensive guards: ema_fast >= ema_slow or entry_k <= 0 -> all flat."""
    close = _make_close().astype(float)
    df = close.to_frame(name="close")
    bad_window = trend_pullback_v1_strategie(
        ema_fast_window=50, ema_slow_window=20, entry_k=1.0
    )
    assert (bad_window(df) == 0).all()
    bad_k = trend_pullback_v1_strategie(
        ema_fast_window=10, ema_slow_window=50, entry_k=0.0
    )
    assert (bad_k(df) == 0).all()


def test_consumes_only_feature_columns_no_raw_close() -> None:
    """Feature-resolver path must give the same signal as the legacy
    auto-resolve path (proves the body reads only ``features`` + ``df.index``).
    """
    fn = trend_pullback_v1_strategie(
        ema_fast_window=10, ema_slow_window=50, entry_k=1.0
    )
    df = _make_close().to_frame(name="close")
    auto_resolved = fn(df)  # legacy path -> auto build_features_for
    reqs = getattr(fn, "_feature_requirements")
    explicit_features = build_features_for(reqs, df)
    explicit_signal = fn(df, explicit_features)
    pd.testing.assert_series_equal(
        auto_resolved, explicit_signal, check_names=False
    )


def test_registry_grid_at_most_eight_combinations() -> None:
    entry = next(s for s in STRATEGIES if s["name"] == "trend_pullback_v1")
    assert count_param_combinations(entry) <= 8
    assert set(entry["params"].keys()) == {
        "ema_fast_window",
        "ema_slow_window",
        "entry_k",
    }


def test_registry_strategy_family_bridge() -> None:
    entry = next(s for s in STRATEGIES if s["name"] == "trend_pullback_v1")
    assert entry["strategy_family"] == "trend_pullback"
    assert entry["enabled"] is True


def test_legacy_trend_pullback_unchanged() -> None:
    """Legacy non-thin trend_pullback / trend_pullback_tp_sl preserved."""
    legacy = next(s for s in STRATEGIES if s["name"] == "trend_pullback")
    assert legacy["strategy_family"] == "trend_following"
    assert set(legacy["params"].keys()) == {
        "ema_kort",
        "ema_lang",
        "pullback_buffer",
        "slope_lookback",
        "vol_lookback",
        "max_volatility",
    }
    assert legacy["enabled"] is True
    legacy_tp = next(s for s in STRATEGIES if s["name"] == "trend_pullback_tp_sl")
    assert legacy_tp["strategy_family"] == "trend_following"
    assert legacy_tp["enabled"] is True
