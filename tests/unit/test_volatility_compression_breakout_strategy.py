"""Contract pins for ``volatility_compression_breakout_strategie`` (v3.15.4).

The strategy is the executable counterpart of the v3.15.4 second
active_discovery hypothesis. Tests pin the exact signal semantics
agreed in the v3.15.4 spec §B:

- long-only (no reversal)
- entry only when both ``compression_ratio[t-1] < threshold`` AND
  ``close[t] > rolling_high_previous[t]``
- exit on either ``close[t] < rolling_low_previous[t]`` OR
  ``compression_ratio[t-1] > 1.0``
- NaN feature on entry condition → no entry (signal stays at prior
  value)
- max 3 parameters
- thin contract: reads only ``df.index`` and ``features`` map (no
  inline TA, no raw OHLCV reads beyond ``df["close"]``)
"""

from __future__ import annotations

import inspect

import numpy as np
import pandas as pd

from agent.backtesting.strategies import volatility_compression_breakout_strategie
from agent.backtesting.thin_strategy import is_thin_strategy
from tests._harness_helpers import build_ohlcv_frame


def _make_features(
    *,
    compression: pd.Series,
    rolling_high_prev: pd.Series,
    rolling_low_prev: pd.Series,
) -> dict[str, pd.Series]:
    return {
        "compression_ratio": compression,
        "rolling_high_previous": rolling_high_prev,
        "rolling_low_previous": rolling_low_prev,
    }


def _flat_index(n: int) -> pd.DatetimeIndex:
    return pd.date_range("2024-01-01", periods=n, freq="D")


def test_strategy_is_thin_contract_v1() -> None:
    strat = volatility_compression_breakout_strategie()
    assert is_thin_strategy(strat)
    aliases = {req.alias for req in strat._feature_requirements}
    assert aliases == {
        "compression_ratio",
        "rolling_high_previous",
        "rolling_low_previous",
    }


def test_strategy_factory_max_three_parameters() -> None:
    sig = inspect.signature(volatility_compression_breakout_strategie)
    assert len(sig.parameters) == 3, (
        f"max 3 params (AGENTS.md); got {list(sig.parameters)}"
    )
    assert set(sig.parameters) == {
        "atr_short_window",
        "atr_long_window",
        "compression_threshold",
    }


def test_no_entry_when_compression_above_threshold() -> None:
    """If compression_ratio[t-1] >= threshold the entry is rejected
    even if close > rolling_high_previous."""
    n = 20
    idx = _flat_index(n)
    df = pd.DataFrame({"close": np.linspace(100.0, 120.0, n)}, index=idx)
    compression = pd.Series(np.full(n, 0.9), index=idx)  # never compressed
    rolling_high_prev = pd.Series(
        np.linspace(99.0, 110.0, n), index=idx
    )  # always below close → would trigger if compressed
    rolling_low_prev = pd.Series(np.full(n, 50.0), index=idx)
    strat = volatility_compression_breakout_strategie(
        atr_short_window=5,
        atr_long_window=10,
        compression_threshold=0.6,
    )
    sig = strat(df, _make_features(
        compression=compression,
        rolling_high_prev=rolling_high_prev,
        rolling_low_prev=rolling_low_prev,
    ))
    assert (sig == 0).all()


def test_entry_when_prior_compressed_and_breakout() -> None:
    """Entry triggers only on the bar where both conditions hold."""
    n = 12
    idx = _flat_index(n)
    df = pd.DataFrame({"close": np.full(n, 100.0)}, index=idx)
    df.loc[idx[7], "close"] = 130.0  # breakout bar
    # compression_ratio[t-1] = 0.4 (compressed) feeding bar t=7
    compression = pd.Series(np.full(n, 0.4), index=idx)
    # rolling_high_previous = 110 → close[7]=130 > 110 = breakout
    rolling_high_prev = pd.Series(np.full(n, 110.0), index=idx)
    rolling_low_prev = pd.Series(np.full(n, 50.0), index=idx)
    strat = volatility_compression_breakout_strategie(
        atr_short_window=5,
        atr_long_window=10,
        compression_threshold=0.6,
    )
    sig = strat(df, _make_features(
        compression=compression,
        rolling_high_prev=rolling_high_prev,
        rolling_low_prev=rolling_low_prev,
    ))
    # All bars where prior compressed AND close > roll_high get long.
    assert sig.loc[idx[7]] == 1


def test_exit_on_breakdown_below_rolling_low() -> None:
    """Close below rolling_low_previous triggers flat regardless of
    compression state."""
    n = 12
    idx = _flat_index(n)
    df = pd.DataFrame({"close": np.full(n, 100.0)}, index=idx)
    df.loc[idx[7], "close"] = 30.0  # breakdown bar
    compression = pd.Series(np.full(n, 0.4), index=idx)
    rolling_high_prev = pd.Series(np.full(n, 200.0), index=idx)
    rolling_low_prev = pd.Series(np.full(n, 50.0), index=idx)
    strat = volatility_compression_breakout_strategie(
        atr_short_window=5,
        atr_long_window=10,
        compression_threshold=0.6,
    )
    sig = strat(df, _make_features(
        compression=compression,
        rolling_high_prev=rolling_high_prev,
        rolling_low_prev=rolling_low_prev,
    ))
    assert sig.loc[idx[7]] == 0


