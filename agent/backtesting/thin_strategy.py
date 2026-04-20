"""Thin strategy contract v1.0 (transitional).

v3.5 ships a **transitional** contract, explicitly not full layer purity:

    def func(df: pd.DataFrame, features: Mapping[str, pd.Series]) -> pd.Series

The strategy body is permitted to read `df.index` (for return-index
alignment) and nothing else from `df`. All actual data access must flow
through `features`. This constraint is enforced by the AST test in
tests/unit/test_thin_strategy_contract.py.

v2.0 (deferred to a later phase) removes `df` from the signature
entirely - the engine will pass only `features`. Keeping `df` in the
signature here lets the engine route legacy `func(df)` strategies and
thin strategies through a single call site with one metadata check,
avoiding a dual-routing regime across 9 strategies at once.

declare_thin stamps three pieces of metadata on the returned callable:

- _thin_contract_version: pinned to "1.0" so the engine can detect
  thin strategies with a single hasattr check
- _feature_requirements: list[FeatureRequirement] describing exactly
  which feature primitives the strategy needs and with which params;
  the engine resolves these at fold boundaries via build_features_for
- _sizing_spec: optional dict describing the strategy's position
  sizing regime; absent means the engine keeps its legacy ±1 path

The contract forbids mutating shared state, reading raw OHLCV columns
off `df`, or recomputing indicators inside the strategy body.
"""

from __future__ import annotations

import functools
from dataclasses import dataclass
from typing import Any, Callable, Literal, Mapping

import pandas as pd

from agent.backtesting.features import FEATURE_REGISTRY


THIN_CONTRACT_VERSION = "1.0"


SourceRole = Literal["primary", "reference"]


@dataclass(frozen=True)
class FeatureRequirement:
    """A single feature request by a thin strategy.

    - name: registry key into FEATURE_REGISTRY
    - params: kwargs forwarded to the feature function
    - alias: key under which the computed series is placed in the
      features mapping handed to the strategy. Defaults to `name`.
    - source_role: which asset leg supplies the columns for this
      feature. None (default) is equivalent to "primary" and preserves
      v3.5 single-frame resolution byte-for-byte. "reference" pulls
      from the reference leg; only meaningful in the multi-asset path.
      Multi-asset primitives that already read both legs via convention
      (columns `close` + `close_ref`) do not need source_role set.
    """

    name: str
    params: dict[str, Any]
    alias: str | None = None
    source_role: SourceRole | None = None

    def resolved_alias(self) -> str:
        return self.alias or self.name


def declare_thin(
    func: Callable[[pd.DataFrame, Mapping[str, pd.Series]], pd.Series],
    *,
    feature_requirements: list[FeatureRequirement],
    sizing_spec: dict[str, Any] | None = None,
) -> Callable[..., pd.Series]:
    """Stamp thin contract metadata and return a dual-arity wrapper.

    The wrapper accepts either the engine's canonical `(df, features)`
    call or a legacy `(df)` call — in the legacy case it auto-resolves
    the declared feature requirements via build_features_for. This
    preserves the v3.4 `strategy(df)` call contract for determinism
    suites and registry consumers while the engine always routes
    through the explicit two-arg form.

    Metadata `_thin_contract_version`, `_feature_requirements`, and
    `_sizing_spec` is stamped on the returned wrapper so the engine
    detects thin strategies with a single hasattr check.
    """
    for req in feature_requirements:
        if req.name not in FEATURE_REGISTRY:
            raise ValueError(
                f"declare_thin: unknown feature '{req.name}'; "
                f"registered={sorted(FEATURE_REGISTRY)}"
            )
    reqs = list(feature_requirements)

    @functools.wraps(func)
    def wrapper(
        df: pd.DataFrame,
        features: Mapping[str, pd.Series] | None = None,
    ) -> pd.Series:
        if features is None:
            features = build_features_for(reqs, df)
        return func(df, features)

    wrapper._thin_contract_version = THIN_CONTRACT_VERSION  # type: ignore[attr-defined]
    wrapper._feature_requirements = reqs  # type: ignore[attr-defined]
    wrapper._sizing_spec = dict(sizing_spec) if sizing_spec else None  # type: ignore[attr-defined]
    wrapper._thin_unwrapped = func  # type: ignore[attr-defined]
    return wrapper


