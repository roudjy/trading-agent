"""Deterministic builders and strict comparison helpers for harness tests."""

from __future__ import annotations

import numpy as np
import pandas as pd
from pandas.testing import assert_frame_equal, assert_series_equal


DEFAULT_START = "2024-01-01"


def build_ohlcv_frame(
    length: int = 180,
    seed: int = 7,
    start: str = DEFAULT_START,
    freq: str = "D",
) -> pd.DataFrame:
    """Build a deterministic synthetic OHLCV frame."""
    rng = np.random.default_rng(seed)
    drift = np.linspace(0.0005, 0.002, length)
    noise = rng.normal(0.0, 0.01, length)
    close = 100.0 * np.cumprod(1.0 + drift + noise)
    open_ = close * (1.0 + rng.normal(0.0, 0.002, length))
    high = np.maximum(open_, close) * (1.0 + rng.uniform(0.0005, 0.01, length))
    low = np.minimum(open_, close) * (1.0 - rng.uniform(0.0005, 0.01, length))
    volume = rng.integers(1_000, 10_000, length, dtype=np.int64)
    index = pd.date_range(start=start, periods=length, freq=freq)
    return pd.DataFrame(
        {
            "open": open_.astype(float),
            "high": high.astype(float),
            "low": low.astype(float),
            "close": close.astype(float),
            "volume": volume,
        },
        index=index,
    )


def build_pairs_frame(
    length: int = 180,
    seed: int = 17,
    start: str = DEFAULT_START,
    freq: str = "D",
) -> pd.DataFrame:
    """Build a deterministic two-column close/close_ref frame."""
    base = build_ohlcv_frame(length=length, seed=seed, start=start, freq=freq)
    close_ref = base["close"] * 0.97 + np.linspace(-1.5, 1.5, length)
    return pd.DataFrame(
        {
            "close": base["close"].astype(float),
            "close_ref": close_ref.astype(float),
        },
        index=base.index.copy(),
    )


def assert_frame_matches(left: pd.DataFrame, right: pd.DataFrame) -> None:
    """Assert frames match on values, index, columns, and dtypes."""
    assert_frame_equal(left, right, check_dtype=True, check_like=False)


def assert_signal_matches(left: pd.Series, right: pd.Series) -> None:
    """Assert signals match on values, index alignment, name, and dtype."""
    assert_series_equal(left, right, check_dtype=True, check_names=True)
