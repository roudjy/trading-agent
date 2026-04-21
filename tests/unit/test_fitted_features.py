"""Unit tests for the fitted feature abstraction (v3.7 step 1).

These tests exercise the abstraction *itself* via a small in-test dummy
fitted feature ("scaled_mean": fit computes the mean of train.close and
stores it as ``beta``; transform returns ``df['close'] * beta``). They
do not depend on any primitive that will be registered in later steps.

The test matrix covers four concerns:

1. Core interface / determinism - fit and transform are pure.
2. FittedParams deep immutability - MappingProxyType, frozen dataclass,
   read-only ndarrays, list->tuple normalization.
3. No reference retention - mutating/destroying the training frame
   after fit must not change subsequent transform output.
4. Param-safety guard - reject-on-construct for pandas objects,
   oversized / disallowed types, nested mappings, non-string keys.
"""

from __future__ import annotations

import dataclasses
import datetime as _dt
import gc
from types import MappingProxyType

import numpy as np
import pandas as pd
import pytest

from agent.backtesting.fitted_features import (
    FITTED_FEATURE_REGISTRY,
    FITTED_FEATURE_VERSION,
    FittedFeatureSpec,
    FittedParams,
    MAX_PARAM_ARRAY_ELEMENTS,
    MAX_PARAM_SEQUENCE_LEN,
    MAX_PARAM_VALUES_ENTRIES,
    validate_fitted_params,
)
from tests._harness_helpers import build_ohlcv_frame


SCALED_MEAN_NAME = "scaled_mean"


def _fit_scaled_mean(df: pd.DataFrame) -> FittedParams:
    beta = float(df["close"].astype(float).mean())
    return FittedParams.build(
        values={"beta": beta},
        feature_name=SCALED_MEAN_NAME,
    )


def _transform_scaled_mean(
    df: pd.DataFrame, params: FittedParams
) -> pd.Series:
    validate_fitted_params(params, SCALED_MEAN_NAME)
    beta = float(params.values["beta"])
    out = df["close"].astype(float) * beta
    return pd.Series(out.values, index=df.index, name=SCALED_MEAN_NAME)


SCALED_MEAN_SPEC = FittedFeatureSpec(
    fit_fn=_fit_scaled_mean,
    transform_fn=_transform_scaled_mean,
    param_names=(),
    required_columns=("close",),
    warmup_bars_fn=lambda _p: 0,
)


# ---------------------------------------------------------------------------
# Core interface / determinism
# ---------------------------------------------------------------------------


def test_fitted_feature_version_is_pinned_string() -> None:
    assert FITTED_FEATURE_VERSION == "1.0"


def test_fitted_feature_registry_contains_expected_entries() -> None:
    # Step 2 registers hedge_ratio_ols. Any additional fitted features
    # land in later steps (or a future phase) and must update this
    # pin consciously.
    assert isinstance(FITTED_FEATURE_REGISTRY, dict)
    assert set(FITTED_FEATURE_REGISTRY.keys()) == {"hedge_ratio_ols"}


def test_fit_is_deterministic() -> None:
    df = build_ohlcv_frame(length=80, seed=11)
    p1 = SCALED_MEAN_SPEC.fit_fn(df)
    p2 = SCALED_MEAN_SPEC.fit_fn(df)
    assert dict(p1.values) == dict(p2.values)


def test_fit_does_not_mutate_input() -> None:
    df = build_ohlcv_frame(length=80, seed=11)
    snapshot = df.copy(deep=True)
    SCALED_MEAN_SPEC.fit_fn(df)
    pd.testing.assert_frame_equal(df, snapshot)


def test_transform_is_deterministic_given_params() -> None:
    df_train = build_ohlcv_frame(length=80, seed=11)
    df_test = build_ohlcv_frame(length=80, seed=23)
    params = SCALED_MEAN_SPEC.fit_fn(df_train)
    s1 = SCALED_MEAN_SPEC.transform_fn(df_test, params)
    s2 = SCALED_MEAN_SPEC.transform_fn(df_test, params)
    pd.testing.assert_series_equal(s1, s2)


def test_transform_is_index_preserving() -> None:
    df_train = build_ohlcv_frame(length=50, seed=11)
    df_test = build_ohlcv_frame(length=50, seed=23)
    params = SCALED_MEAN_SPEC.fit_fn(df_train)
    out = SCALED_MEAN_SPEC.transform_fn(df_test, params)
    assert out.index.equals(df_test.index)


