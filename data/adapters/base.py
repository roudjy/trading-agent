"""Protocol definitions for market and macro data adapters."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

from data.contracts import CanonicalBar, Instrument, MacroSeriesPoint


@runtime_checkable
class MarketAdapter(Protocol):
    @property
    def name(self) -> str:
        ...

    def fetch_bars(
        self,
        instrument: Instrument,
        interval: str,
        start_utc: datetime,
        end_utc: datetime,
    ) -> list[CanonicalBar]:
        ...


@runtime_checkable
class MacroAdapter(Protocol):
    @property
    def name(self) -> str:
        ...

    def fetch_series(
        self,
        series_id: str,
        start_utc: datetime,
        end_utc: datetime,
        as_of_utc: datetime | None,
    ) -> list[MacroSeriesPoint]:
        ...
