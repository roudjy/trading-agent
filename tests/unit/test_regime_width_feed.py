"""Unit tests for research.regime_width_feed.

The feed is deterministic, cache-backed, and must degrade gracefully
when data is unavailable without raising.
"""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from research.regime_width_feed import (
    WIDTH_FEED_VERSION,
    WidthFeedResult,
    build_width_distributions,
)


class _StubRepo:
    """Minimal stand-in for MarketRepository used to keep these tests
    hermetic. Returns a deterministic OHLCV frame for every call."""

    def __init__(self, *, frame: pd.DataFrame, should_raise: bool = False):
        self._frame = frame
        self._calls: list[tuple] = []
        self._should_raise = should_raise

    @property
    def call_log(self) -> list[tuple]:
        return list(self._calls)

    def get_bars(self, *, instrument, interval, start_utc, end_utc):
        self._calls.append((instrument.native_symbol, interval))
        if self._should_raise:
            from data.repository import DataUnavailableError

            raise DataUnavailableError("stub-fail")
        return SimpleNamespace(
            frame=self._frame,
            provenance=SimpleNamespace(adapter="stub-adapter", cache_hit=True),
        )


def _synthetic_close_series(n: int = 400, *, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    # Alternating volatility phases so the classifier emits both
    # expansion and compression buckets deterministically.
    noise = rng.normal(size=n) * 0.01
    noise[150:250] *= 4.0
    close = 100.0 + np.cumsum(noise)
    return pd.DataFrame({"close": close, "high": close, "low": close, "volume": 1.0})


def _registry(entries: list[dict]) -> dict:
    return {"entries": entries}


def test_build_width_distributions_empty_registry():
    frame = _synthetic_close_series()
    repo = _StubRepo(frame=frame)
    result = build_width_distributions(
        registry_v2={"entries": []},
        date_range_by_interval={"4h": ("2024-01-01", "2025-01-01")},
        market_repository=repo,
    )
    assert isinstance(result, WidthFeedResult)
    assert result.distributions == {}
    assert result.lineage == []
    assert repo.call_log == []


def test_build_width_distributions_happy_path_is_deterministic():
    frame = _synthetic_close_series()
    repo_a = _StubRepo(frame=frame)
    repo_b = _StubRepo(frame=frame)
    entries = [
        {"candidate_id": "alpha", "asset": "NVDA", "interval": "4h"},
        {"candidate_id": "beta", "asset": "NVDA", "interval": "4h"},
        {"candidate_id": "gamma", "asset": "MSFT", "interval": "4h"},
    ]
    date_range = {"4h": ("2024-01-01", "2025-01-01")}

    result_a = build_width_distributions(
        registry_v2=_registry(entries),
        date_range_by_interval=date_range,
        market_repository=repo_a,
    )
    result_b = build_width_distributions(
        registry_v2=_registry(entries),
        date_range_by_interval=date_range,
        market_repository=repo_b,
    )
    # Determinism — two different repos returning the same frame must
    # produce byte-equal distribution dicts.
    assert result_a.distributions == result_b.distributions
    # Cache-key sharing — alpha and beta share (asset, interval) so the
    # repository is called twice (one per unique pair), not three
    # times.
    assert len(repo_a.call_log) == 2
    # Each bucket dict must contain every canonical width bucket.
    for buckets in result_a.distributions.values():
        assert set(buckets.keys()) == {"expansion", "compression", "insufficient"}
    # Lineage carries classifier + feed versions.
    assert all(entry["classifier_version"] is not None for entry in result_a.lineage)
    assert all(entry["width_feed_version"] == WIDTH_FEED_VERSION for entry in result_a.lineage)


def test_build_width_distributions_graceful_on_fetch_error():
    repo = _StubRepo(frame=pd.DataFrame(), should_raise=True)
    result = build_width_distributions(
        registry_v2=_registry([
            {"candidate_id": "alpha", "asset": "NVDA", "interval": "4h"},
        ]),
        date_range_by_interval={"4h": ("2024-01-01", "2025-01-01")},
        market_repository=repo,
    )
    assert result.distributions == {}


def test_build_width_distributions_skips_missing_date_range():
    repo = _StubRepo(frame=_synthetic_close_series())
    result = build_width_distributions(
        registry_v2=_registry([
            {"candidate_id": "alpha", "asset": "NVDA", "interval": "4h"},
        ]),
        date_range_by_interval={},  # missing on purpose
        market_repository=repo,
    )
    assert result.distributions == {}
    assert repo.call_log == []


def test_build_width_distributions_ignores_invalid_entries():
    repo = _StubRepo(frame=_synthetic_close_series())
    entries = [
        {"candidate_id": "", "asset": "NVDA", "interval": "4h"},
        {"asset": "NVDA", "interval": "4h"},  # no candidate_id
        {"candidate_id": "good", "asset": "NVDA", "interval": "4h"},
    ]
    result = build_width_distributions(
        registry_v2=_registry(entries),
        date_range_by_interval={"4h": ("2024-01-01", "2025-01-01")},
        market_repository=repo,
    )
    assert set(result.distributions.keys()) == {"good"}
