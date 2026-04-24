# Changelog

All notable changes to the trading-agent research and backtesting
stack are documented here. Live trading / orchestration surfaces
outside the research path are not tracked in this file.

## [v3.15] — Paper Validation Engine

Date: 2026-04-24
Branch: `feature/v3.15-paper-validation-engine`

Strictly additive **paper validation engine** on top of the v3.14
portfolio / sleeve layer. Geen live trading, geen broker-integratie,
geen shadow deployment, geen allocator. Elke wijziging is additief;
de v3.12 / v3.13 / v3.14 frozen artifacts blijven onaangetast en
v3.15 schrijft nooit naar hun paths.

v3.15 beantwoordt drie vragen per kandidaat:

1. **Ledger** — welke signal/order/fill/reject/skip/position events
   genereert deze kandidaat onder paper-semantiek?
2. **Divergence** — hoe wijkt paper af van de engine baseline
   (metrics delta, venue-cost delta, timestamp-aligned coverage)?
3. **Readiness** — is deze kandidaat klaar voor een eventuele v3.16+
   paper-promotion, of is er een blocking reason? `live_eligible`
   is in v3.15 altijd `False`, hard gepind.

### Added

- **Venue mapping** (`research/paper_venues.py`). `asset_type →
  ScenarioSpec` mapping voor `crypto` (Bitvavo: 0.25% per kant +
  10 bps slippage), `equity` (IBKR: €1/€2000 notional = 5 bps per
  kant + 10 bps slippage; `VENUE_IBKR_EQUITY_ASSUMED_NOTIONAL_EUR`
  geëxposeerd in elk artifact dat IBKR gebruikt), en
  `polymarket_binary` (2% spread + 10 bps — **gedefinieerd, niet
  toegepast** in v3.15). `unknown` / `futures` / `index_like`
  krijgen geen fallback — `venue_name_for_asset_type` returnt
  `None` en readiness vertaalt dat naar een
  `insufficient_venue_mapping` blocking reason.
  `PAPER_VENUES_VERSION = "v0.1"`.
- **Timestamped returns bridge**
  (`research/candidate_timestamped_returns_feed.py`). Closes v3.14
  handoff §8.1. Consumeert de al-bestaande
  `evaluation_report.evaluation_streams.oos_daily_returns` typed
  stream van de engine zonder engine-contract uitbreiding. Nieuwe
  `TimestampedCandidateReturnsRecord` dataclass draagt parallel
  `timestamps` en `daily_returns` arrays plus een expliciete
  `stream_error` code wanneer de engine stream missing / malformed
  / duplicate was. v3.14 `CandidateReturnsRecord` blijft frozen.
- **Shared OOS-stream validator** (`research/_oos_stream.py`).
  Extracted uit `portfolio_reporting._normalize_stream` zodat
  `candidate_timestamped_returns_feed` en `paper_divergence`
  dezelfde implementatie hergebruiken. Gedrag byte-identical met
  pre-extraction — v3.12+ artifacts blijven byte-identical.
- **Paper ledger** (`research/paper_ledger.py`). First-class
  lifecycle projectie. Gesloten event-taxonomy (`signal`, `order`,
  `fill`, `reject`, `skip`, `position`) en gesloten
  evidence-status taxonomy (`reconstructed`, `projected_minimal`,
  `projected_insufficient`). Elk event draagt expliciete `lineage`
  pointers naar `oos_execution_events`. Signal + position events
  zijn `projected_minimal` omdat de engine ze niet apart
  serialiseert — v3.15 vindt nooit bron-evidence uit. Unmapped
  venues krijgen alleen `signal` + `reject(reason=
  insufficient_venue_mapping)`. Deterministic ordering via
  `(timestamp_utc, lifecycle_index, event_id)`.
  `PAPER_LEDGER_VERSION = "v0.1"`.
- **Paper divergence** (`research/paper_divergence.py`). Per
  candidate / per sleeve / portfolio-level divergence. Math is het
  per-fill multiplicatieve model uit
  `agent.backtesting.cost_sensitivity` (analytisch equivalent voor
  scalar metrics; bar-level timestamped paper-returns stream
  deferred naar v3.16). Rapporteert: `metrics_delta` (final
  equity, cumulative adjustment, sharpe proxy), `venue_cost_delta`
  (per-fill adjustment, fee drag delta vs baseline, slippage drag),
  `timestamp_aligned_return_diff` (coverage window), en
  `divergence_severity` via named drempels
  (`DIVERGENCE_SEVERITY_MEDIUM_BPS=25`,
  `DIVERGENCE_SEVERITY_HIGH_BPS=75`). Portfolio-level gebruikt
  `exact_timestamp_intersection` (mirror van
  `portfolio_reporting.ALIGNMENT_POLICY`).
  `PAPER_DIVERGENCE_VERSION = "v0.1"`.
- **Paper readiness** (`research/paper_readiness.py`). First-class
  gate. Gesloten blocking-reason taxonomy:
  `insufficient_venue_mapping`, `insufficient_oos_days`,
  `missing_execution_events`, `excessive_divergence`,
  `malformed_return_stream`, `no_candidate_returns`. Gesloten
  warning taxonomy: `negative_paper_sharpe` (warning by default,
  niet blocking), `projected_insufficient_events_ratio_high`,
  `medium_divergence`. Status ∈ `{ready_for_paper_promotion,
  blocked, insufficient_evidence}`. Thresholds named:
  `MIN_PAPER_OOS_DAYS=60`, `MIN_PAPER_SHARPE_FOR_READY=0.3`,
  `WARN_PROJECTED_INSUFFICIENT_RATIO=0.20`. `live_eligible=False`
  is top-level hard-pinned in de payload — geen enkel codepath
  zet het op `True`. `PAPER_READINESS_VERSION = "v0.1"`.
- **Parallel façade** (`research/paper_validation_sidecars.py`).
  Mirrors v3.14 façade exactly. Frozen
  `PaperValidationBuildContext` + single
  `build_and_write_paper_validation_sidecars(ctx)` entry. All
  writes gaan door `_sidecar_io.write_sidecar_atomic` zodat elke
  artifact canonical en byte-reproducible is.
- **Runner hook** (`research/run_research.py`). Één additieve block
  na de v3.14 portfolio-sleeve hook. Leest
  `sleeve_registry_latest.v1.json` voor sleeve membership lookup,
  construeert `PaperValidationBuildContext` uit de al-bestaande
  `evaluations` accumulator + registry_v2 payload, en roept de
  façade aan. Try/except zodat v3.15 falen nooit de v3.14 run
  maskeert.
- **Report extension** (`research/report_agent.py`).
  `_paper_layer_summary()` helper + optionele top-level
  `paper_layer_summary` key + `_append_paper_layer_section()`
  markdown renderer. Aggregeert ledger event counts, divergence
  severity distribution, readiness counts, candidate count. Report
  `schema_version` blijft `"1.1"`.
- **Dashboard endpoints** (`dashboard/dashboard.py`). Vier read-only
  `@requires_auth` endpoints:
  - `GET /api/registry/paper` — summary (readiness counts +
    divergence severity distribution + ledger event counts +
    artifact states)
  - `GET /api/registry/paper/ledger`
  - `GET /api/registry/paper/divergence`
  - `GET /api/registry/paper/readiness`
  Alle vier pinnen `live_eligible=false` in zowel missing-state
  als happy-path schemas.
- **Vier nieuwe sidecars** (alle `schema_version="1.0"`,
  `authoritative=false`, `diagnostic_only=true`,
  `live_eligible=false`):
  - `research/candidate_timestamped_returns_latest.v1.json`
  - `research/paper_ledger_latest.v1.json`
  - `research/paper_divergence_latest.v1.json`
  - `research/paper_readiness_latest.v1.json`

### Changed

