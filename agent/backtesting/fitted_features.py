"""Fitted feature abstraction (v3.7 step 1).

A *fitted feature* has a two-phase lifecycle:

    fit_fn(df_train, **params)                 -> FittedParams
    transform_fn(df, fitted_params, **params)  -> pd.Series

Both phases are pure and deterministic. Leakage prevention is a
structural concern enforced at the engine boundary (Step 3): the engine
passes only the training slice into ``fit_fn`` and only the test slice
into ``transform_fn``. This module enforces a complementary safety net:
``FittedParams`` is deeply immutable, structurally validated on
construction, and cannot carry references to training data.

This is a parallel abstraction to ``agent.backtesting.features``'s pure
``FeatureSpec`` registry - fitted features coexist with non-fitted
primitives rather than replacing them. The v3.5/v3.6 single-pass path
and its Tier 1 bytewise pins are untouched by this module.

Invariants guaranteed by the abstraction:

- ``FittedParams`` is a frozen dataclass.
- ``FittedParams.values`` is a ``types.MappingProxyType`` wrapping a
  dict of *defensively copied*, *type-restricted*, *size-bounded*
  primitives; numpy arrays are stored read-only.
- ``FittedParams`` retains no reference to the caller-supplied
  training frame or any pandas object - validation rejects them
  explicitly and wholesale structural copies break any sharing.

Invariants that remain a layer-separation responsibility of the caller
(not enforceable in this module alone):

- ``fit_fn`` must read only from its training-window input.
- ``transform_fn`` must derive output solely from its input frame and
  the provided ``FittedParams``; no hidden global state, no access to
  fit-time data.

Warmup semantics differ from ``FeatureSpec``: fit is a single-pass over
a window rather than a rolling warmup. ``warmup_bars_fn`` is retained
for uniformity with the non-fitted registry; Step 3 wires its meaning
appropriately when integrating with the engine.
"""

from __future__ import annotations

import types
from collections.abc import Mapping as AbcMapping
from dataclasses import dataclass
from typing import Any, Callable, Mapping

import numpy as np
import pandas as pd


FITTED_FEATURE_VERSION = "1.0"

MAX_PARAM_VALUES_ENTRIES = 64
MAX_PARAM_ARRAY_ELEMENTS = 1024
MAX_PARAM_SEQUENCE_LEN = 1024

ALLOWED_SCALAR_TYPES: tuple[type, ...] = (int, float, bool, str)
_ALLOWED_NDARRAY_KINDS = frozenset({"i", "u", "f", "b"})


def _reject_pandas(key: str, v: Any) -> None:
    if isinstance(v, (pd.Series, pd.DataFrame, pd.Index)):
        raise ValueError(
            f"FittedParams[{key!r}]: pandas objects are forbidden as "
            f"fitted parameter values (got {type(v).__name__})"
        )


def _normalize_leaf(key: str, v: Any) -> Any:
    """Validate and defensively copy a scalar / array leaf value.

    Returns the value to store. Raises ValueError on any violation.
    Ordering is deliberate: pandas rejection first, then the scalar
    whitelist (so ``str`` short-circuits before the generic ``.index``
    attribute guard below catches ``str.index`` as a false positive).
    """
    _reject_pandas(key, v)
    if v is None:
        return None
    if isinstance(v, ALLOWED_SCALAR_TYPES):
        return v
    if isinstance(v, np.ndarray):
        if v.size > MAX_PARAM_ARRAY_ELEMENTS:
            raise ValueError(
                f"FittedParams[{key!r}]: ndarray size {v.size} exceeds "
                f"MAX_PARAM_ARRAY_ELEMENTS={MAX_PARAM_ARRAY_ELEMENTS}"
            )
        if v.dtype.kind not in _ALLOWED_NDARRAY_KINDS:
            raise ValueError(
                f"FittedParams[{key!r}]: ndarray dtype {v.dtype} not "
                f"allowed (numeric kinds only: "
                f"{sorted(_ALLOWED_NDARRAY_KINDS)})"
            )
        arr = v.copy()
        arr.flags.writeable = False
        return arr
    if isinstance(v, AbcMapping):
        raise ValueError(
            f"FittedParams[{key!r}]: nested mappings are not allowed "
            f"(one level only)"
        )
    if hasattr(v, "index") or hasattr(v, "columns"):
        raise ValueError(
            f"FittedParams[{key!r}]: value of type {type(v).__name__} "
            f"carries .index/.columns and is rejected as a potentially "
            f"indexed data structure"
        )
    raise ValueError(
        f"FittedParams[{key!r}]: type {type(v).__name__} is not an "
        f"allowed leaf type (allowed: int, float, bool, str, None, "
        f"numeric ndarray, or tuple/list thereof)"
    )


