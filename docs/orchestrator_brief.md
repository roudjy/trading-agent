# Orchestrator Brief: Quant Strategy & Research Framework --- ## 1. Strategy Universe The 
system must support a defined set of quantitative strategy classes. Each strategy must be 
modular, parameterized, and fully compatible with the existing layered architecture. ### Core 
Strategy Classes 1. **Trend Following (Momentum)** * Objective: capture persistent directional 
moves * Typical signals: * Moving average crossovers * Breakouts (e.g. Donchian channels) * 
Requirements: * deterministic signal generation * configurable lookback windows 2. **Mean 
Reversion** * Objective: exploit deviations from equilibrium * Typical signals: * Z-score 
thresholds * Bollinger Band reversion * Requirements: * rolling statistics * regime awareness 
(avoid strong trends) 3. **Statistical Arbitrage (Pairs Trading)** * Objective: exploit 
relative mispricing between assets * Typical signals: * spread deviation from mean * 
cointegration residuals * Requirements: * pair selection logic * spread construction * 
normalization (Z-score) 4. **Volatility-Based Strategies** * Objective: trade volatility 
regimes or expansions * Typical signals: * volatility breakout * ATR-based triggers * 
Requirements: * volatility estimation * dynamic thresholds 5. **Regime-Based Meta Layer** * 
Objective: switch or filter strategies based on market conditions * Regimes: * trending vs 
mean-reverting * low vs high volatility * Requirements: * regime classification model * gating 
logic for strategies --- ## 2. Core Mathematical Foundations The research system must implement 
standardized mathematical primitives. These must be reusable, deterministic, and validated. ### 
Required Metrics & Transformations * **Returns** * simple returns * log returns (preferred for 
aggregation) * **Moving Averages** * simple moving average (SMA) * exponential moving average 
(EMA) * **Z-Score** * standardized deviation from mean * used in mean reversion and stat arb * 
**Volatility** * rolling standard deviation of returns * required for risk normalization * 
**Sharpe Ratio** * risk-adjusted performance metric * must support configurable risk-free rate 
* **Maximum Drawdown** * peak-to-trough loss * required for risk constraints * **Cointegration 
Model** * linear relationship between assets * residual used as tradable signal * **Position 
Sizing** * volatility targeting (required) * optional: Kelly criterion (experimental) --- ## 3. 
Layer Mapping (Strict Enforcement) All components must adhere to the defined system layers. No 
cross-layer leakage is allowed. ### Data Layer * raw market data ingestion * normalization and 
storage * schema enforcement ### Feature Layer * returns * moving averages * volatility * 
z-scores * spreads (for pairs) ### Strategy Layer * signal generation only * no execution logic 
* no portfolio state mutation ### Execution Layer * order simulation or live execution * 
position sizing * slippage and transaction cost modeling ### Evaluation Layer * backtesting 
engine * performance metrics (Sharpe, drawdown, etc.) * reproducibility guarantees ### 
Orchestration Layer (this agent) * pipeline coordination * scheduling runs * managing 
experiment lifecycle * enforcing configuration-driven execution --- ## 4. Initial Strategy Set 
(Mandatory Implementation Order) The system must first implement a minimal but orthogonal 
strategy set: 1. **SMA Crossover (Trend Following)** * Inputs: price series * Parameters: fast 
window, slow window * Output: long/flat or long/short signal 2. **Z-Score Mean Reversion** * 
Inputs: price or spread * Parameters: lookback window, entry/exit thresholds * Output: mean 
reversion signal 3. **Pairs Trading (Statistical Arbitrage)** * Inputs: two asset price series 
* Parameters: hedge ratio, z-score thresholds * Output: long/short pair positions ### 
Constraints * each strategy must be independently testable * all parameters must be externally 
configurable * no hardcoded constants ### Authority note (ADR-014 §A / §E) Tier-1 baselines (§4.1 SMA Crossover, §4.2 Z-Score Mean Reversion, §4.3 Pairs Trading) are *registered* baselines. Operational exercise is governed by the preset catalog (`research/presets.py`), not by their presence in the registry. `zscore_mean_reversion` is currently registered without a preset bundle — that is a documented gap (ADR-014 §E), not a code defect. Use `research.authority_views.bundle_active(name)` to derive whether any enabled preset references a strategy. --- ## 5. Orchestrator Responsibilities & Rules The 
orchestrator agent is responsible for enforcing system integrity and automation. ### 
Responsibilities * Execute full pipeline: * data → features → strategy → execution → 
evaluation * Schedule: * backtests * parameter sweeps * research experiments * Manage 
configurations: * assets * timeframes * parameters * risk limits ### Enforcement Rules * No 
execution without validated data contracts * No strategy run without explicit configuration * 
All runs must be: * logged * reproducible * versioned ### Observability Each pipeline run must 
log: * input configuration * feature outputs * generated signals * executed trades * evaluation 
metrics Errors must: * halt execution * include full context * be traceable to module + input 
### Automation Target * fully automated research → validation → deployment loop * minimal 
manual intervention * CLI-driven orchestration with agent coordination --- End of 
specification.

---

## Addendum: v3.6 — Multi-Asset Loader & Feature-Purity Progression

This addendum documents the v3.6 additions on top of the base
specification. It does **not** alter any of §1–5; those remain the
load-bearing architecture. v3.6 is an additive extension along one
axis (multi-asset support for pairs) plus a feature-resolution
progression inside the already-established Feature Layer.

### Scope

- Enable `pairs_zscore` as a third Tier 1 baseline (§4.3), running
  through the same engine path as SMA crossover and z-score mean
  reversion.