- `research/portfolio_reporting.py`: `_normalize_stream` is nu een
  thin delegate naar `research._oos_stream.normalize_oos_daily_return_stream`.
  Gedrag byte-identical; v3.12 artifacts blijven byte-identical.
- `research/run_research.py`: één nieuwe try/except block met
  `build_and_write_paper_validation_sidecars` direct na de v3.14
  hook. Runner blijft dun.
- `research/report_agent.py`: additief — `paper_layer_summary` top-
  level key + markdown sectie. `schema_version` blijft `"1.1"`.
- `dashboard/dashboard.py`: vier nieuwe routes; bestaande routes
  onveranderd.
- `VERSION`: `3.14.1` → `3.15.0`.

### Deliberately NOT changed

- `research/candidate_returns_feed.py` (v3.14 frozen). De v3.15
  precision-upgrade is een *nieuwe* sidecar — v3.14's shape en
  bytes blijven onaangetast.
- `research/candidate_scoring.py`. `SCORING_FORMULA_VERSION` blijft
  `"v0.1-experimental"`, `composite_status` blijft `"provisional"`,
  `authoritative` blijft `False`. Scoring-bump naar
  `v0.2-experimental` is uitgesteld naar v3.16 (vereist
  evidence-gedreven goldens-update).
- `agent/backtesting/engine.py` + `agent/backtesting/cost_sensitivity.py`.
  v3.15 hergebruikt beide zonder wijziging.
- Geen forced-sleeves, geen allocator, geen Kelly, geen
  vol-targeting, geen frontend UI-tab.

### Tests

- **Unit**: 63 nieuw
  - `tests/unit/test_paper_venues.py` (16)
  - `tests/unit/test_oos_stream.py` (9)
  - `tests/unit/test_candidate_timestamped_returns_feed.py` (6)
  - `tests/unit/test_paper_ledger.py` (8)
  - `tests/unit/test_paper_divergence.py` (7)
  - `tests/unit/test_paper_readiness.py` (11)
  - `tests/unit/test_paper_validation_sidecars_facade.py` (5)
  - `tests/unit/test_dashboard_api_v315.py` (8)
  - `tests/unit/test_paper_no_live_invariant.py` (3)
  - `tests/unit/test_report_agent_paper_layer.py` (5)
- **Integration**: 3 nieuw
  - `tests/integration/test_paper_validation_end_to_end.py` (3)
- **Regression**: 4 nieuw
  - `tests/regression/test_v3_15_artifacts_deterministic.py` (4)

Totaal **70 nieuwe tests**, alle green. Static analysis (mypy,
flake8, bandit) schoon op alle v3.15 modules.

### Known limitations (voor v3.16)

- **Bar-level timestamped paper-returns stream** deferred. v3.15
  gebruikt het analytische per-fill multiplicatieve model
  (scalar-equivalent aan `cost_sensitivity`). v3.16 kan bar-exact
  replay inschakelen via `build_cost_sensitivity_report` met
  `oos_bar_returns` + `fill_positions` plumbing.
- **Polymarket venue** gedefinieerd, niet toegepast. Wacht op
  Polymarket candidates in de research pipeline via Bot /
  DataArbitrage agent integratie.
- **Scoring bump** `v0.1-experimental → v0.2-experimental` blijft
  uitgesteld. `regime_breadth_signal` als composite-component is
  pas gerechtvaardigd na meerdere runs met consistent bewijs.
- **Allocator / Kelly / vol-targeting** expliciet buiten scope.
  v3.15 blijft equal-weight paper-portfolio (mirror v3.14).
- **Frontend UI**: geen paper-tab; consumptie via 4 endpoints +
  markdown report. v3.16+ kan een read-only paper-tab toevoegen
  wanneer operationele behoefte bevestigd is.
- **Paper-to-live promotion** niet geïmplementeerd.
  `live_eligible=False` is hard gepind en v3.15 levert geen
  codepath die dit verandert.

---

## [v3.14.1] — Runtime budget + preset universe hotfix

Date: 2026-04-24
Branch: `fix/v3.14.1-runtime-budget-and-preset-universe`

Targeted hotfix on top of v3.14 for the two blocking bugs that
prevented daily / canary runs from completing on the VPS. No new
features, no v3.15 work, no new strategies, no output contract
changes. `research/research_latest.json` and
`research/strategy_matrix.csv` schemas are untouched.

### Fixed

- **Screening candidate budget default** — raised from 60s to
  300s (`research/run_research.py::DEFAULT_SCREENING_CANDIDATE_BUDGET_SECONDS`).
  The 60s default was too aggressive for warm-start screening on
  Hetzner CX22 and caused frequent unwanted candidate interrupts.
  Config override via `research.screening.candidate_budget_seconds`
  remains authoritative — explicit values (including `0` =
  no budget) are respected verbatim.
- **Candidate-level timeout on screening interrupt** —
  `execute_screening_candidate_isolated` returning
  `execution_state="interrupted"` no longer raises
  `KeyboardInterrupt`. That `BaseException` bypassed the enclosing
  `except Exception` and killed the entire daily / canary run on
  a single candidate timeout, leaving `running` artifacts behind.
  The branch now emits a candidate-level outcome:
  - `final_status = FINAL_STATUS_TIMED_OUT`
  - `reason_code = "candidate_budget_exceeded"` (already a
    documented v3.12 taxonomy code; no new strings)
  - `legacy_decision.status = "rejected_in_screening"`
  - `legacy_decision.reason = "candidate_budget_exceeded"`
  - preserves isolated_result `elapsed_seconds`, `samples_total`,
    `samples_completed`
  - emits a `screening_candidate_budget_exceeded` tracker event
  Control falls through into the regular post-candidate loop; the
  existing `FINAL_STATUS_TIMED_OUT` branch at
  `run_research.py:2313` continues to tally
  `batch["timed_out_count"]`. The run proceeds to the next
  candidate. A real user `Ctrl-C` from outside still raises
  `BaseException` and propagates unchanged — the enclosing handler
  was never widened.
- **Preset universe is load-bearing for preset-runs** — new helper
  `research.universe.build_research_universe_from_preset`. Before
  v3.14.1, preset-runs first resolved assets via
  `build_research_universe(research_config)`, which reads
  `research.universe.source` (default `crypto_major`). The
  preset's `universe` field was effectively ignored. That meant
  `trend_equities_4h_baseline` silently ran on crypto assets
  instead of NVDA/AMD/ASML/MSFT/META/AMZN/TSM.
  The runner at `run_research.py:1843-1853` now branches: if a
  preset is active, route through the preset helper; otherwise
  use the config-driven path. `preset.universe` is authoritative,
  `intervals` defaults to `[preset.timeframe]`,
  `interval_lookbacks` / `default_lookback_days` still come from
  `research_config`. Empty `preset.universe` raises `ValueError`.
  Snapshot provenance uses `source="preset:<name>"` and
  `resolver="preset"` so lineage is unambiguous.

### Changed (additive only)

- `research/run_research.py`: three edits (budget default,
  interrupted branch rewrite, preset-aware universe wiring).
- `research/universe.py`: new public function
  `build_research_universe_from_preset` +
  `_infer_asset_type_from_symbol` helper.
- `VERSION`: `3.14.0` → `3.14.1`.

### Deliberately **not** changed

- No new config keys.
- No taxonomy extensions (`candidate_budget_exceeded` is a v3.12
  code).
- No engine / cost_sensitivity / backtesting surface change.
- No sidecar schema or byte-identity change.
- No frontend work, no dashboard endpoints, no execution-bridge
  surface.
- No v3.15 paper-validation changes on this branch.

### Tests (19 new)

