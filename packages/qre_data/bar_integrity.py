from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd


def _parse_ts(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    text = str(value).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text).astimezone(UTC)
    except ValueError:
        return None


def _is_crypto_instrument(instrument_id: str) -> bool:
    text = str(instrument_id or "").upper()
    return any(token in text for token in ("BTC", "ETH", "SOL", "XRP", "DOGE", "ADA", "DOT"))


def _timeframe_delta(timeframe: str) -> timedelta | None:
    text = str(timeframe or "").lower()
    if text.endswith("h") and text[:-1].isdigit():
        return timedelta(hours=int(text[:-1]))
    if text.endswith("d") and text[:-1].isdigit():
        return timedelta(days=int(text[:-1]))
    return None


def _expected_bar_count(
    *,
    instrument_id: str,
    timeframe: str,
    start: datetime | None,
    end: datetime | None,
) -> int | None:
    if start is None or end is None or end < start:
        return None
    delta = _timeframe_delta(timeframe)
    if delta is None:
        return None
    is_crypto = _is_crypto_instrument(instrument_id)
    if timeframe == "1d":
        if is_crypto:
            return max((end.date() - start.date()).days + 1, 0)
        count = 0
        current = start.date()
        final = end.date()
        while current <= final:
            if current.weekday() < 5:
                count += 1
            current += timedelta(days=1)
        return count
    if is_crypto and delta.total_seconds() > 0:
        return int(((end - start).total_seconds() // delta.total_seconds()) + 1)
    return None


def _normalize_frame(frame: pd.DataFrame) -> pd.DataFrame:
    normalized = frame.copy()
    if "timestamp_utc" not in normalized.columns:
        normalized["timestamp_utc"] = pd.NaT
    normalized["timestamp_utc"] = pd.to_datetime(normalized["timestamp_utc"], utc=True, errors="coerce")
    for column in ("open", "high", "low", "close", "volume"):
        if column not in normalized.columns:
            normalized[column] = pd.NA
    return normalized[["timestamp_utc", "open", "high", "low", "close", "volume"]]


@dataclass(frozen=True, slots=True)
class UniqueBarIntegrity:
    raw_row_count: int
    unique_bar_count: int
    exact_duplicate_row_count: int
    overlapping_row_count: int
    conflicting_row_count: int
    invalid_row_count: int
    unreadable_file_count: int
    unique_timestamp_count: int
    expected_bar_count: int | None
    coverage_ratio: float | None
    impossible_bar_density: bool
    conflict_intervals: tuple[str, ...]
    canonical_frame: pd.DataFrame


def build_unique_bar_integrity(
    *,
    repo_root: Path,
    partitions: list[str],
    instrument_id: str,
    timeframe: str,
    start: str | None,
    end: str | None,
) -> UniqueBarIntegrity:
    frames: list[pd.DataFrame] = []
    raw_row_count = 0
    invalid_row_count = 0
    unreadable_file_count = 0
    for rel_path in partitions:
        path = repo_root / rel_path
        if not path.is_file():
            continue
        try:
            frame = pd.read_parquet(path)
        except Exception:
            unreadable_file_count += 1
            continue
        normalized = _normalize_frame(frame)
        raw_row_count += int(len(normalized))
        invalid_row_count += int(normalized["timestamp_utc"].isna().sum())
        frames.append(normalized.dropna(subset=["timestamp_utc"]))
    if not frames:
        return UniqueBarIntegrity(
            raw_row_count=0,
            unique_bar_count=0,
            exact_duplicate_row_count=0,
            overlapping_row_count=0,
            conflicting_row_count=0,
            invalid_row_count=0,
            unreadable_file_count=unreadable_file_count,
            unique_timestamp_count=0,
            expected_bar_count=None,
            coverage_ratio=None,
            impossible_bar_density=False,
            conflict_intervals=(),
            canonical_frame=pd.DataFrame(columns=["timestamp_utc", "open", "high", "low", "close", "volume"]),
        )

    combined = pd.concat(frames, ignore_index=True)
    combined = combined.sort_values("timestamp_utc").reset_index(drop=True)
    grouped: dict[pd.Timestamp, list[tuple[Any, Any, Any, Any, Any]]] = defaultdict(list)
    for row in combined.itertuples(index=False):
        grouped[row.timestamp_utc].append((row.open, row.high, row.low, row.close, row.volume))

    canonical_rows: list[dict[str, Any]] = []
    exact_duplicates = 0
    overlaps = 0
    conflicts = 0
    conflict_intervals: list[str] = []
    for ts, rows in sorted(grouped.items(), key=lambda item: item[0]):
        unique_values = []
        for values in rows:
            if values not in unique_values:
                unique_values.append(values)
        if len(rows) > 1:
            overlaps += len(rows) - 1
        if len(unique_values) == 1:
            exact_duplicates += max(len(rows) - 1, 0)
            open_, high, low, close, volume = unique_values[0]
            canonical_rows.append(
                {
                    "timestamp_utc": ts,
                    "open": open_,
                    "high": high,
                    "low": low,
                    "close": close,
                    "volume": volume,
                }
            )
            continue
        conflicts += 1
        conflict_intervals.append(ts.isoformat().replace("+00:00", "Z"))

    canonical_frame = pd.DataFrame(canonical_rows)
    if not canonical_frame.empty:
        canonical_frame = canonical_frame.sort_values("timestamp_utc").reset_index(drop=True)
    unique_count = int(len(canonical_frame))
    unique_timestamps = int(combined["timestamp_utc"].nunique())
    expected = _expected_bar_count(
        instrument_id=instrument_id,
        timeframe=timeframe,
        start=_parse_ts(start),
        end=_parse_ts(end),
    )
    impossible = expected is not None and unique_count > expected
    coverage_ratio = None if expected in {None, 0} else round(unique_count / expected, 6)
    return UniqueBarIntegrity(
        raw_row_count=raw_row_count,
        unique_bar_count=unique_count,
        exact_duplicate_row_count=exact_duplicates,
        overlapping_row_count=overlaps,
        conflicting_row_count=conflicts,
        invalid_row_count=invalid_row_count,
        unreadable_file_count=unreadable_file_count,
        unique_timestamp_count=unique_timestamps,
        expected_bar_count=expected,
        coverage_ratio=coverage_ratio,
        impossible_bar_density=impossible,
        conflict_intervals=tuple(conflict_intervals),
        canonical_frame=canonical_frame,
    )