def test_exit_on_compression_release() -> None:
    """compression_ratio[t-1] > 1.0 forces flat even when no breakdown."""
    n = 12
    idx = _flat_index(n)
    df = pd.DataFrame({"close": np.full(n, 100.0)}, index=idx)
    # compression > 1.0 from t=5 onwards (volatility expanded)
    compression = pd.Series([0.4] * 5 + [1.5] * 7, index=idx)
    rolling_high_prev = pd.Series(np.full(n, 200.0), index=idx)
    rolling_low_prev = pd.Series(np.full(n, 0.0), index=idx)
    strat = volatility_compression_breakout_strategie(
        atr_short_window=5,
        atr_long_window=10,
        compression_threshold=0.6,
    )
    sig = strat(df, _make_features(
        compression=compression,
        rolling_high_prev=rolling_high_prev,
        rolling_low_prev=rolling_low_prev,
    ))
    # From bar 6 onwards prior compression is 1.5 > 1.0 → forced flat.
    assert (sig.iloc[6:] == 0).all()


def test_long_only_no_short_signal_emitted() -> None:
    """Strategy never emits -1 (short) on any input combination."""
    n = 30
    idx = _flat_index(n)
    df = pd.DataFrame({"close": np.linspace(50.0, 150.0, n)}, index=idx)
    compression = pd.Series(np.linspace(0.2, 1.5, n), index=idx)
    rolling_high_prev = pd.Series(np.linspace(40.0, 140.0, n), index=idx)
    rolling_low_prev = pd.Series(np.linspace(60.0, 160.0, n), index=idx)
    strat = volatility_compression_breakout_strategie(
        atr_short_window=3,
        atr_long_window=8,
        compression_threshold=0.6,
    )
    sig = strat(df, _make_features(
        compression=compression,
        rolling_high_prev=rolling_high_prev,
        rolling_low_prev=rolling_low_prev,
    ))
    assert (sig != -1).all()


def test_returns_zeros_on_warmup_underflow() -> None:
    """When the index is shorter than atr_long_window + 2 the strategy
    refuses to emit signals (returns all zeros)."""
    n = 5  # well below atr_long_window=10 + 2
    idx = _flat_index(n)
    df = pd.DataFrame({"close": np.full(n, 100.0)}, index=idx)
    compression = pd.Series(np.full(n, 0.3), index=idx)
    rolling_high_prev = pd.Series(np.full(n, 50.0), index=idx)
    rolling_low_prev = pd.Series(np.full(n, 20.0), index=idx)
    strat = volatility_compression_breakout_strategie(
        atr_short_window=3,
        atr_long_window=10,
        compression_threshold=0.6,
    )
    sig = strat(df, _make_features(
        compression=compression,
        rolling_high_prev=rolling_high_prev,
        rolling_low_prev=rolling_low_prev,
    ))
    assert (sig == 0).all()


def test_invalid_param_combinations_yield_zeros() -> None:
    """``atr_short_window >= atr_long_window`` or invalid threshold
    short-circuits to all zeros (no crash, no degenerate emission)."""
    n = 30
    idx = _flat_index(n)
    df = pd.DataFrame({"close": np.full(n, 100.0)}, index=idx)
    feats = _make_features(
        compression=pd.Series(np.full(n, 0.3), index=idx),
        rolling_high_prev=pd.Series(np.full(n, 90.0), index=idx),
        rolling_low_prev=pd.Series(np.full(n, 50.0), index=idx),
    )
    s_inverted = volatility_compression_breakout_strategie(
        atr_short_window=20, atr_long_window=10, compression_threshold=0.6,
    )(df, feats)
    s_thresh_neg = volatility_compression_breakout_strategie(
        atr_short_window=5, atr_long_window=10, compression_threshold=-0.1,
    )(df, feats)
    s_thresh_too_high = volatility_compression_breakout_strategie(
        atr_short_window=5, atr_long_window=10, compression_threshold=1.5,
    )(df, feats)
    for s in (s_inverted, s_thresh_neg, s_thresh_too_high):
        assert (s == 0).all()


def test_strategy_is_deterministic_on_repeat_call() -> None:
    """Identical inputs produce byte-identical signals across two
    invocations (no module-level state, no randomness)."""
    frame = build_ohlcv_frame(length=120, seed=37)
    df = frame[["close"]]
    n = len(df)
    idx = df.index
    compression = pd.Series(
        np.linspace(0.3, 1.2, n) + 0.05 * np.sin(np.arange(n)),
        index=idx,
    )
    rolling_high_prev = pd.Series(
        df["close"].rolling(10).max().shift(1),
        index=idx,
    )
    rolling_low_prev = pd.Series(
        df["close"].rolling(10).min().shift(1),
        index=idx,
    )
    strat = volatility_compression_breakout_strategie(
        atr_short_window=5, atr_long_window=10, compression_threshold=0.6,
    )
    feats = _make_features(
        compression=compression,
        rolling_high_prev=rolling_high_prev,
        rolling_low_prev=rolling_low_prev,
    )
    pd.testing.assert_series_equal(strat(df, feats), strat(df, feats))