- `tests/unit/test_run_research_screening_budget_v3_14_1.py` (9):
  default = 300, config override authoritative, zero = no-budget
  sentinel, negative clamped to zero, interrupted branch projects
  to candidate-level timeout with correct shape, no legacy
  `KeyboardInterrupt` raise, taxonomy membership, except-scope
  invariant (`except Exception`, not `BaseException`).
- `tests/unit/test_run_research_preset_universe_v3_14_1.py` (10):
  trend_equities_4h_baseline resolves to its preset universe (not
  crypto_major), crypto preset resolves to crypto asset_type,
  intervals = [preset.timeframe], empty preset.universe → clear
  ValueError, None preset rejected, preset path ignores config
  `research.universe.source`, lookback config still honoured,
  non-preset runs still use `build_research_universe`, default
  still `crypto_major` for empty config, runner source actually
  calls the preset helper.

All 19 green. Full suite: green (delta documented in handoff).

---

## [v3.14] — Portfolio / Sleeve Research

Date: 2026-04-23
Branch: `feature/v3.14-portfolio-sleeve-research`

Strictly additive portfolio / sleeve research layer on top of the
v3.12 candidate and v3.13 regime infrastructure. No paper / live /
broker surfaces, no allocator, no Kelly overlay, no optimizer. Every
change is additive; `research/research_latest.json`,
`research/strategy_matrix.csv`, `research/candidate_registry_latest.v1.json`,
and the shape / values of every v3.12 field on
`research/candidate_registry_latest.v2.json` remain byte-identical.
All v3.14 data lands in four new adjacent sidecars joined on
`candidate_id` / `sleeve_id` — no in-place v2/v3.13 mutation.

The v3.14 layer answers "how do these candidates *compose*?" rather
than "is this candidate good?". It is diagnostic-first and explicitly
non-authoritative (`authoritative=false`, `diagnostic_only=true` in
every payload).

### Added

- **Sleeve registry** (`research/sleeve_registry.py`). Deterministic
  grouping of v3.12 candidates by `(strategy_family, asset_class,
  interval)` triples, derived from the existing `experiment_family`
  and `interval` fields on the v2 registry. Only lifecycle
  `candidate` entries are members; `rejected` / `exploratory` are
  excluded. Optional research-variant sleeves with a
  `__regime_filtered` suffix exist for every candidate whose v3.13
  overlay reports `regime_assessment_status == "sufficient"`.
  `ASSIGNMENT_RULE_VERSION = "v0.1"`.
- **Per-candidate returns bridge** (`research/candidate_returns_feed.py`).
  Typed extraction of per-candidate daily-return series from the
  in-memory `evaluations` list populated in
  `research.run_research.run_research`. Returns are read from the
  engine's public `last_evaluation_report.evaluation_samples.daily_returns`
  accessor — no engine contract widening. Every record carries an
  explicit `alignment = "utc_daily_close"` and
  `timestamp_semantics = "engine_window_close_utc"` so consumers can
  reason about the data lineage.
- **Width-axis feed** (`research/regime_width_feed.py`). Closes the
  v3.13 §8.1 gap. For every `(asset, interval)` pair in the v2
  registry the feed reuses the cached OHLCV response produced by the
  backtest's own `data.repository.MarketRepository.get_bars` call,
  runs `research.regime_classifier.classify_bars`, and produces a
  per-candidate `width_distributions` dict. The v3.13 façade now
  consumes this dict so `regime_dependency_score_width`,
  `regime_tags_summary.width`, and the `trend_expansion` gate can
  emit real evidence-backed values. Per-source lineage (asset,
  interval, bar count, adapter, `cache_hit`) is persisted alongside
  the raw distributions. `WIDTH_FEED_VERSION = "v0.1"`.
- **Portfolio / sleeve diagnostics**
  (`research/portfolio_diagnostics.py`). Diagnostic-only correlation
  matrix (aligned-suffix) across the candidate universe, an
  equal-weight research portfolio (Sharpe / Sortino / annualised
  return / max drawdown / Calmar), drawdown attribution over the
  worst-window of the equal-weight portfolio, HHI-based concentration
  warnings on asset and sleeve dimensions, intra-sleeve correlation
  warnings, turnover-activity-ratio per sleeve, and a
  regime-conditioned `regime_breadth_diagnostic` per sleeve derived
  from v3.13 per-axis dependency scores. Every threshold is a named,
  warning-only constant exposed in the artifact `thresholds` block:
  `MIN_OVERLAP_DAYS=90`, `HHI_WARN_THRESHOLD=0.4`,
  `INTRA_SLEEVE_CORR_WARN_THRESHOLD=0.7`,
  `MAX_DRAWDOWN_CONTRIBUTION_WARN_THRESHOLD=0.5`,
  `MIN_SAMPLES_FOR_STATS=5`. `DIAGNOSTICS_LAYER_VERSION = "v0.1"`.
- **Parallel façade** (`research/portfolio_sleeve_sidecars.py`).
  Mirrors the v3.12 and v3.13 façade pattern exactly. One
  `PortfolioSleeveBuildContext` dataclass + single
  `build_and_write_portfolio_sleeve_sidecars(ctx)` entry point
  invoked once from `run_research.py` after the v3.13 façade.
  Canonical atomic writes reuse `_sidecar_io.write_sidecar_atomic`.
- **New sidecars** (overlay-first, all `schema_version="1.0"`):
  - `research/sleeve_registry_latest.v1.json`
  - `research/candidate_returns_latest.v1.json`
  - `research/portfolio_diagnostics_latest.v1.json`
  - `research/regime_width_distributions_latest.v1.json`
- **API endpoint** — `GET /api/registry/portfolio`. Read-only,
  `@requires_auth`, mirrors `/api/registry/regime` verbatim. Stable
  missing-state payload with
  `artifact_state="missing"`, `authoritative=false`,
  `diagnostic_only=true`, and empty collection fields so consumers
  can differentiate "fresh environment" from "corrupted sidecar".

### Changed (additive only)

- `research/run_research.py`: three new thin additions after the
  v3.12/v3.13 façade block — (1) width feed driver, (2) in-place
  wiring of `width_distributions=...` into the existing v3.13
  context, (3) single call to the v3.14 façade with registry v2 +
  regime overlay + in-memory evaluations. No engine-contract change.
- `research/report_agent.py`: new `_portfolio_layer_summary()` helper
  + new optional top-level key `portfolio_layer_summary` + one
  additive markdown section. Report `schema_version` stays `"1.1"`.
- `dashboard/dashboard.py`: `/api/registry/portfolio` added.

### Deliberately **not** changed in v3.14

- `research/candidate_scoring.py` — untouched. `regime_breadth` is
  exposed only as a diagnostic in the portfolio artifacts and the
  sleeve registry. No scoring-formula bump in v3.14;
  `SCORING_FORMULA_VERSION = "v0.1-experimental"`,
  `composite_status = "provisional"`, `authoritative = False` are all
  preserved.
- `research/candidate_registry_v2.py` — untouched. Overlay join is
  preserved as the canonical pattern.
- `research/regime_sidecars.py` — signature untouched.
  `width_distributions` is now populated via the new feed instead of
  `None`; no API change.
- `agent/backtesting/*` — untouched. No engine-contract widening.
- No new strategies, no new presets, no frontend work, no
  execution / paper / live surfaces, no allocator, no optimizer, no
  Kelly overlay.

### Tests (34 new)

- `tests/unit/test_regime_width_feed.py` (5): cache-hit determinism,
  graceful fetch-failure, bucket-count correctness, per-pair
  deduplication, missing-date-range skip.
- `tests/unit/test_candidate_returns_feed.py` (5): record schema,
  insufficient-returns path, alignment field, canonical ordering,
  deduplication rule.
- `tests/unit/test_sleeve_registry.py` (6): empty-registry
  behaviour, lifecycle filter, family/interval grouping,
  regime-filtered variant emission only on `sufficient`, determinism
  under input reordering, canonical payload shape.
