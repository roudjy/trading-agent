# ADR-007: Fitted Feature Abstraction

Status: Accepted
Date: 2026-04-21
Phase: v3.7 (fitted feature abstraction)
Supersedes: -
Superseded by: -
Related: ADR-006 (thin contract v2.0 deferred)

## Context

The feature layer up to v3.6 models every feature as a one-shot pure
transform: `f(df) -> pd.Series`. `FeatureSpec` captures this shape,
and `FEATURE_REGISTRY` holds the canonical primitives (returns,
moving averages, z-score, spread, etc.). This is sufficient for any
feature whose value at bar `t` depends only on a deterministic
window of input columns up to `t`.

A class of features does **not** fit this shape:

- **Static OLS hedge ratio.** The hedge ratio `beta` between two
  assets is the output of a regression over a *training window*. The
  statistically correct way to use it in a walk-forward evaluation is
  to fit `beta` on the training slice and apply the *frozen* `beta`
  when constructing spreads on the test slice. Refitting `beta` on
  the test slice — or, equivalently, fitting it on the full series —
  leaks test information into the signal.
- **Future regressions / PCA-like transforms.** Any feature that
  requires a fitted parameter set (coefficients, loadings, means,
  variances learned from history) has the same shape: one training
  phase, many transforms, frozen params.

Without an explicit fit/transform abstraction:

- Walk-forward semantics are ambiguous. It is not visible at the
  feature-layer boundary which features carry fitted state, so it is
  not visible where fit must happen and where transform must happen.
- Leakage risk rises. A feature implementation is free to peek at
  the full frame inside a supposedly one-shot transform. The engine
  has no structural signal to route fit separately from transform.
- Pairs spread construction is statistically incorrect. The v3.6
  `pairs_zscore` strategy takes a scalar `hedge_ratio` parameter. In
  production this is effectively a researcher-guessed constant or a
  full-window OLS fit — both unsuitable for honest walk-forward
  evaluation of a pairs edge.

v3.7 introduces the minimum abstraction needed to resolve this
safely without touching the v3.5/v3.6 plain feature path.

## Decision

v3.7 adds a **parallel** feature abstraction alongside `FeatureSpec`,
specifically for features that require a fit/transform lifecycle:

- `FittedFeatureSpec(fit_fn, transform_fn, param_names,
  required_columns, warmup_bars_fn)` — a frozen dataclass describing
  a two-phase feature. `fit_fn(df, **params) -> FittedParams`.
  `transform_fn(df, fitted_params, **params) -> pd.Series`.
- `FittedParams` — a frozen dataclass holding the fitted parameter
  mapping. `values` is stored as `types.MappingProxyType` over a
  deep-validated, deep-copied dict. Numpy arrays are copied and
  `flags.writeable=False`; lists become tuples; nested dicts are
  rejected; pandas objects are rejected by explicit sentinel. The
  construction factory enforces hard caps on keys, sequence length,
  and array element count.
- `FITTED_FEATURE_REGISTRY: dict[str, FittedFeatureSpec]` — a
  parallel registry holding the canonical fitted features. In v3.7
  it holds `hedge_ratio_ols` (step 2) and `spread_zscore_ols`
  (step 4).
- `FeatureRequirement.feature_kind: Literal["plain", "fitted"]` —
  explicit discriminator on the strategy→feature contract. Default
  `"plain"` preserves every v3.5/v3.6 path byte-identically.
- `build_features_train / build_features_test` and their multi-asset
  counterparts — fold-aware builders that fit on the training slice
  and transform on the evaluation slice using the frozen params
  returned by fit.
- Engine sequencing — `BacktestEngine` materializes each fold's
  training slice and forwards it to `_invoke_strategy`. When a
  strategy declares any fitted requirement, `_invoke_strategy`
  routes through the train/test helpers. Non-fitted strategies
  ignore the new kwargs and follow the unchanged plain path.
- `pairs_zscore_strategie` gains `use_fitted_hedge_ratio: bool =
  False`. Default behavior is byte-identical to v3.6 and emits the
  same `spread_zscore` plain requirement. When `True`, the strategy
  emits a `spread_zscore_ols` fitted requirement instead.

The strategy layer remains signal generation only. The engine owns
fold slicing and fit/test sequencing. The feature layer owns the
fitted transforms themselves. The evaluation layer is untouched.

## Rationale

### Why a parallel registry rather than extending `FeatureSpec`?

- **Two different lifecycles.** `FeatureSpec` is a single callable.
  A fitted feature is fundamentally two callables plus a typed
  parameter artifact. Forcing both into one dataclass would either
  weaken `FeatureSpec`'s contract for all existing features or
  overload it with optional fields whose presence silently changes
  behavior.