- Introduce a two-leg multi-asset loading path that inner-joins two
  symbols on `DatetimeIndex`.
- Extend the thin feature contract with an optional `source_role`
  field so primitives can declare which leg supplies their columns,
  without rewriting single-asset primitives.
- Preserve every v3.5 guarantee bytewise: Tier 1 digest pins, public
  output contract (`research_latest.json` row and top-level schema,
  19-column CSV row schema), integrity D4 boundary, falsification
  verdict schema, walk-forward `FoldLeakageError` semantics, resume
  integrity gate.

### Out of scope (explicitly deferred)

- N>2 multi-asset (triplets, portfolios).
- Mixed asset-class pairs (crypto × equity) — rejected at the loader
  with a typed error.
- Intraday multi-asset alignment — DST and session-boundary policy
  deferred.
- Static / full-series OLS hedge ratio — requires a fit/transform
  abstraction; tracked for v3.7.
- Thin contract v2.0 (`func(features)` purity) — see
  [ADR-006](adr/ADR-006-v2-contract-deferred.md).
- Generalized pair-selection: pair universe, cointegration discovery,
  dynamic pair rotation. `reference_asset` is a single optional
  config field on the registry entry, not a selection framework.

### Loader contract

`agent/backtesting/multi_asset_loader.py::load_aligned_pair` loads two
symbols through the existing `MarketRepository` and returns an
`AlignedPairFrame(primary, reference, primary_symbol, reference_symbol,
interval, asset_class, provenance)` whose `primary.index` and
`reference.index` are identical.

Alignment invariants, pinned in
`tests/unit/test_aligned_pair_loader.py`:

- **Inner-join only.** Empty intersection raises
  `EmptyIntersectionError`.
- **Truncation idempotence.** Aligning on `[t0..tN]` then slicing to
  `[t0..tK]` equals aligning directly on `[t0..tK]`. This is the
  fold-safety invariant; the engine's fold loop relies on it when it
  does `context.reference_frame.iloc[start:end+1]`.
- **Asset-class homogeneous.** Crypto × equity pairs are rejected
  with `MixedAssetClassError`.
- **Deterministic.** Given `(primary, reference, start, end,
  interval)`, the output is byte-identical run-to-run.

### Feature contract extension

`agent/backtesting/thin_strategy.py` gains:

- `SourceRole = Literal["primary", "reference"]`.
- `FeatureRequirement.source_role: SourceRole | None = None`. Default
  `None` is equivalent to `"primary"` and preserves v3.5 single-frame
  resolution byte-for-byte. Tier 1 hash stability is pinned against
  this default.
- `build_features_for_multi(requirements, frames)` where `frames` is
  a `Mapping[str, pd.DataFrame]` containing a `"primary"` entry and
  optional `"reference"`. When a reference frame is supplied, its
  `close` column is exposed to the feature resolver as `close_ref` on
  a combined primary view — bytewise compatible with the single-frame
  pair fixture used by the v3.5 pairs pin.

The single-frame `build_features_for` is **unchanged**. It remains
the owner of the v3.5 bytewise pin path.

Parity (pinned in `tests/regression/test_multi_asset_feature_parity.py`
and `tests/regression/test_tier1_bytewise_pin.py`):

- `build_features_for(reqs, pairs_frame)` ≡
  `build_features_for_multi(reqs, {"primary": primary, "reference":
  reference})` when the two paths reconstruct the same `close_ref`.
- Pairs digest through the multi-asset engine path equals the
  single-frame v3.5 pin exactly.

### Engine routing

`AssetContext` gains an optional `reference_frame: pd.DataFrame | None`.
`BacktestEngine._invoke_strategy` routes thin strategies through
`build_features_for_multi` when `reference_frame is not None`, else
through `build_features_for`. Both branches produce byte-identical
output for pairs inputs (see parity pin above).

`BacktestEngine.grid_search` accepts a keyword-only
`reference_asset: str | None = None`. When set, the engine loads the
reference leg via `load_aligned_pair` and attaches it to each
`AssetContext`.

### Candidate pipeline

`research/candidate_pipeline.py`:

- The blanket `position_structure == "spread"` → `FIT_BLOCKED` rule
  is relaxed to "blocked unless the strategy declares
  `reference_asset`".
- `candidate_id` hashing includes `reference_asset` **only when
  non-None**, so every SMA / z-score hash stays byte-identical to
  v3.5.
- `reference_asset` is threaded through `strategy_requirements` and
  reaches the engine via batch execution. It is **internal metadata
  only**.

### Public output contract — unchanged

`research_latest.json` row schema and top-level schema, the 19-column
CSV row schema, the integrity and falsification sidecar schemas: all
bytewise identical to v3.5. The `asset` column retains its v3.5
single-symbol semantics — it is not overloaded, concatenated, or
reinterpreted. `reference_asset` lives only on internal surfaces
(candidate metadata, optional `run_manifest.v1.json` field,
optional payload inside existing evidence `details` dicts).

### Thin contract maturity

- **v1.0: production.** All Tier 1 strategies, including pairs, run
  under `func(df, features)`.
- **v2.0: deferred.** See
  [ADR-006](adr/ADR-006-v2-contract-deferred.md) for the trigger
  conditions and migration approach when v2.0 becomes warranted.

---

## Addendum: v3.7 — Fitted Feature Abstraction

This addendum documents the v3.7 additions. It does **not** alter
§1–5 of the base specification or the v3.6 addendum. v3.7 is a
feature-layer extension along one axis (features that require a
fit/transform lifecycle) plus the minimum engine wiring required to
honor walk-forward semantics for such features. No strategy
migration, no public contract drift, no schema change.

