"""Repositories that isolate adapters from engine-facing consumers."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Iterable

import pandas as pd

from data.adapters.base import MarketAdapter
from data.adapters.yfinance_adapter import YFinanceMarketAdapter
from data.contracts import CanonicalBar, Instrument, Provenance


class DataUnavailableError(RuntimeError):
    """Raised when a repository cannot provide the requested data."""


@dataclass(frozen=True)
class BarsResponse:
    frame: pd.DataFrame
    provenance: Provenance


class MarketRepository:
    """Canonical market-data repository with adapter routing and parquet cache."""

    def __init__(
        self,
        adapters: dict[str, MarketAdapter] | None = None,
        cache_dir: Path | None = None,
    ) -> None:
        yfinance_adapter = YFinanceMarketAdapter()
        self._adapters = adapters or {
            "crypto": yfinance_adapter,
            "equity": yfinance_adapter,
        }
        self._cache_dir = cache_dir or Path("data/cache/market")
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    def get_bars(
        self,
        instrument: Instrument,
        interval: str,
        start_utc,
        end_utc,
    ) -> BarsResponse:
        adapter = self._resolve_adapter(instrument.asset_class)
        cache_path = self._cache_path(adapter.name, instrument.native_symbol, interval, start_utc, end_utc)

        try:
            if cache_path.exists():
                bars = self._read_cached_bars(cache_path)
            else:
                bars = adapter.fetch_bars(instrument, interval, start_utc, end_utc)
                self._write_cached_bars(cache_path, bars)
        except Exception as exc:
            raise DataUnavailableError(
                f"Unable to load data for {instrument.native_symbol} via {adapter.name}"
            ) from exc

        if not bars:
            empty = pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
            return BarsResponse(frame=empty, provenance=self._empty_provenance(adapter.name))

        frame = self._bars_to_frame(bars)
        provenance = bars[-1].provenance
        frame.attrs["provenance"] = provenance
        return BarsResponse(frame=frame, provenance=provenance)

    def _resolve_adapter(self, asset_class: str) -> MarketAdapter:
        try:
            return self._adapters[asset_class]
        except KeyError as exc:
            raise DataUnavailableError(f"No market adapter configured for asset_class={asset_class}") from exc

    def _cache_path(self, adapter: str, symbol: str, interval: str, start_utc, end_utc) -> Path:
        safe_symbol = symbol.replace("/", "-")
        key = {
            "adapter": adapter,
            "symbol": symbol,
            "interval": interval,
            "start": start_utc.isoformat(),
            "end": end_utc.isoformat(),
        }
        digest = hashlib.sha256(json.dumps(key, sort_keys=True).encode("utf-8")).hexdigest()[:16]
        filename = f"{adapter}__{safe_symbol}__{interval}__{start_utc:%Y%m%d}__{end_utc:%Y%m%d}__{digest}.parquet"
        return self._cache_dir / filename

    def _write_cached_bars(self, path: Path, bars: Iterable[CanonicalBar]) -> None:
        raw = pd.DataFrame(
            [
                {
                    "instrument_id": bar.instrument.id,
                    "asset_class": bar.instrument.asset_class,
                    "venue": bar.instrument.venue,
                    "native_symbol": bar.instrument.native_symbol,
                    "quote_ccy": bar.instrument.quote_ccy,
                    "interval": bar.interval,
                    "timestamp_utc": bar.timestamp_utc,
                    "open": bar.open,
                    "high": bar.high,
                    "low": bar.low,
                    "close": bar.close,
                    "volume": bar.volume,
                    "provenance_adapter": bar.provenance.adapter,
                    "provenance_fetched_at_utc": bar.provenance.fetched_at_utc,
                    "provenance_config_hash": bar.provenance.config_hash,
                    "provenance_source_version": bar.provenance.source_version,
                    "provenance_cache_hit": bar.provenance.cache_hit,
                }
                for bar in bars
            ]
        )
        raw.to_parquet(path, index=False)

    def _read_cached_bars(self, path: Path) -> list[CanonicalBar]:
        raw = pd.read_parquet(path)
        bars: list[CanonicalBar] = []
        for row in raw.to_dict(orient="records"):
            provenance = Provenance(
                adapter=str(row["provenance_adapter"]),
                fetched_at_utc=pd.Timestamp(row["provenance_fetched_at_utc"]).to_pydatetime(),
                config_hash=str(row["provenance_config_hash"]),
                source_version=str(row["provenance_source_version"]),
                cache_hit=bool(row["provenance_cache_hit"]),
            )
            provenance = replace(provenance, cache_hit=True)
            bars.append(
                CanonicalBar(
                    instrument=Instrument(
                        id=str(row["instrument_id"]),
                        asset_class=str(row["asset_class"]),
                        venue=str(row["venue"]),
                        native_symbol=str(row["native_symbol"]),
                        quote_ccy=str(row["quote_ccy"]),
                    ),
                    interval=str(row["interval"]),
                    timestamp_utc=pd.Timestamp(row["timestamp_utc"]).to_pydatetime(),
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row["volume"]),
                    provenance=provenance,
                )
            )
        return bars

    def _bars_to_frame(self, bars: list[CanonicalBar]) -> pd.DataFrame:
        frame = pd.DataFrame(
            {
                "open": [bar.open for bar in bars],
                "high": [bar.high for bar in bars],
                "low": [bar.low for bar in bars],
                "close": [bar.close for bar in bars],
                "volume": [bar.volume for bar in bars],
            },
            index=pd.DatetimeIndex(
                [self._engine_timestamp(bar.timestamp_utc) for bar in bars]
            ),
        )
        return frame.dropna()

    @staticmethod
    def _engine_timestamp(value) -> pd.Timestamp:
        timestamp = pd.Timestamp(value)
        if timestamp.tzinfo is None:
            return timestamp
        return timestamp.tz_convert("UTC").tz_localize(None)

    @staticmethod
    def _empty_provenance(adapter_name: str) -> Provenance:
        return Provenance(
            adapter=adapter_name,
            fetched_at_utc=pd.Timestamp.utcnow().to_pydatetime(),
            config_hash="",
            source_version="",
            cache_hit=False,
        )