- **Zero risk to existing bytewise pins.** The v3.5 Tier 1 digests
  and the v3.6 multi-asset parity pins all resolve through
  `FEATURE_REGISTRY` and `build_features_for{_multi}`. A parallel
  registry and parallel builders ensure that no plain-feature call
  site can be accidentally re-routed through the fitted path, and no
  fitted call site can reach through `FeatureSpec`'s shape.
- **Explicit at the strategy boundary.** `feature_kind="fitted"` is
  a required, visible declaration. There is no implicit inference
  from the feature name or from the registry it lives in. This makes
  fit/transform lifecycle an auditable property of each
  `FeatureRequirement`.

### Why are fitted params frozen and heavily restricted?

- **Determinism.** Params flow from fit to transform across function
  calls; any mutation between phases would silently corrupt signal.
  Freezing at construction time makes accidental mutation a
  `TypeError` / `FrozenInstanceError` instead of a bytewise drift.
- **No reference retention.** Deep copy on construction plus
  `flags.writeable=False` on arrays guarantees that mutating,
  shuffling, or destroying the training frame after fit cannot
  change a subsequent transform. This is spy-pinned in
  `tests/unit/test_fitted_features.py`.
- **Fingerprintable.** Values are restricted to small serializable
  primitives (int, float, bool, str, None, small numeric ndarray,
  small tuple/list of leaves). This keeps the door open for
  fingerprinting, pinning in regression tests, or persisting params
  without surprises. The `fingerprint` field is a reserved
  placeholder in v3.7; computation is deferred.
- **Leakage sentinel.** Pandas objects are rejected at construction
  with a named error. It is structurally impossible to stuff a
  training DataFrame into params by accident.

### Why is fitted hedge ratio opt-in for pairs, not the new default?

- **Byte-identical default.** The v3.6 Tier 1 `pairs_zscore` bytewise
  pin is load-bearing for the multi-asset engine path. Flipping the
  default would drift that pin and force a re-pin in the same phase
  that introduces the abstraction.
- **Clean rollback.** An opt-in flag lets the system run the fitted
  path on candidate runs and research experiments without touching
  the baseline. Flipping the default — when warranted by evidence —
  is a separate, single-purpose change.
- **Auditable separation.** `use_fitted_hedge_ratio=False` and
  `use_fitted_hedge_ratio=True` are two distinct strategy
  configurations with distinct `FeatureRequirement` shapes. No
  silent switch; no ambient setting.

### Why keep engine wiring minimal and explicit?

- **Single fit point per fold.** The engine materializes each fold's
  training slice exactly once, inside the fold loop, and passes it
  through `_simuleer_detailed → _invoke_strategy`. Fit runs once in
  `_resolve_fitted_features`; the resulting params live only in that
  stack frame and are consumed by the transform call in the same
  function. No module-level cache, no `self`-state, no cross-fold
  reuse.
- **Loud fail.** If a fitted requirement reaches
  `_resolve_fitted_features` without a `train_frame` supplied by the
  caller, the engine raises `ValueError` with a message that names
  the missing slice and the fold responsibility. Silent fallback to
  full-window fit is not a path that exists.
- **Default path untouched.** Non-fitted strategies never enter the
  fitted resolver. `_invoke_strategy` checks `any_fitted` from the
  requirement list before routing; when false, the v3.6
  `build_features_for{_multi}` path runs exactly as before.

### Alternatives considered and rejected

- **Extend every feature into a unified stateful abstraction
  immediately.** Rejected: unnecessary breadth during a refactor
  whose scope is narrow, and a guaranteed bytewise-pin regression
  surface for features that have zero need for a fit phase.
- **Auto-detect fitted features from the feature name or body.**
  Rejected: removes the auditable boundary at the strategy
  declaration and makes lifecycle an implicit property of where a
  name happens to be registered.
- **Change the default `pairs_zscore` behavior to fitted in the same
  phase.** Rejected: drifts the v3.6 Tier 1 bytewise pin inside the
  phase that introduces the abstraction, entangling two decisions
  that should be separable.
- **Store training data or model objects inside `FittedParams`.**
  Rejected: breaks determinism (references into caller-owned
  frames), breaks fingerprintability, breaks persistence, and
  invites leakage by construction. The sentinel-based validator
  refuses this shape.
- **Refit per bar on a rolling window as a general policy.**
  Rejected as the v3.7 default: conflates a separate research
  question (time-varying hedge ratio) with the immediate goal
  (honest walk-forward semantics for static fitted features). A
  rolling-fit abstraction can be added later on top of this one
  without revisiting its shape.

## Walk-forward semantics (pinned by this ADR)

For each fold produced by the walk-forward framework:

1. The engine selects the fold's training slice (`train_bounds`) and
   materializes `train_frame` (plus `train_reference_frame` when the
   strategy is multi-asset) as an `iloc` slice copy of the asset
   context's frame.
