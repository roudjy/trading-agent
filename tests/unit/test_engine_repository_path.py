from datetime import UTC, datetime
from unittest.mock import MagicMock

import pandas as pd

from agent.backtesting.engine import BacktestEngine
from data.repository import BarsResponse
from data.contracts import Provenance


def test_engine_loads_data_via_market_repository(monkeypatch):
    frame = pd.DataFrame(
        {
            "open": [1.0, 2.0],
            "high": [1.1, 2.1],
            "low": [0.9, 1.9],
            "close": [1.05, 2.05],
            "volume": [10.0, 20.0],
        },
        index=pd.date_range("2026-04-01", periods=2, freq="D"),
    )
    repository = MagicMock()
    repository.get_bars.return_value = BarsResponse(
        frame=frame,
        provenance=Provenance(
            adapter="fixture",
            fetched_at_utc=datetime(2026, 4, 10, 10, 0, tzinfo=UTC),
            config_hash="cfg",
            source_version="1.0",
            cache_hit=False,
        ),
    )
    monkeypatch.setattr("agent.backtesting.engine.MarketRepository", lambda: repository)

    engine = BacktestEngine("2026-04-01", "2026-04-10")

    loaded = engine._laad_data("BTC-USD", "1d")

    assert loaded.equals(frame)
    call_kwargs = repository.get_bars.call_args.kwargs
    assert call_kwargs["instrument"].native_symbol == "BTC-USD"
    assert call_kwargs["instrument"].asset_class == "crypto"
    assert call_kwargs["interval"] == "1d"


def test_engine_returns_none_when_repository_fails(monkeypatch):
    repository = MagicMock()
    repository.get_bars.side_effect = RuntimeError("boom")
    monkeypatch.setattr("agent.backtesting.engine.MarketRepository", lambda: repository)

    engine = BacktestEngine("2026-04-01", "2026-04-10")

    assert engine._laad_data("NVDA", "1d") is None