### Scope

- Introduce a parallel feature abstraction for features that carry a
  training phase: `FittedFeatureSpec`, `FittedParams`,
  `FITTED_FEATURE_REGISTRY`.
- Register two fitted features: `hedge_ratio_ols` and
  `spread_zscore_ols`. Both share an OLS fit helper; the latter
  returns `zscore(spread(close, close_ref, beta), lookback)` using
  the fitted `beta`.
- Extend `FeatureRequirement` with an explicit
  `feature_kind: Literal["plain", "fitted"]` discriminator. Default
  `"plain"` preserves every v3.5 / v3.6 path byte-identically.
- Introduce fold-aware builders: `build_features_train`,
  `build_features_test`, and their multi-asset counterparts. The
  single-frame `build_features_for` and multi-frame
  `build_features_for_multi` paths are **unchanged** and remain the
  owners of the v3.5 / v3.6 bytewise pins.
- Engine sequencing: `BacktestEngine._evaluate_windows`
  materializes each fold's training slice (and
  `train_reference_frame` when multi-asset) and forwards them
  through `_simuleer_detailed → _invoke_strategy`. A new
  `_resolve_fitted_features` helper handles fit-on-train /
  transform-on-test routing when any requirement declares
  `feature_kind="fitted"`. Non-fitted strategies ignore the new
  kwargs.
- `pairs_zscore_strategie` gains an explicit
  `use_fitted_hedge_ratio: bool = False` opt-in. Default behavior
  is byte-identical to v3.6; `True` swaps the `spread_zscore`
  requirement for `spread_zscore_ols`.
- Preserve every v3.5 / v3.6 guarantee bytewise: Tier 1 digest
  pins, multi-asset parity pins, public output contract
  (`research_latest.json` row and top-level schema, 19-column CSV
  row schema), integrity / falsification sidecar schemas, D4
  boundary, `FoldLeakageError` semantics, resume-integrity gate.

### Layer placement

- **Feature layer** owns fitted transforms. Fit and transform are
  pure, deterministic, non-mutating functions registered in
  `FITTED_FEATURE_REGISTRY`.
- **Strategy layer** remains signal generation only. A fitted
  strategy declares a fitted `FeatureRequirement`; it never fits
  anything itself and never touches `FittedParams` directly.
- **Engine layer** owns fold slicing and fit/test sequencing. It
  materializes the training slice per fold, calls fit exactly once,
  and calls transform on the evaluation slice using the frozen
  params.
- **Evaluation layer** is untouched. Metrics remain what they were
  in v3.5 / v3.6.

### Walk-forward semantics (pinned by ADR-007)

For each fold:

1. The engine selects the fold's training slice.
2. `fit_fn` runs once on that slice; `FittedParams` are frozen and
   fold-local.
3. `transform_fn` runs on the evaluation slice using those params.
4. The evaluation slice never influences params.
5. There is no refit on the test slice and no cross-fold param
   reuse.
6. Train-slice transform may occur when the same fold's feature
   assembly needs the fitted feature's train-time output. It uses
   the same params returned by the single fit call.

Strategies that declare only `feature_kind="plain"` requirements —
which is every Tier 1 strategy's default configuration as of v3.7 —
follow the v3.6 `build_features_for{_multi}` path byte-for-byte.

### Param safety (enforced at `FittedParams.build`)

- `FittedParams.values` is stored as
  `types.MappingProxyType` over a deep-validated, deep-copied dict.
  Keys must be `str`; leaves must be `int`, `float`, `bool`, `str`,
  `None`, a small numeric ndarray, or a small tuple/list of leaves.
  Lists are normalized to tuples; arrays are copied with
  `flags.writeable=False`; nested dicts are rejected.
- Pandas objects are rejected at construction with a named error.
  Any object exposing `.index` or `.columns` is likewise rejected.
  This closes the accidental-training-frame-retention path by
  construction.
- Hard caps: `MAX_PARAM_VALUES_ENTRIES = 64`,
  `MAX_PARAM_ARRAY_ELEMENTS = 1024`,
  `MAX_PARAM_SEQUENCE_LEN = 1024`.

### Pairs strategy behavior

- `pairs_zscore_strategie(..., use_fitted_hedge_ratio=False)`
  (default) emits the v3.6 requirement
  `FeatureRequirement(name="spread_zscore",
  params={"hedge_ratio", "lookback"}, alias="z")`. The Tier 1
  bytewise pin continues to resolve through this path.
- `pairs_zscore_strategie(..., use_fitted_hedge_ratio=True)` emits
  `FeatureRequirement(name="spread_zscore_ols",
  params={"lookback"}, alias="z", feature_kind="fitted")`. The
  scalar `hedge_ratio` argument is ignored in this mode; the engine
  replaces it with the fold-local OLS beta per the walk-forward
  rules above.
- The strategy body is unchanged between modes: it still reads only
  `df.index` and `features["z"]`. The signal semantics
  (`entry_z`, `exit_z`, `lookback`) are identical. Only the
  spread's hedge-ratio source differs.
- Public artifacts, sidecars, registry entries, and the Tier 1
  bytewise pin are untouched.

### Out of scope (explicitly deferred)

- Unified thin strategy v2.0 contract. ADR-007 records that v3.7
  introduces one of the ADR-006 triggers (fit/transform abstraction)
  but does not itself migrate any strategy to `func(features)`.
- Broader strategy migration to the fitted path. SMA crossover and
  z-score mean reversion remain plain-only.
- Generalized lineage or persistence for fitted params. The
  `FittedParams.fingerprint` placeholder reserves the surface;
  computation and persistence are future work.
