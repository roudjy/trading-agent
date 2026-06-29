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


def build_aligned_pair_frames(
    seed_primary: int = 7,
    seed_reference: int = 13,
    length: int = 180,
    start: str = DEFAULT_START,
    freq: str = "D",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build two deterministic OHLCV frames that share a DatetimeIndex.

    Intended for multi-asset loader / pairs end-to-end tests: the two
    frames are shaped for inner-join alignment without any overlap
    surgery required, and their seeds differ so the close columns are
    not trivially correlated. Idempotent under truncation: slicing either
    frame and then joining equals joining then slicing.
    """
    primary = build_ohlcv_frame(length=length, seed=seed_primary, start=start, freq=freq)
    reference = build_ohlcv_frame(
        length=length, seed=seed_reference, start=start, freq=freq
    )
    return primary, reference


def build_cross_sectional_frame(
    *,
    periods: int = 24,
    assets: tuple[str, ...] = ("AAA", "BBB", "CCC", "DDD"),
    seed: int = 23,
    start: str = DEFAULT_START,
    freq: str = "D",
    universe_id: str = "breadth_resolved_multi_asset_basket",
) -> pd.DataFrame:
    """Build a deterministic cross-sectional OHLCV panel with MultiIndex."""
    rng = np.random.default_rng(seed)
    timestamps = pd.date_range(start=start, periods=periods, freq=freq)
    rows: list[dict[str, object]] = []
    for asset_index, asset in enumerate(assets):
        base_level = 80.0 + asset_index * 12.5
        drift = np.linspace(0.0008 + asset_index * 0.0002, 0.002, periods)
        noise = rng.normal(0.0, 0.008, periods)
        close = base_level * np.cumprod(1.0 + drift + noise)
        open_ = close * (1.0 + rng.normal(0.0, 0.0015, periods))
        high = np.maximum(open_, close) * (
            1.0 + rng.uniform(0.0005, 0.007, periods)
        )
        low = np.minimum(open_, close) * (
            1.0 - rng.uniform(0.0005, 0.007, periods)
        )
        volume = rng.integers(2_000, 20_000, periods, dtype=np.int64)
        for idx, timestamp in enumerate(timestamps):
            rows.append(
                {
                    "timestamp": timestamp,
                    "asset": asset,
                    "open": float(open_[idx]),
                    "high": float(high[idx]),
                    "low": float(low[idx]),
                    "close": float(close[idx]),
                    "volume": int(volume[idx]),
                    "universe_id": universe_id,
                    "eligibility_state": "eligible",
                }
            )
    frame = pd.DataFrame(rows).set_index(["timestamp", "asset"]).sort_index()
    return frame


def assert_frame_matches(left: pd.DataFrame, right: pd.DataFrame) -> None:
    """Assert frames match on values, index, columns, and dtypes."""
    assert_frame_equal(left, right, check_dtype=True, check_like=False)


def assert_signal_matches(left: pd.Series, right: pd.Series) -> None:
    """Assert signals match on values, index alignment, name, and dtype."""
    assert_series_equal(left, right, check_dtype=True, check_names=True)
