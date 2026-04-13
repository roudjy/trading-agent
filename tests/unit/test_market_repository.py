from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest

from data.contracts import CanonicalBar, Instrument, Provenance
from data.repository import DataUnavailableError, MarketRepository


class FixtureAdapter:
    @property
    def name(self) -> str:
        return "fixture"

    def fetch_bars(self, instrument, interval, start_utc, end_utc):
        provenance = Provenance(
            adapter=self.name,
            fetched_at_utc=datetime(2026, 4, 10, 10, 0, tzinfo=UTC),
            config_hash="cfg-1",
            source_version="1.0",
            cache_hit=False,
        )
        return [
            CanonicalBar(
                instrument=instrument,
                interval=interval,
                timestamp_utc=datetime(2026, 4, 9, 0, 0, tzinfo=UTC),
                open=100.0,
                high=110.0,
                low=90.0,
                close=105.0,
                volume=1000.0,
                provenance=provenance,
            ),
            CanonicalBar(
                instrument=instrument,
                interval=interval,
                timestamp_utc=datetime(2026, 4, 10, 0, 0, tzinfo=UTC),
                open=101.0,
                high=111.0,
                low=91.0,
                close=106.0,
                volume=1200.0,
                provenance=provenance,
            ),
        ]


class FailingAdapter:
    @property
    def name(self) -> str:
        return "fixture"

    def fetch_bars(self, instrument, interval, start_utc, end_utc):
        raise RuntimeError("boom")


class EmptyAdapter:
    @property
    def name(self) -> str:
        return "fixture"

    def fetch_bars(self, instrument, interval, start_utc, end_utc):
        return []


class CountingAdapter(FixtureAdapter):
    def __init__(self, bars):
        self._bars = list(bars)
        self.calls = 0

    @property
    def name(self) -> str:
        return "fixture"

    def fetch_bars(self, instrument, interval, start_utc, end_utc):
        self.calls += 1
        return list(self._bars)


def test_market_repository_reshapes_bars_to_engine_frame(tmp_path):
    instrument = Instrument(
        id="btc-usd",
        asset_class="crypto",
        venue="yahoo",
        native_symbol="BTC-USD",
        quote_ccy="USD",
    )
    repository = MarketRepository(
        adapters={"crypto": FixtureAdapter()},
        cache_dir=tmp_path / "market-cache",
    )

    response = repository.get_bars(
        instrument=instrument,
        interval="1d",
        start_utc=datetime(2026, 4, 1, tzinfo=UTC),
        end_utc=datetime(2026, 4, 11, tzinfo=UTC),
    )

    expected = (Path("tests/fixtures/market_repository_golden.csv")).read_text(encoding="utf-8")

    assert response.frame.to_csv(date_format="%Y-%m-%d %H:%M:%S", lineterminator="\n") == expected
    assert response.provenance.adapter == "fixture"
    assert response.provenance.cache_hit is False


def test_market_repository_reads_cached_parquet_without_adapter_call(tmp_path):
    instrument = Instrument(
        id="btc-usd",
        asset_class="crypto",
        venue="yahoo",
        native_symbol="BTC-USD",
        quote_ccy="USD",
    )
    cache_dir = tmp_path / "market-cache"
    repository = MarketRepository(
        adapters={"crypto": FixtureAdapter()},
        cache_dir=cache_dir,
    )

    first = repository.get_bars(
        instrument=instrument,
        interval="1d",
        start_utc=datetime(2026, 4, 1, tzinfo=UTC),
        end_utc=datetime(2026, 4, 11, tzinfo=UTC),
    )
    second = MarketRepository(
        adapters={"crypto": FailingAdapter()},
        cache_dir=cache_dir,
    ).get_bars(
        instrument=instrument,
        interval="1d",
        start_utc=datetime(2026, 4, 1, tzinfo=UTC),
        end_utc=datetime(2026, 4, 11, tzinfo=UTC),
    )

    assert first.frame.equals(second.frame)
    assert second.provenance.cache_hit is True


def test_market_repository_raises_data_unavailable_on_adapter_failure(tmp_path):
    instrument = Instrument(
        id="nvda-usd",
        asset_class="equity",
        venue="yahoo",
        native_symbol="NVDA",
        quote_ccy="USD",
    )
    repository = MarketRepository(
        adapters={"equity": FailingAdapter()},
        cache_dir=tmp_path / "market-cache",
    )

    with pytest.raises(DataUnavailableError):
        repository.get_bars(
            instrument=instrument,
            interval="1d",
            start_utc=datetime(2026, 4, 1, tzinfo=UTC),
            end_utc=datetime(2026, 4, 11, tzinfo=UTC),
        )


