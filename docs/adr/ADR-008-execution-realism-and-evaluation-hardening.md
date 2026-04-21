# ADR-008: Execution Realism & Evaluation Hardening

Status: Accepted
Date: 2026-04-21
Phase: v3.8 (execution realism + evaluation hardening)
Supersedes: -
Superseded by: -
Related: ADR-006 (thin contract v2.0 deferred), ADR-007 (fitted
feature abstraction)

## Context

Up to and including v3.7, `BacktestEngine._simuleer_detailed`
collapsed the entire "signal emitted → trade booked" boundary into
a single inline step. A shifted integer signal was converted
directly into equity impact, with the flat `kosten_per_kant` fee
applied inline at entry and exit. The only per-trade artifact was a
dict in `trade_events` carrying regime and timing. There was no
auditable record of:

- the intended price vs the realized fill price,
- the fee amount realized on a given entry/exit,
- slippage as a typed, attributable quantity,
- rejection / cancellation reasons (if any),
- fold-local execution identity.

That implicit boundary was sufficient for the v3.5 / v3.6 / v3.7
goals (signal fidelity, multi-asset loading, fitted feature
abstraction), but it became a ceiling for four evaluation-hardening
questions:

1. **Fee attribution.** What fraction of a run's drawdown or
   underperformance is explained by transaction costs versus signal
   quality?
2. **Slippage attribution.** If the engine were to model adverse
   fills, where would the equity impact land, and is the current
   "fills at next-bar close" assumption the binding constraint on
   net PnL?
3. **Execution sensitivity.** If fees doubled or a fixed
   basis-point slippage were applied to every fill, does the
   strategy still clear the falsification gate, or does it collapse
   at a realistic cost assumption?
4. **Exit quality.** How much of the favorable excursion during a
   trade is actually captured by the exit rule? Are winning trades
   systematically giving back too much? Does the strategy exit too
   late relative to the favorable peak?

None of these questions could be answered without a deterministic,
auditable, layer-isolated record of what happened between signal
and trade, plus a non-mutating way to replay that record under
alternative cost assumptions and to inspect the realized path
against ideal exit points.

v3.8 is an **evaluation-hardening** phase. Strategy logic, feature
logic, fitted-feature semantics, and the baseline equity/trade
booking semantics are all deliberately untouched. The goal is to
make the existing research truth auditable and stress-testable,
not to change what that truth is.

## Decision

v3.8 adds four additive abstractions, delivered in five steps, each
landing with tests and no public contract drift:

1. **Canonical execution event scaffold** — a frozen, deeply
   immutable `ExecutionEvent` model in
   `agent/backtesting/execution.py`. `EXECUTION_EVENT_VERSION = "1.0"`.
   Five pinned kinds (`accepted`, `partial_fill`, `full_fill`,
   `rejected`, `canceled`); typed reason-code vocabulary; factory
   builders; a pandas/numpy-rejection sentinel; dict round-trip
   helpers. No engine emission in step 1.
2. **Deterministic engine emission.** `_simuleer_detailed` emits
   an `ExecutionEvent.accepted` + `ExecutionEvent.full_fill` pair
   at each booked entry and at each booked exit, with a
   monotone-within-window `sequence` and a fold-local `event_id`.
   Emission is gated by a keyword flag (`include_execution_events`)
   and is only enabled for OOS folds. Execution events are stored
   in `_last_window_streams["oos_execution_events"]`. Baseline
   equity math, fee application, and trade PnL are bytewise
   unchanged.
3. **Fee / slippage attribution basis.** Every emitted `full_fill`
   carries `fill_price`, `fee_amount` (derived from the
   pre-multiplication equity and `kosten_per_kant`),
   `slippage_bps = 0.0` under the baseline next-bar-close model,
   `requested_size = filled_size = 1.0`, and `intended_price`. The
   attribution is mechanical and auditable: event-derived fee sums
   reconcile with the equity drag applied inline by the engine.