2. The engine calls `_invoke_strategy(df, ..., train_frame=...,
   train_reference_frame=...)`. `df` is the evaluation slice for
   that fold.
3. If any declared `FeatureRequirement` has
   `feature_kind == "fitted"`, the engine routes through
   `_resolve_fitted_features`, which calls
   `build_features_train{_multi}` on the training slice and
   `build_features_test{_multi}` on the evaluation slice using the
   params returned by train.
4. `fit_fn` runs exactly once per fold on the training slice. The
   returned `FittedParams` are frozen and fold-local. They do not
   escape the function frame of `_resolve_fitted_features`.
5. `transform_fn` runs on the evaluation slice using those frozen
   params. The evaluation slice never influences params.
6. There is no refit on the test slice. There is no cross-fold
   param reuse. There is no module-level cache and no `self` state.
7. Train-slice transform may also occur when the current feature
   assembly flow requires the same feature on both phases (for
   example, when a downstream feature in the same requirement list
   consumes the fitted feature's train-time output). The fitted
   params used on the train-time transform are the same params
   returned by the single fit call.

The default (non-fitted) feature path is unchanged. Strategies that
declare only `feature_kind="plain"` requirements — which is every
Tier 1 strategy's default configuration as of v3.7 — follow the v3.6
`build_features_for{_multi}` path byte-for-byte.

## Scope of v3.7 (what this ADR covers)

v3.7 delivers:

- the fitted feature abstraction (`FittedFeatureSpec`,
  `FittedParams`, parallel registry, validator, hard caps,
  fingerprint placeholder);
- two registered fitted features: `hedge_ratio_ols` and
  `spread_zscore_ols`;
- `FeatureRequirement.feature_kind` discriminator and fold-aware
  train/test builders;
- engine fold-loop wiring that materializes the training slice,
  forwards it through `_simuleer_detailed → _invoke_strategy`, and
  routes fitted requirements through `_resolve_fitted_features`;
- `pairs_zscore_strategie(..., use_fitted_hedge_ratio=False)` as an
  explicit opt-in, default-off flag.

v3.7 does **not** deliver — and this is deliberate:

- A unified thin strategy v2.0 contract. ADR-006 records the
  deferral and trigger conditions; v3.7 introduces one of the
  triggers (fit/transform abstraction) but does not itself migrate
  any strategy to `func(features)`.
- Broader strategy migration to the fitted path. Only
  `pairs_zscore` gains an opt-in flag; SMA crossover and z-score
  mean reversion are unchanged.
- Generalized lineage or persistence for fitted params. The
  `fingerprint` placeholder reserves the surface; computation and
  persistence are out of scope.
- Evaluation hardening, exit diagnostics, or signal-quality
  telemetry tied to fitted features.
- Portfolio-level or regime-level work.
- Rolling / time-varying fitted parameters. The v3.7 abstraction is
  static-fit-per-fold; rolling-fit is a future, additive shape.
- Config flags exposing the fitted path at the research-pipeline
  level. The opt-in lives at the strategy factory call site today.

## Consequences

Positive:

- Safer out-of-sample semantics for features that require training.
  The engine structurally separates fit-on-train from
  transform-on-test; leakage is a boundary violation, not a review
  comment.
- A forward-compatible home for future fitted statistical features
  (PCA, factor loadings, mean/variance estimators, dynamic linear
  models in a static-fit form).
- Minimal regression surface. The v3.5 Tier 1 bytewise pins and the
  v3.6 multi-asset parity pins pass unchanged. The public output
  contract (`research_latest.json`, 19-column CSV, integrity /
  falsification sidecars) is untouched.
- Preserved backward compatibility. Every v3.6 strategy and
  research configuration runs byte-identically on v3.7 with no
  change to call sites.

Costs:

- Extra complexity in the feature build flow. There are now two
  parallel registries (plain, fitted) and two parallel build paths
  (`build_features_for{_multi}`, `build_features_{train,test}{_multi}`).
  A fresh reader has to learn the distinction before editing the
  feature layer.
- Temporary coexistence of plain and fitted paths. Pairs specifically
  has two valid configurations today; reviewers must check which is
  in use for any given experiment.
- Thin contract v2.0 remains incomplete. One of its triggers
  (fit/transform abstraction) is now present, but the migration
  itself is still future work (see ADR-006).
- Engine signature widens. `_simuleer_detailed` and
  `_invoke_strategy` now accept `train_frame` and
  `train_reference_frame`. Non-fitted strategies ignore them; the
  engine-resumability test had to be updated to forward them through
  a monkey-patched fixture.

## Thin contract maturity statement

As of v3.7: **v1.0 is production for all Tier 1 strategies, including
pairs. The fitted feature abstraction lands alongside v1.0 without
migrating any strategy to v2.0. v2.0 remains deferred per ADR-006,
and v3.7 is one of the two triggers that ADR-006 lists for
revisiting.**
