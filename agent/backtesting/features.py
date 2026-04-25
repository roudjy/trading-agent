"""Canonical feature primitives for the v3.5 thin strategy contract.

These functions are the single source of truth for indicators consumed by
thin strategies. They are:

- pure (no side effects, no IO, no randomness)
- deterministic (identical inputs -> bytewise identical outputs)
- index-preserving (outputs share the input index)
- non-mutating (inputs are never modified)

Every primitive here mirrors a previously inline computation from
agent/backtesting/strategies.py byte-for-byte; the mirror is documented
per-function so any refactor drift is visible. The bytewise pin tests
in tests/regression/test_tier1_bytewise_pin.py are the guardrail.

FEATURE_VERSION is pinned on the module. Any change to a primitive's
numerical contract is a version bump and must re-pin the affected
downstream snapshots explicitly.

FEATURE_REGISTRY at the bottom exposes a name -> spec lookup used by
the engine when resolving a thin strategy's declared requirements.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np
import pandas as pd


FEATURE_VERSION = "1.0"


@dataclass(frozen=True)
class FeatureSpec:
    """Spec for a registered feature primitive.

    - fn: the feature function itself
    - param_names: param names accepted beyond the data series
    - required_columns: DataFrame columns required on the source frame
    - warmup_bars_fn: callable(params) -> minimum bars needed before the
      feature emits its first non-NaN value. Used by integrity checks to
      reject strategies with insufficient data up front.
    """

    fn: Callable
    param_names: tuple[str, ...]
    required_columns: tuple[str, ...]
    warmup_bars_fn: Callable[[dict], int]


def log_returns(close: pd.Series) -> pd.Series:
    """Natural-log returns: np.log(close / close.shift(1)).

    Float-cast on entry so integer price series do not silently degrade
    to int arithmetic. First bar is NaN by construction.
    """
    c = close.astype(float)
    return np.log(c / c.shift(1))


def sma(close: pd.Series, window: int) -> pd.Series:
    """Simple moving average.

    Mirrors inline form `close.astype(float).rolling(window=N).mean()`
    from sma_crossover_strategie. Default pandas min_periods=window, so
    the first (window-1) bars are NaN - that is the intended contract.
    """
    return close.astype(float).rolling(window=window).mean()


def ema(close: pd.Series, span: int) -> pd.Series:
    """Exponential moving average with adjust=False.

    Mirrors inline form `close.astype(float).ewm(span=N, adjust=False).mean()`
    as used by the trend_pullback and breakout_momentum families.
    """
    return close.astype(float).ewm(span=span, adjust=False).mean()


def rolling_volatility(returns: pd.Series, window: int) -> pd.Series:
    """Rolling standard deviation with ddof=1 (pandas default).

    Split intentionally from zscore's denominator (which uses ddof=0).
    Callers that want a Bessel-corrected volatility estimate use this
    primitive; callers that want a biased sample std (e.g. z-score
    denominators) use zscore directly. See risks table in v3.5 plan.
    """
    return returns.astype(float).rolling(window=window).std()


def zscore(series: pd.Series, lookback: int) -> pd.Series:
    """Rolling z-score with ddof=0 and zero-std -> NaN protection.

    Mirrors inline form from zscore_mean_reversion_strategie and
    pairs_zscore_strategie exactly:

        mean = s.rolling(window=N).mean()
        std  = s.rolling(window=N).std(ddof=0)
        z    = (s - mean) / std.replace(0.0, np.nan)

    ddof=0 is intentional (biased sample std, matches the legacy inline
    code). Zero-std bars are replaced by NaN so division yields NaN
    rather than inf / runtime warnings.
    """
    s = series.astype(float)
    mean = s.rolling(window=lookback).mean()
    std = s.rolling(window=lookback).std(ddof=0)
    return (s - mean) / std.replace(0.0, np.nan)


def atr(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    window: int,
) -> pd.Series:
    """Average true range (Wilder-style simple-mean variant).

    True range is max of:
      - high - low
      - abs(high - prev_close)
      - abs(low  - prev_close)

    The rolling mean with default min_periods=window produces NaN for
    the first (window-1) bars, matching the inline usage in the
    trend_pullback family.
    """
    h = high.astype(float)
    low_ = low.astype(float)
    c_prev = close.astype(float).shift(1)
    tr = pd.concat(
        [(h - low_), (h - c_prev).abs(), (low_ - c_prev).abs()],
        axis=1,
    ).max(axis=1)
    return tr.rolling(window=window).mean()


def spread(
    close_a: pd.Series,
    close_b: pd.Series,
    hedge_ratio: float,
) -> pd.Series:
    """Pairs trading spread with a scalar hedge ratio.

    Mirrors `spread = close - hedge_ratio * close_ref` from
    pairs_zscore_strategie. OLS-fitted hedge ratios are deferred to
    hedge_ratio_ols below; see v3.6+ comment.
    """
    return close_a.astype(float) - float(hedge_ratio) * close_b.astype(float)


def spread_zscore(
    close_a: pd.Series,
    close_b: pd.Series,
    hedge_ratio: float,
    lookback: int,
) -> pd.Series:
    """Rolling z-score of the pairs-trading spread.

    Composite of `spread` and `zscore` - kept as a single registry
    entry so the thin pairs strategy declares exactly one feature
    requirement rather than chaining primitives in its body.
    """
    return zscore(spread(close_a, close_b, hedge_ratio), lookback)


def pullback_distance(
    close: pd.Series,
    ema_fast_window: int,
    vol_window: int,
) -> pd.Series:
    """Volatility-normalised distance from a short EMA (v3.15.3).

    Composite of ``ema(close, span=ema_fast_window)`` and
    ``rolling_volatility(log_returns(close), window=vol_window)``::

        ema_fast = ema(close, ema_fast_window)
        vol      = rolling_volatility(log_returns(close), vol_window)
        pullback_distance = (close - ema_fast) / vol

    Owns the zero-volatility guard explicitly: bars where ``vol == 0``
    yield NaN rather than ±inf so the consuming thin strategy gets a
    safe missing-data signal. NaN propagation in the warmup tail is
    inherited from the underlying primitives — no special-casing.

    Layer rules (v3.15.3 §6 feature layer):
    - deterministic
    - explicit NaN handling
    - zero-volatility handling
    - stable indexing (output index == close.index)
    - no lookahead (uses pandas ``ewm`` / ``rolling`` semantics only)

    Used exclusively by ``trend_pullback_v1_strategie``.
    """
    c = close.astype(float)
    ema_fast = c.ewm(span=int(ema_fast_window), adjust=False).mean()
    returns = np.log(c / c.shift(1))
    vol = returns.rolling(window=int(vol_window)).std()
    safe_vol = vol.where(vol != 0.0, np.nan)
    return (c - ema_fast) / safe_vol


# v3.6+: rolling OLS hedge ratio. Unused in v3.5 (pairs uses the fixed
# scalar path above). Implementation kept minimal and well-typed so the
# v3.6 pairs migration can turn it on without another primitive pass.
def hedge_ratio_ols(
    y: pd.Series,
    x: pd.Series,
    lookback: int | None = None,
) -> pd.Series:
    """Static (lookback=None) or rolling OLS hedge ratio beta.

    Returns a Series of the same index as y; rolling variant yields
    NaN for the first (lookback-1) bars. Zero-variance windows yield
    NaN rather than inf. Unused in v3.5.
    """
    y_ = y.astype(float)
    x_ = x.astype(float)

    if lookback is None:
        var = x_.var(ddof=0)
        if var == 0.0 or pd.isna(var):
            return pd.Series(np.nan, index=y.index)
        beta = ((x_ * y_).mean() - x_.mean() * y_.mean()) / var
        return pd.Series(float(beta), index=y.index)

    cov = (x_ * y_).rolling(window=lookback).mean() - (
        x_.rolling(window=lookback).mean() * y_.rolling(window=lookback).mean()
    )
    var = x_.rolling(window=lookback).var(ddof=0)
    return cov / var.replace(0.0, np.nan)


def _warmup_window(params: dict) -> int:
    return int(params.get("window", 0))


def _warmup_span(params: dict) -> int:
    return int(params.get("span", 0))


def _warmup_lookback(params: dict) -> int:
    return int(params.get("lookback", 0))


def _warmup_log_returns(_params: dict) -> int:
    return 1


def _warmup_spread(_params: dict) -> int:
    return 0


def _warmup_spread_zscore(params: dict) -> int:
    return int(params.get("lookback", 0))


def _warmup_pullback_distance(params: dict) -> int:
    # Composite warmup: max of EMA span and the rolling-vol window so
    # the integrity layer counts the longest required look-back.
    return max(
        int(params.get("ema_fast_window", 0)),
        int(params.get("vol_window", 0)),
    )


FEATURE_REGISTRY: dict[str, FeatureSpec] = {
    "log_returns": FeatureSpec(
        fn=log_returns,
        param_names=(),
        required_columns=("close",),
        warmup_bars_fn=_warmup_log_returns,
    ),
    "sma": FeatureSpec(
        fn=sma,
        param_names=("window",),
        required_columns=("close",),
        warmup_bars_fn=_warmup_window,
    ),
    "ema": FeatureSpec(
        fn=ema,
        param_names=("span",),
        required_columns=("close",),
        warmup_bars_fn=_warmup_span,
    ),
    "rolling_volatility": FeatureSpec(
        fn=rolling_volatility,
        param_names=("window",),
        required_columns=("close",),
        warmup_bars_fn=_warmup_window,
    ),
    "zscore": FeatureSpec(
        fn=zscore,
        param_names=("lookback",),
        required_columns=("close",),
        warmup_bars_fn=_warmup_lookback,
    ),
    "atr": FeatureSpec(
        fn=atr,
        param_names=("window",),
        required_columns=("high", "low", "close"),
        warmup_bars_fn=_warmup_window,
    ),
    "spread": FeatureSpec(
        fn=spread,
        param_names=("hedge_ratio",),
        required_columns=("close", "close_ref"),
        warmup_bars_fn=_warmup_spread,
    ),
    "spread_zscore": FeatureSpec(
        fn=spread_zscore,
        param_names=("hedge_ratio", "lookback"),
        required_columns=("close", "close_ref"),
        warmup_bars_fn=_warmup_spread_zscore,
    ),
    "pullback_distance": FeatureSpec(
        fn=pullback_distance,
        param_names=("ema_fast_window", "vol_window"),
        required_columns=("close",),
        warmup_bars_fn=_warmup_pullback_distance,
    ),
}


__all__ = [
    "FEATURE_REGISTRY",
    "FEATURE_VERSION",
    "FeatureSpec",
    "atr",
    "ema",
    "hedge_ratio_ols",
    "log_returns",
    "pullback_distance",
    "rolling_volatility",
    "sma",
    "spread",
    "spread_zscore",
    "zscore",
]
