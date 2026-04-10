"""Canonical data contracts for market and macro adapters."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal


@dataclass(frozen=True)
class Instrument:
    id: str
    asset_class: Literal["crypto", "equity", "prediction", "macro"]
    venue: str
    native_symbol: str
    quote_ccy: str


@dataclass(frozen=True)
class Provenance:
    adapter: str
    fetched_at_utc: datetime
    config_hash: str
    source_version: str
    cache_hit: bool


@dataclass(frozen=True)
class CanonicalBar:
    instrument: Instrument
    interval: str
    timestamp_utc: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    provenance: Provenance


@dataclass(frozen=True)
class MacroSeriesPoint:
    series_id: str
    timestamp_utc: datetime
    value: float
    native_frequency: str
    vintage_as_of_utc: datetime | None
    provenance: Provenance
