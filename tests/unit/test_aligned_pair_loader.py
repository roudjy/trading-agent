"""Unit tests for the v3.6 multi-asset aligned pair loader.

Covers:
- inner-join determinism (identical inputs -> byte-identical output)
- truncation idempotence (the fold-safety invariant)
- empty-intersection rejection
- mixed-asset-class rejection
- missing-leg rejection
- provenance capture
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pandas as pd
import pytest

from agent.backtesting.multi_asset_loader import (
    AlignedPairFrame,
    EmptyIntersectionError,
    LegUnavailableError,
    MixedAssetClassError,
    load_aligned_pair,
)
from data.contracts import Provenance
from data.repository import BarsResponse


def _provenance(adapter: str = "fixture") -> Provenance:
    return Provenance(
        adapter=adapter,
        fetched_at_utc=datetime(2026, 4, 10, 10, 0, tzinfo=UTC),
        config_hash="cfg",
        source_version="1.0",
        cache_hit=False,
    )


def _ohlcv(index: pd.DatetimeIndex, base: float) -> pd.DataFrame:
    n = len(index)
    return pd.DataFrame(
        {
            "open": [base + i for i in range(n)],
            "high": [base + i + 0.5 for i in range(n)],
            "low": [base + i - 0.5 for i in range(n)],
            "close": [base + i + 0.25 for i in range(n)],
            "volume": [1000.0 + i for i in range(n)],
        },
        index=index,
    )


def _repo_returning(primary_frame: pd.DataFrame, reference_frame: pd.DataFrame) -> MagicMock:
    repo = MagicMock()
    call_map = {}

    def _get_bars(*, instrument, interval, start_utc, end_utc):
        if instrument.native_symbol.startswith("BTC"):
            return BarsResponse(frame=primary_frame, provenance=_provenance("primary"))
        return BarsResponse(frame=reference_frame, provenance=_provenance("reference"))

    repo.get_bars.side_effect = _get_bars
    repo.__call_map = call_map
    return repo


@pytest.fixture
def bounds() -> tuple[pd.Timestamp, pd.Timestamp]:
    return pd.Timestamp("2026-01-01", tz="UTC"), pd.Timestamp("2026-04-10", tz="UTC")


def test_inner_join_is_deterministic(bounds):
    start, end = bounds
    index = pd.date_range("2026-01-01", periods=30, freq="D")
    primary = _ohlcv(index, base=100.0)
    reference = _ohlcv(index, base=200.0)
    repo = _repo_returning(primary, reference)

    first = load_aligned_pair(
        "BTC-EUR", "ETH-EUR", "1d", start, end, market_repository=repo
    )
    second = load_aligned_pair(
        "BTC-EUR", "ETH-EUR", "1d", start, end, market_repository=repo
    )

    assert isinstance(first, AlignedPairFrame)
    pd.testing.assert_frame_equal(first.primary, second.primary, check_dtype=True)
    pd.testing.assert_frame_equal(first.reference, second.reference, check_dtype=True)
    assert first.primary.index.equals(first.reference.index)


def test_inner_join_drops_non_shared_timestamps(bounds):
    start, end = bounds
    index_a = pd.date_range("2026-01-01", periods=10, freq="D")
    index_b = pd.date_range("2026-01-03", periods=10, freq="D")
    primary = _ohlcv(index_a, base=100.0)
    reference = _ohlcv(index_b, base=200.0)
    repo = _repo_returning(primary, reference)

    result = load_aligned_pair(
        "BTC-EUR", "ETH-EUR", "1d", start, end, market_repository=repo
    )

    expected_index = index_a.intersection(index_b)
    assert result.primary.index.equals(expected_index)
    assert result.reference.index.equals(expected_index)
    assert result.provenance["aligned_bar_count"] == len(expected_index)


def test_truncation_idempotence_under_fold_slicing(bounds):
    """Aligning on [t0..tN] then slicing to [t0..tK] == aligning on [t0..tK] directly.

    This is the v3.6 fold-safety invariant: dropping bars during alignment
    is driven purely by the data, not by which fold window is active.
    """
    start, end = bounds
    full_index = pd.date_range("2026-01-01", periods=30, freq="D")
    ref_index = full_index.delete([5, 12])
    full_primary = _ohlcv(full_index, base=100.0)
    full_reference = _ohlcv(ref_index, base=200.0)
    repo_full = _repo_returning(full_primary, full_reference)

    full_aligned = load_aligned_pair(
        "BTC-EUR", "ETH-EUR", "1d", start, end, market_repository=repo_full
    )

    fold_end = full_index[20]
    sliced_primary = full_aligned.primary.loc[:fold_end]
    sliced_reference = full_aligned.reference.loc[:fold_end]

    truncated_primary = full_primary.loc[:fold_end]
    truncated_reference = full_reference.loc[:fold_end]
    repo_trunc = _repo_returning(truncated_primary, truncated_reference)
    truncated_aligned = load_aligned_pair(
        "BTC-EUR", "ETH-EUR", "1d", start, end, market_repository=repo_trunc
    )

    pd.testing.assert_frame_equal(sliced_primary, truncated_aligned.primary)
    pd.testing.assert_frame_equal(sliced_reference, truncated_aligned.reference)


def test_empty_intersection_rejected(bounds):
    start, end = bounds
    primary = _ohlcv(pd.date_range("2026-01-01", periods=10, freq="D"), base=100.0)
    reference = _ohlcv(pd.date_range("2026-03-01", periods=10, freq="D"), base=200.0)
    repo = _repo_returning(primary, reference)

    with pytest.raises(EmptyIntersectionError, match="No overlapping timestamps"):
        load_aligned_pair(
            "BTC-EUR", "ETH-EUR", "1d", start, end, market_repository=repo
        )


def test_mixed_asset_class_rejected(bounds):
    start, end = bounds
    repo = MagicMock()

    with pytest.raises(MixedAssetClassError, match="Mixed asset class"):
        load_aligned_pair(
            "BTC-EUR", "NVDA", "1d", start, end, market_repository=repo
        )
    repo.get_bars.assert_not_called()


def test_missing_primary_leg_rejected(bounds):
    start, end = bounds
    empty = pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    reference = _ohlcv(pd.date_range("2026-01-01", periods=10, freq="D"), base=200.0)
    repo = _repo_returning(empty, reference)

    with pytest.raises(LegUnavailableError, match="Primary leg"):
        load_aligned_pair(
            "BTC-EUR", "ETH-EUR", "1d", start, end, market_repository=repo
        )


def test_missing_reference_leg_rejected(bounds):
    start, end = bounds
    primary = _ohlcv(pd.date_range("2026-01-01", periods=10, freq="D"), base=100.0)
    empty = pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    repo = _repo_returning(primary, empty)

    with pytest.raises(LegUnavailableError, match="Reference leg"):
        load_aligned_pair(
            "BTC-EUR", "ETH-EUR", "1d", start, end, market_repository=repo
        )


def test_provenance_carries_both_legs_and_bounds(bounds):
    start, end = bounds
    index = pd.date_range("2026-01-01", periods=30, freq="D")
    repo = _repo_returning(_ohlcv(index, 100.0), _ohlcv(index, 200.0))

    result = load_aligned_pair(
        "BTC-EUR", "ETH-EUR", "1d", start, end, market_repository=repo
    )

    assert "primary" in result.provenance
    assert "reference" in result.provenance
    assert result.provenance["interval"] == "1d"
    assert result.provenance["start_utc"] == start.isoformat()
    assert result.provenance["end_utc"] == end.isoformat()
    assert result.provenance["aligned_bar_count"] == 30
    assert result.asset_class == "crypto"


def test_equity_pair_resolved_as_equity(bounds):
    start, end = bounds
    index = pd.date_range("2026-01-01", periods=10, freq="D")
    repo = MagicMock()
    repo.get_bars.return_value = BarsResponse(
        frame=_ohlcv(index, base=50.0), provenance=_provenance()
    )

    result = load_aligned_pair(
        "NVDA", "AMD", "1d", start, end, market_repository=repo
    )

    assert result.asset_class == "equity"
    call_kwargs = repo.get_bars.call_args_list[0].kwargs
    assert call_kwargs["instrument"].asset_class == "equity"


def test_index_invariant_enforced_post_init():
    idx_a = pd.date_range("2026-01-01", periods=3, freq="D")
    idx_b = pd.date_range("2026-01-02", periods=3, freq="D")
    with pytest.raises(RuntimeError, match="indexes must match"):
        AlignedPairFrame(
            primary=_ohlcv(idx_a, 1.0),
            reference=_ohlcv(idx_b, 2.0),
            primary_symbol="BTC-EUR",
            reference_symbol="ETH-EUR",
            interval="1d",
            asset_class="crypto",
            provenance={},
        )
