"""Unit tests for Tier 1 baseline strategies under the thin contract.

Covers analytic behaviour of the migrated thin-contract factories:
- SMA crossover long-entry on known fast>slow crossings
- Z-score mean reversion entry/exit on engineered price extremes
- Pairs z-score entry on engineered spread deviations

These are deliberately separate from the bytewise pin tests in
tests/regression/test_tier1_bytewise_pin.py: the pins freeze numerical
output byte-for-byte against the pre-refactor inline implementations,
while the tests here exercise analytic edge cases under controlled
synthetic prices.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from agent.backtesting.strategies import (
    pairs_zscore_strategie,
    sma_crossover_strategie,
    zscore_mean_reversion_strategie,
)
from agent.backtesting.thin_strategy import (
    build_features_for,
    is_thin_strategy,
)


def _invoke(strategy, frame: pd.DataFrame) -> pd.Series:
    if is_thin_strategy(strategy):
        features = build_features_for(strategy._feature_requirements, frame)
        return strategy(frame, features)
    return strategy(frame)


def _frame_from_close(close: np.ndarray | list[float]) -> pd.DataFrame:
    close_arr = np.asarray(close, dtype=float)
    idx = pd.date_range("2024-01-01", periods=len(close_arr), freq="D")
    return pd.DataFrame({"close": close_arr}, index=idx)


def _pairs_frame(close: list[float], close_ref: list[float]) -> pd.DataFrame:
    frame = _frame_from_close(close)
    frame["close_ref"] = np.asarray(close_ref, dtype=float)
    return frame


def test_tier1_factories_declare_thin_contract_version():
    for factory in (sma_crossover_strategie, zscore_mean_reversion_strategie, pairs_zscore_strategie):
        strategy = factory()
        assert is_thin_strategy(strategy), f"{factory.__name__} must be thin contract"
        assert strategy._thin_contract_version == "1.0"


def test_tier1_factories_declare_non_empty_feature_requirements():
    for factory in (sma_crossover_strategie, zscore_mean_reversion_strategie, pairs_zscore_strategie):
        strategy = factory()
        assert len(strategy._feature_requirements) > 0


def test_sma_crossover_detects_upward_cross():
    close = [10.0] * 5 + [11.0, 12.0, 13.0, 12.0, 11.0, 10.0]
    frame = _frame_from_close(close)

    sig = _invoke(sma_crossover_strategie(fast_window=3, slow_window=5), frame)

    sma_fast = frame["close"].rolling(window=3).mean()
    sma_slow = frame["close"].rolling(window=5).mean()
    expected_long_mask = sma_fast > sma_slow
    assert sig[expected_long_mask].eq(1).all()


def test_sma_crossover_returns_all_zeros_when_fewer_bars_than_slow_window():
    frame = _frame_from_close([100.0] * 30)

    sig = _invoke(sma_crossover_strategie(fast_window=10, slow_window=50), frame)

    assert (sig == 0).all()


def test_sma_crossover_rejects_fast_not_less_than_slow():
    frame = _frame_from_close(list(range(200)))

    sig = _invoke(sma_crossover_strategie(fast_window=50, slow_window=20), frame)

    assert (sig == 0).all()


def test_zscore_mean_reversion_shorts_on_positive_extreme():
    close = [10.0] * 5 + [20.0, 10.0, 10.0, 10.0, 10.0]
    frame = _frame_from_close(close)

    sig = _invoke(
        zscore_mean_reversion_strategie(lookback=5, entry_z=2.0, exit_z=0.5),
        frame,
    )

    assert sig.iloc[5] == -1


def test_zscore_mean_reversion_longs_on_negative_extreme():
    close = [10.0] * 5 + [2.0, 10.0, 10.0, 10.0, 10.0]
    frame = _frame_from_close(close)

    sig = _invoke(
        zscore_mean_reversion_strategie(lookback=5, entry_z=2.0, exit_z=0.5),
        frame,
    )

    assert sig.iloc[5] == 1


def test_zscore_mean_reversion_rejects_invalid_band():
    frame = _frame_from_close([100.0 + i * 0.1 for i in range(200)])

    sig = _invoke(
        zscore_mean_reversion_strategie(lookback=20, entry_z=0.5, exit_z=0.5),
        frame,
    )

    assert (sig == 0).all()


def test_zscore_mean_reversion_returns_zero_for_insufficient_bars():
    frame = _frame_from_close([10.0] * 10)

    sig = _invoke(
        zscore_mean_reversion_strategie(lookback=20, entry_z=2.0, exit_z=0.5),
        frame,
    )

    assert (sig == 0).all()


def test_pairs_zscore_detects_known_negative_spread_deviation():
    close = [100.0] * 5 + [90.0, 100.0, 100.0]
    close_ref = [100.0] * 8
    frame = _pairs_frame(close, close_ref)

    sig = _invoke(
        pairs_zscore_strategie(lookback=5, entry_z=2.0, exit_z=0.5, hedge_ratio=1.0),
        frame,
    )

    assert sig.iloc[5] == 1


def test_pairs_zscore_raises_keyerror_when_close_ref_missing():
    frame = _frame_from_close([100.0] * 50)

    with pytest.raises(KeyError, match="close_ref"):
        _invoke(pairs_zscore_strategie(lookback=5, entry_z=2.0, exit_z=0.5), frame)


def test_pairs_zscore_rejects_invalid_band():
    frame = _pairs_frame([100.0 + i * 0.1 for i in range(100)], [100.0] * 100)

    sig = _invoke(
        pairs_zscore_strategie(lookback=20, entry_z=0.5, exit_z=0.5, hedge_ratio=1.0),
        frame,
    )

    assert (sig == 0).all()


def test_tier1_signals_are_deterministic_across_calls():
    frame = _frame_from_close([100.0 + i * 0.1 for i in range(200)])
    strategy = sma_crossover_strategie(fast_window=10, slow_window=50)

    first = _invoke(strategy, frame)
    second = _invoke(strategy, frame)

    pd.testing.assert_series_equal(first, second)
    assert first.to_numpy(copy=True).tobytes() == second.to_numpy(copy=True).tobytes()