- Rolling / time-varying fitted parameters. v3.7 is static fit per
  fold; rolling fit is an additive shape for a later phase.
- Config flags exposing the fitted path at the research-pipeline
  level. The opt-in lives at the strategy factory call site today.
- Evaluation hardening, exit diagnostics, regime / portfolio work.

### Relationship to v3.6 and the larger roadmap

v3.7 is a prerequisite for:

- Correct walk-forward semantics for any fitted feature.
- Statistically honest pairs spread construction (fitted hedge
  ratio available as opt-in; promotion to default is a future
  decision backed by evidence).
- Future train/transform-style statistical features (PCA,
  factor loadings, fitted regressions).

v3.7 is **not** a substitute for:

- Thin contract unification (ADR-006, deferred).
- Evaluation hardening, exit diagnostics, portfolio / regime
  work — all of which remain future phases.

### Thin contract maturity

- **v1.0: production.** All Tier 1 strategies, including pairs, run
  under `func(df, features)`.
- **v2.0: still deferred.** See
  [ADR-006](adr/ADR-006-v2-contract-deferred.md). v3.7 introduces
  the fit/transform abstraction trigger listed there without
  migrating any strategy.
- **Fitted feature abstraction: production for opt-in callers.**
  See [ADR-007](adr/ADR-007-fitted-feature-abstraction.md) for
  design, rationale, rejected alternatives, and walk-forward
  invariants.

---

## Addendum: v3.8 — Execution Realism & Evaluation Hardening

This addendum documents the v3.8 additions on top of the base
specification and the v3.6 / v3.7 addenda. It does **not** alter
§1–5; those remain the load-bearing architecture. v3.8 is an
additive **evaluation-hardening** phase: it does not change
strategy logic, feature logic, fitted-feature semantics, or
baseline equity / trade booking. See
[ADR-008](adr/ADR-008-execution-realism-and-evaluation-hardening.md)
for the full design record, rejected alternatives, and pinned
semantics.

### Problem solved

Before v3.8 the engine collapsed "signal emitted → trade booked"
into a single inline step. A shifted signal was converted directly
into equity impact with a flat `kosten_per_kant` applied inline at
entry and exit. There was no auditable record of intended versus
realized price, fee amount, typed slippage, rejection reason, or
fold-local execution identity. That implicit boundary was
sufficient for v3.5 / v3.6 / v3.7 but blocked four
evaluation-hardening questions: fee attribution, slippage
attribution, execution sensitivity, and exit quality.

v3.8 makes the existing research truth auditable and
stress-testable. It does **not** change what that truth is.

### Scope

v3.8 delivers five additive steps:

1. **Canonical execution event scaffold.**
   `agent/backtesting/execution.py`,
   `EXECUTION_EVENT_VERSION = "1.0"`. Frozen `ExecutionEvent` with
   five pinned kinds (`accepted`, `partial_fill`, `full_fill`,
   `rejected`, `canceled`), typed reason-code vocabulary, factory
   builders, pandas/numpy-rejection sentinel, dict round-trip
   helpers. Explicitly disjoint from `execution/protocols.py::Fill`
   (the live / paper-broker success record).
2. **Deterministic engine emission.** `_simuleer_detailed` emits
   an `accepted` + `full_fill` pair at each booked entry and exit
   with monotone `sequence` and fold-local `event_id`. Gated by
   `include_execution_events`; enabled only on OOS folds. Events
   land in `_last_window_streams["oos_execution_events"]`. Baseline
   equity math, fee application, and trade PnL are bytewise
   unchanged.
3. **Fee / slippage attribution basis.** Every emitted `full_fill`
   carries `fill_price`, `fee_amount` (derived from the
   pre-multiplication equity and `kosten_per_kant`),
   `slippage_bps = 0.0` (next-bar-close model),
   `requested_size = filled_size = 1.0`, and `intended_price`.
   Event-derived fee sums reconcile with the engine's inline
   equity drag.
4. **Cost sensitivity harness.**
   `agent/backtesting/cost_sensitivity.py`,
   `COST_SENSITIVITY_VERSION = "1.0"`. Pure evaluation-layer
   replay with per-fill adjustment
   `(1 - m*k) * (1 - s_bps/1e4) / (1 - k)`. Baseline scenario
   reproduces the engine's `dag_returns` bytewise; alternative
   scenarios apply stress without mutating the baseline. Opt-in
   hook `BacktestEngine.build_cost_sensitivity`.
5. **Exit-quality diagnostics.**
   `agent/backtesting/exit_diagnostics.py`,
   `EXIT_DIAGNOSTICS_VERSION = "1.0"`. Pure evaluation-layer
   path analysis on `oos_trade_events` + `oos_bar_returns` +
   `kosten_per_kant`. Per-trade MFE / MAE / realized return /
   capture ratio / winner giveback / exit lag + run-level
   turnover-adjusted exit quality. Opt-in hook
   `BacktestEngine.build_exit_diagnostics`.

### Layer placement

- **Execution-model layer (new, inside the backtest path)** owns
  the event record. Lives in `agent/backtesting/execution.py`.
- **Engine layer** owns emission. Events are produced
  deterministically inside `_simuleer_detailed` during OOS folds;
  the event stream is a side-channel stored in
  `_last_window_streams` and surfaces on the research result dict
  as `evaluation_streams`.
- **Evaluation layer** owns replay and diagnostics
  (`cost_sensitivity.py`, `exit_diagnostics.py`). Both are
  stdlib-only, non-mutating, and invoked through opt-in hooks on
  `BacktestEngine` — never from `run()`.