- `tests/unit/test_portfolio_diagnostics.py` (6): empty-input
  payload shape, correlation+portfolio happy path, concentration
  warning threshold trip, intra-sleeve correlation warning for
  duplicated series, `MIN_OVERLAP_DAYS` flag semantics, envelope
  shape.
- `tests/unit/test_portfolio_sleeve_sidecars_facade.py` (4):
  all-core sidecars written, width sidecar present only when feed
  attached, byte-identical across reruns, graceful empty-registry
  fallback.
- `tests/unit/test_dashboard_api_v314.py` (3): auth, missing-state
  schema, happy-path payload.
- `tests/regression/test_v3_14_artifacts_deterministic.py` (3):
  byte-identical reruns, pinned `schema_version` everywhere, frozen
  v1 registry never touched.
- `tests/integration/test_portfolio_sleeve_end_to_end.py` (2):
  end-to-end wiring produces all four sidecars, rerun byte-identity.

Full suite: **1322 passed, 1 skipped, 0 failed** in 11m12s.
mypy / flake8 / bandit clean on every new and modified v3.14 module.

### Known v3.14 limitations (v3.15 pickup)

- Correlation matrix uses suffix-alignment on aggregated daily
  returns rather than timestamp alignment — honest for the current
  engine output shape, but loses precision when candidates run on
  non-overlapping windows. A typed timestamped returns stream in
  v3.15 would upgrade this.
- Joint `(trend, vol)` bar tagging is still not available;
  `trend_low_vol` continues to use the conservative intersection
  documented in v3.13.
- `regime_breadth_signal` is a diagnostic on portfolio artifacts
  only — `candidate_scoring.py` remains at `v0.1-experimental` and
  non-authoritative. Promoting breadth into the composite is v3.15+.
- No frontend surface. Consumption via `/api/registry/portfolio` and
  the markdown report.
- Equal-weight only. Volatility-targeted and capped-concentration
  research portfolios deferred.

## [v3.13] — Regime Intelligence & Gating

Date: 2026-04-23
Branch: `feature/v3.13-regime-intelligence`

Diagnostic-first regime layer on top of the realized v3.12 candidate
infrastructure. No new strategies, no new presets, no new base
metrics, no allocation logic. Every change is additive; the
v3.11/v3.12 public contracts (`research_latest.json`,
`strategy_matrix.csv`, `candidate_registry_latest.v1.json`, and the
shape/values of every v3.12 field on
`candidate_registry_latest.v2.json`) remain byte-identical. All v3.13
data lands in two new adjacent sidecars joined on `candidate_id` —
no in-place v2-registry enrichment.

### Added

- **Regime classifier** (`research/regime_classifier.py`).
  Axis-separable, deterministic, `shift(1)` no-lookahead. Three
  independent axes: `trend` (trending / non_trending / insufficient),
  `vol` (low_vol / high_vol / insufficient), `width` (expansion /
  compression / insufficient). Trend and volatility normalizers
  consume the labels already produced by
  `agent/backtesting/regime.py`; the width axis is a new Bollinger
  bandwidth vs rolling-median comparator. Explicit named constants
  for every threshold; no tuning loop.
  `REGIME_CLASSIFIER_VERSION = "v0.1"`.
- **Per-candidate regime diagnostics**
  (`research/regime_diagnostics.py`). HHI-style per-axis dependency
  scores (`regime_dependency_score_trend|vol|width`) plus an
  explicit aggregate (`overall`). Hard sufficiency gates
  (`MIN_TRADES_PER_AXIS=10`, `MIN_REGIMES_WITH_EVIDENCE=2`) produce
  `regime_assessment_status ∈ {sufficient,
  insufficient_regime_evidence}`. Silence is preferred over
  fabricated precision — missing or thin axes emit `null` metrics,
  never crash. `REGIME_CONCENTRATED_THRESHOLD = 0.7`.
- **Multi-rule gating framework** (`research/regime_gating.py`).
  Three fixed predefined rules — `trend_only`, `trend_low_vol`,
  `trend_expansion` — each reported with baseline / filtered /
  delta for every sufficient candidate. No gate search, no
  optimization loop, no winner-picking (no `best_rule` field — it
  is always `null` in v3.13). Width-dependent rules mark
  `insufficient_axis_evidence` rather than fabricate a filter.
  Conjunctions with vol use an explicitly documented conservative
  intersection (joint bar tagging is deferred to v3.14).
- **Parallel façade** (`research/regime_sidecars.py`). One
  `RegimeSidecarBuildContext` + `build_and_write_regime_sidecars()`
  call is the sole new hook in `run_research.py`. Canonical atomic
  writes reuse `_sidecar_io.write_sidecar_atomic`. v3.12 façade
  stays untouched.
- **New sidecars** (overlay-first):
  - `research/regime_intelligence_latest.v1.json`
    (`schema_version="1.0"`, `classifier_version="v0.1"`,
    `regime_layer_version="v0.1"`).
  - `research/candidate_registry_regime_overlay_latest.v1.json`
    (`schema_version="1.0"`). Registry-shaped overlay; consumers
    join on `candidate_id` against `candidate_registry_latest.v2.json`.
    Fields: `regime_assessment_status`,
    `regime_dependency_scores`, `regime_concentrated_status`
    (`emitted | below_threshold | insufficient_evidence |
    absent_sidecar`), `regime_gating_summary.best_rule = null`.
- **API endpoint** — `GET /api/registry/regime`. Read-only,
  `@requires_auth`, mirrors the v3.12 endpoint pattern. Stable
  missing-state payload with `schema_version="1.0"`,
  `classifier_version=null`, `generated_at_utc=null`,
  `artifact_state="missing"`, `entries=[]`.

### Changed (additive only)

- `research/rejection_taxonomy.py`: `derive_taxonomy()` accepts
  optional `regime_intelligence=` and
  `regime_concentrated_threshold=` kwargs. When the intelligence
  sidecar carries a matching entry with sufficient evidence and any
  per-axis score ≥ threshold, `regime_concentrated` is emitted with
  `derivation_method="classifier_output"` and
  `observed_sources` lists the triggering axis
  (e.g. `regime_dependency_score_trend`). Sidecar absent for the
  candidate → legacy `flag_source` path unchanged. Sidecar present
  but evidence insufficient → silence (no overclaiming). Positional
  v3.12 signature stays byte-compatible.
- `research/report_agent.py`: new `_enrich_with_regime_fields()`
  additive helper and new optional top-level key
  `regime_layer_summary`. Report `schema_version` stays `"1.1"`.
- `research/run_research.py`: one new thin call after the v3.12
  façade. In v3.13 `width_distributions=None` so the width axis is
  marked insufficient until v3.14 wires a per-asset OHLCV feed.
- `dashboard/dashboard.py`: `/api/registry/regime` added.

### Deliberately **not** changed in v3.13

- `research/candidate_scoring.py` — untouched to keep every v3.12
  field on the v2 registry byte-identical in shape and value.
  Regime-breadth integration into the composite is deferred to
  v3.14 with a proper `SCORING_FORMULA_VERSION` bump and regression
  golden update.
- `research/candidate_registry_v2.py` — untouched. Overlay join
  replaces in-place enrichment.
- `agent/backtesting/*` — untouched. No engine-contract widening.
- No new strategies, no new presets, no frontend refactor, no
  execution/paper/live surfaces, no dynamic allocation.

### Tests (44 new)

- `tests/unit/test_regime_classifier.py` (15): determinism,
  no-lookahead invariant, expansion/compression synthetic fixtures,
  insufficient lookback handling.
- `tests/unit/test_research_regime_diagnostics.py` (8): per-axis
  HHI scores, sufficiency gates, width plumbing, upstream
  unknown-label collapse, overall aggregate semantics.
