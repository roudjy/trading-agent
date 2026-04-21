# Changelog

All notable changes to the trading-agent research and backtesting
stack are documented here. Live trading / orchestration surfaces
outside the research path are not tracked in this file.

## [v3.7] — Fitted Feature Abstraction

Date: 2026-04-21
Branch: `feature/v3.7-fitted-feature-abstraction`

### Added

- `agent/backtesting/fitted_features.py`: parallel feature
  abstraction for features that require a fit/transform lifecycle.
  `FittedFeatureSpec`, `FittedParams` (frozen dataclass with
  `MappingProxyType` values, deep-copy + `flags.writeable=False` on
  arrays, pandas-sentinel rejection, hard caps on entries / array
  elements / sequence length), `FITTED_FEATURE_REGISTRY`,
  `validate_fitted_params`, `FITTED_FEATURE_VERSION = "1.0"`.
  Registered entries: `hedge_ratio_ols` (OLS beta on close vs
  close_ref, ddof=0) and `spread_zscore_ols` (shares the OLS fit
  via a private helper; transform returns
  `zscore(spread(close, close_ref, beta), lookback)`).
- `agent/backtesting/thin_strategy.py`:
  `FeatureRequirement.feature_kind: Literal["plain", "fitted"]`
  (default `"plain"`, byte-identical to v3.6). Fold-aware builders
  `build_features_train`, `build_features_test`,
  `build_features_train_multi`, `build_features_test_multi`. The
  single-frame `build_features_for` and multi-frame
  `build_features_for_multi` paths are unchanged and remain the
  owners of the v3.5 / v3.6 bytewise pins.
- `agent/backtesting/engine.py`:
  `BacktestEngine._evaluate_windows` materializes each fold's
  training slice (and `train_reference_frame` when multi-asset)
  and forwards them through `_simuleer_detailed → _invoke_strategy`.
  New `_resolve_fitted_features` helper routes fitted requirements
  through the train/test helpers; loud-fails when `train_frame` /
  `train_reference_frame` is missing. Non-fitted strategies ignore
  the new kwargs.
- `agent/backtesting/strategies.py::pairs_zscore_strategie`:
  explicit `use_fitted_hedge_ratio: bool = False` opt-in. Default
  emits the v3.6 `spread_zscore` requirement byte-identically;
  `True` swaps to `spread_zscore_ols` (fitted).
- `tests/unit/test_fitted_features.py` (33 tests — v3.7 step 1),
  `tests/unit/test_fitted_hedge_ratio_ols.py` (v3.7 step 2),
  `tests/unit/test_feature_kind_discriminator.py` and
  `tests/unit/test_fold_aware_builders.py` (v3.7 step 3),
  `tests/unit/test_fitted_pairs_engine.py` (19 tests — v3.7 step 4).
- `docs/adr/ADR-007-fitted-feature-abstraction.md`.
- `docs/orchestrator_brief.md` §Addendum: v3.7 fitted feature
  scope, layer placement, walk-forward semantics, param safety,
  pairs strategy behavior, explicit deferrals, roadmap relationship,
  thin contract maturity statement.

### Unchanged — explicitly pinned

- `research_latest.json` row schema and top-level schema (bytewise).
- 19-column CSV row schema (bytewise).
- Integrity (`integrity_report_latest.v1.json`) and falsification
  (`falsification_gates_latest.v1.json`) sidecar schemas.
- Integrity D4 boundary.
- Tier 1 bytewise digests (`sma_crossover`,
  `zscore_mean_reversion`, `pairs_zscore`). Pairs digest continues
  to resolve through the v3.6 multi-asset engine path with
  `use_fitted_hedge_ratio=False` (the default).
- Walk-forward `FoldLeakageError` semantics.
- Resume-integrity gate.
- `FEATURE_REGISTRY`, `FEATURE_VERSION = "1.0"`,
  `build_features_for`, `build_features_for_multi` — the plain
  feature path is unchanged.

### Deferred

- Thin contract v2.0 (`func(features)` purity). v3.7 introduces
  one of the ADR-006 triggers (fit/transform abstraction) but does
  not migrate any strategy. See
  [ADR-006](docs/adr/ADR-006-v2-contract-deferred.md) and
  [ADR-007](docs/adr/ADR-007-fitted-feature-abstraction.md).
- Broader strategy migration to the fitted path. Only
  `pairs_zscore` gains an opt-in flag; SMA crossover and z-score
  mean reversion are plain-only.
- Generalized lineage / persistence for fitted params. The
  `FittedParams.fingerprint` placeholder reserves the surface;
  computation and persistence are future work.
- Rolling / time-varying fitted parameters. v3.7 is static fit per
  fold.
- Config-level exposure of the fitted path at the research
  pipeline. Opt-in lives at the strategy factory call site today.
