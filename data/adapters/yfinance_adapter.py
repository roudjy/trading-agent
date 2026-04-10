"""yfinance-backed market adapter."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

import pandas as pd
import yfinance as yf

from data.adapters.base import MarketAdapter
from data.contracts import CanonicalBar, Instrument, Provenance


class YFinanceMarketAdapter(MarketAdapter):
    @property
    def name(self) -> str:
        return "yfinance"

    def fetch_bars(
        self,
        instrument: Instrument,
        interval: str,
        start_utc: datetime,
        end_utc: datetime,
    ) -> list[CanonicalBar]:
        ticker = instrument.native_symbol.replace("/", "-")
        df = yf.download(
            ticker,
            start=start_utc.strftime("%Y-%m-%d"),
            end=end_utc.strftime("%Y-%m-%d"),
            interval=interval,
            auto_adjust=True,
            progress=False,
            multi_level_index=False,
        )
        if df is None or df.empty:
            return []

        df.columns = [str(column).lower() for column in df.columns]
        is_crypto = "-EUR" in ticker or "-USD" in ticker or "-BTC" in ticker
        if not is_crypto:
            df = df[df["volume"] > 0]
        df = df.dropna()

        provenance = Provenance(
            adapter=self.name,
            fetched_at_utc=datetime.now(UTC),
            config_hash=self._config_hash(ticker, interval, start_utc, end_utc),
            source_version=getattr(yf, "__version__", "unknown"),
            cache_hit=False,
        )

        bars: list[CanonicalBar] = []
        for timestamp, row in df.iterrows():
            bars.append(
                CanonicalBar(
                    instrument=instrument,
                    interval=interval,
                    timestamp_utc=self._timestamp_utc(timestamp),
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row["volume"]),
                    provenance=provenance,
                )
            )
        return bars

    @staticmethod
    def _config_hash(ticker: str, interval: str, start_utc: datetime, end_utc: datetime) -> str:
        payload = {
            "ticker": ticker,
            "interval": interval,
            "start": start_utc.astimezone(UTC).isoformat(),
            "end": end_utc.astimezone(UTC).isoformat(),
            "auto_adjust": True,
            "progress": False,
            "multi_level_index": False,
        }
        encoded = json.dumps(payload, sort_keys=True).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    @staticmethod
    def _timestamp_utc(timestamp: object) -> datetime:
        ts = pd.Timestamp(timestamp)
        if ts.tzinfo is None:
            ts = ts.tz_localize(UTC)
        else:
            ts = ts.tz_convert(UTC)
        return ts.to_pydatetime()