- `tests/unit/test_regime_gating.py` (7): three fixed rules,
  width-dependent rules marked insufficient, conservative
  intersection on `trend_low_vol`, no winner-picking API surface.
- `tests/unit/test_rejection_taxonomy_v3_13.py` (5):
  classifier-output derivation above threshold, silence below and
  on insufficient evidence, legacy fallback when the sidecar is
  absent.
- `tests/unit/test_dashboard_api_v313.py` (3): auth, missing-state
  schema, happy-path payload.
- `tests/integration/test_regime_sidecars_end_to_end.py` (6):
  both sidecars written, overlay join on every `candidate_id`,
  missing-state graceful, byte-identical reruns, `best_rule=null`.
- `tests/regression/test_v12_contracts_preserved.py` (4):
  `derive_taxonomy` v3.12 signature and semantics preserved when
  the new v3.13 optional params are unused.

Full suite: **1221 passed, 1 skipped, 0 failed**.
mypy / flake8 / bandit clean on every new and modified v3.13 module.

### Known v3.13 limitations (v3.14 pickup)

- Width axis runs empty in production (width_distributions=None);
  classifier is complete and tested, only the feed is deferred.
- Joint (trend, vol) bar tagging is not available in
  `regime_diagnostics_latest.v1.json`; `trend_low_vol` uses a
  conservative intersection.
- Sharpe / max-drawdown on filtered subsets are reported as `null`
  because bar-level streams are not serialized.
- Composite scoring is unchanged; regime-breadth integration is
  v3.14 work.

## [v3.12] — Candidate Promotion Framework 2.0

Date: 2026-04-23
Branch: `feature/v3.12-candidate-promotion-framework`

First-class candidate lifecycle and lineage. No new strategies, no
new metrics, no new promotion thresholds. Every change is additive;
the v3.11 public contracts (`research_latest.json`,
`strategy_matrix.csv`, `candidate_registry_latest.v1.json`) remain
byte-identical. All v3.12 data lands in new adjacent sidecars with
their own `schema_version` pins.

### Added

- **Candidate lifecycle status model** (`research/candidate_lifecycle.py`).
  Durable 8-status enum spanning v3.12–v3.17:
  `rejected | exploratory | candidate | paper_ready | paper_validated
  | live_shadow_ready | live_enabled | retired`. Two-layer validation:
  - `FULL_LIFECYCLE_GRAPH` — the complete reference graph for
    downstream phases.
  - `ACTIVE_TRANSITIONS_V3_12` — strict runtime subset
    (`exploratory → candidate | rejected`, `candidate → rejected`).
    Transitions into reserved statuses raise `ReservedStatusError`
    so later-phase slots cannot be entered accidentally.
  - `map_legacy_verdict()` returns `(lifecycle_status, mapping_reason)`,
    preserving `needs_investigation → exploratory` as
    `legacy_needs_investigation_mapped_to_exploratory`.
  - `STATUS_MODEL_VERSION = "v3.12.0"`.
- **Unified rejection taxonomy** (`research/rejection_taxonomy.py`).
  Eight codes from the spec: `insufficient_trades`, `no_oos_samples`,
  `oos_collapse`, `cost_sensitive`,
  `unstable_parameter_neighborhood`, `regime_concentrated`,
  `single_asset_dependency`, `low_statistical_defensibility`.
  Observed vs derived split:
  - `collect_observed_reason_codes()` — raw v3.11 reasoning codes,
    unchanged.
  - `derive_taxonomy()` — only emits codes with defensible
    derivation (direct mapping from promotion codes,
    flag_source from regime/cost sidecars).
  - `DEFERRED_TAXONOMY_CODES`: `unstable_parameter_neighborhood`,
    `single_asset_dependency`, `no_oos_samples` — deliberately not
    derived in v3.12.
  - No per-entry timestamps — per-entry byte-reproducibility.
- **Deterministic candidate scoring** (`research/candidate_scoring.py`).
  Components (each 0..1, `None` when source missing): `dsr_signal`,
  `psr_signal`, `drawdown_signal`, `stability_signal`,
  `trade_density_signal`, `breadth_signal`. Composite is
  equal-weighted mean of available components, emitted with
  `composite_status="provisional"` and `authoritative=False`
  (double signal so no downstream consumer mistakes it for a
  promotion authority). `SCORING_FORMULA_VERSION = "v0.1-experimental"`.
- **Candidate status history** (`research/candidate_status_history.py`).
  Append-only sidecar with deterministic
  `event_id = sha256(candidate_id|from|to|run_id|reason_code)`.
  Merge is idempotent (rerun on identical input yields zero new
  events), stable-sorted per candidate on `(at_utc, event_id)`,
  with sorted top-level candidate_id keys. Writes via atomic
  tempfile+rename through `_sidecar_io`.
- **Candidate registry v2** (`research/candidate_registry_v2.py`).
  Additive first-class view alongside the frozen v1 sidecar.
  Entries carry `candidate_id`, `experiment_family`, `preset_origin`,
  strict separation of `processing_state` (v3.11) and
  `lifecycle_status` (v3.12), `legacy_verdict + mapping_reason`,
  `observed_reason_codes + taxonomy_rejection_codes +
  taxonomy_derivations`, `scores`, `paper_readiness_flags = null`
  with `paper_readiness_assessment_status =
  "reserved_for_future_phase"`, `deployment_eligibility =
  "reserved_for_future_phase"`, full `lineage_metadata`, and
  `source_artifact_references`. Schema pinned at `"2.0"`.
- **Advisory-only agent_definition bridge** (`research/execution_bridge/`).
  Single artifact (`research/agent_definitions_latest.v1.json`).
  Every entry carries `runnable=false` +
  `execution_scope="future_paper_phase_only"`; payload
  `runnable_entries` is pinned to 0 as a structural invariant.
  Scope-locked to `trend_equities_4h_baseline` and
  `regime_filter_equities_4h_experimental` presets with
  `lifecycle_status in {exploratory, candidate}`. AST test asserts
  no imports from `agent.execution`, `execution.paper`, `ccxt`,
  `yfinance`, `polymarket`, or `alchemy`.
- **Single candidate-sidecars façade** (`research/candidate_sidecars.py`).
  `build_and_write_all(ctx)` is the only new call-site in
  `run_research.py`, orchestrating registry-v2 → status-history →
  agent-definitions through the shared
  `_sidecar_io.write_sidecar_atomic` helper.
- **Canonical sidecar IO helper** (`research/_sidecar_io.py`).
  `sort_keys=True, indent=2, LF line endings, trailing newline,
  tempfile+rename`. Used by every v3.12 sidecar writer for uniform
  determinism and atomicity.
- **Report additive enrichment** (`research/report_agent.py`).
  `per_candidate_diagnostics[]` gains optional `lifecycle_status`,
  `legacy_verdict`, `observed_reason_codes`,
  `taxonomy_rejection_codes`, and `scores` fields pulled from the
  v2 sidecar. Top-level `lifecycle_breakdown` counter and optional
  "Candidate Lifecycle Breakdown (v3.12)" markdown section.
  Report `schema_version` unchanged ("1.1") — consumers read with
  `.get()`; no breaking change.
- **Read-only API endpoints** (`dashboard/dashboard.py`).
  `GET /api/registry/v2` and `GET /api/registry/status-history`
  follow the existing `/api/candidates/latest` auth + error pattern.
  Graceful `{ artifact_state: "missing" }` response when sidecars
  are absent.

### Preserved / frozen

- `research/research_latest.json` — 19-column schema, byte-identical.
- `research/strategy_matrix.csv` — column order, byte-identical.
- `research/candidate_registry_latest.v1.json` — structure + summary
  keys byte-identical (regression test
  `tests/regression/test_candidate_registry_v1_immutable.py` pins
  this).