4. **Cost sensitivity harness** —
   `agent/backtesting/cost_sensitivity.py`,
   `COST_SENSITIVITY_VERSION = "1.0"`. A pure evaluation-layer
   replay that takes `(execution_events, bar_return_stream,
   baseline_dag_returns, kosten_per_kant, scenarios)` and applies
   a per-fill multiplicative adjustment
   `(1 - m*k) * (1 - s_bps/1e4) / (1 - k)`. The baseline scenario
   reproduces the engine's `dag_returns` bytewise; alternative
   scenarios produce stressed-equity paths without mutating the
   baseline. Opt-in engine hook `BacktestEngine.build_cost_sensitivity`.
5. **Exit-quality diagnostics** —
   `agent/backtesting/exit_diagnostics.py`,
   `EXIT_DIAGNOSTICS_VERSION = "1.0"`. A pure evaluation-layer
   module that consumes `oos_trade_events` + `oos_bar_returns` +
   `kosten_per_kant` and produces per-trade and run-level
   MFE / MAE / realized return / capture ratio / winner giveback /
   exit lag / turnover-adjusted exit quality. Opt-in engine hook
   `BacktestEngine.build_exit_diagnostics`.

Discipline, pinned across all five steps:

- **Determinism.** Stdlib-only math in the evaluation layer; no
  randomness; no hidden state; no module-level caches. Given
  identical inputs the reports are bytewise identical across runs.
- **Auditability.** Every event carries version, sequence,
  fold-local identity, asset, side, and timestamp.
- **No hidden state.** Evaluation hooks read `_last_window_streams`
  and return a fresh dict. They mutate nothing.
- **No public artifact drift.** `research_latest.json` row and
  top-level schema, 19-column CSV, integrity /
  falsification sidecars, `candidate_id` hashing inputs — all
  unchanged.
- **Minimal regression surface.** Step 1 was pure scaffolding.
  Step 2 gated emission behind a keyword flag so non-OOS paths stay
  byte-identical. Steps 3–5 are evaluation-only modules with
  opt-in engine hooks not called from `run()`.
- **Strict layer separation.** Execution events live in
  `agent/backtesting/`; live/paper `Fill` lives in
  `execution/protocols.py`. The two layers remain disjoint in v3.8.

## Execution-event semantics (pinned by this ADR)

### Kinds

- `accepted` — signal was eligible to act. Pre-fill acknowledgement.
  Fill fields (`fill_price`, `filled_size`, `fee_amount`,
  `slippage_bps`) are `None`. `reason_code` is `None`.
- `full_fill` — the entire requested size was filled. All four
  fill fields are non-`None`; `filled_size == requested_size`;
  `reason_code` is `None`.
- `partial_fill` — scaffolded in the model but not emitted by the
  current engine. `0 < filled_size < requested_size`.
- `rejected` — scaffolded. `reason_code` required from
  `ALLOWED_REASON_CODES`.
- `canceled` — scaffolded. Same shape as `rejected`.

The current engine path emits only `accepted` + `full_fill` per
entry and per exit, reflecting the v3.7 truth: signals fill at the
next bar's close, one-sided fee per side, no partials, no explicit
rejections. Step 2 **mirrors** the current backtest truth; it does
not invent a broker model.

### Field semantics (v1.0)

- `intended_price: float` — the price the signal was evaluated
  at. Under the current engine that is the next-bar close.
- `fill_price: float | None` — the realized fill price on fill
  kinds. Under the current engine, `fill_price == intended_price`
  for both entries and exits (the engine does not inject price
  impact); `slippage_bps = 0.0`.
- `requested_size: float` — size the signal asked for. Under the
  current engine, `1.0` (unit-notional). `>= 0`.
- `filled_size: float | None` — realized fill size on fill kinds.
  Under the current engine, `1.0` on each emitted fill.
- `fee_amount: float | None` — account-currency fee. Always
  `>= 0` in v1.0. Computed at emission time from the
  pre-multiplication equity and `kosten_per_kant`, so event-derived
  fee sums reconcile with the engine's inline equity drag.
- `slippage_bps: float | None` — signed slippage in basis points
  relative to `intended_price`. Positive means adverse for the side
  taken. `0.0` under the current engine.
- `sequence: int` — monotone non-negative counter within a
  `(run_id, asset, fold_index)` scope. Assigned at emission.
- `fold_index: int | None` — fold this event belongs to.
- `reason_code / reason_detail` — present for `rejected` /
  `canceled`; `None` for fill kinds.
- `fingerprint: str | None` — structural placeholder; unset in
  v1.0. Reserved for future event-stream fingerprinting.

