# Changelog

All notable changes to the trading-agent research and backtesting
stack are documented here. Live trading / orchestration surfaces
outside the research path are not tracked in this file.

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