- `research/run_meta_latest.v1.json` — v1.1 unchanged.
- `research/report_latest.{md,json}` — v1.1 schema_version unchanged.
- Frontend components — untouched. React Reports.tsx primitive
  filter already tolerates new nested v3.12 keys.

### Tests added (v3.12)

- `tests/unit/test_sidecar_io.py` — 12 tests, canonical serialization.
- `tests/unit/test_candidate_lifecycle.py` — 21 tests, graph +
  transitions + legacy mapping.
- `tests/unit/test_rejection_taxonomy.py` — 16 tests, observed vs
  derived split, no per-entry timestamps.
- `tests/unit/test_candidate_scoring.py` — 14 tests, deterministic
  unit signals + provisional composite.
- `tests/unit/test_candidate_status_history.py` — 16 tests,
  event_id determinism, idempotent merge, stable sort.
- `tests/unit/test_candidate_registry_v2.py` — 14 tests.
- `tests/unit/test_agent_definition_bridge.py` — 13 tests incl.
  AST-based import isolation.
- `tests/unit/test_candidate_sidecars_facade.py` — 7 tests.
- `tests/unit/test_report_agent_v312_enrichment.py` — 7 tests.
- `tests/unit/test_dashboard_api_v312.py` — 7 tests.
- `tests/integration/test_v312_sidecars_e2e.py` — 5 end-to-end
  scenarios incl. rerun byte-identity.
- `tests/regression/test_candidate_registry_v1_immutable.py` — 6
  tests pinning v1 contract.
- `tests/regression/test_v312_sidecar_schema_stability.py` — 14
  tests pinning key sets and schema_version values for all three
  v3.12 artifacts.

### Explicitly out of scope (deferred)

- Execution preview with replay / fees / slippage / synthetic PnL
  → **v3.15 Paper Validation Engine**.
- Runnable paper path → **v3.15**.
- Regime classifier and gating → **v3.13 Regime Intelligence**.
- Portfolio / sleeves → **v3.14**.
- Kill switches, shadow mode, monitoring → **v3.16**.
- Controlled live enablement → **v3.17**.
- ML or optimizer-heavy scoring — permanently out of roadmap scope.
- Frontend component changes — deferred; additive report schema
  is enough for v3.12.
- `unstable_parameter_neighborhood` and `single_asset_dependency`
  taxonomy derivation — both remain `DEFERRED_TAXONOMY_CODES` in
  v3.12, scheduled for v3.13+ when breadth and neighborhood context
  become first-class.

## [v3.11] — Research Quality Engine

Date: 2026-04-22
Branch: `feature/v3.11-research-quality-engine`

Quality-hardening release. Zero new infra, zero new strategy
families, zero new metrics. Every change is additive and consumer-only
against the existing v3.10 artifact landscape. Public output contracts
(`research_latest.json`, `strategy_matrix.csv`) remain **byte-identical
to v3.10**; new data lands exclusively in schema-bumped adjacent
sidecars (`run_meta_latest.v1.json` v1.1, `report_latest.{md,json}`
v1.1) and a new consumer-only join module.

The bottleneck after v3.10 was input + interpretation quality, not
throughput. v3.11 formalises hypothesis metadata per preset, separates
screening (mild, observability) from promotion (strict, DSR/PSR/
stability) in report output, and wires per-candidate diagnostics that
explain **why** each row survived, stalled, or failed — without the
engine growing a single new threshold or metric.

### Added

- **Preset Quality Layer.** `ResearchPreset` dataclass extended with
  four fields:
  - `preset_class: Literal["baseline", "diagnostic", "experimental"]`
    — orthogonal to the existing `status` lifecycle label.
  - `rationale`, `expected_behavior`, `falsification` — structured
    hypothesis metadata. All three enabled presets
    (`trend_equities_4h_baseline`, `trend_regime_filtered_equities_4h`,
    `crypto_diagnostic_1h`) ship with the fields filled. Planned
    `pairs_equities_daily_baseline` stays empty (backlog_reason still
    load-bearing).
  - `hypothesis_metadata_issues()` helper returns only the v3.11
    soft-issue codes so the runner can emit dedicated warnings.
- **Soft preset validation + opt-in strict mode.** `validate_preset`
  returns soft issues on empty rationale / expected_behavior /
  falsification for enabled presets. The runner emits
  `preset_validation_warning` tracker events. Setting
  `QRE_STRICT_PRESET_VALIDATION=1` elevates to hard failure via a
  new `PresetValidationError`. Default is soft — v3.11 never
  self-blocks.
- **run_meta schema v1.1** (additive). New fields on
  `research/run_meta_latest.v1.json`: `preset_class`,
  `preset_rationale`, `preset_expected_behavior`, `preset_falsification`,
  `preset_bundle_hypotheses` (resolved read-only from `STRATEGIES`).
  `is_run_excluded_from_promotion` and all v1.0 keys are unchanged.
  v1.0-shaped sidecars remain readable bytewise.
- **`research/report_candidate_diagnostics.py`** (new module). Pure
  join functions — no IO, no new metrics, no threshold derivation.
  Returns `(per_candidate_diagnostics, join_stats)`.
  - Verdict enum pinned at four values:
    `promoted | needs_investigation | rejected_promotion | rejected_screening`.
  - Rejection_layer enum: `fit_prior | eligibility | screening |
    promotion | null`.
  - Stability flags (`noise_warning`, `psr_below_threshold`,
    `dsr_canonical_below_threshold`, `bootstrap_sharpe_ci_includes_zero`)
    sourced read-only from
    `candidate_registry.candidates[].reasoning.failed/.escalated/.passed`.
  - `cost_sensitivity_flag` and `regime_suspicion_flag` consume
    pre-computed booleans only; null when the source sidecar is
    absent or exposes only numeric fields.
  - Join discipline: primary key `build_strategy_id(name, asset,
    interval, params)`; defensibility triple `(name, asset, interval)`;
    unmatched counts surface in `join_stats`.
  - Soft warning sentinel `join_stats.warning = "large_candidate_count"`
    at > 1000 rows; no hard cap.
- **Report agent v1.1.** `research/report_agent.py`:
  - `REPORT_SCHEMA_VERSION = "1.1"`.
  - `summary` carries additive `screening` and `promotion` sub-dicts
    (legacy v3.10 keys preserved for dashboard consumers).
  - `top_rejection_reasons_by_layer` splits screening-layer codes
    (from `run_filter_summary_latest.v1.json`) and promotion-layer
    codes (from `candidate_registry_latest.v1.json`). Flat
    `top_rejection_reasons` list remains for legacy consumers.
  - `per_candidate_diagnostics` and `join_stats` payload keys.
  - Markdown sections: **Hypothese**, **Samenvatting** (with
    Screening-laag + Promotion-laag + Join stats sub-blocks), **Wat
    werkte**, **Wat werkte niet** (split), **Waarom (per candidate)**,
    **Volgende stap**.
  - `suggest_next_experiment` extended with layer-aware + failure-type
    logic (statistical / risk / trades / noise) driven by existing
    promotion-reason codes only. Signature adds keyword-only
    `rejection_reasons_by_layer` (backwards compatible).
- **Test coverage.** 43 new unit tests pinning the v3.11 contract:
  - `tests/unit/test_presets.py` +9 tests.
  - `tests/unit/test_run_meta.py` +6 tests.
  - `tests/unit/test_report_agent.py` +8 tests.
  - `tests/unit/test_report_candidate_diagnostics.py` (new) 20 tests
    covering verdict mapping, stability flag sourcing, cost/regime
    flag null-safety, join mismatches, malformed rows, soft warning.

### Changed