- **Strategy layer, feature layer, fitted-feature layer** — all
  unchanged.
- **Live / paper broker layer (`execution/protocols.py`,
  `execution/paper/polymarket_sim.py`)** — unchanged and
  disjoint. `Fill` is a live success record; `ExecutionEvent` is
  a backtest evaluation record. Nothing imports across.

### Execution-event semantics (pinned by ADR-008)

- `accepted` + `full_fill` are emitted per entry and per exit. The
  current engine mirrors the v3.7 truth: next-bar-close fills,
  one-sided fee per side, no partials, no explicit rejections.
- `partial_fill`, `rejected`, `canceled` are **scaffolded** in the
  model but not emitted by the current engine. Richer emission
  awaits a concrete trigger (capacity-bounded sizing, liquidity
  filters, venue-state modeling).
- Field semantics v1.0: `intended_price` = next-bar close;
  `fill_price == intended_price` and `slippage_bps = 0.0`;
  `requested_size = filled_size = 1.0`; `fee_amount` is account
  currency, `>= 0`, reconciles with the engine's equity drag;
  `sequence` monotone within `(run_id, asset, fold_index)`;
  `fold_index` carried on every event; `fingerprint` reserved,
  unset.

### Cost sensitivity semantics (pinned by ADR-008)

- Replay layer only. Does not call strategies, does not rebuild
  features, does not invoke the engine loop.
- Baseline scenario (`fee_multiplier=1.0, slippage_bps=0.0`)
  reproduces `dag_returns` bytewise. This invariant is pinned by
  unit tests and is the reason the replay can be trusted as a
  side-channel on the baseline.
- Alternative scenarios apply a per-fill multiplicative adjustment;
  the baseline is not mutated.
- Any stress-conditioned metrics are **internal / additive** and
  do not replace the main evaluation framework. Tier 1 metrics in
  `research_latest` are unchanged.

### Exit-quality semantics (pinned by ADR-008)

Per-trade path: `[0.0, interior_cumulative (side-adjusted raw
ratios), realized_pnl + kosten_per_kant]`. Interior bars are the
`oos_bar_returns` entries strictly between entry and exit for the
matching `(asset, fold_index)` partition. The exit bar's bar-stream
return is polluted by the engine's `(1 - k)` fee factor and is
**not** used; the clean exit-bar anchor is `pnl + k`.

Pinned per-trade definitions:

- `mfe = max(max(path), 0.0)`; `mae = max(-min(path), 0.0)`.
- `realized_return = path[-1] = pnl + k`.
- `capture_ratio = realized_return / mfe if mfe > 0.0 else None`.
- `winner_giveback = mfe - realized_return if realized_return >
  0.0 else None`.
- `exit_lag_bars = len(path) - 1 - argmax(path)`;
  `holding_bars = len(path) - 1`.

Pinned aggregate: `turnover_adjusted_exit_quality =
avg_capture_ratio * (1 - min(trade_count / max(total_bars, 1),
1.0))`; `0.0` when `trade_count == 0`.

Long/short symmetry: `side_sign ∈ {+1, -1}` makes the path
construction symmetric under the engine's side-adjusted bar stream.

Zero-opportunity / zero-trade conventions: `capture_ratio` and
`winner_giveback` are `None` where undefined; zero-trade runs
return valid empty structures with all summary floats `0.0`.

Bar-based path only: exit-quality diagnostics are a bar-resolution
analysis of the engine's own truth. No intrabar inference, no tick
data, no touches the engine did not observe.

### Out of scope (explicitly deferred)

v3.8 does not deliver:

- Paper validation as a formal gate.
- Live / paper divergence reporting between live `Fill` outcomes
  and backtest `ExecutionEvent` projections.
- Full execution shortfall framework (quote midpoint, bid/ask,
  impact curves). Current backtest slippage is `0.0 bps` (next-bar
  close).
- Richer rejection / partial-fill semantics in the engine. The
  scaffold exists; engine emission is still entry + exit fills
  only.
- Broader promotion framework integration. Cost-sensitivity and
  exit-diagnostic reports are opt-in side-channels and are not
  gates.
- Regime / portfolio research. Unchanged.
- Broader orchestration / platform automation. Unchanged.
- Thin contract v2.0 unification (ADR-006) and broader strategy
  migration to the fitted path (ADR-007). Still deferred; v3.8
  neither introduces new ADR-006 triggers nor resolves any of its
  conditions.
- Config-level surfacing of `build_cost_sensitivity` and
  `build_exit_diagnostics`. Both are callable on `BacktestEngine`
  instances only.

### Preserved bytewise

- Tier 1 digest pins (SMA crossover, z-score mean reversion, pairs
  z-score).
- `research_latest.json` row and top-level schema.
- 19-column CSV row schema.
- Integrity and falsification sidecar schemas; D4 boundary.
- Walk-forward `FoldLeakageError` semantics.
- Resume-integrity gate.
- `candidate_id` hashing inputs (execution shape is explicitly
  out of the hash).
- `FEATURE_REGISTRY`, `FEATURE_VERSION = "1.0"`,
  `FITTED_FEATURE_REGISTRY`, `FITTED_FEATURE_VERSION = "1.0"`.
- `execution/protocols.py`, `execution/paper/polymarket_sim.py`.

### Phase character

v3.8 is an **evaluation-hardening phase**, not a
strategy-expansion phase. Every change is additive,
deterministic, non-mutating with respect to baseline results, and
gated behind opt-in hooks or flags that default off. See
[ADR-008](adr/ADR-008-execution-realism-and-evaluation-hardening.md).