def is_thin_strategy(func: Callable) -> bool:
    return getattr(func, "_thin_contract_version", None) == THIN_CONTRACT_VERSION


def build_features_for(
    requirements: list[FeatureRequirement],
    df: pd.DataFrame,
) -> dict[str, pd.Series]:
    """Resolve a strategy's feature requirements against a DataFrame.

    Single owner of feature computation from the engine's perspective.
    Raises with a typed message when a required column is missing; the
    integrity layer surfaces these as FEATURE_INCOMPLETE.
    """
    features: dict[str, pd.Series] = {}
    for req in requirements:
        spec = FEATURE_REGISTRY[req.name]
        missing = [c for c in spec.required_columns if c not in df.columns]
        if missing:
            raise KeyError(
                f"thin_strategy: feature '{req.name}' needs columns "
                f"{spec.required_columns}, missing {missing} from frame"
            )
        args = [df[c] for c in spec.required_columns]
        kwargs = {k: v for k, v in req.params.items() if k in spec.param_names}
        features[req.resolved_alias()] = spec.fn(*args, **kwargs)
    return features


def build_features_for_multi(
    requirements: list[FeatureRequirement],
    frames: Mapping[str, pd.DataFrame],
) -> dict[str, pd.Series]:
    """Resolve thin strategy requirements against aligned multi-asset frames.

    `frames` must contain a "primary" entry; "reference" is optional.
    When a reference frame is supplied, its `close` column is exposed
    to the feature resolver as `close_ref` on a combined primary view -
    this mirrors how the bytewise pin test feeds a single frame with
    both columns, keeping multi-asset primitive output byte-identical
    to the single-frame path.

    A requirement with `source_role="reference"` is resolved directly
    against the reference frame (useful for single-asset features
    computed on the reference leg). All other requirements resolve
    against the combined-primary view.

    v3.6 scope: exactly two legs (primary + optional reference). The
    single-frame `build_features_for` is unchanged and still owns the
    v3.5 bytewise pin path.
    """
    if "primary" not in frames:
        raise KeyError("build_features_for_multi requires a 'primary' frame")
    primary = frames["primary"]
    reference = frames.get("reference")

    if reference is not None:
        combined = primary.copy()
        combined["close_ref"] = reference["close"]
    else:
        combined = primary

    primary_reqs: list[FeatureRequirement] = []
    reference_reqs: list[FeatureRequirement] = []
    for req in requirements:
        if req.source_role == "reference":
            reference_reqs.append(req)
        else:
            primary_reqs.append(req)

    features: dict[str, pd.Series] = {}
    if primary_reqs:
        features.update(build_features_for(primary_reqs, combined))
    if reference_reqs:
        if reference is None:
            raise KeyError(
                "thin_strategy: source_role='reference' requires a reference "
                "frame in frames['reference']"
            )
        features.update(build_features_for(reference_reqs, reference))
    return features


def validate_thin_strategy_output(sig: pd.Series, index: pd.Index) -> None:
    """Assert shape, dtype and index conformance of a thin strategy output.

    A thin strategy must return an int-typed Series whose index equals
    the engine-provided df.index. Any violation raises ValueError so
    the engine surfaces the misbehaviour as a typed failure rather
    than silently propagating bad signals.
    """
    if not isinstance(sig, pd.Series):
        raise ValueError(
            f"thin_strategy output must be pd.Series, got {type(sig).__name__}"
        )
    if not sig.index.equals(index):
        raise ValueError(
            "thin_strategy output index does not match input df.index"
        )
    if sig.dtype.kind not in {"i", "f"}:
        raise ValueError(
            f"thin_strategy output dtype must be numeric, got {sig.dtype}"
        )


__all__ = [
    "FeatureRequirement",
    "SourceRole",
    "THIN_CONTRACT_VERSION",
    "build_features_for",
    "build_features_for_multi",
    "declare_thin",
    "is_thin_strategy",
    "validate_thin_strategy_output",
]