- `render_markdown` section titles updated from v3.10 English labels
  to v3.11 Dutch narrative labels (Samenvatting / Wat werkte / Wat
  werkte niet / Waarom / Volgende stap). Corresponding test assertions
  updated in the same commit as the rename.
- `build_run_meta_payload` now resolves `preset_bundle_hypotheses`
  via a read-only local import of `STRATEGIES`; avoids a module-level
  circular import with the registry.

### Preserved bytewise

- `ROW_SCHEMA` (19 columns) and `JSON_TOP_LEVEL_SCHEMA`.
- `candidate_registry_latest.v1.json` schema + writer.
- All other sidecar schemas and writers (statistical defensibility,
  regime diagnostics, falsification gates, integrity report,
  portfolio aggregation, empty run diagnostics).
- Tier 1 digest pins, walk-forward `FoldLeakageError` semantics,
  resume-integrity gate.
- `run_meta` v1.0-shaped sidecars still parse via
  `read_run_meta_sidecar`.

### Deferred (explicit)

- Portfolio layer (v3.12).
- Candidate registry schema extensions (v3.12).
- Regime classification engine (v3.13).
- Paper trading, new strategy families, ML/ranking, UI expansion
  beyond the preset-card additive fields.
- Hard-fail default for preset validation (remains opt-in via env
  flag in v3.11).

### Known risks

- Dashboard report-viewer must tolerate the new v1.1 schema fields;
  they are additive and null-safe but any tight JSON-Schema consumer
  will need an update.
- `cost_sensitivity_flag` and `regime_suspicion_flag` stay `null` in
  the current pipeline because no upstream sidecar writer emits a
  pre-computed boolean. They go live the moment the writers choose
  to expose one — no v3.11 code change needed.
- Falsification criteria quality is subjective on the initial fill
  of the 3 enabled presets. Iteration happens via runs + feedback
  loop, not via engine changes.
- Per-candidate diagnostics can grow with universe size; the soft
  warning at >1000 rows is a visibility aid, not a guard. Retention
  discipline arrives with v3.12's candidate registry.

## [v3.10] — Research Ops & Frontend Migration

Date: 2026-04-22
Branch: `feature/v3.10-research-ops-react`

Operations release. Preset catalog, single-command `researchctl`
CLI, post-run analysis/report agent, Flask control-surface API
extension, React + TypeScript SPA on `:8050`, nginx anti-indexing
reverse proxy, host-level systemd-timer for the daily default run,
and explicit `scripts/deploy.sh` deploy channel from GHCR to the
VPS. No strategy-logic changes. Public output contracts
(`research_latest.json`, `strategy_matrix.csv`) are byte-identical
to pre-v3.10; new fields land in adjacent artifacts
(`research/run_meta_latest.v1.json`, `research/report_latest.md`,
`research/report_latest.json`). See
[ADR-011](docs/adr/ADR-011-v3.10-architecture.md) for the full
design record and
[ADR-012](docs/adr/ADR-012-v3.10-approval-override-audit.md) for
the engine approval-override audit outcome.

### Added

- `research/presets.py`: frozen `ResearchPreset` dataclass + four
  registered presets (`trend_equities_4h_baseline` default,
  `pairs_equities_daily_baseline` planned/disabled,
  `trend_regime_filtered_equities_4h`, `crypto_diagnostic_1h` with
  diagnostic/exclusion flags). Public API: `list_presets`,
  `get_preset`, `resolve_preset_bundle`, `validate_preset`,
  `default_daily_preset`, `daily_schedulable_presets`, `preset_to_card`.
- `research/run_meta.py`: new adjacent sidecar
  `research/run_meta_latest.v1.json` (schema v1.0) carrying preset
  metadata, candidate summary, top rejection reasons, and artifact
  paths. Safe-default promotion-exclusion when the sidecar is missing
  or diagnostic (ADR-011 §9).
- `research/report_agent.py`: post-run analysis that composes
  `research/report_latest.md` + `research/report_latest.json` from
  the existing reporting modules. Verdicts:
  `promoted | candidates_no_promotion | niets_bruikbaars_vandaag`.
- `research/run_research.py --preset <name>`: threads a preset through
  candidate planning, writes the run_meta sidecar, and invokes the
  report agent at the end of each run (best-effort, never fails the run).
- `researchctl.py` CLI at the repo root with subcommands
  `run / report / history / doctor` (no `deploy` — ADR-011 §4).
- Dashboard endpoints: `/api/presets`, `/api/presets/<name>/run`,
  `/api/report/latest`, `/api/report/history`, `/api/candidates/latest`,
  `/api/health`, `/api/session/login`, `/api/session/logout`.
- React + TypeScript SPA under `frontend/` with Login, Dashboard,
  Presets, History, Reports, Candidate Inspector screens. Multi-stage
  Dockerfile builds the bundle on `node:20-alpine` and ships it in the
  Python runtime image.
- `ops/nginx/nginx.conf` + `robots.txt`: reverse proxy with
  `X-Robots-Tag: noindex, nofollow, noarchive, nosnippet`, AI/crawler
  UA block (20+ agents → 403), cookie/auth pass-through to Flask.
- `ops/systemd/trading-agent-daily-research.{service,timer}` + README:
  host-level systemd-timer that calls
  `docker exec jvr_dashboard python /app/researchctl.py run
  trend_equities_4h_baseline` at 06:00 UTC daily. Crypto diagnostic
  preset is never auto-scheduled.
- `scripts/deploy.sh`: explicit GHCR pull + compose up + health-check
  deploy with retry, rollback via `IMAGE_TAG=<prev-tag>`.
- `docker-compose.prod.yml`: GHCR-image override for VPS deploys.
- `docs/adr/ADR-011-v3.10-architecture.md`: architecture record for the
  whole v3.10 shape.
- `docs/adr/ADR-012-v3.10-approval-override-audit.md`: audit of
  engine.py / promotion.py / run_research.py for gate-bypass logic —
  outcome A, no production bypass exists.
- Regression / smoke coverage: `test_make_result_row_strategy_name.py`,
  `test_execution_event_roundtrip.py`,
  `test_screening_interrupt_reason_detail.py`,
  `test_daily_preset_smoke.py`, `test_presets.py`,
  `test_run_meta.py`, `test_report_agent.py`,
  `test_dashboard_api_v310.py`.

### Changed

- `VERSION`: `0.1.0` → `3.10.0`.
- `Dockerfile` is now multi-stage (node builder → python runtime copies
  `frontend/dist`).
- `docker-compose.yml`: dashboard no longer binds the host port; nginx
  binds `8050:80` and proxies to `dashboard:8050` internally. New
  `./state:/app/state` bind-mount preserves session/operator secrets
  across deploys.
- `dashboard/dashboard.py`: SPA index served at `/`; legacy Jinja
  dashboards kept reachable at `/legacy/dashboard` and
  `/legacy/research-control` for one release.
- `dashboard/research_runner.launch_research_run` accepts an optional
  `preset` kwarg and threads `--preset <name>` into the subprocess
  command.

### Fixed

- `research/results.py::make_result_row` now raises `ValueError` when
  `strategy["name"]` is None or empty, closing the strategy-None leak
  in `strategy_matrix.csv` / `research_latest.json`. The frozen
  ROW_SCHEMA tuple is untouched — only a precondition was added.
- `researchctl doctor` detects stale `strategy_matrix.csv` headers
  (the v3.x legacy `strategy_family,asset_type,…` header class) and
  fails the check instead of letting it slide.

### Security

- Anti-indexing enforced at three layers: nginx `X-Robots-Tag`
  response header + AI-crawler UA 403 block, Flask `X-Robots-Tag`
  injection on the SPA index, and React `<meta name="robots">` tag.
  `/robots.txt` served by both nginx and Flask.
