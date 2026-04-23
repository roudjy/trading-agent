"""v3.13 research-layer regime classifier.

Axis-separable, deterministic, no-lookahead regime tagging on three
independent axes:

- ``trend`` : trending / non_trending / insufficient
- ``vol``   : low_vol / high_vol / insufficient
- ``width`` : expansion / compression / insufficient

Trend and volatility tags are the same concepts produced during the
backtest by :mod:`agent.backtesting.regime` and already carried by
``regime_diagnostics_latest.v1.json``. This module does not re-derive
them — it exposes the normalization and width-axis computation the
v3.13 layer needs.

No HMM, no ML, no tuning loops, no gate search. Every threshold is an
explicit named constant. Every rolling statistic uses ``shift(1)``
discipline so bar ``t`` depends only on bars ``≤ t-1``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

import pandas as pd

from agent.backtesting.features import sma


REGIME_CLASSIFIER_VERSION = "v0.1"
REGIME_LAYER_VERSION = "v0.1"
REGIME_AXES: tuple[str, ...] = ("trend", "vol", "width")

# Width axis (Bollinger-bandwidth vs its own rolling median).
# Values are documented, not tuned.
WIDTH_WINDOW = 20
WIDTH_MEDIAN_WINDOW = 60
WIDTH_EXPANSION_RATIO = 1.10     # bandwidth >= 1.10 * median → expansion
WIDTH_COMPRESSION_RATIO = 0.90   # bandwidth <= 0.90 * median → compression


TrendTag = Literal["trending", "non_trending", "insufficient"]
VolTag = Literal["low_vol", "high_vol", "insufficient"]
WidthTag = Literal["expansion", "compression", "insufficient"]


@dataclass(frozen=True)
class RegimeTag:
    """Per-bar regime tag on three independent axes.

    ``insufficient`` is emitted when a rolling window lacks enough
    prior bars to produce a meaningful statistic, or when the upstream
    label normalization yielded ``unknown``. Consumers must treat
    ``insufficient`` as "no evidence", not as a fourth regime.
    """

    trend: TrendTag
    vol: VolTag
    width: WidthTag


# ---------------------------------------------------------------------------
# Public helpers — label normalization
# ---------------------------------------------------------------------------


_TREND_NORMALIZATION: dict[str, TrendTag] = {
    "trending": "trending",
    "non_trending": "non_trending",
}
_VOL_NORMALIZATION: dict[str, VolTag] = {
    "high_vol": "high_vol",
    "low_vol": "low_vol",
}


def normalize_trend_label(raw: Any) -> TrendTag:
    """Map an upstream trend label to the v3.13 closed set.

    Any value outside the closed set — including the upstream
    ``"unknown"`` marker — collapses to ``"insufficient"`` so the
    v3.13 layer never carries ambiguous buckets.
    """
    if isinstance(raw, str):
        return _TREND_NORMALIZATION.get(raw, "insufficient")
    return "insufficient"


def normalize_vol_label(raw: Any) -> VolTag:
    """Map an upstream volatility label to the v3.13 closed set."""
    if isinstance(raw, str):
        return _VOL_NORMALIZATION.get(raw, "insufficient")
    return "insufficient"


# ---------------------------------------------------------------------------
# Width axis — Bollinger bandwidth vs rolling median
# ---------------------------------------------------------------------------


def bollinger_bandwidth(
    close: pd.Series,
    *,
    window: int = WIDTH_WINDOW,
    num_std: float = 2.0,
) -> pd.Series:
    """Relative Bollinger bandwidth = (upper - lower) / mid.

    Uses :func:`agent.backtesting.features.sma` for the mid band and
    a population std (``ddof=0``) for the width. Returns NaN for the
    first ``window - 1`` bars (pandas rolling default).
    """
    c = close.astype(float)
    mid = sma(c, window)
    # population std here so the width value is defined on a constant
    # series (std=0 → bandwidth 0) without raising.
    std = c.rolling(window=window).std(ddof=0)
    upper = mid + num_std * std
    lower = mid - num_std * std
    safe_mid = mid.where(mid != 0.0)
    return (upper - lower) / safe_mid


def classify_width(
    close: pd.Series,
    *,
    window: int = WIDTH_WINDOW,
    median_window: int = WIDTH_MEDIAN_WINDOW,
    expansion_ratio: float = WIDTH_EXPANSION_RATIO,
    compression_ratio: float = WIDTH_COMPRESSION_RATIO,
) -> pd.Series:
    """Deterministic, no-lookahead width-axis classification.

    For bar ``t`` we compare bandwidth at ``t-1`` (strict prior-bar
    discipline) against the median of bandwidth over the preceding
    ``median_window`` bars. The ``shift(1)`` is applied to both the
    numerator and the denominator so bar ``t`` never sees its own
    bandwidth or its own contribution to the median.

    Bars without sufficient history are tagged ``"insufficient"``.
    """
    bandwidth = bollinger_bandwidth(close, window=window).shift(1)
    baseline = bandwidth.rolling(window=median_window).median()

    out = pd.Series("insufficient", index=close.index, dtype="object")
    valid = bandwidth.notna() & baseline.notna() & (baseline > 0.0)
    if not valid.any():
        return out

    ratio = bandwidth.where(valid) / baseline.where(valid)
    out.loc[valid & (ratio >= expansion_ratio)] = "expansion"
    out.loc[valid & (ratio <= compression_ratio)] = "compression"
    # values strictly inside the band stay at "insufficient" on
    # purpose — we do not introduce a third "neutral" regime in v3.13.
    return out


# ---------------------------------------------------------------------------
# Frame classification
# ---------------------------------------------------------------------------


def classify_bars(
    frame: pd.DataFrame,
    *,
    width_window: int = WIDTH_WINDOW,
    width_median_window: int = WIDTH_MEDIAN_WINDOW,
    width_expansion_ratio: float = WIDTH_EXPANSION_RATIO,
    width_compression_ratio: float = WIDTH_COMPRESSION_RATIO,
) -> pd.DataFrame:
    """Produce a per-bar width-axis tag frame for an OHLCV ``frame``.

    Only the width axis is computed here. Trend and volatility axes
    are produced inside the backtest engine (single source of truth
    in :mod:`agent.backtesting.regime`) and must be consumed from the
    existing ``regime_diagnostics_latest.v1.json`` sidecar.

    The returned frame carries a single column, ``regime_width``,
    indexed identically to ``frame``. Callers may merge this with
    trend/vol labels from the engine output.
    """
    if "close" not in frame.columns:
        raise ValueError("classify_bars: frame must contain a 'close' column")

    width = classify_width(
        frame["close"],
        window=width_window,
        median_window=width_median_window,
        expansion_ratio=width_expansion_ratio,
        compression_ratio=width_compression_ratio,
    )
    return pd.DataFrame({"regime_width": width}, index=frame.index)


def summarize_width_distribution(width_tags: pd.Series) -> dict[str, int]:
    """Return a deterministic bucket-count dict for the width axis.

    Buckets are always present in the returned dict (zero counts
    included) so sidecar key ordering is stable.
    """
    counts = {"expansion": 0, "compression": 0, "insufficient": 0}
    for value in width_tags:
        if value in counts:
            counts[value] += 1
        else:
            counts["insufficient"] += 1
    return counts


__all__ = [
    "REGIME_CLASSIFIER_VERSION",
    "REGIME_LAYER_VERSION",
    "REGIME_AXES",
    "WIDTH_WINDOW",
    "WIDTH_MEDIAN_WINDOW",
    "WIDTH_EXPANSION_RATIO",
    "WIDTH_COMPRESSION_RATIO",
    "RegimeTag",
    "normalize_trend_label",
    "normalize_vol_label",
    "bollinger_bandwidth",
    "classify_width",
    "classify_bars",
    "summarize_width_distribution",
]
