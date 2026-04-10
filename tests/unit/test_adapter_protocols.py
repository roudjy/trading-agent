from datetime import UTC, datetime

from data.adapters.base import MacroAdapter, MarketAdapter
from data.contracts import CanonicalBar, Instrument, MacroSeriesPoint, Provenance


class DummyMarketAdapter:
    @property
    def name(self) -> str:
        return "dummy-market"

    def fetch_bars(
        self,
        instrument: Instrument,
        interval: str,
        start_utc: datetime,
        end_utc: datetime,
    ) -> list[CanonicalBar]:
        return []


class DummyMacroAdapter:
    @property
    def name(self) -> str:
        return "dummy-macro"

    def fetch_series(
        self,
        series_id: str,
        start_utc: datetime,
        end_utc: datetime,
        as_of_utc: datetime | None,
    ) -> list[MacroSeriesPoint]:
        return []


def test_market_adapter_protocol_is_runtime_checkable():
    adapter = DummyMarketAdapter()

    assert isinstance(adapter, MarketAdapter)


def test_macro_adapter_protocol_is_runtime_checkable():
    adapter = DummyMacroAdapter()

    assert isinstance(adapter, MacroAdapter)


def test_protocol_examples_match_canonical_contracts():
    provenance = Provenance(
        adapter="dummy",
        fetched_at_utc=datetime(2026, 4, 10, 10, 0, tzinfo=UTC),
        config_hash="cfg",
        source_version="1.0",
        cache_hit=False,
    )
    instrument = Instrument(
        id="nvda-usd",
        asset_class="equity",
        venue="yahoo",
        native_symbol="NVDA",
        quote_ccy="USD",
    )

    bar = CanonicalBar(
        instrument=instrument,
        interval="1d",
        timestamp_utc=datetime(2026, 4, 9, 0, 0, tzinfo=UTC),
        open=1.0,
        high=1.1,
        low=0.9,
        close=1.05,
        volume=10.0,
        provenance=provenance,
    )
    point = MacroSeriesPoint(
        series_id="GDP",
        timestamp_utc=datetime(2026, 1, 1, 0, 0, tzinfo=UTC),
        value=100.0,
        native_frequency="quarterly",
        vintage_as_of_utc=None,
        provenance=provenance,
    )

    assert bar.instrument == instrument
    assert point.provenance == provenance
