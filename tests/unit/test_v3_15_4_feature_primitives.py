"""Determinism + no-lookahead pins for the v3.15.4 feature primitives.

Three primitives back the volatility_compression_breakout active_discovery
hypothesis: ``compression_ratio``, ``rolling_high_previous``,
``rolling_low_previous``. All three must be:

- pure / deterministic (identical inputs → identical outputs)
- index-preserving (output index == close.index)
- no-lookahead (rolling high/low explicitly shifted by 1 bar so the
  value at index t never includes the bar t itself)
- safe under zero-volatility (compression_ratio when ``atr_long == 0``)
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from agent.backtesting.features import (
    FEATURE_REGISTRY,
    compression_ratio,
    rolling_high_previous,
    rolling_low_previous,
)
from tests._harness_helpers import build_ohlcv_frame


def test_compression_ratio_is_deterministic() -> None:
    frame = build_ohlcv_frame(length=120, seed=11)
    first = compression_ratio(
        frame["high"], frame["low"], frame["close"],
        atr_short_window=5, atr_long_window=20,
    )
    second = compression_ratio(
        frame["high"], frame["low"], frame["close"],
        atr_short_window=5, atr_long_window=20,
    )
    pd.testing.assert_series_equal(first, second, check_dtype=True)


def test_compression_ratio_index_preserving() -> None:
    frame = build_ohlcv_frame(length=80, seed=23)
    out = compression_ratio(
        frame["high"], frame["low"], frame["close"],
        atr_short_window=3, atr_long_window=10,
    )
    assert out.index.equals(frame["close"].index)


def test_compression_ratio_handles_zero_long_atr_with_nan() -> None:
    """Zero atr_long → NaN (never inf or division-by-zero error)."""
    index = pd.date_range("2024-01-01", periods=10, freq="D")
    flat_close = pd.Series([100.0] * 10, index=index)
    flat_high = flat_close.copy()
    flat_low = flat_close.copy()
    out = compression_ratio(
        flat_high, flat_low, flat_close,
        atr_short_window=2, atr_long_window=5,
    )
    # All bars after warmup have atr_long == 0 (flat series) → NaN.
    assert out.isna().all()


def test_rolling_high_previous_is_deterministic() -> None:
    frame = build_ohlcv_frame(length=80, seed=29)
    first = rolling_high_previous(frame["close"], window=10)
    second = rolling_high_previous(frame["close"], window=10)
    pd.testing.assert_series_equal(first, second, check_dtype=True)


def test_rolling_high_previous_excludes_current_bar() -> None:
    """No-lookahead pin: spike at index t must NOT appear in the
    rolling high at index t (only at index t+1).
    """
    index = pd.date_range("2024-01-01", periods=20, freq="D")
    close = pd.Series(np.full(20, 100.0), index=index)
    spike_idx = 12
    close.iloc[spike_idx] = 250.0
    out = rolling_high_previous(close, window=5)
    # At the spike bar t the rolling-high-previous excludes that bar.
    assert out.iloc[spike_idx] == 100.0, (
        "rolling_high_previous must lag by 1 — spike at t leaks into "
        "the value at t."
    )
    # At t+1 the spike is now inside the lookback window.
    assert out.iloc[spike_idx + 1] == 250.0


def test_rolling_low_previous_is_deterministic() -> None:
    frame = build_ohlcv_frame(length=80, seed=31)
    first = rolling_low_previous(frame["close"], window=10)
    second = rolling_low_previous(frame["close"], window=10)
    pd.testing.assert_series_equal(first, second, check_dtype=True)


def test_rolling_low_previous_excludes_current_bar() -> None:
    """Symmetric no-lookahead pin to the rolling-high test."""
    index = pd.date_range("2024-01-01", periods=20, freq="D")
    close = pd.Series(np.full(20, 100.0), index=index)
    drop_idx = 12
    close.iloc[drop_idx] = 25.0
    out = rolling_low_previous(close, window=5)
    assert out.iloc[drop_idx] == 100.0, (
        "rolling_low_previous must lag by 1 — drop at t leaks into "
        "the value at t."
    )
    assert out.iloc[drop_idx + 1] == 25.0


def test_v3_15_4_primitives_registered() -> None:
    """The 3 new primitives are in FEATURE_REGISTRY with the right
    column requirements + warmup math."""
    spec_compression = FEATURE_REGISTRY["compression_ratio"]
    assert spec_compression.required_columns == ("high", "low", "close")
    assert set(spec_compression.param_names) == {
        "atr_short_window",
        "atr_long_window",
    }
    assert spec_compression.warmup_bars_fn(
        {"atr_short_window": 5, "atr_long_window": 20}
    ) == 20

    for name in ("rolling_high_previous", "rolling_low_previous"):
        spec = FEATURE_REGISTRY[name]
        assert spec.required_columns == ("close",)
        assert spec.param_names == ("window",)
        assert spec.warmup_bars_fn({"window": 10}) == 11  # window + 1
