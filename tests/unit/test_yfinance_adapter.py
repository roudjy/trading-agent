from datetime import UTC, datetime

import pandas as pd

from data.adapters.yfinance_adapter import YFinanceMarketAdapter
from data.contracts import Instrument


def test_yfinance_adapter_returns_canonical_bars(monkeypatch):
    index = pd.to_datetime(["2026-04-09 00:00:00", "2026-04-10 00:00:00"])
    frame = pd.DataFrame(
        {
            "Open": [100.0, 101.0],
            "High": [110.0, 111.0],
            "Low": [90.0, 91.0],
            "Close": [105.0, 106.0],
            "Volume": [1000.0, 1200.0],
        },
        index=index,
    )
    captured: dict[str, object] = {}

    def fake_download(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return frame

    monkeypatch.setattr("data.adapters.yfinance_adapter.yf.download", fake_download)
    monkeypatch.setattr("data.adapters.yfinance_adapter.yf.__version__", "9.9.9", raising=False)

    adapter = YFinanceMarketAdapter()
    instrument = Instrument(
        id="btc-usd",
        asset_class="crypto",
        venue="yahoo",
        native_symbol="BTC-USD",
        quote_ccy="USD",
    )

    bars = adapter.fetch_bars(
        instrument=instrument,
        interval="1d",
        start_utc=datetime(2026, 4, 1, tzinfo=UTC),
        end_utc=datetime(2026, 4, 11, tzinfo=UTC),
    )

    assert captured["args"] == ("BTC-USD",)
    assert captured["kwargs"] == {
        "start": "2026-04-01",
        "end": "2026-04-11",
        "interval": "1d",
        "auto_adjust": True,
        "progress": False,
        "multi_level_index": False,
    }
    assert len(bars) == 2
    assert bars[0].open == 100.0
    assert bars[0].timestamp_utc == datetime(2026, 4, 9, 0, 0, tzinfo=UTC)
    assert bars[0].provenance.adapter == "yfinance"
    assert bars[0].provenance.source_version == "9.9.9"


def test_yfinance_adapter_filters_zero_volume_for_equities(monkeypatch):
    frame = pd.DataFrame(
        {
            "Open": [10.0, 20.0],
            "High": [11.0, 21.0],
            "Low": [9.0, 19.0],
            "Close": [10.5, 20.5],
            "Volume": [0.0, 100.0],
        },
        index=pd.to_datetime(["2026-04-09", "2026-04-10"]),
    )

    monkeypatch.setattr("data.adapters.yfinance_adapter.yf.download", lambda *args, **kwargs: frame)

    adapter = YFinanceMarketAdapter()
    instrument = Instrument(
        id="nvda-usd",
        asset_class="equity",
        venue="yahoo",
        native_symbol="NVDA",
        quote_ccy="USD",
    )

    bars = adapter.fetch_bars(
        instrument=instrument,
        interval="1d",
        start_utc=datetime(2026, 4, 1, tzinfo=UTC),
        end_utc=datetime(2026, 4, 11, tzinfo=UTC),
    )

    assert len(bars) == 1
    assert bars[0].close == 20.5
