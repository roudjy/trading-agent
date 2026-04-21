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


def test_fitted_feature_registry_is_initially_empty() -> None:
    assert isinstance(FITTED_FEATURE_REGISTRY, dict)
    assert FITTED_FEATURE_REGISTRY == {}


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
