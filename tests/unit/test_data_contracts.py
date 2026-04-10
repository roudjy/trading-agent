from dataclasses import FrozenInstanceError, asdict
from datetime import UTC, datetime

import pytest

from data.contracts import CanonicalBar, Instrument, MacroSeriesPoint, Provenance


def test_contracts_are_frozen():
    provenance = Provenance(
        adapter="yfinance",
        fetched_at_utc=datetime(2026, 4, 10, 10, 0, tzinfo=UTC),
        config_hash="abc123",
        source_version="0.2.55",
        cache_hit=False,
    )

    with pytest.raises(FrozenInstanceError):
        provenance.adapter = "fredapi"


def test_provenance_round_trips_through_dataclass_mapping():
    original = Provenance(
        adapter="fredapi",
        fetched_at_utc=datetime(2026, 4, 10, 10, 0, tzinfo=UTC),
        config_hash="cfg-1",
        source_version="0.5.2",
        cache_hit=True,
    )

    restored = Provenance(**asdict(original))

    assert restored == original


def test_canonical_models_hold_nested_provenance():
    provenance = Provenance(
        adapter="fixture",
        fetched_at_utc=datetime(2026, 4, 10, 10, 0, tzinfo=UTC),
        config_hash="cfg-2",
        source_version="1.0",
        cache_hit=False,
    )
    instrument = Instrument(
        id="btc-usd",
        asset_class="crypto",
        venue="yahoo",
        native_symbol="BTC-USD",
        quote_ccy="USD",
    )
    bar = CanonicalBar(
        instrument=instrument,
        interval="1h",
        timestamp_utc=datetime(2026, 4, 9, 10, 0, tzinfo=UTC),
        open=1.0,
        high=2.0,
        low=0.5,
        close=1.5,
        volume=100.0,
        provenance=provenance,
    )
    point = MacroSeriesPoint(
        series_id="CPIAUCSL",
        timestamp_utc=datetime(2026, 4, 1, 0, 0, tzinfo=UTC),
        value=320.5,
        native_frequency="monthly",
        vintage_as_of_utc=datetime(2026, 4, 10, 10, 0, tzinfo=UTC),
        provenance=provenance,
    )

    assert bar.provenance == provenance
    assert point.provenance == provenance
