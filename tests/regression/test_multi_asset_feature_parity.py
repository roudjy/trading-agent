"""v3.6 multi-asset feature parity regression.

Guards the invariant that multi-asset feature resolution is a
bytewise-compatible extension of single-frame resolution for pairs
inputs. Concretely: for the pairs_zscore feature requirements, the
output of

    build_features_for(reqs, pairs_frame)

must be byte-identical to

    build_features_for_multi(reqs, {"primary": primary, "reference": reference})

when `pairs_frame` is the single-frame synthetic fixture with `close`
and `close_ref` columns, and `primary`/`reference` are two OHLCV frames
whose columns combine (via the multi-path's reference.close ->
primary.close_ref projection) into the same view. Any drift here means
the multi-asset path introduced a numerical divergence from the v3.5
bytewise pin — a contract break, not a refactor.
"""

from __future__ import annotations

import pandas as pd
from pandas.testing import assert_series_equal

from agent.backtesting.strategies import pairs_zscore_strategie
from agent.backtesting.thin_strategy import (
    FeatureRequirement,
    build_features_for,
    build_features_for_multi,
)
from tests._harness_helpers import build_ohlcv_frame, build_pairs_frame


PAIRS_LEN = 260
PAIRS_SEED = 37


def _pairs_reqs() -> list[FeatureRequirement]:
    return list(
        pairs_zscore_strategie(
            lookback=30, entry_z=2.0, exit_z=0.5, hedge_ratio=1.0
        )._feature_requirements  # type: ignore[attr-defined]
    )


def _split_pairs_frame(
    pairs_frame: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Rebuild a primary + reference OHLCV pair that, under the multi
    path's reference.close -> primary.close_ref projection, reproduces
    the single-frame `pairs_frame` exactly.
    """
    primary = build_ohlcv_frame(length=PAIRS_LEN, seed=PAIRS_SEED)
    reference = build_ohlcv_frame(length=PAIRS_LEN, seed=PAIRS_SEED)
    reference["close"] = pairs_frame["close_ref"].to_numpy()
    return primary, reference


def test_pairs_single_frame_and_multi_frame_resolve_byte_identical() -> None:
    reqs = _pairs_reqs()
    pairs_frame = build_pairs_frame(length=PAIRS_LEN, seed=PAIRS_SEED)
    primary, reference = _split_pairs_frame(pairs_frame)

    single = build_features_for(reqs, pairs_frame)
    multi = build_features_for_multi(
        reqs, {"primary": primary, "reference": reference}
    )

    assert set(single) == set(multi)
    for alias in single:
        assert_series_equal(single[alias], multi[alias], check_dtype=True)
        assert (
            single[alias].to_numpy(copy=True).tobytes()
            == multi[alias].to_numpy(copy=True).tobytes()
        )


def test_pairs_multi_frame_close_ref_comes_from_reference_close() -> None:
    """Explicit projection check: the multi path exposes reference.close
    as close_ref on the combined primary view; no other column mapping
    is permitted. If this ever changes, spread_zscore output drifts
    silently."""
    reqs = _pairs_reqs()
    pairs_frame = build_pairs_frame(length=PAIRS_LEN, seed=PAIRS_SEED)
    primary, reference = _split_pairs_frame(pairs_frame)

    multi = build_features_for_multi(
        reqs, {"primary": primary, "reference": reference}
    )
    reference_drifted = reference.copy()
    reference_drifted["close"] = reference_drifted["close"] + 1.0
    drifted = build_features_for_multi(
        reqs, {"primary": primary, "reference": reference_drifted}
    )

    assert (
        multi["z"].to_numpy(copy=True).tobytes()
        != drifted["z"].to_numpy(copy=True).tobytes()
    ), "reference.close perturbation must flow into spread_zscore output"


def test_pairs_multi_frame_does_not_mutate_primary_frame() -> None:
    reqs = _pairs_reqs()
    pairs_frame = build_pairs_frame(length=PAIRS_LEN, seed=PAIRS_SEED)
    primary, reference = _split_pairs_frame(pairs_frame)
    before_cols = list(primary.columns)
    before_close = primary["close"].copy()

    build_features_for_multi(
        reqs, {"primary": primary, "reference": reference}
    )

    assert list(primary.columns) == before_cols
    assert_series_equal(primary["close"], before_close, check_dtype=True)
