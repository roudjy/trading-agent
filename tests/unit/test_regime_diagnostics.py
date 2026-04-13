from datetime import UTC

import numpy as np
import pandas as pd

from agent.backtesting.regime import (
    HIGH_VOL,
    LOW_VOL,
    NON_TRENDING,
    TRENDING,
    UNKNOWN,
    build_regime_frame,
    normalize_regime_config,
)


def _frame(closes: list[float]) -> pd.DataFrame:
    index = pd.date_range("2026-01-01", periods=len(closes), freq="D", tz=UTC)
    return pd.DataFrame({"close": closes}, index=index)


def test_build_regime_frame_is_deterministic_for_same_input_and_config():
    frame = _frame([100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110])
    config = {
        "trend_lookback_bars": 3,
        "volatility_lookback_bars": 3,
        "volatility_baseline_lookback_bars": 3,
        "trend_strength_threshold": 0.5,
        "high_vol_ratio_threshold": 1.5,
    }

    first = build_regime_frame(frame, config)
    second = build_regime_frame(frame, config)

    pd.testing.assert_frame_equal(first, second)


def test_regime_labels_do_not_change_when_future_shock_is_appended():
    base = [100, 101, 102, 103, 104, 105, 106, 107]
    shocked = base + [80, 81, 82]
    config = {
        "trend_lookback_bars": 3,
        "volatility_lookback_bars": 3,
        "volatility_baseline_lookback_bars": 3,
        "trend_strength_threshold": 0.5,
        "high_vol_ratio_threshold": 1.5,
    }

    truncated = build_regime_frame(_frame(base), config)
    full = build_regime_frame(_frame(shocked), config).iloc[: len(base)]

    pd.testing.assert_series_equal(
        truncated["combined_regime"],
        full["combined_regime"],
        check_names=False,
    )


def test_flat_market_becomes_non_trending_low_vol_after_enough_history():
    frame = _frame([100.0] * 12)
    config = {
        "trend_lookback_bars": 3,
        "volatility_lookback_bars": 3,
        "volatility_baseline_lookback_bars": 3,
        "trend_strength_threshold": 0.5,
        "high_vol_ratio_threshold": 1.5,
    }

    result = build_regime_frame(frame, config)

    assert result["trend_regime"].iloc[0] == UNKNOWN
    assert result["volatility_regime"].iloc[-1] == LOW_VOL
    assert result["trend_regime"].iloc[-1] == NON_TRENDING


def test_monotonic_uptrend_and_downtrend_are_labeled_trending():
    config = {
        "trend_lookback_bars": 3,
        "volatility_lookback_bars": 3,
        "volatility_baseline_lookback_bars": 3,
        "trend_strength_threshold": 0.5,
        "high_vol_ratio_threshold": 1.5,
    }

    up = build_regime_frame(_frame([100, 102, 104, 106, 108, 110, 112]), config)
    down = build_regime_frame(_frame([112, 110, 108, 106, 104, 102, 100]), config)

    assert up["trend_regime"].iloc[-1] == TRENDING
    assert down["trend_regime"].iloc[-1] == TRENDING


def test_volatility_shock_is_labeled_high_vol_when_baseline_exists():
    closes = [100, 100.5, 101, 101.5, 102, 102.5, 103, 120, 90, 121, 89]
    result = build_regime_frame(
        _frame(closes),
        {
            "trend_lookback_bars": 3,
            "volatility_lookback_bars": 3,
            "volatility_baseline_lookback_bars": 3,
            "trend_strength_threshold": 0.5,
            "high_vol_ratio_threshold": 1.2,
        },
    )

    assert HIGH_VOL in set(result["volatility_regime"].iloc[-3:])


def test_missing_data_and_short_series_remain_unknown_without_crashing():
    closes = [100, np.nan, 101, 102]
    result = build_regime_frame(_frame(closes), None)

    assert all(label == UNKNOWN for label in result["combined_regime"])


def test_normalize_regime_config_rejects_non_positive_values():
    try:
        normalize_regime_config({"trend_lookback_bars": 0})
    except ValueError as exc:
        assert "trend_lookback_bars" in str(exc)
    else:
        raise AssertionError("Expected ValueError for non-positive lookback")