---

## Addendum: v3.9 — Orchestration Layer (Phases 1-3)

This addendum documents the v3.9 additions on top of the base
specification and the v3.6 / v3.7 / v3.8 addenda. It does **not**
alter §1-5; those remain the load-bearing architecture. v3.9 is an
**orchestration-hardening** phase: it introduces a dedicated
platform layer as a peer package to `agent/`, `research/`, and
`dashboard/`, and routes the existing batch-execution flow through a
named `Orchestrator` entity - without altering strategy, feature,
fitted-feature, or engine semantics and without breaking any public
output contract. See
[ADR-009](adr/ADR-009-platform-layer-introduction.md) for the full
design record, rejected alternatives, and dependency rules.

### Scope (phases 1-3)

v3.9 phases 1-3 deliver three additive steps:

1. **Package shell and boundary contract.** New `orchestration/`
   top-level package with an empty public surface in
   `orchestration/__init__.py` (only `ORCHESTRATION_LAYER_VERSION`
   is exported). Static import-direction lint in
   [tests/unit/test_orchestration_boundary.py](../tests/unit/test_orchestration_boundary.py)
   enforces the allowed / forbidden import matrix at CI time.
   ADR-009 and this addendum document the boundary contract.
2. **Task data model.** Frozen dataclasses in
   `orchestration/task.py`: `Task`, `TaskResult`, `TaskFailure`, plus
   the typed `ReasonCode` enum and its retriable / non-retriable
   classification. All types are pickle-safe by construction.
   `task_id` is deterministic in `(candidate_id, kind, attempt)`.
3. **ExecutionBackend + Orchestrator, behavior-preserving.**
   `orchestration/executor.py` introduces the `ExecutionBackend`
   abstract interface with two concrete implementations
   (`InlineBackend`, `ProcessPoolBackend`). `orchestration/worker.py`
   exposes the worker-side entry point that constructs a fresh
   `BacktestEngine` per task. `orchestration/orchestrator.py`
   introduces the `Orchestrator` entity as a thin seam that
   `research/run_research.py` now calls into for its screening and
   validation phase execution. Behavior is bytewise preserved:
   `research/run_research.py` continues to own CLI parsing, config
   loading, candidate planning, D4 gating, artifact writing, and
   post-run reporting; only the direct invocations of
   `_run_parallel_screening_batches`, `_run_parallel_validation_batches`,
   and the inline per-batch drivers are routed through the
   Orchestrator seam.

### Package-name rationale

The v3.9 design brief calls this "the platform layer". The package
is named `orchestration`, not `platform`, because a top-level Python
package named `platform` collides with the Python standard library
`platform` module. The collision is unavoidable on common installs:
Python 3.11+ with the frozen stdlib in `python313.zip` at
`sys.path[0]` resolves stdlib ahead of any project-root package,
leaving the local package unimportable; Linux installs without the
frozen stdlib resolve the local package ahead of stdlib, breaking
every library that uses stdlib `platform.system()`,
`platform.python_version()`, etc. The name `orchestration` matches
this brief's §5 "Orchestration Layer" and avoids the shadow
entirely. The conceptual label "platform layer" remains valid in
prose.

### Layer placement (pinned by ADR-009)

- **Orchestration layer (new top-level `orchestration/` package)**
  owns run lifecycle coordination, task dispatch, and (in later
  v3.9 phases) scheduling, queueing, and failure handling. It
  instantiates the engine at worker boundaries and nowhere else.
- **Engine layer (`agent/backtesting/`)** is unchanged. The engine
  imports nothing from `orchestration/` or `research/`. Tier 1
  bytewise digest pins continue to resolve through the v3.5 / v3.6 /
  v3.7 / v3.8 paths byte-for-byte.
- **Research layer (`research/`)** keeps its v3.8 contents. Existing
  modules (`run_state.py`, `batching.py`, `batch_execution.py`,
  `recovery.py`, `orchestration_policy.py`, `observability.py`,
  `screening_process.py`) remain in `research/` and are called
  through narrow named-symbol imports from `orchestration/`. No file
  is relocated in v3.9 phases 1-3.
- **Dashboard layer (`dashboard/`)** is unchanged in phases 1-3.

### Dependency rules (enforced by test)

The complete matrix is defined in
[ADR-009](adr/ADR-009-platform-layer-introduction.md). In summary:

- `agent/backtesting/` imports nothing from `orchestration/` or
  `research/`, and no concurrency primitives.
- `research/` (excluding `research/run_research.py`) imports nothing
  from `orchestration/`.
- `orchestration/` imports from `agent/backtesting/` through the
  engine-construction surface only, and imports narrow pure helpers
  from `research/`; it must not import `research.run_research` or
  any strategy-defining module.
- `research/run_research.py` is the single crossing from research
  into `orchestration/`.
- `dashboard/` must not reach into engine or research orchestration
  modules.

### Worker defaults

Fresh `BacktestEngine` per task. No engine reuse across tasks. No
module-level engine cache. The ProcessPool may keep worker processes
alive, but the engine instance is constructed inside the task body
and released at task completion. Any future cross-task caching is
deferred and gated behind explicit proof obligations documented in
ADR-009.

### Out of scope (explicitly deferred)

v3.9 phases 1-3 do not deliver:

- Scheduler and Queue as separate named entities (phase 4).
- Cross-Batch parallelism (phase 4, gated on bytewise regression).
- Task-level resume (phase 5, provisional).
- Platform event log (phase 5, provisional).
- Retry policy tuning (phase 5).
- Selective file relocation from `research/` to `orchestration/`
  (phase 6, zero to two files).
