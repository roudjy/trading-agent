"""v3.14 width-axis data feed — closes v3.13 §8.1.

Builds the ``width_distributions`` dict consumed by
:mod:`research.regime_sidecars` so that the v3.13 regime
intelligence sidecar can populate a real width axis instead of an
all-``insufficient`` placeholder.

The feed is deliberately thin:

- Input = registry v2 entries (each carries ``asset``, ``interval``
  and ``candidate_id``) + a :class:`data.repository.MarketRepository`
  and a date range.
- Per unique (asset, interval) pair we request OHLCV via
  ``MarketRepository.get_bars``. This is the same call the backtest
  engine makes during its own run, so for a run that has already
  finished backtesting the cache is warm and no network request
  is issued.
- For each frame we run :func:`research.regime_classifier.classify_bars`
  and summarise the resulting width tags via
  :func:`research.regime_classifier.summarize_width_distribution`.
- The per-candidate dict is keyed by ``candidate_id``; entries that
  share an (asset, interval) pair point at the same summary.

Design constraints:

- No engine contract widening. This module imports
  :class:`MarketRepository` directly and never reaches into the
  backtest engine.
- ``DataUnavailableError`` and any other fetch error is swallowed
  per (asset, interval): the candidate gets no width entry rather
  than causing the run to fail. Downstream ``regime_sidecars``
  already degrades that case gracefully to ``insufficient``.
- Deterministic output ordering is enforced by the calling façade
  via canonical JSON; this module itself returns a plain dict.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import pandas as pd

from data.contracts import Instrument
from data.repository import DataUnavailableError, MarketRepository
from research.regime_classifier import (
    REGIME_CLASSIFIER_VERSION,
    classify_bars,
    summarize_width_distribution,
)


WIDTH_FEED_VERSION = "v0.1"


@dataclass(frozen=True)
class WidthFeedResult:
    """What the feed produced, for both sidecar and debug consumers."""

    distributions: dict[str, dict[str, int]]
    lineage: list[dict[str, Any]]


def _is_crypto_ticker(ticker: str) -> bool:
    return "-EUR" in ticker or "-USD" in ticker or "-BTC" in ticker


def _build_instrument(asset: str) -> Instrument:
    """Mirror :meth:`BacktestEngine._laad_data`'s instrument shape so
    the cache key matches the backtest's key exactly."""
    ticker = asset.replace("/", "-")
    quote_ccy = ticker.split("-")[-1] if "-" in ticker else "USD"
    return Instrument(
        id=ticker.lower(),
        asset_class="crypto" if _is_crypto_ticker(ticker) else "equity",
        venue="yahoo",
        native_symbol=ticker,
        quote_ccy=quote_ccy,
    )


def _parse_bound(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        return value
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        parsed = datetime.strptime(str(value), "%Y-%m-%d")
    return parsed


def _summarize_frame(frame: pd.DataFrame) -> dict[str, int]:
    tags = classify_bars(frame)["regime_width"]
    return summarize_width_distribution(tags)


def _registry_entries(registry_v2: dict[str, Any]) -> list[dict[str, Any]]:
    entries = registry_v2.get("entries") or []
    return [e for e in entries if isinstance(e, dict) and e.get("candidate_id")]


def build_width_distributions(
    *,
    registry_v2: dict[str, Any],
    date_range_by_interval: dict[str, tuple[str, str]],
    market_repository: MarketRepository | None = None,
) -> WidthFeedResult:
    """Produce ``width_distributions`` for every candidate in the v2 registry.

    ``date_range_by_interval`` must map each interval present in the
    registry to a ``(start_iso, end_iso)`` pair — these are the
    boundaries the backtest used, so the cache key matches.

    Returns a :class:`WidthFeedResult` carrying both the dict that
    feeds :class:`~research.regime_sidecars.RegimeSidecarBuildContext`
    and a per-source lineage list that the v3.14 façade persists as
    an adjacent overlay artifact.
    """
    repo = market_repository or MarketRepository()
    entries = _registry_entries(registry_v2)

    per_pair_summary: dict[tuple[str, str], dict[str, int]] = {}
    per_pair_lineage: dict[tuple[str, str], dict[str, Any]] = {}
    distributions: dict[str, dict[str, int]] = {}

    for entry in entries:
        asset = str(entry["asset"])
        interval = str(entry["interval"])
        candidate_id = str(entry["candidate_id"])
        pair_key = (asset, interval)

        if pair_key not in per_pair_summary:
            date_range = date_range_by_interval.get(interval)
            if not date_range:
                continue
            start_iso, end_iso = date_range
            try:
                response = repo.get_bars(
                    instrument=_build_instrument(asset),
                    interval=interval,
                    start_utc=_parse_bound(start_iso),
                    end_utc=_parse_bound(end_iso),
                )
            except DataUnavailableError:
                continue
            frame = response.frame
            if frame is None or frame.empty or "close" not in frame.columns:
                continue
            summary = _summarize_frame(frame)
            per_pair_summary[pair_key] = summary
            per_pair_lineage[pair_key] = {
                "asset": asset,
                "interval": interval,
                "start_iso": start_iso,
                "end_iso": end_iso,
                "n_bars": int(len(frame)),
                "adapter": getattr(response.provenance, "adapter", "unknown"),
                "cache_hit": bool(getattr(response.provenance, "cache_hit", False)),
                "classifier_version": REGIME_CLASSIFIER_VERSION,
                "width_feed_version": WIDTH_FEED_VERSION,
            }

        cached_summary = per_pair_summary.get(pair_key)
        if cached_summary is None:
            continue
        distributions[candidate_id] = dict(cached_summary)

    lineage = [per_pair_lineage[pair] for pair in sorted(per_pair_lineage)]
    return WidthFeedResult(distributions=distributions, lineage=lineage)


__all__ = [
    "WIDTH_FEED_VERSION",
    "WidthFeedResult",
    "build_width_distributions",
]
