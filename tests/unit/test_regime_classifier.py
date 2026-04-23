"""Unit tests for research.regime_classifier (v3.13)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from research.regime_classifier import (
    REGIME_AXES,
    REGIME_CLASSIFIER_VERSION,
    REGIME_LAYER_VERSION,
    RegimeTag,
    bollinger_bandwidth,
    classify_bars,
    classify_width,
    normalize_trend_label,
    normalize_vol_label,
    summarize_width_distribution,
)


def _synthetic_expansion_frame(n: int = 200, seed: int = 42) -> pd.DataFrame:
    """Low-vol then high-vol regime: constant price, then widening shocks."""
    rng = np.random.default_rng(seed)
    low = np.full(n // 2, 100.0)
    shocks = rng.normal(loc=0.0, scale=5.0, size=n - n // 2)
    high = 100.0 + np.cumsum(shocks)
    close = np.concatenate([low, high])
    return pd.DataFrame({"close": close})


def _synthetic_compression_frame(n: int = 200) -> pd.DataFrame:
    """High-vol then low-vol: volatile start, quiet-but-non-zero tail.

    The tail keeps a small amount of noise so the Bollinger bandwidth
    remains strictly positive and the rolling-median baseline does
    not collapse to zero (which would mark every bar insufficient).
    """
    rng = np.random.default_rng(17)
    shocks = rng.normal(loc=0.0, scale=5.0, size=n // 2)
    high = 100.0 + np.cumsum(shocks)
    quiet_shocks = rng.normal(loc=0.0, scale=0.05, size=n - n // 2)
    low = high[-1] + np.cumsum(quiet_shocks)
    close = np.concatenate([high, low])
    return pd.DataFrame({"close": close})


def _constant_frame(n: int = 200) -> pd.DataFrame:
    return pd.DataFrame({"close": np.full(n, 100.0)})


def test_version_strings_are_semver_like() -> None:
    assert REGIME_CLASSIFIER_VERSION.startswith("v")
    assert REGIME_LAYER_VERSION.startswith("v")
    assert REGIME_AXES == ("trend", "vol", "width")


def test_regime_tag_literals_are_closed_set() -> None:
    tag = RegimeTag(trend="trending", vol="low_vol", width="expansion")
    assert tag.trend == "trending"
    assert tag.vol == "low_vol"
    assert tag.width == "expansion"


def test_normalize_trend_label_maps_unknown_to_insufficient() -> None:
    assert normalize_trend_label("trending") == "trending"
    assert normalize_trend_label("non_trending") == "non_trending"
    assert normalize_trend_label("unknown") == "insufficient"
    assert normalize_trend_label(None) == "insufficient"
    assert normalize_trend_label(42) == "insufficient"


def test_normalize_vol_label_maps_unknown_to_insufficient() -> None:
    assert normalize_vol_label("high_vol") == "high_vol"
    assert normalize_vol_label("low_vol") == "low_vol"
    assert normalize_vol_label("unknown") == "insufficient"
    assert normalize_vol_label(None) == "insufficient"


def test_bollinger_bandwidth_is_deterministic() -> None:
    frame = _synthetic_expansion_frame()
    a = bollinger_bandwidth(frame["close"])
    b = bollinger_bandwidth(frame["close"])
    assert (a.fillna(-1).values == b.fillna(-1).values).all()


def test_bollinger_bandwidth_is_zero_on_constant_series() -> None:
    frame = _constant_frame()
    bw = bollinger_bandwidth(frame["close"])
    # after the warmup window every value must be 0 (no dispersion)
    non_nan = bw.dropna()
    assert (non_nan.abs() <= 1e-12).all()


def test_classify_width_is_no_lookahead() -> None:
    """Truncating the tail must not change earlier tags."""
    frame = _synthetic_expansion_frame()
    full = classify_width(frame["close"])
    truncated = classify_width(frame["close"].iloc[:150])
    common_index = truncated.index
    assert (full.loc[common_index].values == truncated.values).all()


def test_classify_width_marks_insufficient_on_short_series() -> None:
    short = pd.Series([100.0] * 10)
    tags = classify_width(short)
    assert set(tags.unique()).issubset({"insufficient", "expansion", "compression"})
    # short series — all must be insufficient
    assert (tags == "insufficient").all()


def test_classify_width_flags_expansion_on_widening_vol() -> None:
    frame = _synthetic_expansion_frame(n=400)
    tags = classify_width(frame["close"])
    # at least one bar should be tagged expansion in the high-vol tail
    tail_tags = tags.iloc[250:].value_counts()
    assert tail_tags.get("expansion", 0) >= 1


def test_classify_width_flags_compression_on_narrowing_vol() -> None:
    frame = _synthetic_compression_frame(n=400)
    tags = classify_width(frame["close"])
    # the flat tail must produce at least one compression tag once the
    # rolling median falls behind bandwidth
    tail_tags = tags.iloc[250:].value_counts()
    assert tail_tags.get("compression", 0) >= 1


def test_classify_bars_returns_frame_with_width_column() -> None:
    frame = _synthetic_expansion_frame()
    out = classify_bars(frame)
    assert list(out.columns) == ["regime_width"]
    assert len(out) == len(frame)


def test_classify_bars_is_deterministic() -> None:
    frame = _synthetic_expansion_frame()
    a = classify_bars(frame)
    b = classify_bars(frame)
    assert (a["regime_width"].values == b["regime_width"].values).all()


def test_summarize_width_distribution_includes_all_buckets() -> None:
    tags = pd.Series(["expansion", "compression", "compression", "insufficient"])
    dist = summarize_width_distribution(tags)
    assert dist == {"expansion": 1, "compression": 2, "insufficient": 1}


def test_summarize_width_distribution_collapses_unknown_to_insufficient() -> None:
    tags = pd.Series(["expansion", "totally_unknown", None])
    dist = summarize_width_distribution(tags)
    assert dist["expansion"] == 1
    assert dist["insufficient"] == 2
    assert dist["compression"] == 0
