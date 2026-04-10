"""fredapi-backed macro data adapter."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
from fredapi import Fred, __version__ as fredapi_version

from data.adapters.base import MacroAdapter
from data.contracts import AdapterAuthError, MacroSeriesPoint, Provenance

FRED_SECRET_PATH = Path("state/fred.secret")


class FredMacroAdapter(MacroAdapter):
    @property
    def name(self) -> str:
        return "fredapi"

    def fetch_series(
        self,
        series_id: str,
        start_utc: datetime,
        end_utc: datetime,
        as_of_utc: datetime | None,
    ) -> list[MacroSeriesPoint]:
        fred = Fred(api_key=self._resolve_api_key())
        info = fred.get_series_info(series_id)
        native_frequency = str(info.get("frequency_short") or info.get("frequency") or "").lower()
        provenance = Provenance(
            adapter=self.name,
            fetched_at_utc=datetime.now(UTC),
            config_hash=self._config_hash(series_id, start_utc, end_utc, as_of_utc),
            source_version=fredapi_version,
            cache_hit=False,
        )

        if as_of_utc is None:
            series = fred.get_series(
                series_id,
                observation_start=start_utc.strftime("%Y-%m-%d"),
                observation_end=end_utc.strftime("%Y-%m-%d"),
            )
            return [
                MacroSeriesPoint(
                    series_id=series_id,
                    timestamp_utc=self._timestamp_utc(timestamp),
                    value=float(value),
                    native_frequency=native_frequency,
                    vintage_as_of_utc=None,
                    provenance=provenance,
                )
                for timestamp, value in series.dropna().items()
            ]

        vintage_frame = fred.get_series_as_of_date(series_id, as_of_utc.strftime("%Y-%m-%d"))
        if vintage_frame is None or vintage_frame.empty:
            return []

        vintage_frame = vintage_frame.copy()
        vintage_frame["date"] = pd.to_datetime(vintage_frame["date"])
        vintage_frame["realtime_start"] = pd.to_datetime(vintage_frame["realtime_start"])
        vintage_frame = vintage_frame.sort_values(["date", "realtime_start"]).groupby("date", as_index=False).tail(1)
        vintage_frame = vintage_frame[
            (vintage_frame["date"] >= pd.Timestamp(start_utc.replace(tzinfo=None)))
            & (vintage_frame["date"] <= pd.Timestamp(end_utc.replace(tzinfo=None)))
        ]

        points: list[MacroSeriesPoint] = []
        for row in vintage_frame.to_dict(orient="records"):
            points.append(
                MacroSeriesPoint(
                    series_id=series_id,
                    timestamp_utc=self._timestamp_utc(row["date"]),
                    value=float(row["value"]),
                    native_frequency=native_frequency,
                    vintage_as_of_utc=self._timestamp_utc(row["realtime_start"]),
                    provenance=provenance,
                )
            )
        return points

    @staticmethod
    def _resolve_api_key() -> str:
        api_key = os.environ.get("FRED_API_KEY")
        if api_key:
            return api_key.strip()

        if FRED_SECRET_PATH.exists():
            return FRED_SECRET_PATH.read_text(encoding="utf-8").strip()

        raise AdapterAuthError("FRED API key not found in FRED_API_KEY or state/fred.secret")

    @staticmethod
    def _config_hash(
        series_id: str,
        start_utc: datetime,
        end_utc: datetime,
        as_of_utc: datetime | None,
    ) -> str:
        payload = {
            "series_id": series_id,
            "start": start_utc.astimezone(UTC).isoformat(),
            "end": end_utc.astimezone(UTC).isoformat(),
            "as_of": as_of_utc.astimezone(UTC).isoformat() if as_of_utc else None,
        }
        encoded = json.dumps(payload, sort_keys=True).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    @staticmethod
    def _timestamp_utc(value: object) -> datetime:
        timestamp = pd.Timestamp(value)
        if timestamp.tzinfo is None:
            timestamp = timestamp.tz_localize(UTC)
        else:
            timestamp = timestamp.tz_convert(UTC)
        return timestamp.to_pydatetime()