def test_transform_does_not_mutate_input() -> None:
    df_train = build_ohlcv_frame(length=50, seed=11)
    df_test = build_ohlcv_frame(length=50, seed=23)
    snapshot = df_test.copy(deep=True)
    params = SCALED_MEAN_SPEC.fit_fn(df_train)
    SCALED_MEAN_SPEC.transform_fn(df_test, params)
    pd.testing.assert_frame_equal(df_test, snapshot)


# ---------------------------------------------------------------------------
# FittedParams deep immutability
# ---------------------------------------------------------------------------


def test_fitted_params_dataclass_is_frozen() -> None:
    params = FittedParams.build({"beta": 1.0}, feature_name=SCALED_MEAN_NAME)
    with pytest.raises(dataclasses.FrozenInstanceError):
        params.feature_name = "other"  # type: ignore[misc]


def test_fitted_params_values_is_mappingproxy() -> None:
    params = FittedParams.build({"beta": 1.0}, feature_name=SCALED_MEAN_NAME)
    assert type(params.values) is MappingProxyType
    with pytest.raises(TypeError):
        params.values["new_key"] = 2.0  # type: ignore[index]


def test_fitted_params_ndarray_values_are_not_writeable() -> None:
    arr = np.array([1.0, 2.0, 3.0])
    params = FittedParams.build(
        {"weights": arr}, feature_name=SCALED_MEAN_NAME
    )
    stored = params.values["weights"]
    assert isinstance(stored, np.ndarray)
    assert stored.flags.writeable is False
    with pytest.raises(ValueError):
        stored[0] = 99.0


def test_fitted_params_lists_are_stored_as_tuples() -> None:
    params = FittedParams.build(
        {"coeffs": [1.0, 2.0, 3.0]}, feature_name=SCALED_MEAN_NAME
    )
    stored = params.values["coeffs"]
    assert isinstance(stored, tuple)
    assert stored == (1.0, 2.0, 3.0)


# ---------------------------------------------------------------------------
# No reference retention / leakage resistance
# ---------------------------------------------------------------------------


def test_mutating_training_frame_after_fit_does_not_change_transform() -> None:
    df_train = build_ohlcv_frame(length=60, seed=11)
    df_test = build_ohlcv_frame(length=60, seed=23)
    params = SCALED_MEAN_SPEC.fit_fn(df_train)
    before = SCALED_MEAN_SPEC.transform_fn(df_test, params).copy()

    df_train["close"] = df_train["close"] * 1000.0
    df_train.iloc[0, df_train.columns.get_loc("close")] = -9999.0
    df_train.loc[df_train.index[-1], "open"] = 0.0

    after = SCALED_MEAN_SPEC.transform_fn(df_test, params)
    pd.testing.assert_series_equal(before, after)


def test_destroying_training_frame_after_fit_leaves_transform_stable(
) -> None:
    df_train = build_ohlcv_frame(length=60, seed=11)
    df_test = build_ohlcv_frame(length=60, seed=23)
    params = SCALED_MEAN_SPEC.fit_fn(df_train)
    before = SCALED_MEAN_SPEC.transform_fn(df_test, params).copy()

    del df_train
    gc.collect()

    after = SCALED_MEAN_SPEC.transform_fn(df_test, params)
    pd.testing.assert_series_equal(before, after)


def test_shuffling_training_frame_after_fit_leaves_transform_stable(
) -> None:
    df_train = build_ohlcv_frame(length=60, seed=11)
    df_test = build_ohlcv_frame(length=60, seed=23)
    params = SCALED_MEAN_SPEC.fit_fn(df_train)
    before = SCALED_MEAN_SPEC.transform_fn(df_test, params).copy()

    rng = np.random.default_rng(99)
    permutation = rng.permutation(len(df_train))
    df_train.iloc[:, :] = df_train.iloc[permutation, :].values

    after = SCALED_MEAN_SPEC.transform_fn(df_test, params)
    pd.testing.assert_series_equal(before, after)


def test_noise_injection_into_training_frame_leaves_transform_stable(
) -> None:
    df_train = build_ohlcv_frame(length=60, seed=11)
    df_test = build_ohlcv_frame(length=60, seed=23)
    params = SCALED_MEAN_SPEC.fit_fn(df_train)
    before = SCALED_MEAN_SPEC.transform_fn(df_test, params).copy()

    rng = np.random.default_rng(17)
    df_train["close"] = df_train["close"] + rng.normal(0.0, 5.0, len(df_train))

    after = SCALED_MEAN_SPEC.transform_fn(df_test, params)
    pd.testing.assert_series_equal(before, after)