- Dashboard launch API (phase 7).
- Any change to `ExecutionEvent` semantics, cost-sensitivity,
  exit-diagnostics, fitted-feature behavior, or engine purity.

### Preserved bytewise

- Tier 1 digest pins (SMA crossover, z-score mean reversion, pairs
  z-score).
- Multi-asset and fitted-feature parity pins.
- `research_latest.json` row and top-level schema.
- 19-column CSV row schema.
- Integrity and falsification sidecar schemas; D4 boundary.
- Walk-forward `FoldLeakageError` semantics.
- Resume-integrity gate.
- `candidate_id` hashing inputs.
- `FEATURE_REGISTRY`, `FEATURE_VERSION = "1.0"`,
  `FITTED_FEATURE_REGISTRY`, `FITTED_FEATURE_VERSION = "1.0"`,
  `EXECUTION_EVENT_VERSION = "1.0"`,
  `COST_SENSITIVITY_VERSION = "1.0"`,
  `EXIT_DIAGNOSTICS_VERSION = "1.0"`.
- `execution/protocols.py`, `execution/paper/polymarket_sim.py`.
- `dashboard/` behavior.

### Phase character

v3.9 phases 1-3 are an **orchestration-hardening phase**, not a
strategy-expansion, feature-expansion, or engine-behavior-changing
phase. Every change is additive, deterministic, non-mutating with
respect to baseline engine behavior, and enforced by a static
boundary lint test plus the existing Tier 1 regression pins. See
[ADR-009](adr/ADR-009-platform-layer-introduction.md).

---

## Addendum: v3.9 Closure (Phase 6)

v3.9 is formally closed. The closure rationale, the preserved
bytewise guarantees, and the explicit classification of remaining
open points (resolved-now / accepted / deferred-to-v4+) are
recorded in
[ADR-010](adr/ADR-010-v3.9-closure.md).

### Closure evidence

- **Tier 1 bytewise pins:** unchanged across all v3.9 phases.
- **Public artifact contracts:** unchanged across all v3.9 phases
  (`research_latest.json`, 19-column CSV, integrity and
  falsification sidecars, run/batch/candidate state artifacts).
- **Engine purity:** unchanged. `agent/backtesting/` imports
  nothing from `orchestration/` or `research/`; no concurrency
  primitives added to the engine. CI-enforced by
  `tests/unit/test_orchestration_boundary.py`.
- **Orchestration layer:** `orchestration/` exists as a peer
  top-level package. Owns dispatch for both inline and parallel
  research paths. `Scheduler`, `TaskQueue`, `BatchOutcome`
  express the orchestration contract.
- **Artifact-truth invariant:** the `TaskQueue` is an in-memory
  cache scoped to one Orchestrator instance; recovery reads only
  artifacts. Pinned by
  `tests/unit/test_orchestration_artifact_truth.py`.
- **Crash/resume canary:** an end-to-end test
  (`tests/resilience/test_orchestration_crash_resume_canary.py`)
  forces a mid-run crash via a monkey-patched persistence helper,
  then re-invokes `run_research(resume=True,
  retry_failed_batches=True)`. The canary validates: (1) the
  crashed run records a consistent `status="failed"` lifecycle
  state, (2) the resume run completes with `status="completed"`,
  (3) no duplicate strategy rows appear in the final
  `research_latest.json` or `strategy_matrix.csv`, (4) all
  batches reach a terminal status, (5) two distinct `Orchestrator`
  instances are constructed across the boundary with disjoint
  `TaskQueue` state - proving the resume cannot have read back
  stale in-memory state.
- **`_default_complete` fallback:** scoped by docstring to
  "legacy / test fallback only"; pinned by a static AST test
  (`tests/unit/test_orchestration_default_complete_scope.py`)
  that asserts every `dispatch_serial_batches` /
  `dispatch_parallel_batches` call in `research/run_research.py`
  supplies an explicit `on_batch_complete=` hook.

### Out of scope (deferred to v4+)

- Automatic intra-run retry (surface exists via
  `BatchOutcome.is_retriable()`; not exercised).
- Task-level resume beyond the existing batch-level path.
- Distributed execution, cross-host orchestration, durable queue.
- Dashboard launch API upgrade.
- Campaign framework spanning multiple runs.
- Richer `ExecutionEvent` emission kinds.
- Typed `BatchTaskResult` wrapper for
  `TaskResult.payload["batch_result"]`.
- Selective relocation of orchestration-native `research/`
  modules into `orchestration/` (zero moves occurred during
  v3.9).

See [ADR-010](adr/ADR-010-v3.9-closure.md) for the full closure
record and classification of each remaining open point.

---

## Addendum: v3.11 — Research Quality Engine

This addendum documents the v3.11 additions on top of the base
specification and all prior addenda. It does **not** alter §1–5 of
the base specification or any prior addendum. v3.11 is a
**quality-hardening phase**: it formalises hypothesis metadata per
preset, splits screening from promotion in report output, and wires
per-candidate diagnostics — without introducing new metrics,
thresholds, or engine behavior changes. The registry, engine, and
orchestration layers are untouched.

### Scope

v3.11 delivers five additive capabilities:

1. **Preset Quality Layer.** `research.presets.ResearchPreset` gains
   four fields: `preset_class`, `rationale`, `expected_behavior`,
   `falsification`. `preset_class` is orthogonal to the existing
   `status` lifecycle label — one answers "what function does this
   preset serve in our research?" while the other answers "may the
   scheduler run this preset today?"
