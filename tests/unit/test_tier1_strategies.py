from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from agent.backtesting.strategies import (
    pairs_zscore_strategie,
    sma_crossover_strategie,
    zscore_mean_reversion_strategie,
)
from research.registry import STRATEGIES, get_enabled_strategies


def make_ohlcv_frame(n: int = 300, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    returns = rng.normal(0.0005, 0.015, n)
    close = 100.0 * np.cumprod(1 + returns)
    return make_frame_from_close(close, seed=seed + 1)


def make_frame_from_close(close: np.ndarray | list[float], seed: int = 11) -> pd.DataFrame:
    close_arr = np.asarray(close, dtype=float)
    rng = np.random.default_rng(seed)
    high = close_arr * (1 + rng.uniform(0.0, 0.01, len(close_arr)))
    low = close_arr * (1 - rng.uniform(0.0, 0.01, len(close_arr)))
    open_ = close_arr * (1 + rng.normal(0.0, 0.003, len(close_arr)))
    volume = rng.integers(1_000, 10_000, len(close_arr))
    index = pd.date_range("2024-01-01", periods=len(close_arr), freq="D")
    return pd.DataFrame(
        {
            "open": open_,
            "high": high,
            "low": low,
            "close": close_arr,
            "volume": volume,
        },
        index=index,
    )


def make_pairs_frame(n: int = 300, seed: int = 21) -> pd.DataFrame:
    df = make_ohlcv_frame(n=n, seed=seed)
    rng = np.random.default_rng(seed + 1)
    df["close_ref"] = df["close"] * 0.99 + rng.normal(0.0, 0.2, n)
    return df


def test_sma_crossover_output_length():
    df = make_ohlcv_frame(300, seed=1)
    sig = sma_crossover_strategie()(df)

    assert len(sig) == len(df)


def test_sma_crossover_signal_values_in_valid_set():
    df = make_ohlcv_frame(300, seed=2)
    sig = sma_crossover_strategie()(df)

    assert set(sig.unique()) <= {0, 1}


def test_sma_crossover_returns_zeros_when_insufficient_bars():
    df = make_ohlcv_frame(10, seed=3)
    sig = sma_crossover_strategie()(df)

    assert (sig == 0).all()


def test_sma_crossover_rejects_inverted_windows():
    df = make_ohlcv_frame(300, seed=4)
    sig = sma_crossover_strategie(fast_window=50, slow_window=20)(df)

    assert (sig == 0).all()


def test_sma_crossover_detects_known_cross():
    close = np.array([10, 10, 10, 10, 10, 11, 12, 13, 12, 11, 10], dtype=float)
    df = make_frame_from_close(close)
    sig = sma_crossover_strategie(fast_window=3, slow_window=5)(df)
    sma_fast = df["close"].rolling(window=3).mean()
    sma_slow = df["close"].rolling(window=5).mean()
    active_mask = sma_fast > sma_slow

    assert sig.iloc[5] == pytest.approx(1.0)
    assert sig[active_mask].eq(1).all()


def test_zscore_mr_output_length():
    df = make_ohlcv_frame(300, seed=5)
    sig = zscore_mean_reversion_strategie()(df)

    assert len(sig) == len(df)


def test_zscore_mr_signal_values_in_valid_set():
    df = make_ohlcv_frame(300, seed=6)
    sig = zscore_mean_reversion_strategie()(df)

    assert set(sig.unique()) <= {-1, 0, 1}


def test_zscore_mr_returns_zeros_when_insufficient_bars():
    df = make_ohlcv_frame(10, seed=7)
    sig = zscore_mean_reversion_strategie()(df)

    assert (sig == 0).all()


def test_zscore_mr_rejects_degenerate_thresholds():
    df = make_ohlcv_frame(300, seed=8)
    sig = zscore_mean_reversion_strategie(entry_z=0.5, exit_z=1.0)(df)

    assert (sig == 0).all()


def test_zscore_mr_detects_known_extreme():
    close = np.array([10, 10, 10, 10, 10, 20, 10, 10, 10, 10], dtype=float)
    df = make_frame_from_close(close)
    sig = zscore_mean_reversion_strategie(
        lookback=5,
        entry_z=2.0,
        exit_z=0.5,
    )(df)

    assert sig.iloc[5] == pytest.approx(-1.0)
    assert sig.iloc[6] == pytest.approx(0.0)


def test_pairs_zscore_output_length():
    df = make_pairs_frame(300, seed=9)
    sig = pairs_zscore_strategie()(df)

    assert len(sig) == len(df)


def test_pairs_zscore_signal_values_in_valid_set():
    df = make_pairs_frame(300, seed=10)
    sig = pairs_zscore_strategie()(df)

    assert set(sig.unique()) <= {-1, 0, 1}


def test_pairs_zscore_raises_when_close_ref_missing():
    """Post-refactor semantics: missing close_ref is surfaced as a
    feature resolution failure (KeyError), not a silent zero-signal.
    The integrity layer flags this as FEATURE_INCOMPLETE upstream in
    apply_eligibility so the run aborts with a typed reason code.
    """
    df = make_ohlcv_frame(300, seed=11)[["close"]]

    with pytest.raises(KeyError, match="close_ref"):
        pairs_zscore_strategie()(df)


def test_pairs_zscore_returns_zeros_when_insufficient_bars():
    df = make_pairs_frame(10, seed=12)
    sig = pairs_zscore_strategie()(df)

    assert (sig == 0).all()


def test_pairs_zscore_detects_known_spread_deviation():
    close = np.array([100, 100, 100, 100, 100, 90, 100, 100], dtype=float)
    close_ref = np.array([100, 100, 100, 100, 100, 100, 100, 100], dtype=float)
    df = make_frame_from_close(close)
    df["close_ref"] = close_ref
    sig = pairs_zscore_strategie(
        lookback=5,
        entry_z=2.0,
        exit_z=0.5,
        hedge_ratio=1.0,
    )(df)

    assert sig.iloc[5] == pytest.approx(1.0)


def test_registry_includes_all_tier1_baseline_names():
    names = {strategy["name"] for strategy in STRATEGIES}

    assert {"sma_crossover", "zscore_mean_reversion", "pairs_zscore"} <= names


def test_tier1_enabled_flags_match_baseline_blocker():
    lookup = {strategy["name"]: strategy["enabled"] for strategy in STRATEGIES}

    assert lookup["sma_crossover"] is True
    assert lookup["zscore_mean_reversion"] is True
    assert lookup["pairs_zscore"] is False


def test_get_enabled_strategies_excludes_pairs_zscore():
    names = {strategy["name"] for strategy in get_enabled_strategies()}

    assert "pairs_zscore" not in names
    assert "sma_crossover" in names
    assert "zscore_mean_reversion" in names


def test_tier1_param_grids_fit_sweep_budget():
    lookup = {
        strategy["name"]: strategy
        for strategy in STRATEGIES
        if strategy["name"] in {"sma_crossover", "zscore_mean_reversion", "pairs_zscore"}
    }

    for strategy in lookup.values():
        cells = math.prod(len(values) for values in strategy["params"].values())
        assert cells <= 64
