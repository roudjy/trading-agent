"""Unit tests for v3.6 multi-asset feature resolution.

Covers:
- FeatureRequirement.source_role default None is byte-identical to v3.5
- build_features_for_multi with only primary frame matches build_features_for
- build_features_for_multi with primary + reference matches legacy single-frame
  resolution on a combined frame (the bytewise pin path)
- source_role="reference" routes to the reference frame
- Missing reference raises a typed KeyError
- Missing 'primary' key raises a typed KeyError
- Engine _invoke_strategy threads reference_frame correctly
"""

from __future__ import annotations

import pandas as pd
import pytest

from agent.backtesting.strategies import pairs_zscore_strategie, sma_crossover_strategie
from agent.backtesting.thin_strategy import (
    FeatureRequirement,
    build_features_for,
    build_features_for_multi,
)
from tests._harness_helpers import build_ohlcv_frame, build_pairs_frame


def _sma_reqs(window: int = 10) -> list[FeatureRequirement]:
    return [FeatureRequirement(name="sma", params={"window": window}, alias="sma10")]


def _pairs_reqs(lookback: int = 30, hedge_ratio: float = 1.0) -> list[FeatureRequirement]:
    return [
        FeatureRequirement(
            name="spread_zscore",
            params={"hedge_ratio": hedge_ratio, "lookback": lookback},
            alias="z",
        )
    ]


def test_feature_requirement_default_source_role_is_none():
    req = FeatureRequirement(name="sma", params={"window": 10})
    assert req.source_role is None


def test_feature_requirement_equality_unchanged_when_source_role_default():
    """v3.5 callers construct FeatureRequirement without source_role - the new
    default None must equal identically to unchanged v3.5 behaviour.
    The dataclass is frozen but not hashable (params is a dict), same as v3.5.
    """
    a = FeatureRequirement(name="sma", params={"window": 10}, alias="x")
    b = FeatureRequirement(name="sma", params={"window": 10}, alias="x")
    assert a == b
    assert a.source_role is None
    assert b.source_role is None


def test_build_features_for_multi_primary_only_matches_single_frame():
    frame = build_ohlcv_frame(length=50, seed=7)
    reqs = _sma_reqs(window=10)

    single = build_features_for(reqs, frame)
    multi = build_features_for_multi(reqs, {"primary": frame})

    assert set(single) == set(multi)
    pd.testing.assert_series_equal(single["sma10"], multi["sma10"])


def test_build_features_for_multi_pairs_matches_combined_frame():
    """Multi-frame resolution of pairs features is byte-identical to
    single-frame resolution on a combined (close + close_ref) frame.
    This is the parity pin that protects the Tier 1 bytewise pairs test.
    """
    length = 260
    seed = 37
    pairs_frame = build_pairs_frame(length=length, seed=seed)

    primary = pd.DataFrame(
        {"close": pairs_frame["close"].astype(float)},
        index=pairs_frame.index.copy(),
    )
    reference = pd.DataFrame(
        {"close": pairs_frame["close_ref"].astype(float)},
        index=pairs_frame.index.copy(),
    )

    reqs = _pairs_reqs(lookback=30, hedge_ratio=1.0)

    legacy = build_features_for(reqs, pairs_frame)
    multi = build_features_for_multi(
        reqs, {"primary": primary, "reference": reference}
    )

    pd.testing.assert_series_equal(legacy["z"], multi["z"])


def test_build_features_for_multi_routes_source_role_reference():
    length = 50
    primary = build_ohlcv_frame(length=length, seed=11)
    reference = build_ohlcv_frame(length=length, seed=13)

    reqs = [
        FeatureRequirement(
            name="sma",
            params={"window": 5},
            alias="sma_ref",
            source_role="reference",
        )
    ]

    features = build_features_for_multi(
        reqs, {"primary": primary, "reference": reference}
    )

    expected = build_features_for(
        [FeatureRequirement(name="sma", params={"window": 5}, alias="sma_ref")],
        reference,
    )
    pd.testing.assert_series_equal(features["sma_ref"], expected["sma_ref"])


def test_build_features_for_multi_source_role_reference_without_reference_raises():
    frame = build_ohlcv_frame(length=30, seed=7)
    reqs = [
        FeatureRequirement(
            name="sma",
            params={"window": 5},
            alias="sma_ref",
            source_role="reference",
        )
    ]

    with pytest.raises(KeyError, match="reference"):
        build_features_for_multi(reqs, {"primary": frame})


def test_build_features_for_multi_missing_primary_raises():
    frame = build_ohlcv_frame(length=30, seed=7)
    reqs = _sma_reqs()

    with pytest.raises(KeyError, match="primary"):
        build_features_for_multi(reqs, {"reference": frame})


def test_build_features_for_multi_missing_close_ref_raises_with_close_ref_key():
    """Without reference, pairs reqs must still surface KeyError mentioning
    close_ref so the FEATURE_INCOMPLETE integrity code keeps its evidence."""
    primary = build_ohlcv_frame(length=50, seed=7)
    reqs = _pairs_reqs()

    with pytest.raises(KeyError, match="close_ref"):
        build_features_for_multi(reqs, {"primary": primary})


def test_build_features_for_multi_does_not_mutate_primary_frame():
    primary = build_ohlcv_frame(length=30, seed=7)
    reference = build_ohlcv_frame(length=30, seed=9)
    original_columns = list(primary.columns)

    build_features_for_multi(
        _pairs_reqs(), {"primary": primary, "reference": reference}
    )

    assert list(primary.columns) == original_columns
    assert "close_ref" not in primary.columns


class _DummyEngine:
    """Minimal surface needed to exercise _invoke_strategy in isolation."""

    kosten_per_kant = 0.0


def test_engine_invoke_strategy_single_asset_path_unchanged():
    from agent.backtesting.engine import BacktestEngine

    engine = BacktestEngine("2026-01-01", "2026-02-01")
    frame = build_ohlcv_frame(length=80, seed=7)
    strategy = sma_crossover_strategie(fast_window=5, slow_window=20)

    sig_no_ref = engine._invoke_strategy(frame, strategy)
    sig_legacy = engine._invoke_strategy(frame, strategy, reference_frame=None)

    pd.testing.assert_series_equal(sig_no_ref, sig_legacy)
    assert sig_no_ref.dtype.kind in {"i", "f"}


def test_engine_invoke_strategy_pairs_through_reference_frame():
    from agent.backtesting.engine import BacktestEngine

    engine = BacktestEngine("2026-01-01", "2026-02-01")
    pairs_frame = build_pairs_frame(length=260, seed=37)
    primary = pd.DataFrame(
        {"close": pairs_frame["close"].astype(float)},
        index=pairs_frame.index.copy(),
    )
    reference = pd.DataFrame(
        {"close": pairs_frame["close_ref"].astype(float)},
        index=pairs_frame.index.copy(),
    )
    strategy = pairs_zscore_strategie(
        lookback=30, entry_z=2.0, exit_z=0.5, hedge_ratio=1.0
    )

    sig_multi = engine._invoke_strategy(primary, strategy, reference_frame=reference)
    sig_legacy = engine._invoke_strategy(pairs_frame, strategy)

    pd.testing.assert_series_equal(sig_multi, sig_legacy)