2. **Hypothesis Formalization.** `research/run_meta_latest.v1.json`
   bumps to schema v1.1 with additive preset metadata fields plus
   `preset_bundle_hypotheses` resolved read-only from the registry.
   All v1.0 consumers keep reading; the safe-default promotion
   exclusion rule (ADR-011 §9) is preserved.
3. **Screening vs Promotion Separation (labeling).** `report_agent`
   surfaces the two layers explicitly: `summary.screening` and
   `summary.promotion` sub-dicts, and `top_rejection_reasons_by_layer`
   sibling key. No pipeline logic changes; the existing
   `research.screening_process` / `research.screening_runtime` and
   `research.promotion` / `research.promotion_reporting` modules
   remain the owners of their respective decisions.
4. **Candidate Diagnostics (Report Intelligence).** New module
   `research/report_candidate_diagnostics.py` — pure join functions,
   consumer-only, no new metrics. Returns per-row verdict +
   rejection_layer + rejection_reasons + stability_flags +
   cost_sensitivity_flag + regime_suspicion_flag + hypothesis +
   metrics, plus explicit `join_stats` that surface unmatched
   counts per sidecar.
5. **Research Interpretability.** Markdown report sections
   (Hypothese / Samenvatting / Wat werkte / Wat werkte niet /
   Waarom / Volgende stap) render the joined diagnostics.
   `suggest_next_experiment` becomes layer-aware + failure-type
   aware using only existing reason-code vocabularies.

### Layer placement

- **Preset layer** (`research/presets.py`) owns the hypothesis
  metadata shape. The runner only *reads* it via
  `hypothesis_metadata_issues` + `validate_preset`.
- **Research layer** gains one new consumer module
  (`research/report_candidate_diagnostics.py`). All existing
  modules remain unchanged in schema + writer behavior.
- **Engine layer** is untouched. Tier 1 bytewise digest pins and
  walk-forward semantics remain byte-identical.
- **Orchestration layer** is untouched.
- **Dashboard / frontend** may optionally surface the new preset
  card fields (`preset_class`, `rationale`, `expected_behavior`,
  `falsification`); no mandatory change.

### Verdict semantics (pinned)

`report_candidate_diagnostics` emits exactly four verdicts:

- `rejected_screening` — fit_prior / eligibility / screening failure.
- `rejected_promotion` — passed screening, failed promotion hard gates.
- `needs_investigation` — promotion escalation (soft gates).
- `promoted` — promotion pass and row `goedgekeurd=True`.

Internal inconsistencies (`candidate_registry.status == "candidate"`
while `row.goedgekeurd=False`) surface as an explicit
`internal_final_gate_conflict` rejection_reason — never hidden.

### Stability / cost / regime flags — consumer-only

- **Stability flags** (`noise_warning`, `psr_below_threshold`,
  `dsr_canonical_below_threshold`, `bootstrap_sharpe_ci_includes_zero`)
  read the `reasoning.failed` / `.escalated` / `.passed` code lists
  from `candidate_registry_latest.v1.json`. True means the check
  fired, False means the check was explicitly passed, null means the
  check was not evaluated for this candidate.
- **cost_sensitivity_flag** reads a pre-computed boolean from the
  cost-sensitivity sidecar (when present). v3.11 never derives this
  boolean from raw numeric deltas; null when no pre-computed flag
  exists.
- **regime_suspicion_flag** reads a pre-computed per-candidate
  boolean from the regime-diagnostics sidecar (when present). v3.11
  introduces no new regime classification rules; null when the
  sidecar omits a flag.

### Join discipline (pinned)

- Primary key between `research_latest.results[]` rows and
  `candidate_registry.candidates[]`:
  `build_strategy_id(strategy_name, asset, interval, parsed_params)`
  — imported from `research.promotion.build_strategy_id` (used by
  the candidate registry writer since v3.9).
- Secondary key for defensibility / regime / cost sidecars:
  `(strategy_name, asset, interval)` triple.
- Unmatched counts surface in `join_stats`. Silent failures are a
  pinned non-goal; rows that cannot be joined carry an
  `unmatched_candidate_registry` rejection_reason so the mismatch
  remains visible.

### Validation semantics

`validate_preset` retains its v3.10 structural checks and adds
three hypothesis-metadata soft checks on enabled presets. Runner
default: emit `preset_validation_warning` tracker events and
continue. Opt-in strict: set `QRE_STRICT_PRESET_VALIDATION=1` to
raise `PresetValidationError` before the run starts. Graduation of
strict mode to default is deferred (v3.12+).

### Out of scope (explicitly deferred)

v3.11 does not deliver:

- Portfolio layer, candidate registry schema extensions,
  paper-trading validation gate, regime classification engine — see
  CHANGELOG.md §v3.11 Deferred.
- Any change to the engine, strategy registry, orchestration layer,
  or any frozen public output contract.
- New metrics, thresholds, or decisions in the report layer. The
  report remains explanation-only.

### Preserved bytewise

- `ROW_SCHEMA` (19 columns), `JSON_TOP_LEVEL_SCHEMA`.
- Tier 1 digest pins, multi-asset parity pins, fitted-feature
  semantics, execution event semantics, cost sensitivity replay
  invariants, exit diagnostics semantics.
- `candidate_registry_latest.v1.json` schema + writer; all other
  sidecar schemas and writers.
- Walk-forward `FoldLeakageError` semantics, resume-integrity gate,
  orchestration boundary import rules.

### Phase character

v3.11 is a **quality-hardening phase**, not a strategy-expansion,
feature-expansion, or engine-behavior-changing phase. Every change
is additive, consumer-only against the v3.10 artifact landscape,
and visible in the report output rather than the engine decisions.

