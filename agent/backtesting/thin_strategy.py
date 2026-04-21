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

v3.7 step 3: fitted feature integration. `FeatureRequirement.feature_kind`
discriminates between ordinary (`"plain"`) features resolved against the
``FEATURE_REGISTRY`` and fitted (`"fitted"`) features resolved against
the ``FITTED_FEATURE_REGISTRY`` via a two-phase fit-then-transform
lifecycle. The fold-aware helpers ``build_features_train`` and
``build_features_test`` (plus the multi-asset variants) own this
lifecycle and enforce train-only fitting / test-only transform with
frozen params. The plain-path helpers ``build_features_for`` and
``build_features_for_multi`` structurally reject fitted requirements -
there is no silent fallback.
"""

from __future__ import annotations

import functools
from dataclasses import dataclass, field
from typing import Any, Callable, Literal, Mapping

import pandas as pd

from agent.backtesting.features import FEATURE_REGISTRY
from agent.backtesting.fitted_features import (
    FITTED_FEATURE_REGISTRY,
    FittedParams,
    validate_fitted_params,
)


THIN_CONTRACT_VERSION = "1.0"


SourceRole = Literal["primary", "reference"]
FeatureKind = Literal["plain", "fitted"]


@dataclass(frozen=True)
class FeatureRequirement:
    """A single feature request by a thin strategy.

    - name: registry key into FEATURE_REGISTRY (kind="plain") or into
      FITTED_FEATURE_REGISTRY (kind="fitted").
    - params: kwargs forwarded to the feature function (both phases
      for fitted features).
    - alias: key under which the computed series is placed in the
      features mapping handed to the strategy. Defaults to `name`.
    - source_role: which asset leg supplies the columns for this
      feature. None (default) is equivalent to "primary" and preserves
      v3.5 single-frame resolution byte-for-byte. "reference" pulls
      from the reference leg; only meaningful in the multi-asset path.
      Multi-asset primitives that already read both legs via convention
      (columns `close` + `close_ref`) do not need source_role set.
      In Step 3, fitted features are resolved against the combined
      primary+reference view only; `source_role="reference"` on a
      fitted requirement is rejected.
    - feature_kind: "plain" (default) routes through FEATURE_REGISTRY
      and the v3.5 pure-feature path. "fitted" routes through
      FITTED_FEATURE_REGISTRY and requires the fold-aware train/test
      helpers; the plain-path helpers reject fitted requirements
      loudly to prevent silent fallback.
    """

    name: str
    params: dict[str, Any] = field(default_factory=dict)
    alias: str | None = None
    source_role: SourceRole | None = None
    feature_kind: FeatureKind = "plain"

    def resolved_alias(self) -> str:
        return self.alias or self.name

    def is_fitted(self) -> bool:
        return self.feature_kind == "fitted"


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

    A requirement is validated against the registry matching its
    `feature_kind`. Strategies that declare any fitted requirement
    cannot be auto-resolved through the legacy one-arg call path -
    the auto-resolve step runs the plain-path ``build_features_for``
    which will loud-fail on fitted requirements. Such strategies must
    be driven by the engine via the train/test helpers.
    """
    for req in feature_requirements:
        if req.feature_kind == "plain":
            if req.name not in FEATURE_REGISTRY:
                raise ValueError(
                    f"declare_thin: unknown feature '{req.name}' "
                    f"(kind=plain); registered={sorted(FEATURE_REGISTRY)}"
                )
        elif req.feature_kind == "fitted":
            if req.name not in FITTED_FEATURE_REGISTRY:
                raise ValueError(
                    f"declare_thin: unknown fitted feature "
                    f"'{req.name}' (kind=fitted); "
                    f"registered={sorted(FITTED_FEATURE_REGISTRY)}"
                )
        else:  # pragma: no cover - Literal guards this at type level
            raise ValueError(
                f"declare_thin: unknown feature_kind "
                f"{req.feature_kind!r}"
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


def _reject_fitted_requirements(
    requirements: list[FeatureRequirement], caller: str
) -> None:
    fitted = [r.name for r in requirements if r.is_fitted()]
    if fitted:
        raise ValueError(
            f"{caller}: fitted feature(s) {fitted} cannot be resolved "
            f"via the plain path; use build_features_train / "
            f"build_features_test (or the _multi variants) so fit "
            f"runs on the training slice and transform reuses the "
            f"frozen params on the test slice"
        )


def _resolve_plain_requirement(
    req: FeatureRequirement, df: pd.DataFrame
) -> pd.Series:
    spec = FEATURE_REGISTRY[req.name]
    missing = [c for c in spec.required_columns if c not in df.columns]
    if missing:
        raise KeyError(
            f"thin_strategy: feature '{req.name}' needs columns "
            f"{spec.required_columns}, missing {missing} from frame"
        )
    args = [df[c] for c in spec.required_columns]
    kwargs = {k: v for k, v in req.params.items() if k in spec.param_names}
    return spec.fn(*args, **kwargs)


def _fitted_kwargs(req: FeatureRequirement) -> dict[str, Any]:
    spec = FITTED_FEATURE_REGISTRY[req.name]
    return {k: v for k, v in req.params.items() if k in spec.param_names}


def build_features_for(
    requirements: list[FeatureRequirement],
    df: pd.DataFrame,
) -> dict[str, pd.Series]:
    """Resolve a strategy's *plain* feature requirements against a DataFrame.

    Single owner of plain feature computation from the engine's
    perspective. Raises with a typed message when a required column is
    missing; the integrity layer surfaces these as FEATURE_INCOMPLETE.

    Fitted requirements are rejected: fitted features have a two-phase
    lifecycle and must be driven via ``build_features_train`` /
    ``build_features_test``. No silent fallback.
    """
    _reject_fitted_requirements(requirements, "build_features_for")
    features: dict[str, pd.Series] = {}
    for req in requirements:
        features[req.resolved_alias()] = _resolve_plain_requirement(req, df)
    return features


def build_features_for_multi(
    requirements: list[FeatureRequirement],
    frames: Mapping[str, pd.DataFrame],
) -> dict[str, pd.Series]:
    """Resolve *plain* thin strategy requirements on aligned multi-asset frames.

    See v3.6 docstring below for the combined-primary semantics.
    Fitted requirements are rejected here - use
    ``build_features_train_multi`` / ``build_features_test_multi``.

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
    _reject_fitted_requirements(requirements, "build_features_for_multi")
    combined, reference = _build_combined_multi_view(frames)

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


def _build_combined_multi_view(
    frames: Mapping[str, pd.DataFrame],
) -> tuple[pd.DataFrame, pd.DataFrame | None]:
    """Shared helper: validate frames and build the primary+close_ref view.

    Returns (combined_primary_view, reference_frame_or_None). Reused
    by both the plain and the fitted multi-asset paths so that their
    column projection semantics stay byte-identical.
    """
    if "primary" not in frames:
        raise KeyError(
            "thin_strategy: multi-asset resolution requires a "
            "'primary' frame in frames"
        )
    primary = frames["primary"]
    reference = frames.get("reference")
    if reference is not None:
        combined = primary.copy()
        combined["close_ref"] = reference["close"]
    else:
        combined = primary
    return combined, reference


def _fit_and_transform_fitted(
    req: FeatureRequirement, df: pd.DataFrame
) -> tuple[pd.Series, FittedParams]:
    """Fit a fitted feature on ``df`` and transform the same frame once.

    Used by the training-phase helpers. Factors the per-requirement
    fit+transform so multi-asset and single-asset paths stay in sync.
    """
    spec = FITTED_FEATURE_REGISTRY[req.name]
    missing = [c for c in spec.required_columns if c not in df.columns]
    if missing:
        raise KeyError(
            f"thin_strategy: fitted feature '{req.name}' needs "
            f"columns {spec.required_columns}, missing {missing} "
            f"from frame"
        )
    kwargs = _fitted_kwargs(req)
    fp = spec.fit_fn(df, **kwargs)
    validate_fitted_params(fp, req.name)
    series = spec.transform_fn(df, fp, **kwargs)
    return series, fp


def _transform_fitted_only(
    req: FeatureRequirement,
    df: pd.DataFrame,
    fp: FittedParams,
) -> pd.Series:
    """Transform a fitted feature on ``df`` using ``fp``; no refit."""
    spec = FITTED_FEATURE_REGISTRY[req.name]
    missing = [c for c in spec.required_columns if c not in df.columns]
    if missing:
        raise KeyError(
            f"thin_strategy: fitted feature '{req.name}' needs "
            f"columns {spec.required_columns}, missing {missing} "
            f"from frame"
        )
    validate_fitted_params(fp, req.name)
    kwargs = _fitted_kwargs(req)
    return spec.transform_fn(df, fp, **kwargs)


def _reject_fitted_reference_source(req: FeatureRequirement) -> None:
    if req.is_fitted() and req.source_role == "reference":
        raise ValueError(
            f"thin_strategy: fitted feature {req.name!r} with "
            f"source_role='reference' is not supported in v3.7 "
            f"step 3; fitted features resolve against the combined "
            f"primary+reference view"
        )


def build_features_train(
    requirements: list[FeatureRequirement],
    df: pd.DataFrame,
) -> tuple[dict[str, pd.Series], dict[str, FittedParams]]:
    """Training-phase feature build with fold-local fitted params.

    For each requirement:

    - plain: resolve via FEATURE_REGISTRY on ``df`` exactly like
      ``build_features_for`` (bytewise identical output).
    - fitted: call ``fit_fn(df, **params)`` once to produce
      ``FittedParams``, then call ``transform_fn(df, fp, **params)``
      on the same training slice for downstream feature assembly.
      The params are stored under the requirement's resolved alias.

    Returns ``(features, fitted_params)``. ``fitted_params`` has one
    entry per fitted requirement, keyed by ``resolved_alias()``. The
    caller owns the mapping for the fold and must pass it to
    ``build_features_test`` on the matching test slice. No module-
    level cache, no retained train frame, no cross-fold state.
    """
    features: dict[str, pd.Series] = {}
    fitted_params: dict[str, FittedParams] = {}
    for req in requirements:
        alias = req.resolved_alias()
        if req.is_fitted():
            series, fp = _fit_and_transform_fitted(req, df)
            features[alias] = series
            fitted_params[alias] = fp
        else:
            features[alias] = _resolve_plain_requirement(req, df)
    return features, fitted_params


def build_features_test(
    requirements: list[FeatureRequirement],
    df: pd.DataFrame,
    fitted_params: Mapping[str, FittedParams],
) -> dict[str, pd.Series]:
    """Test-phase feature build. Reuses frozen fitted_params; no refit.

    For each requirement:

    - plain: resolve via FEATURE_REGISTRY on ``df``.
    - fitted: look up the alias in ``fitted_params`` and call
      ``transform_fn(df, fp, **params)``. Raises KeyError if the
      caller did not supply params for a fitted requirement (wrong
      fold? training phase skipped? silent fallback would leak).

    Does NOT call any ``fit_fn``. Structural: there is no code path
    from ``build_features_test`` to a fit invocation.
    """
    features: dict[str, pd.Series] = {}
    for req in requirements:
        alias = req.resolved_alias()
        if req.is_fitted():
            if alias not in fitted_params:
                raise KeyError(
                    f"build_features_test: fitted feature "
                    f"{req.name!r} (alias {alias!r}) has no "
                    f"fold-local fitted params; the training phase "
                    f"must fit these before the test phase runs"
                )
            fp = fitted_params[alias]
            features[alias] = _transform_fitted_only(req, df, fp)
        else:
            features[alias] = _resolve_plain_requirement(req, df)
    return features


def build_features_train_multi(
    requirements: list[FeatureRequirement],
    frames: Mapping[str, pd.DataFrame],
) -> tuple[dict[str, pd.Series], dict[str, FittedParams]]:
    """Multi-asset training-phase build.

    Combines primary + reference frames the same way
    ``build_features_for_multi`` does (reference ``close`` projected
    as ``close_ref`` on a primary copy), then fits and resolves
    requirements against the combined view (plain + fitted) or the
    reference frame (plain only; ``source_role='reference'`` is not
    supported on fitted requirements in step 3).
    """
    combined, reference = _build_combined_multi_view(frames)

    primary_reqs: list[FeatureRequirement] = []
    reference_reqs: list[FeatureRequirement] = []
    for req in requirements:
        _reject_fitted_reference_source(req)
        if req.source_role == "reference":
            reference_reqs.append(req)
        else:
            primary_reqs.append(req)

    features, fitted_params = build_features_train(primary_reqs, combined)
    if reference_reqs:
        if reference is None:
            raise KeyError(
                "thin_strategy: source_role='reference' requires a "
                "reference frame in frames['reference']"
            )
        _reject_fitted_requirements(
            reference_reqs, "build_features_train_multi[reference]"
        )
        features.update(build_features_for(reference_reqs, reference))
    return features, fitted_params


def build_features_test_multi(
    requirements: list[FeatureRequirement],
    frames: Mapping[str, pd.DataFrame],
    fitted_params: Mapping[str, FittedParams],
) -> dict[str, pd.Series]:
    """Multi-asset test-phase build. Reuses frozen fitted_params."""
    combined, reference = _build_combined_multi_view(frames)

    primary_reqs: list[FeatureRequirement] = []
    reference_reqs: list[FeatureRequirement] = []
    for req in requirements:
        _reject_fitted_reference_source(req)
        if req.source_role == "reference":
            reference_reqs.append(req)
        else:
            primary_reqs.append(req)

    features = build_features_test(primary_reqs, combined, fitted_params)
    if reference_reqs:
        if reference is None:
            raise KeyError(
                "thin_strategy: source_role='reference' requires a "
                "reference frame in frames['reference']"
            )
        _reject_fitted_requirements(
            reference_reqs, "build_features_test_multi[reference]"
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
    "FeatureKind",
    "FeatureRequirement",
    "SourceRole",
    "THIN_CONTRACT_VERSION",
    "build_features_for",
    "build_features_for_multi",
    "build_features_test",
    "build_features_test_multi",
    "build_features_train",
    "build_features_train_multi",
    "declare_thin",
    "is_thin_strategy",
    "validate_thin_strategy_output",
]
