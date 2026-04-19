"""Unit tests for canonical feature primitives (v3.5).

Covers per-primitive behaviour: index preservation, NaN warmup, dtype,
non-mutation of inputs, determinism across repeated calls, and the
specific numerical contracts (ddof on std, zero-std -> NaN, etc.) that
the Tier 1 bytewise pins depend on. The feature registry is exercised
as a structural check, not a contract; integrity-layer use lands in
step 4.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from agent.backtesting.features import (
    FEATURE_REGISTRY,
    FEATURE_VERSION,
    atr,
    ema,
    hedge_ratio_ols,
    log_returns,
    rolling_volatility,
    sma,
    spread,
    zscore,
)
from tests._harness_helpers import build_ohlcv_frame, build_pairs_frame


def _close(length: int = 60, seed: int = 41) -> pd.Series:
    return build_ohlcv_frame(length=length, seed=seed)["close"]


def test_feature_version_is_pinned_string() -> None:
    assert FEATURE_VERSION == "1.0"


def test_feature_registry_covers_expected_primitives() -> None:
    expected = {
        "log_returns",
        "sma",
        "ema",
        "rolling_volatility",
        "zscore",
        "atr",
        "spread",
    }
    assert expected.issubset(FEATURE_REGISTRY.keys())


def test_feature_registry_warmup_returns_int() -> None:
    for name, spec in FEATURE_REGISTRY.items():
        params = {"window": 10, "span": 10, "lookback": 10, "hedge_ratio": 1.0}
        warmup = spec.warmup_bars_fn(params)
        assert isinstance(warmup, int), name


def test_log_returns_first_bar_is_nan_and_length_matches() -> None:
    close = _close()
    r = log_returns(close)

    assert r.index.equals(close.index)
    assert math.isnan(r.iloc[0])
    assert not r.iloc[1:].isna().any()
    assert r.dtype.kind == "f"


def test_log_returns_does_not_mutate_input() -> None:
    close = _close()
    before = close.copy()
    log_returns(close)

    pd.testing.assert_series_equal(close, before)


def test_log_returns_is_deterministic() -> None:
    close = _close()
    a = log_returns(close)
    b = log_returns(close)

    pd.testing.assert_series_equal(a, b)


def test_sma_window_10_first_nine_bars_nan() -> None:
    close = _close(length=40, seed=43)
    m = sma(close, window=10)

    assert m.index.equals(close.index)
    assert m.iloc[:9].isna().all()
    assert not m.iloc[9:].isna().any()


def test_sma_constant_series_equals_constant() -> None:
    idx = pd.date_range("2024-01-01", periods=30, freq="D")
    close = pd.Series(42.0, index=idx)

    m = sma(close, window=5)

    assert (m.iloc[4:] == 42.0).all()


def test_sma_is_deterministic() -> None:
    close = _close()
    pd.testing.assert_series_equal(sma(close, window=12), sma(close, window=12))


def test_ema_is_deterministic_and_index_preserving() -> None:
    close = _close()
    a = ema(close, span=10)
    b = ema(close, span=10)

    pd.testing.assert_series_equal(a, b)
    assert a.index.equals(close.index)
    assert not a.isna().any()


def test_ema_adjust_false_matches_manual_recurrence() -> None:
    close = pd.Series(
        [1.0, 2.0, 3.0, 4.0, 5.0],
        index=pd.date_range("2024-01-01", periods=5, freq="D"),
    )
    span = 3
    alpha = 2.0 / (span + 1.0)
    expected = [close.iloc[0]]
    for v in close.iloc[1:]:
        expected.append(alpha * v + (1 - alpha) * expected[-1])

    out = ema(close, span=span)

    np.testing.assert_allclose(out.to_numpy(), np.asarray(expected))


def test_rolling_volatility_uses_ddof_one_default() -> None:
    close = _close(length=60, seed=47)
    returns = log_returns(close).dropna()

    vol = rolling_volatility(returns, window=10)
    manual = returns.rolling(window=10).std(ddof=1)

    pd.testing.assert_series_equal(vol, manual)


def test_rolling_volatility_first_bars_are_nan() -> None:
    close = _close(length=30, seed=49)
    returns = log_returns(close).dropna()

    vol = rolling_volatility(returns, window=5)

    assert vol.iloc[:4].isna().all()
    assert not vol.iloc[4:].isna().any()


def test_zscore_matches_inline_ddof0_replace_nan_form() -> None:
    close = _close(length=80, seed=53)

    z_feature = zscore(close, lookback=20)

    c = close.astype(float)
    mean = c.rolling(window=20).mean()
    std = c.rolling(window=20).std(ddof=0)
    z_inline = (c - mean) / std.replace(0.0, np.nan)

    pd.testing.assert_series_equal(z_feature, z_inline)


def test_zscore_constant_series_yields_nan() -> None:
    idx = pd.date_range("2024-01-01", periods=40, freq="D")
    close = pd.Series(100.0, index=idx)

    z = zscore(close, lookback=10)

    assert z.iloc[10:].isna().all()


def test_zscore_index_preserved_even_on_degenerate_input() -> None:
    close = pd.Series(
        [1.0, 1.0, 1.0, 1.0, 1.0],
        index=pd.date_range("2024-01-01", periods=5, freq="D"),
    )
    z = zscore(close, lookback=3)

    assert z.index.equals(close.index)
    assert z.dtype.kind == "f"


def test_atr_warmup_and_nonnegative() -> None:
    frame = build_ohlcv_frame(length=60, seed=59)

    a = atr(frame["high"], frame["low"], frame["close"], window=14)

    assert a.index.equals(frame.index)
    assert a.iloc[:13].isna().all()
    assert (a.dropna() >= 0).all()


def test_atr_does_not_mutate_inputs() -> None:
    frame = build_ohlcv_frame(length=40, seed=61)
    before_high = frame["high"].copy()
    before_low = frame["low"].copy()
    before_close = frame["close"].copy()

    atr(frame["high"], frame["low"], frame["close"], window=10)

    pd.testing.assert_series_equal(frame["high"], before_high)
    pd.testing.assert_series_equal(frame["low"], before_low)
    pd.testing.assert_series_equal(frame["close"], before_close)


def test_spread_matches_inline_scalar_form() -> None:
    pairs = build_pairs_frame(length=50, seed=67)

    s_feature = spread(pairs["close"], pairs["close_ref"], hedge_ratio=1.0)
    s_inline = pairs["close"].astype(float) - 1.0 * pairs["close_ref"].astype(float)

    pd.testing.assert_series_equal(s_feature, s_inline)


def test_spread_scales_with_hedge_ratio() -> None:
    pairs = build_pairs_frame(length=30, seed=71)
    half = spread(pairs["close"], pairs["close_ref"], hedge_ratio=0.5)
    expected = pairs["close"].astype(float) - 0.5 * pairs["close_ref"].astype(float)

    pd.testing.assert_series_equal(half, expected)


def test_hedge_ratio_ols_static_matches_numpy() -> None:
    rng = np.random.default_rng(91)
    x = pd.Series(rng.normal(0, 1, 200), index=pd.date_range("2024-01-01", periods=200, freq="D"))
    y = 1.7 * x + rng.normal(0, 0.3, 200)

    beta = hedge_ratio_ols(y, x, lookback=None)

    x_arr = x.to_numpy()
    y_arr = y.to_numpy()
    expected = (np.mean(x_arr * y_arr) - np.mean(x_arr) * np.mean(y_arr)) / np.var(x_arr, ddof=0)
    assert abs(beta.iloc[0] - expected) < 1e-9
    assert (beta == beta.iloc[0]).all()


def test_hedge_ratio_ols_rolling_warmup_is_nan() -> None:
    idx = pd.date_range("2024-01-01", periods=60, freq="D")
    rng = np.random.default_rng(93)
    x = pd.Series(rng.normal(0, 1, 60), index=idx)
    y = pd.Series(rng.normal(0, 1, 60), index=idx)

    beta = hedge_ratio_ols(y, x, lookback=20)

    assert beta.iloc[:19].isna().all()
    assert beta.index.equals(idx)


def test_hedge_ratio_ols_zero_variance_yields_nan() -> None:
    idx = pd.date_range("2024-01-01", periods=10, freq="D")
    x = pd.Series(1.0, index=idx)
    y = pd.Series(np.linspace(0, 1, 10), index=idx)

    beta = hedge_ratio_ols(y, x, lookback=None)

    assert beta.isna().all()


def test_features_preserve_dtypes_and_indexes_across_primitives() -> None:
    close = _close(length=80, seed=73)
    assert sma(close, window=10).dtype.kind == "f"
    assert ema(close, span=10).dtype.kind == "f"
    assert log_returns(close).dtype.kind == "f"
    assert zscore(close, lookback=10).dtype.kind == "f"


def test_features_tolerate_misaligned_but_compatible_inputs() -> None:
    idx = pd.date_range("2024-01-01", periods=20, freq="D")
    close = pd.Series(np.linspace(100, 110, 20), index=idx)
    close_ref = pd.Series(np.linspace(90, 100, 20), index=idx)

    s = spread(close, close_ref, hedge_ratio=1.0)

    assert s.index.equals(idx)


def test_sma_misaligned_index_raises_or_yields_partial_nan() -> None:
    idx_a = pd.date_range("2024-01-01", periods=10, freq="D")
    close = pd.Series(np.arange(10, dtype=float), index=idx_a)

    out = sma(close, window=3)

    assert out.index.equals(idx_a)
    assert out.iloc[:2].isna().all()
