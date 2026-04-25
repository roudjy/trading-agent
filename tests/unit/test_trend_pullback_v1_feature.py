"""Tests for v3.15.3 ``pullback_distance`` feature primitive."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from agent.backtesting.features import (
    FEATURE_REGISTRY,
    pullback_distance,
)


@pytest.fixture
def steady_close() -> pd.Series:
    # Smooth synthetic price walk so the EMA + rolling std produce
    # well-defined values once warmed up.
    rng = np.random.default_rng(seed=42)
    n = 200
    walk = np.cumsum(rng.normal(0.0, 0.5, size=n)) + 100.0
    idx = pd.date_range("2026-01-01", periods=n, freq="1h")
    return pd.Series(walk, index=idx, name="close")


def test_registered_in_feature_registry() -> None:
    spec = FEATURE_REGISTRY["pullback_distance"]
    assert spec.required_columns == ("close",)
    assert set(spec.param_names) == {"ema_fast_window", "vol_window"}


def test_index_aligned_with_close(steady_close: pd.Series) -> None:
    out = pullback_distance(steady_close, ema_fast_window=10, vol_window=20)
    assert out.index.equals(steady_close.index)


def test_warmup_first_rows_nan(steady_close: pd.Series) -> None:
    out = pullback_distance(steady_close, ema_fast_window=10, vol_window=20)
    # log_returns drops the first bar; rolling std needs `vol_window`
    # bars before it can emit; so the leading vol_window bars must be
    # NaN.
    leading = out.iloc[:20]
    assert leading.isna().sum() >= 19


def test_zero_volatility_returns_nan() -> None:
    # A perfectly flat price series produces zero log-returns -> zero
    # rolling std -> NaN (not inf).
    flat = pd.Series([100.0] * 100, index=pd.RangeIndex(100), name="close")
    out = pullback_distance(flat, ema_fast_window=5, vol_window=10)
    # After warmup, every value should be NaN because vol == 0.
    tail = out.iloc[20:]
    assert tail.isna().all()
    # No infinities anywhere.
    assert not np.isinf(out.dropna()).any()


def test_no_lookahead(steady_close: pd.Series) -> None:
    """Truncating the input must not change earlier values."""
    out_full = pullback_distance(steady_close, ema_fast_window=10, vol_window=20)
    out_truncated = pullback_distance(
        steady_close.iloc[:150], ema_fast_window=10, vol_window=20
    )
    # Compare overlap region (after warmup so we have real values).
    overlap = out_full.iloc[50:150]
    truncated_overlap = out_truncated.iloc[50:150]
    pd.testing.assert_series_equal(
        overlap.dropna(), truncated_overlap.dropna(), check_names=False
    )


def test_deterministic_across_runs(steady_close: pd.Series) -> None:
    a = pullback_distance(steady_close, ema_fast_window=10, vol_window=20)
    b = pullback_distance(steady_close, ema_fast_window=10, vol_window=20)
    pd.testing.assert_series_equal(a, b, check_names=False)


def test_values_finite_after_warmup(steady_close: pd.Series) -> None:
    out = pullback_distance(steady_close, ema_fast_window=10, vol_window=20)
    finite = out.dropna()
    assert len(finite) > 0
    assert not np.isinf(finite).any()


def test_negative_when_close_below_ema_fast() -> None:
    # Construct a deterministic dip: rising series then a single dip.
    n = 60
    base = np.linspace(100.0, 110.0, n)
    base[-1] = 95.0  # sudden dip below the running EMA
    s = pd.Series(base, index=pd.RangeIndex(n), name="close")
    out = pullback_distance(s, ema_fast_window=5, vol_window=10)
    # The terminal bar dipped well below the EMA, so pullback_distance
    # there must be strictly negative.
    assert out.iloc[-1] < 0
    assert math.isfinite(out.iloc[-1])
