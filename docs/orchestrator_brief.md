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
configurable * no hardcoded constants --- ## 5. Orchestrator Responsibilities & Rules The 
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

