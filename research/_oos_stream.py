"""Shared validator for the engine-emitted OOS daily return stream.

Extracted in v3.15 so ``portfolio_reporting`` and the new
``candidate_timestamped_returns_feed`` / ``paper_divergence``
modules use one implementation. Behaviour is byte-identical to
the pre-extraction ``portfolio_reporting._normalize_stream``.

Error codes (stable, consumed downstream):

- ``missing_oos_daily_return_stream`` — input is not a non-empty list.
- ``malformed_oos_daily_return_stream`` — a point is not a dict, or
  lacks a ``timestamp_utc: str`` + ``return: int|float`` pair.
- ``duplicate_timestamp_in_oos_daily_return_stream`` — the same
  ``timestamp_utc`` appears more than once.

Output is sorted ascending by ``timestamp_utc`` and carries only
the ``timestamp_utc`` and ``return`` keys, floats coerced.
"""

from __future__ import annotations

from typing import Any


ERROR_MISSING: str = "missing_oos_daily_return_stream"
ERROR_MALFORMED: str = "malformed_oos_daily_return_stream"
ERROR_DUPLICATE: str = "duplicate_timestamp_in_oos_daily_return_stream"


def normalize_oos_daily_return_stream(
    raw_stream: Any,
) -> tuple[list[dict[str, Any]], str | None]:
    """Validate + normalize an OOS daily return stream.

    Returns ``(stream, error_code)``. When an error code is returned
    the stream is always empty. When the stream is non-empty the
    error code is ``None``.
    """
    if not isinstance(raw_stream, list) or not raw_stream:
        return [], ERROR_MISSING

    stream: list[dict[str, Any]] = []
    seen_timestamps: set[str] = set()
    for point in raw_stream:
        if not isinstance(point, dict):
            return [], ERROR_MALFORMED
        timestamp = point.get("timestamp_utc")
        value = point.get("return")
        if not isinstance(timestamp, str) or not isinstance(value, (int, float)):
            return [], ERROR_MALFORMED
        if timestamp in seen_timestamps:
            return [], ERROR_DUPLICATE
        seen_timestamps.add(timestamp)
        stream.append({
            "timestamp_utc": timestamp,
            "return": float(value),
        })

    stream.sort(key=lambda item: item["timestamp_utc"])
    return stream, None


__all__ = [
    "ERROR_MISSING",
    "ERROR_MALFORMED",
    "ERROR_DUPLICATE",
    "normalize_oos_daily_return_stream",
]