def test_transform_with_different_params_differs() -> None:
    df_a = build_ohlcv_frame(length=60, seed=11)
    df_b = build_ohlcv_frame(length=60, seed=41)
    df_test = build_ohlcv_frame(length=60, seed=23)

    params_a = SCALED_MEAN_SPEC.fit_fn(df_a)
    params_b = SCALED_MEAN_SPEC.fit_fn(df_b)
    assert params_a.values["beta"] != params_b.values["beta"]

    out_a = SCALED_MEAN_SPEC.transform_fn(df_test, params_a)
    out_b = SCALED_MEAN_SPEC.transform_fn(df_test, params_b)
    assert not out_a.equals(out_b)


# ---------------------------------------------------------------------------
# Param safety (reject-on-construct)
# ---------------------------------------------------------------------------


def test_fitted_params_rejects_pandas_series_value() -> None:
    with pytest.raises(ValueError, match="pandas"):
        FittedParams.build(
            {"bad": pd.Series([1.0, 2.0])}, feature_name="x"
        )


def test_fitted_params_rejects_pandas_dataframe_value() -> None:
    with pytest.raises(ValueError, match="pandas"):
        FittedParams.build(
            {"bad": pd.DataFrame({"a": [1.0]})}, feature_name="x"
        )


def test_fitted_params_rejects_pandas_index_value() -> None:
    with pytest.raises(ValueError, match="pandas"):
        FittedParams.build(
            {"bad": pd.Index([1, 2, 3])}, feature_name="x"
        )


def test_fitted_params_rejects_object_with_index_attribute() -> None:
    class _FakeIndexed:
        def __init__(self) -> None:
            self.index = [0, 1, 2]

    with pytest.raises(ValueError, match="index"):
        FittedParams.build({"bad": _FakeIndexed()}, feature_name="x")


def test_fitted_params_rejects_oversized_ndarray() -> None:
    big = np.zeros(MAX_PARAM_ARRAY_ELEMENTS + 1, dtype=np.float64)
    with pytest.raises(ValueError, match="MAX_PARAM_ARRAY_ELEMENTS"):
        FittedParams.build({"bad": big}, feature_name="x")


def test_fitted_params_rejects_oversized_sequence() -> None:
    big = [0.0] * (MAX_PARAM_SEQUENCE_LEN + 1)
    with pytest.raises(ValueError, match="MAX_PARAM_SEQUENCE_LEN"):
        FittedParams.build({"bad": big}, feature_name="x")


def test_fitted_params_rejects_too_many_entries() -> None:
    bad = {f"k{i}": float(i) for i in range(MAX_PARAM_VALUES_ENTRIES + 1)}
    with pytest.raises(ValueError, match="MAX_PARAM_VALUES_ENTRIES"):
        FittedParams.build(bad, feature_name="x")


def test_fitted_params_rejects_non_string_key() -> None:
    with pytest.raises(ValueError, match="keys must be str"):
        FittedParams.build(
            {1: 1.0}, feature_name="x",  # type: ignore[dict-item]
        )


def test_fitted_params_rejects_nested_dict_value() -> None:
    with pytest.raises(ValueError, match="nested mappings"):
        FittedParams.build({"bad": {"inner": 1.0}}, feature_name="x")


def test_fitted_params_rejects_disallowed_scalar_type() -> None:
    with pytest.raises(ValueError, match="not an allowed leaf type"):
        FittedParams.build(
            {"bad": _dt.datetime(2024, 1, 1)}, feature_name="x"
        )
    with pytest.raises(ValueError, match="not an allowed leaf type"):
        FittedParams.build({"bad": 1 + 2j}, feature_name="x")


def test_fitted_params_accepts_scalar_int_float_bool_str_none() -> None:
    params = FittedParams.build(
        {
            "i": 1,
            "f": 1.5,
            "b": True,
            "s": "ok",
            "n": None,
        },
        feature_name="x",
    )
    assert params.values["i"] == 1
    assert params.values["f"] == 1.5
    assert params.values["b"] is True
    assert params.values["s"] == "ok"
    assert params.values["n"] is None


def test_fitted_params_accepts_small_numeric_ndarray() -> None:
    arr = np.arange(8, dtype=np.float64)
    params = FittedParams.build({"w": arr}, feature_name="x")
    assert isinstance(params.values["w"], np.ndarray)
    assert params.values["w"].dtype.kind == "f"


def test_fitted_params_accepts_small_tuple_and_list() -> None:
    params = FittedParams.build(
        {"t": (1.0, 2.0), "l": [3.0, 4.0]}, feature_name="x"
    )
    assert params.values["t"] == (1.0, 2.0)
    assert params.values["l"] == (3.0, 4.0)


# ---------------------------------------------------------------------------
# validate_fitted_params guardrail
# ---------------------------------------------------------------------------