def test_market_repository_does_not_cache_empty_fetch_results(tmp_path):
    instrument = Instrument(
        id="btc-usd",
        asset_class="crypto",
        venue="yahoo",
        native_symbol="BTC-USD",
        quote_ccy="USD",
    )
    cache_dir = tmp_path / "market-cache"
    repository = MarketRepository(
        adapters={"crypto": EmptyAdapter()},
        cache_dir=cache_dir,
    )

    response = repository.get_bars(
        instrument=instrument,
        interval="1h",
        start_utc=datetime(2026, 4, 1, tzinfo=UTC),
        end_utc=datetime(2026, 4, 11, tzinfo=UTC),
    )

    assert response.frame.empty is True
    assert list(cache_dir.glob("*.parquet")) == []


def test_market_repository_refetches_when_existing_cache_artifact_is_empty(tmp_path):
    instrument = Instrument(
        id="btc-usd",
        asset_class="crypto",
        venue="yahoo",
        native_symbol="BTC-USD",
        quote_ccy="USD",
    )
    cache_dir = tmp_path / "market-cache"
    adapter = CountingAdapter(FixtureAdapter().fetch_bars(instrument, "1h", None, None))
    repository = MarketRepository(
        adapters={"crypto": adapter},
        cache_dir=cache_dir,
    )
    cache_path = repository._cache_path(
        adapter.name,
        instrument.native_symbol,
        "1h",
        datetime(2026, 4, 1, tzinfo=UTC),
        datetime(2026, 4, 11, tzinfo=UTC),
    )
    pd.DataFrame().to_parquet(cache_path, index=False)

    response = repository.get_bars(
        instrument=instrument,
        interval="1h",
        start_utc=datetime(2026, 4, 1, tzinfo=UTC),
        end_utc=datetime(2026, 4, 11, tzinfo=UTC),
    )

    cached = pd.read_parquet(cache_path)
    assert adapter.calls == 1
    assert response.frame.empty is False
    assert response.provenance.cache_hit is False
    assert cached.empty is False
    assert "timestamp_utc" in cached.columns


def test_market_repository_keeps_valid_non_empty_cache_behavior_unchanged(tmp_path):
    instrument = Instrument(
        id="btc-usd",
        asset_class="crypto",
        venue="yahoo",
        native_symbol="BTC-USD",
        quote_ccy="USD",
    )
    cache_dir = tmp_path / "market-cache"
    repository = MarketRepository(
        adapters={"crypto": FixtureAdapter()},
        cache_dir=cache_dir,
    )
    repository.get_bars(
        instrument=instrument,
        interval="1d",
        start_utc=datetime(2026, 4, 1, tzinfo=UTC),
        end_utc=datetime(2026, 4, 11, tzinfo=UTC),
    )

    adapter = CountingAdapter([])
    second = MarketRepository(
        adapters={"crypto": adapter},
        cache_dir=cache_dir,
    ).get_bars(
        instrument=instrument,
        interval="1d",
        start_utc=datetime(2026, 4, 1, tzinfo=UTC),
        end_utc=datetime(2026, 4, 11, tzinfo=UTC),
    )

    assert adapter.calls == 0
    assert second.frame.empty is False
    assert second.provenance.cache_hit is True


def test_market_repository_does_not_trust_empty_cache_when_refetch_stays_empty(tmp_path):
    instrument = Instrument(
        id="btc-usd",
        asset_class="crypto",
        venue="yahoo",
        native_symbol="BTC-USD",
        quote_ccy="USD",
    )
    cache_dir = tmp_path / "market-cache"
    adapter = CountingAdapter([])
    repository = MarketRepository(
        adapters={"crypto": adapter},
        cache_dir=cache_dir,
    )
    cache_path = repository._cache_path(
        adapter.name,
        instrument.native_symbol,
        "1h",
        datetime(2026, 4, 1, tzinfo=UTC),
        datetime(2026, 4, 11, tzinfo=UTC),
    )
    pd.DataFrame().to_parquet(cache_path, index=False)

    response = repository.get_bars(
        instrument=instrument,
        interval="1h",
        start_utc=datetime(2026, 4, 1, tzinfo=UTC),
        end_utc=datetime(2026, 4, 11, tzinfo=UTC),
    )

    assert adapter.calls == 1
    assert response.frame.empty is True
    assert pd.read_parquet(cache_path).empty is True
