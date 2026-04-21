"""Integration tests for v3.7 step 3 - fitted feature engine plumbing.

These tests exercise the fold-aware helpers added to
``agent.backtesting.thin_strategy``: ``build_features_train``,
``build_features_test``, ``build_features_train_multi``, and
``build_features_test_multi``. They use a *spy* fitted feature with
call counters to prove fit-once / no-refit semantics, and they use the
real ``hedge_ratio_ols`` fitted feature (registered by step 2) to
exercise the multi-asset path.

Guarantees verified (one per category from the step 3 brief):

1. fitted feature in training path fits exactly once
2. fitted feature in test path reuses training params and does NOT refit
3. fitted params are fold-local - each fold gets its own params
4. missing fold-local params in the test phase raise loudly
5. ordinary features keep the unchanged plain path
6. mixed ordinary + fitted requests resolve in one call
7. walk-forward uses train-only fit and test-only transform
8. mutating the test frame after fit does not affect fitted params
9. fold A's params never leak into fold B
10. determinism: same input/config produces identical outputs
11. multi-asset fitted feature integration on aligned pair data
12. existing plain path remains byte-identical when fitted features
    are not requested
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
import pytest

from agent.backtesting.features import FEATURE_REGISTRY
from agent.backtesting.fitted_features import (
    FITTED_FEATURE_REGISTRY,
    FittedFeatureSpec,
    FittedParams,
)
from agent.backtesting.thin_strategy import (
    FeatureRequirement,
    build_features_for,
    build_features_for_multi,
    build_features_test,
    build_features_test_multi,
    build_features_train,
    build_features_train_multi,
)
from tests._harness_helpers import (
    build_aligned_pair_frames,
    build_ohlcv_frame,
    build_pairs_frame,
)


# ---------------------------------------------------------------------------
# Spy fitted feature: a scaled-mean example with call counters.
# Fits a single ``scale`` scalar = float(mean(close)); transform returns
# close * scale. Registered/unregistered via an autouse fixture so the
# global ``FITTED_FEATURE_REGISTRY`` is left untouched after each test.
# ---------------------------------------------------------------------------


SPY_FEATURE_NAME = "spy_scaled_mean"


@dataclass
class _SpyCounter:
    fit_calls: int = 0
    transform_calls: int = 0
    fit_lens: list[int] = field(default_factory=list)
    transform_lens: list[int] = field(default_factory=list)

    def reset(self) -> None:
        self.fit_calls = 0
        self.transform_calls = 0
        self.fit_lens.clear()
        self.transform_lens.clear()


_SPY = _SpyCounter()


def _spy_fit(df: pd.DataFrame) -> FittedParams:
    _SPY.fit_calls += 1
    _SPY.fit_lens.append(len(df))
    scale = float(df["close"].astype(float).mean())
    return FittedParams.build(
        values={"scale": scale}, feature_name=SPY_FEATURE_NAME
    )


def _spy_transform(df: pd.DataFrame, params: FittedParams) -> pd.Series:
    _SPY.transform_calls += 1
    _SPY.transform_lens.append(len(df))
    scale = float(params.values["scale"])
    return df["close"].astype(float) * scale


def _spy_warmup(_params: dict) -> int:
    return 0


@pytest.fixture(autouse=True)
def _register_spy_feature():
    FITTED_FEATURE_REGISTRY[SPY_FEATURE_NAME] = FittedFeatureSpec(
        fit_fn=_spy_fit,
        transform_fn=_spy_transform,
        param_names=(),
        required_columns=("close",),
        warmup_bars_fn=_spy_warmup,
    )
    _SPY.reset()
    try:
        yield
    finally:
        FITTED_FEATURE_REGISTRY.pop(SPY_FEATURE_NAME, None)
        _SPY.reset()


def _spy_req(alias: str | None = None) -> FeatureRequirement:
    return FeatureRequirement(
        name=SPY_FEATURE_NAME, feature_kind="fitted", alias=alias
    )


def _plain_sma_req(window: int = 5, alias: str | None = None) -> FeatureRequirement:
    return FeatureRequirement(
        name="sma", params={"window": window}, alias=alias
    )


# ---------------------------------------------------------------------------
# Category 1 - training path fits exactly once
# ---------------------------------------------------------------------------


def test_training_path_fits_exactly_once_per_requirement() -> None:
    df = build_ohlcv_frame(length=60, seed=3)
    reqs = [_spy_req()]

    features, fitted = build_features_train(reqs, df)

    assert _SPY.fit_calls == 1
    assert _SPY.transform_calls == 1
    assert set(features) == {SPY_FEATURE_NAME}
    assert set(fitted) == {SPY_FEATURE_NAME}
    assert isinstance(fitted[SPY_FEATURE_NAME], FittedParams)


def test_training_path_multiple_fitted_requirements_each_fit_once() -> None:
    df = build_ohlcv_frame(length=60, seed=5)
    reqs = [
        FeatureRequirement(
            name=SPY_FEATURE_NAME, feature_kind="fitted", alias="a"
        ),
        FeatureRequirement(
            name=SPY_FEATURE_NAME, feature_kind="fitted", alias="b"
        ),
    ]

    features, fitted = build_features_train(reqs, df)

    assert _SPY.fit_calls == 2
    assert _SPY.transform_calls == 2
    assert set(features) == {"a", "b"}
    assert set(fitted) == {"a", "b"}


# ---------------------------------------------------------------------------
# Category 2 - test path reuses frozen params; no refit
# ---------------------------------------------------------------------------


def test_test_path_reuses_params_and_does_not_refit() -> None:
    df_train = build_ohlcv_frame(length=80, seed=7)
    df_test = build_ohlcv_frame(length=40, seed=9, start="2024-07-01")
    reqs = [_spy_req()]

    _train_features, fitted = build_features_train(reqs, df_train)
    fit_after_train = _SPY.fit_calls
    transform_after_train = _SPY.transform_calls

    out = build_features_test(reqs, df_test, fitted)

    assert _SPY.fit_calls == fit_after_train  # no additional fit
    assert _SPY.transform_calls == transform_after_train + 1
    assert fit_after_train == 1
    assert out[SPY_FEATURE_NAME].index.equals(df_test.index)


def test_test_path_produces_expected_scaled_mean() -> None:
    df_train = build_ohlcv_frame(length=50, seed=11)
    df_test = build_ohlcv_frame(length=25, seed=13, start="2024-06-01")
    reqs = [_spy_req()]

    _f, fitted = build_features_train(reqs, df_train)
    out = build_features_test(reqs, df_test, fitted)

    expected_scale = float(df_train["close"].astype(float).mean())
    expected = df_test["close"].astype(float) * expected_scale
    pd.testing.assert_series_equal(out[SPY_FEATURE_NAME], expected)


# ---------------------------------------------------------------------------
# Category 4 - missing fold-local params in test phase raises loudly
# ---------------------------------------------------------------------------


def test_test_path_without_fitted_params_raises_key_error() -> None:
    df_test = build_ohlcv_frame(length=30, seed=17)
    reqs = [_spy_req()]

    with pytest.raises(KeyError, match="fold-local fitted params"):
        build_features_test(reqs, df_test, fitted_params={})


def test_test_path_with_wrong_alias_raises_key_error() -> None:
    df_train = build_ohlcv_frame(length=40, seed=19)
    df_test = build_ohlcv_frame(length=20, seed=21, start="2024-06-01")
    reqs_train = [_spy_req(alias="a")]
    reqs_test = [_spy_req(alias="b")]

    _f, fitted = build_features_train(reqs_train, df_train)

    with pytest.raises(KeyError, match="fold-local fitted params"):
        build_features_test(reqs_test, df_test, fitted)


# ---------------------------------------------------------------------------
# Category 5 - ordinary (plain) features use the unchanged path
# ---------------------------------------------------------------------------


def test_plain_only_train_path_does_not_touch_fit_fn() -> None:
    df = build_ohlcv_frame(length=40, seed=23)
    reqs = [_plain_sma_req(window=5)]

    features, fitted = build_features_train(reqs, df)

    assert _SPY.fit_calls == 0
    assert _SPY.transform_calls == 0
    assert list(features.keys()) == ["sma"]
    assert fitted == {}


def test_plain_only_test_path_ignores_fitted_params() -> None:
    df = build_ohlcv_frame(length=40, seed=25)
    reqs = [_plain_sma_req(window=5)]

    out = build_features_test(reqs, df, fitted_params={})

    assert list(out.keys()) == ["sma"]
    pd.testing.assert_series_equal(
        out["sma"], FEATURE_REGISTRY["sma"].fn(df["close"], window=5)
    )


def test_build_features_for_rejects_fitted_requirement() -> None:
    df = build_ohlcv_frame(length=30, seed=27)
    reqs = [_spy_req()]

    with pytest.raises(ValueError, match="cannot be resolved via the plain"):
        build_features_for(reqs, df)


# ---------------------------------------------------------------------------
# Category 6 - mixed plain + fitted requests in a single call
# ---------------------------------------------------------------------------


def test_mixed_plain_and_fitted_train_and_test() -> None:
    df_train = build_ohlcv_frame(length=60, seed=29)
    df_test = build_ohlcv_frame(length=30, seed=31, start="2024-06-01")
    reqs = [_plain_sma_req(window=5), _spy_req()]

    train_features, fitted = build_features_train(reqs, df_train)
    test_features = build_features_test(reqs, df_test, fitted)

    assert set(train_features) == {"sma", SPY_FEATURE_NAME}
    assert set(fitted) == {SPY_FEATURE_NAME}
    assert _SPY.fit_calls == 1
    assert _SPY.transform_calls == 2  # one during fit, one during test

    pd.testing.assert_series_equal(
        train_features["sma"],
        FEATURE_REGISTRY["sma"].fn(df_train["close"], window=5),
    )
    pd.testing.assert_series_equal(
        test_features["sma"],
        FEATURE_REGISTRY["sma"].fn(df_test["close"], window=5),
    )


# ---------------------------------------------------------------------------
# Category 7 - walk-forward semantics: train-only fit, test-only transform
# ---------------------------------------------------------------------------


def test_walk_forward_style_train_test_split_fits_only_on_train() -> None:
    full = build_ohlcv_frame(length=120, seed=33)
    split = 80
    df_train = full.iloc[:split].copy()
    df_test = full.iloc[split:].copy()
    reqs = [_spy_req()]

    _f, fitted = build_features_train(reqs, df_train)
    assert _SPY.fit_lens == [split]

    _ = build_features_test(reqs, df_test, fitted)
    assert _SPY.fit_lens == [split]  # no new fit
    assert _SPY.transform_lens[-1] == len(df_test)

    # The fitted scale must reflect only the training slice.
    expected_scale = float(df_train["close"].astype(float).mean())
    assert fitted[SPY_FEATURE_NAME].values["scale"] == pytest.approx(
        expected_scale
    )
    # And must NOT equal the full-window scale.
    full_scale = float(full["close"].astype(float).mean())
    assert fitted[SPY_FEATURE_NAME].values["scale"] != pytest.approx(full_scale)


# ---------------------------------------------------------------------------
# Category 8 - leakage resistance: test-slice mutation doesn't affect params
# ---------------------------------------------------------------------------


def test_mutating_test_frame_after_fit_does_not_change_fitted_params() -> None:
    df_train = build_ohlcv_frame(length=50, seed=35)
    df_test = build_ohlcv_frame(length=30, seed=37, start="2024-06-01")
    reqs = [_spy_req()]

    _f, fitted = build_features_train(reqs, df_train)
    scale_before = float(fitted[SPY_FEATURE_NAME].values["scale"])

    baseline = build_features_test(reqs, df_test, fitted)

    df_test["close"] = df_test["close"] * 10.0 + 999.0

    scale_after = float(fitted[SPY_FEATURE_NAME].values["scale"])
    assert scale_before == scale_after

    # Re-running transform on the unmutated test frame would still produce
    # the baseline output - this guards against fit side-channels leaking
    # through shared buffers.
    df_test_fresh = build_ohlcv_frame(length=30, seed=37, start="2024-06-01")
    out = build_features_test(reqs, df_test_fresh, fitted)
    pd.testing.assert_series_equal(out[SPY_FEATURE_NAME], baseline[SPY_FEATURE_NAME])


def test_fitted_params_values_are_not_writeable_from_caller() -> None:
    df_train = build_ohlcv_frame(length=40, seed=39)
    reqs = [_spy_req()]

    _f, fitted = build_features_train(reqs, df_train)
    fp = fitted[SPY_FEATURE_NAME]

    with pytest.raises(TypeError):
        fp.values["scale"] = 0.0  # type: ignore[index]


# ---------------------------------------------------------------------------
# Category 3 + 9 - fold-local params; no cross-fold leakage
# ---------------------------------------------------------------------------


def test_two_folds_produce_independent_fitted_params() -> None:
    df_fold_a = build_ohlcv_frame(length=50, seed=41, start="2024-01-01")
    df_fold_b = build_ohlcv_frame(length=50, seed=43, start="2024-04-01")
    reqs = [_spy_req()]

    _fa, fitted_a = build_features_train(reqs, df_fold_a)
    _fb, fitted_b = build_features_train(reqs, df_fold_b)

    assert fitted_a[SPY_FEATURE_NAME] is not fitted_b[SPY_FEATURE_NAME]
    assert (
        fitted_a[SPY_FEATURE_NAME].values["scale"]
        != fitted_b[SPY_FEATURE_NAME].values["scale"]
    )


def test_fold_b_test_phase_uses_fold_b_params_not_fold_a() -> None:
    df_train_a = build_ohlcv_frame(length=60, seed=45, start="2024-01-01")
    df_train_b = build_ohlcv_frame(length=60, seed=47, start="2024-04-01")
    df_test_b = build_ohlcv_frame(length=20, seed=49, start="2024-07-01")
    reqs = [_spy_req()]

    _fa, fitted_a = build_features_train(reqs, df_train_a)
    _fb, fitted_b = build_features_train(reqs, df_train_b)

    out_with_b = build_features_test(reqs, df_test_b, fitted_b)
    out_with_a = build_features_test(reqs, df_test_b, fitted_a)

    # Different fold params must produce different test-phase outputs on
    # the same test slice - proves fold-local ownership is honoured.
    assert not out_with_a[SPY_FEATURE_NAME].equals(out_with_b[SPY_FEATURE_NAME])


def test_fold_a_params_unchanged_after_fold_b_train_and_test() -> None:
    df_train_a = build_ohlcv_frame(length=60, seed=51, start="2024-01-01")
    df_train_b = build_ohlcv_frame(length=60, seed=53, start="2024-04-01")
    df_test_b = build_ohlcv_frame(length=20, seed=55, start="2024-07-01")
    reqs = [_spy_req()]

    _fa, fitted_a = build_features_train(reqs, df_train_a)
    scale_a_before = float(fitted_a[SPY_FEATURE_NAME].values["scale"])

    _fb, fitted_b = build_features_train(reqs, df_train_b)
    _ = build_features_test(reqs, df_test_b, fitted_b)

    scale_a_after = float(fitted_a[SPY_FEATURE_NAME].values["scale"])
    assert scale_a_before == scale_a_after


# ---------------------------------------------------------------------------
# Category 10 - determinism
# ---------------------------------------------------------------------------


def test_repeated_train_then_test_produces_identical_outputs() -> None:
    df_train = build_ohlcv_frame(length=60, seed=57)
    df_test = build_ohlcv_frame(length=30, seed=59, start="2024-06-01")
    reqs = [_plain_sma_req(window=5), _spy_req()]

    train_1, fitted_1 = build_features_train(reqs, df_train)
    test_1 = build_features_test(reqs, df_test, fitted_1)

    train_2, fitted_2 = build_features_train(reqs, df_train)
    test_2 = build_features_test(reqs, df_test, fitted_2)

    for key in train_1:
        pd.testing.assert_series_equal(train_1[key], train_2[key])
        assert (
            train_1[key].to_numpy(copy=True).tobytes()
            == train_2[key].to_numpy(copy=True).tobytes()
        )
    for key in test_1:
        pd.testing.assert_series_equal(test_1[key], test_2[key])
        assert (
            test_1[key].to_numpy(copy=True).tobytes()
            == test_2[key].to_numpy(copy=True).tobytes()
        )

    assert (
        fitted_1[SPY_FEATURE_NAME].values["scale"]
        == fitted_2[SPY_FEATURE_NAME].values["scale"]
    )


# ---------------------------------------------------------------------------
# Category 11 - multi-asset fitted integration (hedge_ratio_ols)
# ---------------------------------------------------------------------------


def test_multi_asset_train_fits_hedge_ratio_on_combined_view() -> None:
    primary, reference = build_aligned_pair_frames(
        seed_primary=61, seed_reference=63, length=120
    )
    frames = {"primary": primary, "reference": reference}
    reqs = [
        FeatureRequirement(name="hedge_ratio_ols", feature_kind="fitted"),
    ]

    features, fitted = build_features_train_multi(reqs, frames)

    assert set(features) == {"hedge_ratio_ols"}
    assert set(fitted) == {"hedge_ratio_ols"}
    fp = fitted["hedge_ratio_ols"]
    assert fp.feature_name == "hedge_ratio_ols"
    assert "beta" in fp.values
    beta = float(fp.values["beta"])
    assert np.isfinite(beta)

    # Verify transform output matches spread = y - beta*x on the combined
    # primary+close_ref view.
    combined = primary.copy()
    combined["close_ref"] = reference["close"]
    expected = combined["close"].astype(float) - beta * combined[
        "close_ref"
    ].astype(float)
    pd.testing.assert_series_equal(features["hedge_ratio_ols"], expected)


def test_multi_asset_test_uses_train_params_no_refit() -> None:
    primary, reference = build_aligned_pair_frames(
        seed_primary=65, seed_reference=67, length=120
    )
    split = 80
    train_frames = {
        "primary": primary.iloc[:split].copy(),
        "reference": reference.iloc[:split].copy(),
    }
    test_frames = {
        "primary": primary.iloc[split:].copy(),
        "reference": reference.iloc[split:].copy(),
    }
    reqs = [
        FeatureRequirement(name="hedge_ratio_ols", feature_kind="fitted"),
    ]

    _train, fitted = build_features_train_multi(reqs, train_frames)
    beta_train = float(fitted["hedge_ratio_ols"].values["beta"])

    test_features = build_features_test_multi(reqs, test_frames, fitted)

    # Re-fitting on test would yield a different beta - verify the stored
    # beta still equals the training-slice beta after the test call.
    assert fitted["hedge_ratio_ols"].values["beta"] == beta_train

    # And: the test-phase spread must use the training beta, not a
    # freshly-fit one.
    combined_test = test_frames["primary"].copy()
    combined_test["close_ref"] = test_frames["reference"]["close"]
    expected = combined_test["close"].astype(float) - beta_train * combined_test[
        "close_ref"
    ].astype(float)
    pd.testing.assert_series_equal(test_features["hedge_ratio_ols"], expected)


def test_multi_asset_mixed_plain_and_fitted_requests() -> None:
    primary, reference = build_aligned_pair_frames(
        seed_primary=69, seed_reference=71, length=80
    )
    frames = {"primary": primary, "reference": reference}
    reqs = [
        _plain_sma_req(window=5),
        FeatureRequirement(name="hedge_ratio_ols", feature_kind="fitted"),
    ]

    features, fitted = build_features_train_multi(reqs, frames)

    assert set(features) == {"sma", "hedge_ratio_ols"}
    assert set(fitted) == {"hedge_ratio_ols"}
    # The plain sma must be resolvable on the combined primary view using
    # primary.close - byte-for-byte equal to the plain single-frame path.
    pd.testing.assert_series_equal(
        features["sma"], FEATURE_REGISTRY["sma"].fn(primary["close"], window=5)
    )


def test_multi_asset_rejects_fitted_with_reference_source_role() -> None:
    primary, reference = build_aligned_pair_frames(
        seed_primary=73, seed_reference=75, length=60
    )
    frames = {"primary": primary, "reference": reference}
    reqs = [
        FeatureRequirement(
            name="hedge_ratio_ols",
            feature_kind="fitted",
            source_role="reference",
        ),
    ]

    with pytest.raises(ValueError, match="source_role='reference'"):
        build_features_train_multi(reqs, frames)


def test_build_features_for_multi_rejects_fitted_requirement() -> None:
    primary, reference = build_aligned_pair_frames(
        seed_primary=77, seed_reference=79, length=40
    )
    frames = {"primary": primary, "reference": reference}
    reqs = [
        FeatureRequirement(name="hedge_ratio_ols", feature_kind="fitted"),
    ]

    with pytest.raises(ValueError, match="cannot be resolved via the plain"):
        build_features_for_multi(reqs, frames)


# ---------------------------------------------------------------------------
# Category 12 - non-fitted paths remain byte-identical
# ---------------------------------------------------------------------------


def test_plain_path_output_unchanged_across_build_features_for() -> None:
    df = build_ohlcv_frame(length=80, seed=81)
    reqs = [_plain_sma_req(window=10), FeatureRequirement(name="ema", params={"span": 20})]

    out_plain = build_features_for(reqs, df)
    out_train, fitted = build_features_train(reqs, df)

    assert fitted == {}
    for key in out_plain:
        pd.testing.assert_series_equal(out_plain[key], out_train[key])
        assert (
            out_plain[key].to_numpy(copy=True).tobytes()
            == out_train[key].to_numpy(copy=True).tobytes()
        )


def test_multi_asset_plain_path_unchanged_when_no_fitted_requested() -> None:
    primary, reference = build_aligned_pair_frames(
        seed_primary=83, seed_reference=85, length=80
    )
    frames = {"primary": primary, "reference": reference}
    reqs = [
        FeatureRequirement(
            name="spread", params={"hedge_ratio": 1.0}
        ),
        FeatureRequirement(
            name="spread_zscore",
            params={"hedge_ratio": 1.0, "lookback": 20},
        ),
    ]

    out_plain = build_features_for_multi(reqs, frames)
    out_train, fitted = build_features_train_multi(reqs, frames)

    assert fitted == {}
    for key in out_plain:
        pd.testing.assert_series_equal(out_plain[key], out_train[key])
        assert (
            out_plain[key].to_numpy(copy=True).tobytes()
            == out_train[key].to_numpy(copy=True).tobytes()
        )


def test_single_frame_pairs_plain_resolution_still_works() -> None:
    # Sanity: the v3.5 single-frame pairs harness (pairs frame with close +
    # close_ref columns) must still resolve plain pair features via
    # build_features_for - the fitted-feature plumbing does not disturb it.
    pairs = build_pairs_frame(length=120, seed=87)
    reqs = [
        FeatureRequirement(name="spread", params={"hedge_ratio": 1.0}),
    ]

    out = build_features_for(reqs, pairs)

    expected = FEATURE_REGISTRY["spread"].fn(
        pairs["close"], pairs["close_ref"], hedge_ratio=1.0
    )
    pd.testing.assert_series_equal(out["spread"], expected)