def test_validate_fitted_params_rejects_name_mismatch() -> None:
    params = FittedParams.build({"beta": 1.0}, feature_name="feature_a")
    with pytest.raises(ValueError, match="feature_name mismatch"):
        validate_fitted_params(params, "feature_b")


def test_validate_fitted_params_rejects_version_mismatch() -> None:
    params = FittedParams(
        values=MappingProxyType({"beta": 1.0}),
        feature_name="x",
        version="0.9",
    )
    with pytest.raises(ValueError, match="version mismatch"):
        validate_fitted_params(params, "x")


def test_validate_fitted_params_accepts_matching_pair() -> None:
    params = FittedParams.build({"beta": 1.0}, feature_name="x")
    validate_fitted_params(params, "x")


# ---------------------------------------------------------------------------
# Fingerprint placeholder
# ---------------------------------------------------------------------------


def test_fingerprint_defaults_to_none_and_is_frozen_after_build() -> None:
    p_default = FittedParams.build({"beta": 1.0}, feature_name="x")
    assert p_default.fingerprint is None

    p_set = FittedParams.build(
        {"beta": 1.0}, feature_name="x", fingerprint="abc123"
    )
    assert p_set.fingerprint == "abc123"

    with pytest.raises(dataclasses.FrozenInstanceError):
        p_set.fingerprint = "other"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# hedge_ratio_ols (v3.7 step 2)
# ---------------------------------------------------------------------------


def _linear_pairs_frame(
    n: int = 20, beta_true: float = 2.0, alpha_true: float = 5.0
) -> pd.DataFrame:
    """Build a clean y = alpha + beta*x frame with integer-spaced x."""
    x = np.arange(1, n + 1, dtype=float)
    y = alpha_true + beta_true * x
    index = pd.date_range("2024-01-01", periods=n, freq="D")
    return pd.DataFrame({"close": y, "close_ref": x}, index=index)


def test_hedge_ratio_ols_is_registered_as_fitted_feature() -> None:
    spec = FITTED_FEATURE_REGISTRY["hedge_ratio_ols"]
    assert isinstance(spec, FittedFeatureSpec)
    assert spec.required_columns == ("close", "close_ref")
    assert spec.param_names == ()
    assert spec.warmup_bars_fn({}) == 0


def test_hedge_ratio_ols_fit_returns_expected_beta_on_known_linear_input(
) -> None:
    df = _linear_pairs_frame(n=20, beta_true=2.0, alpha_true=5.0)
    spec = FITTED_FEATURE_REGISTRY["hedge_ratio_ols"]
    params = spec.fit_fn(df)
    beta = params.values["beta"]
    assert isinstance(beta, float)
    assert beta == pytest.approx(2.0, rel=0, abs=1e-12)


def test_hedge_ratio_ols_intercept_is_allowed_during_fit() -> None:
    # y = 2x + 5. OLS with intercept -> beta = 2.0 exactly.
    # Through-origin OLS (beta = sum(xy)/sum(x^2)) on x=1..20 would give
    # ~2.357 - materially different. This test locks the intercept-
    # allowed convention against an accidental through-origin drift.
    df = _linear_pairs_frame(n=20, beta_true=2.0, alpha_true=5.0)
    spec = FITTED_FEATURE_REGISTRY["hedge_ratio_ols"]
    params = spec.fit_fn(df)
    beta = params.values["beta"]
    assert beta == pytest.approx(2.0, rel=0, abs=1e-12)

    x = df["close_ref"].to_numpy()
    y = df["close"].to_numpy()
    through_origin = float((x * y).sum() / (x * x).sum())
    assert abs(through_origin - 2.0) > 0.1


def test_hedge_ratio_ols_transform_returns_expected_spread_on_known_input(
) -> None:
    # y = 2x + 5; with beta=2 the spread is the constant intercept 5.
    df = _linear_pairs_frame(n=20, beta_true=2.0, alpha_true=5.0)
    spec = FITTED_FEATURE_REGISTRY["hedge_ratio_ols"]
    params = spec.fit_fn(df)
    spread = spec.transform_fn(df, params)
    expected = pd.Series(
        np.full(len(df), 5.0), index=df.index
    )
    pd.testing.assert_series_equal(
        spread, expected, check_names=False, atol=1e-12
    )


def test_hedge_ratio_ols_fit_is_deterministic() -> None:
    df = _linear_pairs_frame(n=30)
    spec = FITTED_FEATURE_REGISTRY["hedge_ratio_ols"]
    p1 = spec.fit_fn(df)
    p2 = spec.fit_fn(df)
    assert p1.values["beta"] == p2.values["beta"]