- Evaluation hardening, exit diagnostics, regime / portfolio work.
- Promotion of `use_fitted_hedge_ratio=True` to the pairs default —
  requires evidence and would drift the Tier 1 bytewise pin; a
  separate single-purpose change.

### Thin contract maturity

- v1.0 is production for all Tier 1 strategies, including pairs.
- v2.0 is still deferred (ADR-006). v3.7 introduces one of its
  triggers without performing the migration.
- Fitted feature abstraction is production for opt-in callers.

## [v3.6] — Multi-Asset Loader & Feature-Purity Progression

Date: 2026-04-21
Branch: `feature/v3.6-multi-asset-loader-and-feature-purity`

### Added

- `agent/backtesting/multi_asset_loader.py`: `load_aligned_pair`,
  `AlignedPairFrame`, typed errors
  (`EmptyIntersectionError`, `MixedAssetClassError`,
  `LegUnavailableError`). Inner-join alignment with truncation
  idempotence as the fold-safety invariant.
- `agent/backtesting/thin_strategy.py`:
  `FeatureRequirement.source_role` (default `None`, byte-identical to
  v3.5) and `build_features_for_multi(requirements, frames)`. The
  single-frame `build_features_for` path is unchanged.
- `agent/backtesting/engine.py`: optional
  `AssetContext.reference_frame`, `_invoke_strategy` multi-asset
  routing, keyword-only `grid_search(reference_asset=...)`.
- `research/candidate_pipeline.py`: `reference_asset` plumbing from
  registry → candidate metadata → engine. Included in
  `candidate_id` hashing **only when non-None** so SMA / z-score
  hashes stay byte-identical to v3.5.
- `research/registry.py`: `pairs_zscore.enabled = True` with
  `reference_asset = "ETH-EUR"` alongside `asset = "BTC-EUR"`.
- `tests/unit/test_aligned_pair_loader.py` (10 tests),
  `tests/integration/test_pairs_end_to_end.py` (9 tests),
  `tests/unit/test_multi_asset_feature_resolution.py` (10 tests),
  `tests/regression/test_multi_asset_feature_parity.py` (3 tests),
  `tests/regression/test_tier1_bytewise_pin.py::
  test_pairs_bytewise_pin_through_multi_asset_engine`,
  `tests/unit/test_walk_forward_framework.py::
  test_multi_asset_fold_slices_match_direct_alignment_per_fold`.
- `docs/adr/ADR-006-v2-contract-deferred.md`.
- `docs/orchestrator_brief.md` §Addendum: v3.6 multi-asset scope,
  loader contract, feature contract extension, engine routing,
  candidate pipeline plumbing, public output contract invariant,
  thin contract maturity statement.
- `CHANGELOG.md` (this file).

### Unchanged — explicitly pinned

- `research_latest.json` row schema and top-level schema (bytewise).
- 19-column CSV row schema (bytewise).
- Integrity (`integrity_report_latest.v1.json`) and falsification
  (`falsification_gates_latest.v1.json`) sidecar schemas.
- Integrity D4 boundary — no `status` field added to sidecars.
- Public `asset` column semantics — single symbol string, never
  concatenated, never reinterpreted. `reference_asset` lives only on
  internal surfaces.
- Tier 1 bytewise digests (`sma_crossover`,
  `zscore_mean_reversion`, `pairs_zscore`) — including pairs, whose
  digest through the multi-asset engine path equals the single-frame
  v3.5 pin exactly.
- Walk-forward `FoldLeakageError` semantics.
- Resume-integrity gate.

### Deferred

- Static / full-series OLS hedge ratio — requires fit/transform
  abstraction; tracked for v3.7
  (`feature/v3.7-fitted-feature-abstraction`).
- N > 2 multi-asset (triplets, portfolios).
- Mixed asset-class pairs (crypto × equity).
- Intraday multi-asset alignment (DST / session boundary policy).
- Thin contract v2.0 (`func(features)` purity). See
  `docs/adr/ADR-006-v2-contract-deferred.md` for trigger conditions
  and migration approach.
- Generalized pair-selection: pair universe, cointegration
  discovery, dynamic pair rotation.

### Thin contract maturity

v1.0 is production for all Tier 1 strategies, including pairs.
v2.0 is deferred to v3.7+ pending a concrete triggering use case.

## [v3.5] — Canonical Feature Primitives & Thin Strategy Contract v1.0

Date: earlier in 2026, pre-v3.6.
Branch: merged to `main` at `72e70aa`.

- Canonical feature primitives and registry.
- Thin strategy contract v1.0 (`func(df, features)`) with AST-level
  body enforcement (strategies may read `df.index` only).
- Engine-side thin routing through `build_features_for`.
- Integrity / falsification sidecars with typed reason codes and the
  D4 boundary invariant.
- Artifact-integrity resume gate.
- Tier 1 bytewise pins for `sma_crossover` and
  `zscore_mean_reversion`. Pairs scaffolded under the thin contract
  but registry-disabled pending multi-asset support (landed in v3.6).