### Why `ExecutionEvent` is separate from live/paper `Fill`

- `execution/protocols.py::Fill` is a **live-broker success**
  record: `fill_price`, `slippage_bps`, `fee_amount`,
  `timestamp_utc`, venue / client-tag context. Only one state: the
  fill succeeded.
- `ExecutionEvent` must cover **five** states under the backtest
  path, including pre-fill acknowledgement and typed rejection
  codes. Merging the two would drag live-broker concerns into the
  evaluation surface and weaken one layer's contract to fit the
  other.
- Keeping them disjoint means the backtest path has no live
  dependency and the live layer has no research dependency. Each
  layer models what it needs; nothing imports across.

## Cost sensitivity semantics (pinned by this ADR)

- Cost sensitivity is a **replay / evaluation layer**, not a
  rerun. It does not call the strategy, does not rebuild features,
  does not invoke the engine loop, does not touch signals.
- Input: `execution_events` (emitted by step 2), `bar_return_stream`
  (the engine's `oos_bar_returns`, side-adjusted per-bar returns),
  `baseline_dag_returns` (the engine's OOS `dag_returns` for the
  same window), `kosten_per_kant`, and a tuple of `ScenarioSpec`.
- `ScenarioSpec(name, fee_multiplier, slippage_bps)` — `name` is
  free-form; `fee_multiplier` is a non-negative float applied to
  `kosten_per_kant`; `slippage_bps` is signed (positive adverse).
- **Baseline scenario** (`fee_multiplier=1.0, slippage_bps=0.0`)
  reproduces the engine's `dag_returns` bytewise. This is a pinned
  test invariant, not a target. It is the reason the replay can be
  trusted as a side-channel on the baseline.
- **Alternative scenarios** apply a per-fill multiplicative
  adjustment `(1 - m*k) * (1 - s_bps / 1e4) / (1 - k)` at the bar
  index `j+1` that follows each fill's bar. The result is a
  stressed equity path and a stressed `dag_returns`; the baseline
  is not mutated.
- Scope discipline: cost sensitivity reports **robustness
  diagnostics**. Its outputs are additive and are explicitly not
  a replacement for the baseline evaluation framework. Any
  scenario-conditioned metrics (e.g. a stress-adjusted Sharpe
  implied by the stressed `dag_returns`) remain internal /
  additive and do not replace Tier 1 metrics in `research_latest`.

## Exit-quality semantics (pinned by this ADR)

### Definitions (v1.0)

For each trade, the module reconstructs a side-adjusted *notional*
unrealized-return path:

1. `path[0] = 0.0` at the entry bar.
2. For each interior bar `q` strictly between entry and exit,
   `raw_ratio = 1.0 + bar_return[q] * side_sign`. Cumulate
   `raw_ratio`. `path[q] = (cumulative_raw - 1.0) * side_sign`.
3. `path[-1] = realized_pnl + kosten_per_kant` — the clean
   side-adjusted exit-bar notional return. This equals
   `(close_exit / close_entry - 1) * side` (up to floating-point
   rounding) for both long and short trades under the engine's PnL
   formula `pnl = (close_exit/close_entry - 1) * side - k`.

Pinned per-trade definitions:

- `mfe = max(max(path), 0.0)` — non-negative.
- `mae = max(-min(path), 0.0)` — non-negative (magnitude of the
  worst adverse excursion).
- `realized_return = path[-1]` — equals `pnl + k`.
- `capture_ratio = realized_return / mfe if mfe > 0.0 else None` —
  `None` for zero-MFE trades (zero-opportunity convention).
- `winner_giveback = mfe - realized_return if realized_return >
  0.0 else None` — `None` on losing trades. Non-negative by
  construction on winners.
- `exit_lag_bars = len(path) - 1 - argmax(path)` — integer; 0
  when the peak is at the exit bar.
- `holding_bars = len(path) - 1`.

Pinned aggregate:

- `turnover_adjusted_exit_quality =
  avg_capture_ratio * (1.0 - min(trade_count / max(total_bars, 1),
  1.0))` — `0.0` when `trade_count == 0`.

### Data source

Trade-path reconstruction uses only two engine-emitted streams:

- `_last_window_streams["oos_trade_events"]` for entry/exit
  timestamps, asset, fold, side, and realized `pnl`.
- `_last_window_streams["oos_bar_returns"]` for interior
  per-bar side-adjusted returns. The exit bar's bar-stream return
  is polluted by the engine's `(1 - k)` fee factor and is
  deliberately **not** used; the clean exit-bar anchor comes from
  `pnl + k`.

The module never reads close prices directly and never invokes
strategies or features. It is a pure path-analysis side-channel.

### Long/short symmetry

The `side_sign` transform — `+1` for long, `-1` for short — makes
the path construction symmetric. For a short, `raw_ratio`
recovers the close ratio correctly because the engine's stored
bar return is already side-adjusted.

### Zero-opportunity and zero-trade conventions

- Zero-opportunity trade (MFE clamps to 0): `capture_ratio = None`,
  `winner_giveback = None`.
- Zero-trade run (no `oos_trade_events`): summary floats are all
  `0.0`, `per_trade` is `[]`, `turnover_adjusted_exit_quality =
  0.0`.

### Bar-based path only

Exit-quality diagnostics are a **bar-based path analysis**. They do
not perform intrabar inference, do not ingest tick data, and do not
speculate about touches the engine did not observe. The pinned
definitions are statements about the engine's own bar-resolution
truth.

## Consequences

### Positive

- Execution is now auditable. Every OOS entry and exit leaves a
  typed event with price, fee, slippage, sequence, and fold
  identity.
- Fee and slippage impact are measurable. Events reconcile
  numerically with the engine's equity drag.
- Robustness to cost assumptions is testable. The cost-sensitivity
  harness produces stressed equity paths without mutating the
  baseline.
- Exit quality is now part of the falsification surface. Strategies
  with good signal but systematically late exits are visible.
- Paper-validation work has a cleaner foundation. The execution
  event model is the natural bridge a future paper/live layer can
  attach to, without mixing baseline semantics.

### Costs

- More internal evaluation surface area. Reviewers now have four
  additive modules (`execution`, `cost_sensitivity`,
  `exit_diagnostics`, plus the emission paths inside
  `_simuleer_detailed`) to keep in mind.
- Temporary coexistence of baseline and additive evaluation views.
  Tier 1 metrics remain the promotion gate; cost-sensitivity and
  exit-diagnostic reports are side-channels. A fresh reader must
  understand this separation before interpreting results.
- Some metrics remain intentionally heuristic / v1.0. The
  turnover-adjusted exit quality formula is a first cut; the
  cost-sensitivity adjustment factor assumes a multiplicative
  per-fill stress. Both are versioned (`"1.0"`) and pinned.
- Paper/live divergence analysis is still deferred.

## Alternatives considered and rejected

- **Rewriting baseline execution semantics in v3.8.** Rejected:
  drifts Tier 1 bytewise pins and the public output contract, and
  entangles an evaluation-hardening phase with a behavior change.
  Additive abstractions with opt-in hooks deliver the audit surface
  at zero regression risk.
- **Merging backtest execution events with the live broker
  `Fill`.** Rejected: `Fill` is a success-only record in the live
  layer; execution events must cover five states in the backtest
  layer. Merging would drag venue / client-tag / instrument-id
  concerns into research code and weaken both contracts.
- **Mutating baseline outputs under stressed scenarios.**
  Rejected: a replay layer that rewrites the baseline erases the
  audit trail it is supposed to support. The baseline scenario is
  required to reproduce the engine's `dag_returns` bytewise, which
  is only possible when the baseline itself is left intact.
- **Adding strategy-level exit logic changes in the same phase.**
  Rejected: exit-quality diagnostics measure what the current exit
  rules do; changing the rules simultaneously would make the first
  measurement uninterpretable. Exit-rule changes, if any, are a
  separate future decision backed by v3.8 evidence.
- **Widening directly into paper / live validation.** Rejected:
  paper validation is a formal gate that needs a clean evaluation
  foundation underneath it. v3.8 builds that foundation; paper
  validation is the next phase, not part of this one.
- **Computing `fingerprint` on execution events in v1.0.**
  Rejected: fingerprinting needs a stable serialization policy
  that reviewers can pin regression tests against. Landing a
  placeholder and deferring computation keeps the surface stable
  and avoids a premature commitment.

## Walk-forward and fold interaction

v3.8 respects the v3.7 walk-forward invariants verbatim:

- Execution events are emitted only for OOS folds (the training
  phase is excluded via `include_execution_events=not use_train`
  at the call site).
- `fold_index` is carried on every event. Cost-sensitivity and
  exit-diagnostic reports group by `(asset, fold_index)`.
- No cross-fold state. No module-level caches.
- Fitted-feature semantics (ADR-007) are unchanged; v3.8 does not
  read or depend on `FittedParams`.

## What v3.8 did **not** change

- Strategy logic (`agent/backtesting/strategies.py`,
  `thin_strategy.py`).
- Feature logic (`agent/backtesting/features.py`,
  `FEATURE_REGISTRY`, `FEATURE_VERSION`).
- Fitted feature semantics (`fitted_features.py`,
  `FITTED_FEATURE_REGISTRY`, `FITTED_FEATURE_VERSION`).
- Baseline equity / trade booking semantics. Tier 1 bytewise pins,
  multi-asset parity pins, walk-forward `FoldLeakageError`
  semantics, resume-integrity gate.
- Public JSON / CSV schemas. `research_latest.json` row and
  top-level schema, 19-column CSV, integrity and falsification
  sidecars.
- `candidate_id` hashing inputs. Execution shape is explicitly out
  of the hash (as it was in ADR-007).
- Paper / live workflow. `execution/protocols.py` and
  `execution/paper/polymarket_sim.py` are untouched.
- Regime or portfolio logic. No new regime machinery, no portfolio
  aggregation, no cross-asset sizing changes.

## Deferred items (explicit)

v3.8 does **not** deliver:

- **Paper validation as a formal gate.** Execution events give a
  clean bridge to a future paper layer; paper validation itself
  remains a later phase.
- **Live / paper divergence reporting.** Comparing live-broker
  `Fill` outcomes against backtest `ExecutionEvent` projections is
  a natural next step; no infrastructure for it lands here.
- **Full execution shortfall framework.** The current slippage
  model on the backtest path is `slippage_bps = 0.0` (next-bar
  close). A realistic shortfall model — quote-midpoint reference,
  bid/ask reconstruction, impact curves — is future work.
- **Richer rejection / partial-fill semantics in the engine.** The
  `ExecutionEvent` model scaffolds `partial_fill`, `rejected`, and
  `canceled` with a typed `ALLOWED_REASON_CODES` vocabulary. The
  current engine emits only `accepted` + `full_fill`. Richer
  emission awaits a concrete trigger (e.g. capacity-bounded
  sizing, explicit liquidity filters, venue-state modeling).
- **Broader promotion framework integration.** Cost-sensitivity and
  exit-quality reports are opt-in side-channels and are not wired
  into the promotion gate in v3.8. Integrating them as gates (e.g.
  "reject if stressed Sharpe < X" or "reject if average
  winner_giveback > Y") requires a separate policy decision and
  re-pin surface.
- **Regime / portfolio research.** Regime-conditioned evaluation,
  cross-asset portfolio aggregation, correlation-aware sizing — all
  remain out of scope.
- **Broader orchestration / platform automation.** Scheduler
  integration, CI promotion hooks, orchestrator brief §5
  automation targets — unchanged by this phase.
- **Thin contract v2.0 unification (ADR-006) and broader strategy
  migration to the fitted path (ADR-007).** Still deferred; v3.8
  neither introduces new triggers for ADR-006 nor resolves any of
  its conditions.
- **Config-level surfacing of the opt-in hooks.**
  `build_cost_sensitivity` and `build_exit_diagnostics` are
  callable on `BacktestEngine` instances and are not exposed
  through the research pipeline config.

## Scope discipline statement

v3.8 is an **evaluation-hardening phase**, not a strategy-expansion
phase. Every change in this phase is additive, deterministic,
non-mutating with respect to baseline results, and gated behind
opt-in hooks or flags that default off. The Tier 1 digests, public
artifacts, and promotion inputs are pinned at their v3.7 values.

Step 1 landed abstraction without emission. Step 2 landed emission
without behavior change. Step 3 landed a replay layer without
baseline mutation. Step 4 landed diagnostics without exit-rule
changes. Step 5 (this document) lands the record without any
runtime change at all.