def test_hedge_ratio_ols_transform_is_deterministic_given_params() -> None:
    df = _linear_pairs_frame(n=30)
    spec = FITTED_FEATURE_REGISTRY["hedge_ratio_ols"]
    params = spec.fit_fn(df)
    s1 = spec.transform_fn(df, params)
    s2 = spec.transform_fn(df, params)
    pd.testing.assert_series_equal(s1, s2)


def test_hedge_ratio_ols_transform_is_index_preserving() -> None:
    df = _linear_pairs_frame(n=15)
    spec = FITTED_FEATURE_REGISTRY["hedge_ratio_ols"]
    params = spec.fit_fn(df)
    out = spec.transform_fn(df, params)
    assert out.index.equals(df.index)
    assert len(out) == len(df)


def test_hedge_ratio_ols_fit_does_not_mutate_input() -> None:
    df = _linear_pairs_frame(n=20)
    snapshot = df.copy(deep=True)
    spec = FITTED_FEATURE_REGISTRY["hedge_ratio_ols"]
    spec.fit_fn(df)
    pd.testing.assert_frame_equal(df, snapshot)


def test_hedge_ratio_ols_transform_does_not_mutate_input() -> None:
    df = _linear_pairs_frame(n=20)
    spec = FITTED_FEATURE_REGISTRY["hedge_ratio_ols"]
    params = spec.fit_fn(df)
    snapshot = df.copy(deep=True)
    spec.transform_fn(df, params)
    pd.testing.assert_frame_equal(df, snapshot)


def test_hedge_ratio_ols_rejects_missing_columns() -> None:
    spec = FITTED_FEATURE_REGISTRY["hedge_ratio_ols"]
    df = _linear_pairs_frame(n=10).drop(columns=["close_ref"])
    with pytest.raises(ValueError, match="missing required columns"):
        spec.fit_fn(df)

    params = spec.fit_fn(_linear_pairs_frame(n=10))
    with pytest.raises(ValueError, match="missing required columns"):
        spec.transform_fn(df, params)


def test_hedge_ratio_ols_rejects_empty_input() -> None:
    spec = FITTED_FEATURE_REGISTRY["hedge_ratio_ols"]
    df = pd.DataFrame(
        {"close": pd.Series([], dtype=float),
         "close_ref": pd.Series([], dtype=float)}
    )
    with pytest.raises(ValueError, match="empty input frame"):
        spec.fit_fn(df)


def test_hedge_ratio_ols_rejects_too_few_rows() -> None:
    spec = FITTED_FEATURE_REGISTRY["hedge_ratio_ols"]
    df = pd.DataFrame(
        {"close": [1.0], "close_ref": [1.0]},
        index=pd.date_range("2024-01-01", periods=1, freq="D"),
    )
    with pytest.raises(ValueError, match="need >= 2 rows"):
        spec.fit_fn(df)


def test_hedge_ratio_ols_rejects_nan_inputs() -> None:
    spec = FITTED_FEATURE_REGISTRY["hedge_ratio_ols"]
    df = _linear_pairs_frame(n=10)
    df.loc[df.index[3], "close"] = np.nan
    with pytest.raises(ValueError, match="NaN values"):
        spec.fit_fn(df)

    df2 = _linear_pairs_frame(n=10)
    df2.loc[df2.index[5], "close_ref"] = np.nan
    with pytest.raises(ValueError, match="NaN values"):
        spec.fit_fn(df2)


def test_hedge_ratio_ols_rejects_constant_or_singular_reference_series(
) -> None:
    spec = FITTED_FEATURE_REGISTRY["hedge_ratio_ols"]
    df = pd.DataFrame(
        {"close": np.arange(10, dtype=float),
         "close_ref": np.full(10, 3.14, dtype=float)},
        index=pd.date_range("2024-01-01", periods=10, freq="D"),
    )
    with pytest.raises(ValueError, match="zero or non-finite variance"):
        spec.fit_fn(df)


def test_hedge_ratio_ols_params_stay_small_and_carry_no_training_data(
) -> None:
    df = _linear_pairs_frame(n=50)
    spec = FITTED_FEATURE_REGISTRY["hedge_ratio_ols"]
    params = spec.fit_fn(df)

    assert set(params.values.keys()) == {"beta"}
    assert isinstance(params.values["beta"], float)
    # Defensive: no pandas-ish payload, no ndarrays, no sequences.
    for v in params.values.values():
        assert not isinstance(v, (pd.Series, pd.DataFrame, pd.Index))
        assert not isinstance(v, np.ndarray)
        assert not isinstance(v, (tuple, list))
