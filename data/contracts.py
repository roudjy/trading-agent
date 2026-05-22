"""Compatibility path for canonical QRE data contracts.

The canonical implementation lives in ``packages.qre_data.contracts``. This
module preserves the historical ``data.contracts`` public API.
"""

from __future__ import annotations

from packages.qre_data.contracts import (
    AdapterAuthError,
    CanonicalBar,
    Instrument,
    MacroSeriesPoint,
    Provenance,
)

__all__ = [
    "AdapterAuthError",
    "CanonicalBar",
    "Instrument",
    "MacroSeriesPoint",
    "Provenance",
]