- New `/api/session/login` validates via the existing SHA256+SALT hash
  and `hmac.compare_digest`; no new credential store. Session cookie
  `SameSite=Lax` (no TLS in v3.10, `Secure` flag deferred to v3.11).

### Contracts

- No mutations to `ROW_SCHEMA`, `JSON_TOP_LEVEL_SCHEMA`, or
  `JSON_SUMMARY_SCHEMA` in `research/results.py`. All new v3.10
  fields are recorded in adjacent sidecar artifacts
  (`research/run_meta_latest.v1.json`, `research/report_latest.md`,
  `research/report_latest.json`).
- Existing `/api/research/run-status` remains the canonical run-status
  endpoint (ADR-011 §12). No `/api/run-status` introduced.

## [v3.8] — Execution Realism & Evaluation Hardening

Date: 2026-04-21
Branch: `feature/v3.7-fitted-feature-abstraction`

Evaluation-hardening phase. Additive abstractions and opt-in
evaluation hooks only. No change to strategy logic, feature logic,
fitted-feature semantics, baseline equity / trade booking, public
JSON / CSV schemas, `candidate_id` hashing, or Tier 1 bytewise
pins. See
[ADR-008](docs/adr/ADR-008-execution-realism-and-evaluation-hardening.md)
for the full design record, rejected alternatives, pinned
semantics, and deferred items.

### Added

- `agent/backtesting/execution.py` (v3.8 step 1). Canonical
  execution event scaffold. `EXECUTION_EVENT_VERSION = "1.0"`,
  frozen `ExecutionEvent` with five pinned kinds (`accepted`,
  `partial_fill`, `full_fill`, `rejected`, `canceled`), typed
  `ALLOWED_REASON_CODES`, factory builders (`.accepted`,
  `.full_fill`, `.partial_fill`, `.rejected`, `.canceled`),
  pandas / numpy sentinel rejection, dict round-trip helpers
  (`execution_event_to_dict`, `execution_event_from_dict`),
  structural `fingerprint` placeholder (unset in v1.0).
  Deliberately disjoint from `execution/protocols.py::Fill`
  (live / paper-broker success record).
- `agent/backtesting/engine.py::_simuleer_detailed` (v3.8 step 2).
  Deterministic emission of `ExecutionEvent.accepted` +
  `ExecutionEvent.full_fill` pairs at each booked entry and exit.
  Monotone `sequence` within `(run_id, asset, fold_index)`; every
  event carries `fold_index`. Gated behind
  `include_execution_events` keyword flag; enabled only on OOS
  folds. Events land in
  `_last_window_streams["oos_execution_events"]` and surface on
  the research result dict as `evaluation_streams`. Baseline
  equity math, fee application, and trade PnL bytewise unchanged.
- `agent/backtesting/cost_sensitivity.py` (v3.8 step 3).
  `COST_SENSITIVITY_VERSION = "1.0"`, frozen `ScenarioSpec`,
  `DEFAULT_SCENARIOS`, `run_cost_sensitivity`,
  `derive_fill_positions`, `build_cost_sensitivity_report`. Pure
  evaluation-layer replay applying per-fill multiplicative
  adjustment `(1 - m*k) * (1 - s_bps/1e4) / (1 - k)`. Baseline
  scenario reproduces the engine's `dag_returns` bytewise;
  alternative scenarios apply stress without mutating the
  baseline. Opt-in hook `BacktestEngine.build_cost_sensitivity`
  (not called from `run()`).
- `agent/backtesting/exit_diagnostics.py` (v3.8 step 4).
  `EXIT_DIAGNOSTICS_VERSION = "1.0"`, frozen `TradeDiagnostic`,
  `compute_trade_diagnostic`, `extract_interior_bar_returns`,
  `build_exit_diagnostics_report`. Pure evaluation-layer path
  analysis consuming `oos_trade_events` + `oos_bar_returns` +
  `kosten_per_kant`. Pinned per-trade definitions: MFE, MAE,
  realized return, capture ratio (with `None` on zero MFE),
  winner giveback (with `None` on losers), exit lag, holding
  bars. Pinned aggregate: turnover-adjusted exit quality
  (`avg_capture * (1 - density)`, zero on zero-trade). Exit-bar
  pollution by `(1 - k)` fee factor is handled by anchoring the
  exit path point at `pnl + k`. Opt-in hook
  `BacktestEngine.build_exit_diagnostics` (not called from
  `run()`).
- `tests/unit/test_execution_event_scaffold.py` (v3.8 step 1,
  ~23 tests).
- `tests/unit/test_execution_event_emission.py` (v3.8 step 2).
- `tests/unit/test_cost_sensitivity.py` (v3.8 step 3, 30 tests).
- `tests/unit/test_exit_diagnostics.py` (v3.8 step 4, 26 tests).
- `docs/adr/ADR-008-execution-realism-and-evaluation-hardening.md`
  (v3.8 step 5).
- `docs/orchestrator_brief.md` §Addendum: v3.8 scope, layer
  placement, execution-event / cost-sensitivity / exit-quality
  semantics, deferred items, preserved bytewise invariants, phase
  character.

### Unchanged — explicitly pinned

- `research_latest.json` row schema and top-level schema
  (bytewise).
- 19-column CSV row schema (bytewise).
- Integrity (`integrity_report_latest.v1.json`) and falsification
  (`falsification_gates_latest.v1.json`) sidecar schemas.
- Integrity D4 boundary.
- Tier 1 bytewise digests (`sma_crossover`,
  `zscore_mean_reversion`, `pairs_zscore`).
- Walk-forward `FoldLeakageError` semantics.
- Resume-integrity gate.
- `candidate_id` hashing inputs (`research/candidate_pipeline.py
  ::_hash_payload`). Execution shape is explicitly out of the
  hash.
- `FEATURE_REGISTRY`, `FEATURE_VERSION = "1.0"`,
  `build_features_for`, `build_features_for_multi`.
- `FITTED_FEATURE_REGISTRY`, `FITTED_FEATURE_VERSION = "1.0"`,
  fold-aware builders.
- Strategy logic (`strategies.py`, `thin_strategy.py`).
- Baseline equity math, fee application, trade PnL formula in
  `_simuleer_detailed`.
- Live / paper broker path (`execution/protocols.py`,
  `execution/paper/polymarket_sim.py`).

### Deferred

- Paper validation as a formal gate.
- Live / paper divergence reporting between live `Fill` outcomes
  and backtest `ExecutionEvent` projections.
- Full execution shortfall framework (quote midpoint, bid/ask,
  impact curves). Current backtest slippage is `0.0 bps`
  (next-bar close).
- Richer rejection / partial-fill semantics in the engine. The
  scaffold exists; current emission is entry + exit fills only.
- Broader promotion framework integration of cost-sensitivity and
  exit-quality reports. Both remain opt-in side-channels and are
  not gates in v3.8.
- Regime / portfolio research.
- Broader orchestration / platform automation.
- Thin contract v2.0 unification. See
  [ADR-006](docs/adr/ADR-006-v2-contract-deferred.md). v3.8 does
  not introduce new ADR-006 triggers and does not resolve any of
  its conditions.
- Broader strategy migration to the fitted path (ADR-007). v3.8
  neither widens nor narrows the v3.7 opt-in surface.
- `ExecutionEvent.fingerprint` computation. v1.0 reserves the
  field as a structural placeholder.
- Config-level surfacing of `build_cost_sensitivity` and
  `build_exit_diagnostics` on the research pipeline. Both remain
  callable on `BacktestEngine` instances only.

### Phase character

v3.8 is an evaluation-hardening phase, not a strategy-expansion
phase. Every change is additive, deterministic, non-mutating with
respect to baseline results, and gated behind opt-in hooks or
flags that default off. Tier 1 digests, public artifacts, and
promotion inputs are pinned at their v3.7 values.

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
