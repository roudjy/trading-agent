"""Injectable wall-clock for observability.

Per the v3.15.15.2 audit hardening: ``datetime.now()`` is NOT called
directly inside any aggregation module. Instead, every public entry
point accepts a ``now_utc`` parameter, defaulting to
``default_now_utc()`` when None. Tests inject a frozen ``datetime``
to assert byte-identical output.

This module imports only stdlib (``datetime``, ``typing``).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Callable

NowProvider = Callable[[], datetime]


def default_now_utc() -> datetime:
    """Return a timezone-aware UTC ``datetime`` for the current wall clock.

    The single sanctioned call to ``datetime.now`` in the observability
    package. Every other module accepts ``now_utc`` (or ``now_provider``)
    to allow injection.
    """
    return datetime.now(UTC)


def to_iso_z(dt: datetime) -> str:
    """Render a ``datetime`` as an ISO-8601 ``Z``-suffixed UTC string.

    Always produces second-precision output ending in ``Z`` for stable
    string formatting across artifact diffs.
    """
    if dt.tzinfo is None:
        raise ValueError("naive datetime not supported")
    iso = dt.astimezone(UTC).isoformat(timespec="seconds")
    if iso.endswith("+00:00"):
        iso = iso[:-6] + "Z"
    return iso


__all__ = ["NowProvider", "default_now_utc", "to_iso_z"]
