"""Multi-asset loader for v3.6 pairs baseline.

Loads two symbols via the existing MarketRepository and inner-joins them
on DatetimeIndex. Alignment is idempotent under truncation: aligning on
[t0..tN] then slicing to [t0..tK] equals aligning on [t0..tK] directly.
This invariant is the fold-safety guarantee for multi-asset features.

Scope (v3.6):
- Exactly two legs (N=2). No triplets or portfolios.
- Same asset class only (reject crypto x equity).
- Daily/weekly intervals only (intraday DST/session handling deferred).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Mapping

import pandas as pd

from data.contracts import Instrument
from data.repository import DataUnavailableError, MarketRepository


AssetClass = Literal["crypto", "equity"]


class MultiAssetLoaderError(RuntimeError):
    """Base error for multi-asset loader failures."""


class EmptyIntersectionError(MultiAssetLoaderError):
    """Raised when primary and reference share no common timestamps."""


class MixedAssetClassError(MultiAssetLoaderError):
    """Raised when a pair mixes asset classes (e.g. crypto x equity)."""


class LegUnavailableError(MultiAssetLoaderError):
    """Raised when either leg returns no data."""


@dataclass(frozen=True)
class AlignedPairFrame:
    """Two inner-joined OHLCV frames sharing a DatetimeIndex."""

    primary: pd.DataFrame
    reference: pd.DataFrame
    primary_symbol: str
    reference_symbol: str
    interval: str
    asset_class: AssetClass
    provenance: Mapping[str, Any]

    def __post_init__(self) -> None:
        if not self.primary.index.equals(self.reference.index):
            raise MultiAssetLoaderError(
                "AlignedPairFrame primary and reference indexes must match"
            )


def _resolve_asset_class(symbol: str) -> AssetClass:
    ticker = symbol.replace("/", "-")
    if "-EUR" in ticker or "-USD" in ticker or "-BTC" in ticker:
        return "crypto"
    return "equity"


def _build_instrument(symbol: str, asset_class: AssetClass) -> Instrument:
    ticker = symbol.replace("/", "-")
    quote_ccy = ticker.split("-")[-1] if "-" in ticker else "USD"
    return Instrument(
        id=ticker.lower(),
        asset_class=asset_class,
        venue="yahoo",
        native_symbol=ticker,
        quote_ccy=quote_ccy,
    )


def load_aligned_pair(
    primary: str,
    reference: str,
    interval: str,
    start_utc: pd.Timestamp,
    end_utc: pd.Timestamp,
    *,
    market_repository: MarketRepository | None = None,
) -> AlignedPairFrame:
    """Load two symbols and inner-join on DatetimeIndex.

    Determinism: given identical inputs and cached data, produces
    byte-identical frames. Alignment is idempotent under truncation.
    """
    primary_class = _resolve_asset_class(primary)
    reference_class = _resolve_asset_class(reference)
    if primary_class != reference_class:
        raise MixedAssetClassError(
            f"Mixed asset class not supported in v3.6: "
            f"{primary} ({primary_class}) / {reference} ({reference_class})"
        )

    repo = market_repository or MarketRepository()

    try:
        primary_response = repo.get_bars(
            instrument=_build_instrument(primary, primary_class),
            interval=interval,
            start_utc=start_utc,
            end_utc=end_utc,
        )
        reference_response = repo.get_bars(
            instrument=_build_instrument(reference, reference_class),
            interval=interval,
            start_utc=start_utc,
            end_utc=end_utc,
        )
    except DataUnavailableError as exc:
        raise LegUnavailableError(str(exc)) from exc

    primary_frame = primary_response.frame
    reference_frame = reference_response.frame

    if primary_frame.empty:
        raise LegUnavailableError(f"Primary leg returned no data: {primary}")
    if reference_frame.empty:
        raise LegUnavailableError(f"Reference leg returned no data: {reference}")

    shared_index = primary_frame.index.intersection(reference_frame.index)
    if len(shared_index) == 0:
        raise EmptyIntersectionError(
            f"No overlapping timestamps between {primary} and {reference} "
            f"over {start_utc} .. {end_utc} at interval {interval}"
        )

    aligned_primary = primary_frame.loc[shared_index].copy()
    aligned_reference = reference_frame.loc[shared_index].copy()

    provenance: dict[str, Any] = {
        "primary": primary_response.provenance,
        "reference": reference_response.provenance,
        "interval": interval,
        "start_utc": pd.Timestamp(start_utc).isoformat(),
        "end_utc": pd.Timestamp(end_utc).isoformat(),
        "aligned_bar_count": len(shared_index),
    }

    return AlignedPairFrame(
        primary=aligned_primary,
        reference=aligned_reference,
        primary_symbol=primary,
        reference_symbol=reference,
        interval=interval,
        asset_class=primary_class,
        provenance=provenance,
    )
