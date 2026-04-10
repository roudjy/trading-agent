from datetime import UTC, datetime

import pandas as pd
import pytest

from data.adapters.fred_adapter import FredMacroAdapter
from data.contracts import AdapterAuthError


class FakeFred:
    def __init__(self, api_key):
        self.api_key = api_key

    def get_series_info(self, series_id):
        return {"frequency_short": "M"}

    def get_series(self, series_id, observation_start=None, observation_end=None):
        return pd.Series(
            [100.0, 101.0],
            index=pd.to_datetime(["2026-01-01", "2026-02-01"]),
        )

    def get_series_as_of_date(self, series_id, as_of_date):
        return pd.DataFrame(
            {
                "date": pd.to_datetime(["2026-01-01", "2026-01-01", "2026-02-01"]),
                "realtime_start": pd.to_datetime(["2026-01-15", "2026-01-20", "2026-02-15"]),
                "value": [99.0, 100.0, 101.0],
            }
        )


def test_fred_adapter_reads_api_key_from_env(monkeypatch):
    monkeypatch.setenv("FRED_API_KEY", "env-key")
    monkeypatch.setattr("data.adapters.fred_adapter.Fred", FakeFred)

    adapter = FredMacroAdapter()
    points = adapter.fetch_series(
        series_id="CPIAUCSL",
        start_utc=datetime(2026, 1, 1, tzinfo=UTC),
        end_utc=datetime(2026, 3, 1, tzinfo=UTC),
        as_of_utc=None,
    )

    assert [point.value for point in points] == [100.0, 101.0]
    assert points[0].native_frequency == "m"
    assert points[0].provenance.adapter == "fredapi"


def test_fred_adapter_uses_as_of_path_and_records_vintage(monkeypatch):
    monkeypatch.setenv("FRED_API_KEY", "env-key")
    monkeypatch.setattr("data.adapters.fred_adapter.Fred", FakeFred)

    adapter = FredMacroAdapter()
    points = adapter.fetch_series(
        series_id="GDP",
        start_utc=datetime(2026, 1, 1, tzinfo=UTC),
        end_utc=datetime(2026, 3, 1, tzinfo=UTC),
        as_of_utc=datetime(2026, 3, 31, tzinfo=UTC),
    )

    assert len(points) == 2
    assert points[0].value == 100.0
    assert points[0].vintage_as_of_utc == datetime(2026, 1, 20, tzinfo=UTC)


def test_fred_adapter_raises_auth_error_when_no_credentials(monkeypatch, tmp_path):
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    monkeypatch.setattr("data.adapters.fred_adapter.FRED_SECRET_PATH", tmp_path / "missing.secret")

    adapter = FredMacroAdapter()

    with pytest.raises(AdapterAuthError):
        adapter.fetch_series(
            series_id="GDP",
            start_utc=datetime(2026, 1, 1, tzinfo=UTC),
            end_utc=datetime(2026, 3, 1, tzinfo=UTC),
            as_of_utc=None,
        )
