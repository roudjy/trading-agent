from datetime import UTC, datetime

import pytest

from data.contracts import MacroSeriesPoint, Provenance
from data.repository import DataUnavailableError, MacroRepository


class FixtureMacroAdapter:
    @property
    def name(self) -> str:
        return "fredapi"

    def fetch_series(self, series_id, start_utc, end_utc, as_of_utc):
        provenance = Provenance(
            adapter=self.name,
            fetched_at_utc=datetime(2026, 4, 10, 10, 0, tzinfo=UTC),
            config_hash="cfg-1",
            source_version="0.5.2",
            cache_hit=False,
        )
        return [
            MacroSeriesPoint(
                series_id=series_id,
                timestamp_utc=datetime(2026, 1, 1, tzinfo=UTC),
                value=100.0,
                native_frequency="m",
                vintage_as_of_utc=datetime(2026, 1, 20, tzinfo=UTC),
                provenance=provenance,
            )
        ]


class FailingMacroAdapter:
    @property
    def name(self) -> str:
        return "fredapi"

    def fetch_series(self, series_id, start_utc, end_utc, as_of_utc):
        raise RuntimeError("boom")


def test_macro_repository_returns_cached_series_points(tmp_path):
    repository = MacroRepository(
        adapters={"fred": FixtureMacroAdapter()},
        cache_dir=tmp_path / "macro-cache",
    )

    first = repository.get_series(
        series_id="GDP",
        start_utc=datetime(2026, 1, 1, tzinfo=UTC),
        end_utc=datetime(2026, 3, 1, tzinfo=UTC),
        as_of_utc=datetime(2026, 3, 31, tzinfo=UTC),
    )
    second = MacroRepository(
        adapters={"fred": FailingMacroAdapter()},
        cache_dir=tmp_path / "macro-cache",
    ).get_series(
        series_id="GDP",
        start_utc=datetime(2026, 1, 1, tzinfo=UTC),
        end_utc=datetime(2026, 3, 1, tzinfo=UTC),
        as_of_utc=datetime(2026, 3, 31, tzinfo=UTC),
    )

    assert len(first.points) == 1
    assert second.points[0].value == 100.0
    assert second.points[0].provenance.cache_hit is True


def test_macro_repository_raises_data_unavailable_on_adapter_failure(tmp_path):
    repository = MacroRepository(
        adapters={"fred": FailingMacroAdapter()},
        cache_dir=tmp_path / "macro-cache",
    )

    with pytest.raises(DataUnavailableError):
        repository.get_series(
            series_id="GDP",
            start_utc=datetime(2026, 1, 1, tzinfo=UTC),
            end_utc=datetime(2026, 3, 1, tzinfo=UTC),
            as_of_utc=None,
        )