def _normalize_value(key: str, v: Any) -> Any:
    """Validate a top-level value. Lists become tuples; leaves deep-copied."""
    _reject_pandas(key, v)
    if isinstance(v, (tuple, list)):
        if len(v) > MAX_PARAM_SEQUENCE_LEN:
            raise ValueError(
                f"FittedParams[{key!r}]: sequence length {len(v)} exceeds "
                f"MAX_PARAM_SEQUENCE_LEN={MAX_PARAM_SEQUENCE_LEN}"
            )
        return tuple(
            _normalize_leaf(f"{key}[{i}]", elem) for i, elem in enumerate(v)
        )
    return _normalize_leaf(key, v)


def _validate_params_mapping(values: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and deep-copy a caller-supplied params mapping.

    Returns a fresh plain dict suitable for wrapping in MappingProxyType.
    Rejects pandas objects (wholesale) and anything outside the
    type/size whitelist.
    """
    if isinstance(values, (pd.Series, pd.DataFrame, pd.Index)):
        raise ValueError(
            f"FittedParams.values: pandas objects are forbidden as the "
            f"container (got {type(values).__name__})"
        )
    if not isinstance(values, AbcMapping):
        raise ValueError(
            f"FittedParams.values must be a Mapping, got "
            f"{type(values).__name__}"
        )
    if len(values) > MAX_PARAM_VALUES_ENTRIES:
        raise ValueError(
            f"FittedParams.values: {len(values)} entries exceeds "
            f"MAX_PARAM_VALUES_ENTRIES={MAX_PARAM_VALUES_ENTRIES}"
        )
    out: dict[str, Any] = {}
    for key, v in values.items():
        if not isinstance(key, str):
            raise ValueError(
                f"FittedParams.values: keys must be str, got key of type "
                f"{type(key).__name__}"
            )
        out[key] = _normalize_value(key, v)
    return out


@dataclass(frozen=True)
class FittedParams:
    """Immutable, leakage-proof container for fitted parameters.

    Construct via ``FittedParams.build(...)`` - the factory runs
    ``_validate_params_mapping`` and wraps the result in
    ``MappingProxyType`` before the dataclass is instantiated. Direct
    construction is supported for tests but callers should prefer
    ``build``; direct construction does **not** re-validate.

    Fields:

    - ``values``: read-only mapping of parameter name to value. The
      underlying dict is owned by this instance; external mutation of
      the caller's original mapping cannot affect it.
    - ``feature_name``: the name of the ``FittedFeatureSpec`` that
      produced these params. ``validate_fitted_params`` cross-checks
      this against the spec name at transform time.
    - ``version``: module-level ``FITTED_FEATURE_VERSION`` at build
      time. Mismatches are loud-failed.
    - ``fingerprint``: structural placeholder for future param
      fingerprinting (v3.7+). Left ``None`` in Step 1; frozen field
      so downstream code can begin reading it without a later
      contract break.
    """

    values: Mapping[str, Any]
    feature_name: str
    version: str
    fingerprint: str | None = None

    @classmethod
    def build(
        cls,
        values: Mapping[str, Any],
        feature_name: str,
        version: str = FITTED_FEATURE_VERSION,
        fingerprint: str | None = None,
    ) -> "FittedParams":
        validated = _validate_params_mapping(values)
        frozen = types.MappingProxyType(validated)
        return cls(
            values=frozen,
            feature_name=feature_name,
            version=version,
            fingerprint=fingerprint,
        )


@dataclass(frozen=True)
class FittedFeatureSpec:
    """Spec for a registered fitted feature.

    - ``fit_fn(df, **params) -> FittedParams``
    - ``transform_fn(df, fitted_params, **params) -> pd.Series``
    - ``param_names``: kwargs accepted by fit/transform beyond data
    - ``required_columns``: columns that must be present on the input
      frame for both phases
    - ``warmup_bars_fn``: kept for uniformity with FeatureSpec; see
      the module docstring for how fitted-feature warmup differs.
    """

    fit_fn: Callable[..., FittedParams]
    transform_fn: Callable[..., pd.Series]
    param_names: tuple[str, ...]
    required_columns: tuple[str, ...]
    warmup_bars_fn: Callable[[dict], int]


FITTED_FEATURE_REGISTRY: dict[str, FittedFeatureSpec] = {}


# ---------------------------------------------------------------------------
# hedge_ratio_ols - static OLS hedge ratio (v3.7 step 2)
# ---------------------------------------------------------------------------

_HEDGE_RATIO_OLS_NAME = "hedge_ratio_ols"
_HEDGE_RATIO_OLS_REQUIRED_COLUMNS: tuple[str, ...] = ("close", "close_ref")
_MIN_OLS_ROWS = 2


def _fit_hedge_ratio_ols(df: pd.DataFrame) -> FittedParams:
    """Fit a static OLS hedge ratio on the training window.

    Convention (locked):

    - y = df["close"] (primary leg)
    - x = df["close_ref"] (reference leg)
    - Model: y = alpha + beta * x + eps. Intercept is allowed during
      fit; slope is computed as Cov(x, y) / Var(x, ddof=0) which is
      the OLS slope of a regression *with* intercept. Only beta is
      retained in FittedParams - the intercept is absorbed into the
      mean of the resulting spread and centered away downstream by
      the z-score (not this function's concern).

    Loud-fails (ValueError) on: missing required columns, empty input,
    fewer than ``_MIN_OLS_ROWS`` rows, NaN in inputs, zero / non-finite
    variance in the reference leg, or a non-finite fitted beta. No
    silent fallback to a naive ratio; the caller gets a clear error.
    """
    missing = [c for c in _HEDGE_RATIO_OLS_REQUIRED_COLUMNS
               if c not in df.columns]
    if missing:
        raise ValueError(
            f"{_HEDGE_RATIO_OLS_NAME}.fit: missing required columns "
            f"{missing}"
        )
    if len(df) == 0:
        raise ValueError(
            f"{_HEDGE_RATIO_OLS_NAME}.fit: empty input frame"
        )
    if len(df) < _MIN_OLS_ROWS:
        raise ValueError(
            f"{_HEDGE_RATIO_OLS_NAME}.fit: need >= {_MIN_OLS_ROWS} rows, "
            f"got {len(df)}"
        )
    y = df["close"].astype(float)
    x = df["close_ref"].astype(float)
    if y.isna().any() or x.isna().any():
        raise ValueError(
            f"{_HEDGE_RATIO_OLS_NAME}.fit: NaN values present in "
            f"required inputs"
        )
    var_x = float(x.var(ddof=0))
    if var_x == 0.0 or not np.isfinite(var_x):
        raise ValueError(
            f"{_HEDGE_RATIO_OLS_NAME}.fit: reference series has zero "
            f"or non-finite variance (singular design)"
        )
    cov_xy = float((x * y).mean() - x.mean() * y.mean())
    beta = cov_xy / var_x
    if not np.isfinite(beta):
        raise ValueError(
            f"{_HEDGE_RATIO_OLS_NAME}.fit: fitted beta is non-finite "
            f"({beta!r})"
        )
    return FittedParams.build(
        values={"beta": float(beta)},
        feature_name=_HEDGE_RATIO_OLS_NAME,
    )


def _transform_hedge_ratio_ols(
    df: pd.DataFrame, params: FittedParams
) -> pd.Series:
    """Transform: spread = close - beta * close_ref.

    Reads only ``df`` and the frozen ``params``; no refit, no external
    state. Index-preserving, non-mutating. Loud-fails (ValueError) on
    missing required columns or a params object that does not belong
    to ``hedge_ratio_ols``.
    """
    validate_fitted_params(params, _HEDGE_RATIO_OLS_NAME)
    missing = [c for c in _HEDGE_RATIO_OLS_REQUIRED_COLUMNS
               if c not in df.columns]
    if missing:
        raise ValueError(
            f"{_HEDGE_RATIO_OLS_NAME}.transform: missing required "
            f"columns {missing}"
        )
    beta = float(params.values["beta"])
    y = df["close"].astype(float)
    x = df["close_ref"].astype(float)
    return y - beta * x


def _warmup_hedge_ratio_ols(_params: dict) -> int:
    """Static fit has no rolling warmup on the transform path."""
    return 0


FITTED_FEATURE_REGISTRY[_HEDGE_RATIO_OLS_NAME] = FittedFeatureSpec(
    fit_fn=_fit_hedge_ratio_ols,
    transform_fn=_transform_hedge_ratio_ols,
    param_names=(),
    required_columns=_HEDGE_RATIO_OLS_REQUIRED_COLUMNS,
    warmup_bars_fn=_warmup_hedge_ratio_ols,
)


def validate_fitted_params(params: FittedParams, spec_name: str) -> None:
    """Assert params originate from ``spec_name`` at the current version.

    Loud-fail entrypoint. The engine (Step 3) will call this before any
    transform to guarantee the fit/transform pairing is consistent and
    that no stale params from a prior module version leak through.
    """
    if not isinstance(params, FittedParams):
        raise ValueError(
            f"validate_fitted_params: expected FittedParams, got "
            f"{type(params).__name__}"
        )
    if params.feature_name != spec_name:
        raise ValueError(
            f"validate_fitted_params: feature_name mismatch - params "
            f"from {params.feature_name!r}, spec {spec_name!r}"
        )
    if params.version != FITTED_FEATURE_VERSION:
        raise ValueError(
            f"validate_fitted_params: version mismatch - params "
            f"{params.version!r}, module {FITTED_FEATURE_VERSION!r}"
        )


__all__ = [
    "FITTED_FEATURE_REGISTRY",
    "FITTED_FEATURE_VERSION",
    "FittedFeatureSpec",
    "FittedParams",
    "MAX_PARAM_ARRAY_ELEMENTS",
    "MAX_PARAM_SEQUENCE_LEN",
    "MAX_PARAM_VALUES_ENTRIES",
    "validate_fitted_params",
]
