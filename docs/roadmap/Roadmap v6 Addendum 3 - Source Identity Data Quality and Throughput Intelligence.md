# Roadmap v6 Addendum 3
## Source Identity, Data Quality & Throughput Intelligence

## Execution Status (as of 2026-05-21)

Status: **DEFERRED — REFERENCE-ONLY**

Implementation-scope sections: **NOT ACTIVE**

Doctrine and §10 "Not Allowed" sections: **ACTIVE PROJECT-WIDE**

This addendum is preserved verbatim as architectural reference. It is
not active execution scope. No queue item, planner task, product-owner
backlog entry, or autonomous PR runner unit may be derived from this
addendum unless an explicit operator-approved ADR reactivates the
specific subsection. See
[`docs/governance/roadmap_scope_status.md`](../governance/roadmap_scope_status.md)
and
[`docs/adr/_drafts/ADR-018-roadmap-execution-reset.md`](../adr/_drafts/ADR-018-roadmap-execution-reset.md)
for the reset record and reactivation gates.

Doctrine that remains binding regardless of execution status:

- Source adapters do not trade.
- Source identity is infrastructure, not alpha.
- Source quality gates are mandatory.
- Throughput infrastructure is not permission to lower standards.
- External data is not alpha.
- The §10 "Not Allowed" list remains project-wide invariant.

---

## 1. Purpose

This addendum extends:

```text
Roadmap v6 Addendum — Mechanistic Behavior Diagnostics & External Intelligence Intake
Roadmap v6 Addendum 2 — State, Sequential, Knowledge & Retrieval Intelligence
```

It is a direct follow-up addendum, not a replacement.

The first addendum introduced:

```text
External Intelligence Intake
Mechanistic Behavior Diagnostics Layer
Behavior Diagnostics Library / Research Diagnostics Primitives
physics-informed diagnostics
complex-systems diagnostics
public-data hypothesis seeds
```

The second addendum introduced:

```text
Research Knowledge & Retrieval Layer
State & Sequential Diagnostics Layer
state-transition diagnostics
research memory
ontology
entity resolution
knowledge graph lineage
retrieval-supported duplicate suppression
queueing diagnostics
```

This third addendum adds a complementary capability family:

```text
Source Identity, Data Quality & Throughput Intelligence
```

The purpose is to make the QRE better at:

```text
identifying instruments correctly
normalizing asset and source identities
ranking external sources by research usefulness
separating source candidates from active sources
caching data reproducibly
scaling research throughput without weakening quality
tracking source usefulness over time
preventing vendor/API sprawl
preventing low-quality data from becoming hypothesis input
using throughput infrastructure without turning it into trading authority
```

This addendum keeps the same core philosophy:

```text
External data is not alpha.
Source adapters do not trade.
Caches do not certify truth.
Throughput does not justify lower evidence standards.
Vendor APIs do not bypass QRE validation.
```

The QRE should not become:

```text
vendor-data aggregation project
Bloomberg-terminal clone
API-spaghetti research engine
paid-feed dependency trap
real-time data hoarder
source-count maximizer
throughput-over-quality optimizer
LLM-driven source selector
cache-backed trading system
```

The QRE should become:

```text
deterministic market-behavior research system
with canonical source identity, quality-gated external intelligence,
reproducible local data caches and scalable research throughput
```

---

## 2. Relationship to Addendum 1 and Addendum 2

Addendum 1 introduced the extended research-intelligence architecture:

```text
External Intelligence Intake
↓
Mechanistic Behavior Diagnostics Layer
↓
Market Behavior Layer
↓
Hypothesis Discovery Layer
↓
Strategy Mapping
↓
Preset Layer
↓
Campaign Layer
↓
Funnel Layer
↓
Evidence Layer
↓
Policy Layer
↓
Shadow / Paper / Live
```

Addendum 2 inserted research memory and state/sequential intelligence:

```text
External Intelligence Intake
↓
Research Knowledge & Retrieval Layer
↓
State & Sequential Diagnostics Layer
↓
Mechanistic Behavior Diagnostics Layer
↓
Market Behavior Layer
↓
Hypothesis Discovery Layer
↓
Strategy Mapping
↓
Preset Layer
↓
Campaign Layer
↓
Funnel Layer
↓
Evidence Layer
↓
Policy Layer
↓
Shadow / Paper / Live
```

Addendum 3 refines the entry point into that architecture by splitting External Intelligence Intake into governed sublayers:

```text
Source Candidate Registry
↓
Source Identity & Symbology Layer
↓
Source Manifest & Quality Gate Layer
↓
Local Data Cache & Throughput Layer
↓
External Intelligence Intake
↓
Research Knowledge & Retrieval Layer
↓
State & Sequential Diagnostics Layer
↓
Mechanistic Behavior Diagnostics Layer
↓
Market Behavior Layer
↓
Hypothesis Discovery Layer
↓
Strategy Mapping
↓
Preset Layer
↓
Campaign Layer
↓
Funnel Layer
↓
Evidence Layer
↓
Policy Layer
↓
Shadow / Paper / Live
```

Interpretation:

```text
Source Candidate Registry
= inventory of possible future sources, with allowed use, activation phase and quality gates

Source Identity & Symbology Layer
= canonical instrument identity, alias resolution, ticker/exchange mapping and asset metadata

Source Manifest & Quality Gate Layer
= source metadata, freshness, coverage, license terms, missing data and source-agreement checks

Local Data Cache & Throughput Layer
= reproducible Parquet/DuckDB/Polars-style research cache and batch processing discipline

External Intelligence Intake
= only quality-gated, manifest-backed external data that can become unvalidated research context
```

---

## 3. Core Rules

Add these rules to Addendum 1 and Addendum 2 principles.

```text
Source adapters do not trade.
```

A source adapter may:

```text
fetch public/free or approved source data
write source snapshots to sidecar artifacts
write source quality reports
support source agreement checks
support hypothesis seed context
support routing, sampling and observability context
support cross-source validation
```

A source adapter may not:

```text
place trades
generate executable strategies
authorize paper/shadow/live deployment
allocate capital
mutate live risk
promote candidates
bypass evidence policy
bypass source quality gates
change frozen output contracts
```

```text
Source identity is infrastructure, not alpha.
```

Source identity may:

```text
canonicalize tickers
map exchange symbols
resolve aliases
identify share classes, ADRs, ETFs, crypto pairs and delisted/renamed assets
prevent duplicate research artifacts
block ambiguous research inputs
```

Source identity may not:

```text
rank trades
certify signal quality
replace research validation
replace evidence scoring
authorize candidate promotion
```

```text
Source quality gates are mandatory.
```

A source may not feed hypothesis discovery, routing or diagnostics until it has:

```text
source manifest
license/terms metadata
freshness checks
coverage checks
missing-data checks
timestamp monotonicity checks
duplicate-bar checks
outlier checks
source-agreement checks where possible
known limitations
allowed-use and forbidden-use fields
```

```text
Throughput infrastructure is not permission to lower standards.
```

Throughput systems may:

```text
cache data
speed up backtests
parallelize diagnostics
compact artifacts
reduce redundant API calls
improve campaign queue efficiency
```

Throughput systems may not:

```text
skip OOS validation
skip null-model tests
skip frozen-contract checks
skip artifact validity checks
turn failed hypotheses into survivors
prioritize compute only by speed
bypass policy because data is available
```

---

## 4. New Roadmap Components

Add under the Addendum 2 architecture:

```text
Source Candidate Registry
Source Identity & Symbology Layer
Source Manifest & Quality Gate Layer
Local Data Cache & Throughput Layer
Source Usefulness Ledger
```

### 4.1 Source Candidate Registry

Purpose:

```text
Maintain a controlled inventory of possible future data sources without activating them prematurely.
```

This layer records:

```text
source_id
source_name
source_category
source_status
activation_phase
value_type
allowed_use
forbidden_use
coverage_scope
expected_latency
expected_freshness
license_or_terms_reference
quality_gates_required
implementation_priority
risk_level
```

Source statuses:

```text
candidate
quarantined
manual_research_only
staging
quality_gated
active_read_only
deprecated
blocked
```

Rule:

```text
A source in candidate, quarantined or manual_research_only status may not feed automated QRE hypothesis discovery.
```

---

### 4.2 Source Identity & Symbology Layer

Purpose:

```text
Ensure the QRE knows exactly which instrument, market, exchange, company, crypto pair, ETF or index it is researching.
```

This layer stores:

```text
canonical_instrument_id
ticker
exchange
asset_class
currency
quote_currency
base_currency
figi_or_external_identifier where available
company_id or issuer_id where available
crypto_network or exchange_pair_id where applicable
instrument_aliases
source_symbol_map
identity_confidence
ambiguous_mapping_warning
```

Primary future source candidate:

```text
OpenFIGI
```

Allowed use:

```text
instrument identity
symbol mapping
universe validation
asset metadata normalization
cross-source mapping checks
```

Forbidden use:

```text
trade signal
candidate promotion
live eligibility
capital allocation
```

Rule:

```text
Ambiguous instrument identity blocks hypothesis escalation until resolved.
```

---

### 4.3 Source Manifest & Quality Gate Layer

Purpose:

```text
Prevent external data from becoming research context unless it is inspectable, licensed, fresh enough and internally coherent.
```

Every source manifest must include:

```text
source_id
source_type
access_method
authentication_required
cost_model
expected_latency
expected_freshness
asset_coverage
timeframe_coverage
history_depth
allowed_use
forbidden_use
known_limitations
license_terms_reference
reproducibility_method
quality_gates
source_owner
last_reviewed_at
```

Core quality gates:

```text
freshness_check
missing_data_check
timestamp_monotonicity_check
duplicate_observation_check
outlier_check
coverage_check
source_agreement_check
identity_mapping_check
license_terms_present_check
schema_version_check
```

Optional later quality gates:

```text
point_in_time_revision_check
corporate_action_adjustment_check
survivorship_bias_check
lookahead_bias_check
split_dividend_adjustment_check
exchange_session_calendar_check
```

Rule:

```text
No source-derived hypothesis seed may escalate without passing the required source gates for its source category.
```

---

### 4.4 Local Data Cache & Throughput Layer

Purpose:

```text
Increase research throughput by storing quality-gated data locally in reproducible, queryable, versioned formats.
```

Preferred local-storage pattern:

```text
Parquet snapshots
DuckDB metadata/query catalog
Polars or equivalent vectorized processing for heavy diagnostics
content-addressed or versioned artifact manifests
cache validity reports
```

This layer supports:

```text
batch research
cross-asset scans
source agreement checks
repeatable diagnostics
faster campaign routing
faster sampling plans
local null-model generation
artifact compaction
```

This layer does not support:

```text
live order placement
real-time broker routing
unvalidated low-latency trading
automatic capital allocation
```

Rule:

```text
Cached data is only as trusted as its manifest, identity mapping and quality gates.
```

---

### 4.5 Source Usefulness Ledger

Purpose:

```text
Track which sources actually improved QRE research quality or throughput over time.
```

This ledger records:

```text
source_id
hypothesis_seeds_generated
hypothesis_seeds_suppressed
campaigns_influenced
survivors_influenced
false_positives_influenced
null_model_failures
quality_gate_failures
freshness_failures
coverage_failures
source_disagreements
compute_cost_saved
api_calls_avoided
cache_hit_rate
operator_visible_value
```

Downstream use:

```text
promote useful sources from staging to active_read_only
deprecate noisy or unreliable sources
prioritize source adapter work
reduce external API dependency
improve routing and sampling quality
```

Rule:

```text
A source that repeatedly produces false positives or quality failures should be cooled down, deprecated or blocked.
```

---

## 5. Proposed Repo Structure

Planned architecture only; implementation should happen in scoped roadmap phases.

```text
research/
  external_intelligence/
    source_candidates.py              # read-only registry of candidate sources
    source_manifest_schema.py         # shared manifest schema
    source_quality_gates.py           # deterministic source quality checks
    source_status.py                  # candidate/staging/active/deprecated statuses
    source_usefulness.py              # source usefulness ledger helpers

    adapters/
      __init__.py
      openfigi_adapter.py             # instrument identity and symbology, later
      fred_alfred_adapter.py          # macro and revision-aware macro, later
      cftc_cot_adapter.py             # positioning/crowding context, later
      eia_adapter.py                  # energy/commodity/macro regime context, later
      openbb_staging_adapter.py       # staging connector only, later
      financialdatasets_mcp_adapter.py# manual/quarantined research context, later
      binance_bulk_adapter.py         # reproducible crypto bulk data, later
      coingecko_context_adapter.py    # crypto metadata/dominance/category context, later
      events_calendar_adapter.py      # earnings/dividends/splits/macro calendars, later
      etf_index_constituents_adapter.py # network/portfolio context, later

  identity/
    instrument_identity.py            # canonical instrument IDs
    symbology.py                      # ticker/exchange/source symbol mapping
    asset_metadata.py                 # asset class, currency, venue, issuer metadata
    identity_quality.py               # ambiguity and mapping confidence checks

  cache/
    cache_manifest.py                 # local cache manifest schema
    parquet_writer.py                 # optional later
    duckdb_catalog.py                 # optional later
    cache_quality.py                  # cache integrity checks
    cache_compaction.py               # optional later

  throughput/
    research_throughput.py            # batch throughput metrics
    compute_cost_ledger.py            # compute/API/cache cost tracking
    batch_planner.py                  # deterministic batch planning, later
    orchestration_manifest.py         # optional Dagster/Prefect-style manifest, later

artifacts/
  external_intelligence/
    source_candidates_latest.v1.json
    source_manifests_latest.v1.json
    source_quality_latest.v1.json
    source_usefulness_latest.v1.json

  identity/
    instrument_identity_latest.v1.json
    symbology_map_latest.v1.json
    identity_quality_latest.v1.json

  cache/
    cache_manifest_latest.v1.json
    cache_quality_latest.v1.json
    cache_coverage_latest.v1.json

  throughput/
    research_throughput_latest.v1.json
    compute_cost_ledger_latest.v1.json
    batch_plan_latest.v1.json
```

Do not mutate:

```text
research_latest.json
strategy_matrix.csv
```

New source, identity, cache and throughput information must live in sidecar artifacts.

---

# 6. Source Candidate Mapping

## 6.1 Summary Table

| Source / Tool | Verdict | Roadmap Fit | Allowed Form |
|---|---:|---:|---|
| OpenFIGI | Very strong | Add early | instrument identity / symbology |
| FRED / ALFRED | Strong | Add | macro regime and revision-aware macro |
| CFTC COT | Strong | Add later | positioning / crowding context |
| EIA | Strong | Add later | energy / commodity / inflation regime context |
| OpenBB ODP | Useful | Staging only | connector discovery / prototyping |
| Financial Datasets MCP | Useful but controlled | Manual/staging only | Claude Code research sandbox / source candidate |
| Binance public bulk data | Very strong for crypto | Add | reproducible crypto OHLCV cache |
| CoinGecko context data | Strong | Add | crypto metadata, dominance, category context |
| Earnings / events calendars | Strong | Add later | event-aware research context |
| ETF / index constituents | Strong | Add later | network / portfolio / sector context |
| Options / OPRA / Cboe-style data | Strong later | Reserve | volatility/event risk context only |
| Social / X / Reddit scraping | Not now | Exclude | possible future research only after gates |
| Paid vendor alpha feeds | Not now | Exclude | blocked until explicit approval |

---

## 6.2 OpenFIGI / Instrument Identity

Layer:

```text
Source Identity & Symbology Layer
Research Knowledge & Retrieval Layer
External Intelligence Intake
Universe Management
```

Applied to:

```text
ticker mapping
exchange symbol normalization
share class distinction
ETF and issuer identification
ADR/common stock distinction
source symbol reconciliation
asset universe validation
```

Outputs:

```text
canonical_instrument_id
external_identifier
source_symbol_map
identity_confidence
ambiguous_mapping_warning
alias_resolution_table
```

Downstream use:

```text
prevent duplicate assets
avoid ticker collision
connect external data to internal artifacts
improve source agreement checks
block ambiguous hypothesis escalation
```

Rule:

```text
Instrument identity improves correctness.
It does not imply edge.
```

Priority:

```text
High, before broad equity universe expansion.
```

---

## 6.3 FRED / ALFRED Revision-Aware Macro

Layer:

```text
External Intelligence Intake
Source Manifest & Quality Gate Layer
Regime Intelligence
State & Sequential Diagnostics
Research Observability
```

Applied to:

```text
rates regime
inflation regime
liquidity regime
macro stress context
revision-aware macro history
point-in-time macro context
```

Outputs:

```text
macro_regime_context
macro_series_snapshot
revision_awareness_flag
point_in_time_available
macro_freshness_status
macro_source_quality
```

Downstream use:

```text
support regime segmentation
avoid lookahead from revised macro data
explain macro context during campaign results
condition hypothesis discovery on broad regime context
```

Rule:

```text
Latest macro data is not necessarily point-in-time research data.
Revision awareness is required before macro context influences historical research conclusions.
```

Priority:

```text
Medium-high, after initial routing/sampling scaffolds are stable.
```

---

## 6.4 CFTC COT / Positioning Context

Layer:

```text
External Intelligence Intake
Adversarial Market Behavior Diagnostics
Regime Intelligence
Portfolio Intelligence
```

Applied to:

```text
futures positioning
crowding context
risk-on/risk-off structure
commodity/FX/equity index proxy context
sentiment-like positioning extremes
```

Outputs:

```text
positioning_crowding_score
commercial_noncommercial_imbalance
positioning_extreme_flag
positioning_regime_context
source_freshness_status
```

Downstream use:

```text
increase confirmation requirement in crowded regimes
seed adversarial/crowding hypotheses
explain fragile trend behavior
support regime-aware routing
```

Rule:

```text
Positioning context may identify crowding risk.
It may not generate trades or override evidence.
```

Priority:

```text
Medium, useful after source-quality framework exists.
```

---

## 6.5 EIA / Energy and Commodity Context

Layer:

```text
External Intelligence Intake
Macro / Regime Intelligence
Criticality Diagnostics
Seismic / Shock Diagnostics
```

Applied to:

```text
energy inventories
oil/gas regime context
commodity supply shock context
inflation/liquidity proxies
risk regime interpretation
```

Outputs:

```text
energy_regime_context
inventory_shock_flag
commodity_stress_score
macro_energy_context
source_quality_status
```

Downstream use:

```text
explain energy-sensitive equity or macro regimes
support shock/aftershock context
support portfolio and sector-level diagnostics
```

Rule:

```text
Energy data is regime context, not alpha.
```

Priority:

```text
Medium, especially useful for macro-aware equity and commodity research.
```

---

## 6.6 OpenBB ODP / Connector Staging Layer

Layer:

```text
Source Candidate Registry
External Intelligence Intake
Manual Research Sandbox
Source Discovery
```

Allowed use:

```text
discover possible data models
prototype source access
compare available fields
manual Claude Code research support
adapter scouting
```

Not allowed:

```text
canonical source of truth by default
automated hypothesis seeding without per-source manifests
promotion gate input without quality gates
live/paper/shadow signal generation
```

Outputs:

```text
openbb_staging_snapshot
underlying_source_candidates
source_model_inventory
staging_quality_warning
```

Rule:

```text
OpenBB is a connector convenience layer, not a trusted source by default.
Each underlying source still needs its own manifest and quality gates.
```

Priority:

```text
Medium for prototyping, low for production until source-specific gates exist.
```

---

## 6.7 Financial Datasets MCP / Claude Code Research Sandbox

Layer:

```text
Source Candidate Registry
Manual Research Sandbox
External Intelligence Intake later, only if quality-gated
```

Allowed use now:

```text
manual Claude Code research
candidate source exploration
fundamental context scouting
hypothesis seed brainstorming labeled as unvalidated_prior
cross-checking source availability
```

Allowed use later, only after quality gates:

```text
financial statement context
company news context
current/historical price cross-checking
fundamental hypothesis seed context
read-only observability context
```

Not allowed:

```text
trade recommendation
live signal
paper/shadow/live promotion
capital allocation
frozen contract mutation
automated source-of-truth status without validation
```

Outputs:

```text
financialdatasets_mcp_snapshot
financialdatasets_source_quality
manual_research_note
unvalidated_prior_hypothesis_seed
```

Rule:

```text
MCP access increases research convenience.
It does not replace QRE source manifests, quality gates or evidence validation.
```

Priority:

```text
Low-medium. Keep as toolbox/manual sandbox until the core external-intelligence layer exists.
```

---

## 6.8 Binance Public Bulk Data / Crypto Cache

Layer:

```text
External Intelligence Intake
Local Data Cache & Throughput Layer
Crypto Market Behavior Layer
Diagnostics
```

Applied to:

```text
crypto OHLCV history
batch diagnostics
entropy/tail/barrier/aftershock diagnostics
exchange-specific validation
local reproducible backtests
```

Outputs:

```text
crypto_bulk_cache_manifest
crypto_ohlcv_parquet_snapshot
crypto_cache_quality
coverage_by_pair_timeframe
```

Downstream use:

```text
reduce REST API calls
improve reproducibility
speed up crypto diagnostics
support source agreement with Bitvavo/CoinGecko where possible
```

Rule:

```text
Bulk data improves reproducibility and throughput.
It does not remove the need for source freshness and exchange-specific validation.
```

Priority:

```text
High for crypto research throughput.
```

---

## 6.9 CoinGecko Context Data

Layer:

```text
External Intelligence Intake
Crypto Market Behavior Layer
Regime Intelligence
Research Observability
```

Applied to:

```text
crypto market cap context
volume context
dominance regimes
category/sector metadata
broad crypto universe context
```

Outputs:

```text
crypto_dominance_context
crypto_category_context
market_cap_context
volume_context_quality
```

Downstream use:

```text
identify broad crypto regimes
condition crypto hypotheses on dominance/category context
explain asset-specific crypto behavior within broader market state
```

Rule:

```text
Crypto metadata is context.
It is not a signal by itself.
```

Priority:

```text
Medium-high for crypto regime intelligence.
```

---

## 6.10 Event Calendars / Earnings, Dividends, Splits, Macro Releases

Layer:

```text
External Intelligence Intake
Event Context Layer
Regime Intelligence
Failure Analysis
Research Observability
```

Applied to:

```text
earnings dates
dividends
splits
macro release windows
IPO/calendar events
known market-moving scheduled events
```

Outputs:

```text
event_context_snapshot
event_window_flag
earnings_proximity_flag
corporate_action_flag
macro_release_proximity_flag
```

Downstream use:

```text
avoid mistaking event exposure for repeatable edge
segment research around event windows
explain anomalous campaign results
increase confirmation requirements around scheduled events
```

Rule:

```text
Event context helps avoid false positives.
It is not an event-trading system.
```

Priority:

```text
High for equities before serious robustness filtering.
```

---

## 6.11 ETF / Index Constituents and Sector Context

Layer:

```text
External Intelligence Intake
Network Diagnostics
Portfolio Intelligence
Knowledge Graph
```

Applied to:

```text
sector classification
index membership
ETF holdings
peer groups
portfolio overlap
cross-asset network structure
```

Outputs:

```text
sector_context
index_constituent_map
etf_holding_overlap
peer_group_map
portfolio_overlap_warning
```

Downstream use:

```text
improve network diagnostics
avoid hidden concentration
support candidate clustering
support portfolio intelligence
explain correlation and contagion behavior
```

Rule:

```text
Constituent and holdings data explain structure.
They do not allocate capital.
```

Priority:

```text
Medium-high before v3.16.5 Portfolio Intelligence.
```

---

## 6.12 Options / Volatility Surface Data

Status:

```text
Reserve for later, likely after v3.16.2 or during v4/v5 preparation.
```

Layer:

```text
Volatility Regime Intelligence
Event Risk Context
Shadow Execution Realism later
Paper Risk later
```

Applied to:

```text
implied volatility context
skew regimes
term structure
options volume/crowding
earnings/event risk context
volatility stress diagnostics
```

Outputs:

```text
implied_vol_context
skew_regime_context
vol_surface_stress
options_crowding_context
```

Not allowed now:

```text
paid-feed dependency
options trade generation
vol-surface alpha engine
candidate promotion from implied vol alone
```

Rule:

```text
Options data is high-value but high-complexity.
Do not add until source licensing, quality gates and equity regime context are mature.
```

Priority:

```text
Low now, high later for volatility and event-risk research.
```

---

# 7. Throughput Infrastructure Mapping

## 7.1 Summary Table

| Tool / Concept | Verdict | Roadmap Fit | Allowed Form |
|---|---:|---:|---|
| Parquet cache | Very strong | Add | reproducible local data snapshots |
| DuckDB catalog | Very strong | Add | local analytical query layer |
| Polars | Strong | Add selectively | vectorized diagnostics / batch transforms |
| SQLite FTS5 | Strong | Already aligned | retrieval / metadata index |
| Dask | Useful later | Reserve | parallel batch diagnostics |
| Ray | Useful later | Reserve | distributed research workers, only if needed |
| Celery | Useful later | Reserve | task queue only if native queue insufficient |
| Dagster / Prefect | Useful later | Reserve | data pipeline observability / scheduling |
| Airflow | Heavy | Not now | likely overkill |
| Kafka / streaming stack | Not now | Exclude v3.x | possible future real-time phase only |

---

## 7.2 Parquet Cache

Layer:

```text
Local Data Cache & Throughput Layer
External Intelligence Intake
Diagnostics
Sampling Intelligence
```

Applied to:

```text
OHLCV snapshots
fundamental snapshots
source quality snapshots
event calendar snapshots
macro snapshots
intermediate diagnostic tables
```

Outputs:

```text
cache_manifest_latest.v1.json
cache_coverage_latest.v1.json
cache_quality_latest.v1.json
```

Downstream use:

```text
reduce API calls
increase reproducibility
support fast cross-asset scans
support deterministic batch diagnostics
support source agreement checks
```

Rule:

```text
Every cache file must have a manifest entry, source lineage and schema version.
```

Priority:

```text
Very high for throughput.
```

---

## 7.3 DuckDB Metadata and Query Catalog

Layer:

```text
Local Data Cache & Throughput Layer
Research Observability
Diagnostics
Sampling Intelligence
```

Applied to:

```text
querying Parquet snapshots
coverage analysis
source agreement analysis
batch diagnostic scans
cache health reporting
```

Outputs:

```text
duckdb_catalog_manifest
queryable_cache_index
coverage_by_source_asset_timeframe
cache_health_summary
```

Downstream use:

```text
speed up research scans
avoid loading unnecessary data into memory
make coverage gaps visible
support deterministic sampling and routing
```

Rule:

```text
DuckDB is an analytical cache/query layer, not a source of truth independent of artifacts.
```

Priority:

```text
Very high after initial cache manifest exists.
```

---

## 7.4 Polars / Vectorized Diagnostics

Layer:

```text
Diagnostics
Sampling Intelligence
Throughput Layer
```

Applied to:

```text
large OHLCV transforms
cross-asset feature scans
entropy/tail/network preprocessing
state transition table construction
source agreement comparisons
```

Outputs:

```text
batch_transform_report
vectorized_diagnostic_summary
compute_time_saved_estimate
```

Downstream use:

```text
improve throughput of diagnostic generation
reduce pandas bottlenecks
support more assets/timeframes without brute-force waste
```

Rule:

```text
Use Polars selectively for heavy transforms.
Do not rewrite stable pandas paths just for novelty.
```

Priority:

```text
High for heavy diagnostic workloads, medium for early scaffolding.
```

---

## 7.5 Dask / Ray / Distributed Research Workers

Status:

```text
Reserve until local cache and batch processing are insufficient.
```

Layer:

```text
Campaign Layer
Diagnostics
Throughput Layer
Worker Lease / Admission Control
```

Applied to:

```text
parallel diagnostic generation
large campaign batches
multi-asset scans
expensive null-model tests
```

Outputs:

```text
worker_utilization
parallel_batch_report
compute_cost_ledger
admission_control_reason
```

Downstream use:

```text
increase throughput after deterministic batch plans exist
avoid queue starvation
track compute efficiency
```

Rule:

```text
Do not introduce distributed compute before the local throughput bottleneck is measured.
```

Priority:

```text
Low now, medium later.
```

---

## 7.6 Dagster / Prefect-Style Orchestration

Status:

```text
Reserve until scheduled source adapters and cache jobs become operationally complex.
```

Layer:

```text
External Intelligence Intake
Local Data Cache
Source Quality Gates
Research Observability
ADE reporting where appropriate
```

Applied to:

```text
scheduled data refreshes
quality gate runs
cache compaction
source snapshots
nightly diagnostics
research digests
```

Outputs:

```text
orchestration_manifest
job_status_summary
last_successful_refresh
failed_quality_gate_job
operator_visible_pipeline_status
```

Downstream use:

```text
make source refresh reliable
surface failed data jobs
avoid stale research inputs
support reproducible nightly research cycles
```

Rule:

```text
Do not add a workflow orchestrator until QRE's native queue/reporting surfaces are insufficient.
```

Priority:

```text
Medium-low now, medium-high after several source adapters are active.
```

---

# 8. Changes to Roadmap v6 Phases

## v3.15.16 — Intelligent Routing Layer

Add:

```text
source-quality-aware routing
identity-confidence-aware routing
cache-coverage-aware routing
source-usefulness-aware routing
prior-source-failure-aware routing
throughput-cost-aware routing
```

Routing should consider:

```text
source quality
instrument identity confidence
coverage by asset/timeframe
source agreement
cache availability
expected compute cost
source usefulness history
```

Not allowed:

```text
source-only route promotion
vendor-data route promotion
cache-availability-only prioritization
identity-unresolved campaign escalation
```

---

## v3.15.17 — Sampling Intelligence

Add:

```text
coverage-aware sampling
source-agreement sampling
identity-ambiguity exclusion
cache-aware batch sampling
cost-aware diagnostic sampling
source-quality stratification
```

Sampling should answer:

```text
which assets/timeframes have sufficient source coverage?
which sources agree or disagree?
which samples would be cheap because cache exists?
which samples should be avoided because identity is ambiguous?
which regions provide the highest information per compute unit?
```

---

## v3.15.18 — Research Observability Expansion

Add observable surfaces for:

```text
source candidate status
source manifest completeness
source quality gate results
identity resolution decisions
instrument alias mappings
cache coverage
cache freshness
cache hit rate
source usefulness ledger
compute cost per survivor
API calls avoided
```

The operator should see:

```text
which source supplied context
whether the source passed gates
whether identity was resolved confidently
whether data came from cache or live fetch
whether source disagreement exists
whether a source historically produced useful hypothesis seeds
```

---

## v3.15.19 — Hypothesis Discovery Engine

Extend planned modules with:

```text
source_context_adapter.py
identity_context_adapter.py
cache_context_adapter.py
source_quality_adapter.py
```

New hypothesis seed examples:

```text
source_quality_confirmed_equity_momentum_daily_v0
macro_revision_aware_liquidity_regime_equities_v0
crypto_dominance_regime_continuation_v0
earnings_window_false_positive_filter_v0
positioning_crowding_trend_fragility_v0
energy_shock_sector_dispersion_v0
etf_overlap_network_fragility_v0
identity_ambiguous_hypothesis_block_v0
```

Scoring may consider:

```text
source quality
source coverage
source agreement
identity confidence
cache availability
source historical usefulness
compute cost efficiency
known event contamination risk
```

Important:

```text
opportunity_probability_score still means expected research value.
It does not mean prediction certainty, alpha certainty or vendor confidence.
```

---

## v3.15.20 — Failure → Action Mapping

Add deterministic mappings:

```text
source_quality_failed
→ block hypothesis escalation

identity_resolution_ambiguous
→ block until canonical identity is resolved

source_agreement_failed
→ require independent confirmation or suppress

coverage_insufficient
→ collect more data or avoid campaign

cache_stale
→ refresh cache before sampling

source_usefulness_low
→ down-rank source-derived seeds

source_false_positive_high
→ cool down source

high_compute_cost_low_information_gain
→ defer campaign

event_window_contamination_detected
→ require event segmentation

vendor_or_paid_source_detected_without_approval
→ block source activation
```

---

## v3.16.0 — Campaign Feedback Loop

Add:

```text
source usefulness feedback
cache usefulness feedback
identity failure feedback
source disagreement feedback
compute cost feedback
API cost feedback
```

The engine should learn:

```text
which sources produced useful hypothesis seeds
which sources produced false positives
which sources failed quality gates repeatedly
which cache layouts improved throughput
which campaign types had poor information gain per compute unit
```

---

## v3.16.1 — Strategy Fitness Scoring

Add:

```text
source-conditioned survival rate
source-quality-supported survival
identity-confidence-supported survival
cache-backed reproducibility score
source-false-positive association
compute-cost-adjusted research fitness
```

Fitness remains:

```text
research viability
```

not:

```text
capital allocation
live ranking
vendor-source ranking for trading
```

---

## v3.16.2 — Regime Intelligence

Add:

```text
macro source context
revision-aware macro context
energy/commodity context
positioning/crowding context
crypto dominance context
event-calendar regime context
```

Guardrail:

```text
Regime context from external sources is unvalidated prior context until QRE evidence supports it.
```

---

## v3.16.3 — Candidate Clustering

Add:

```text
source-lineage similarity
identity-family similarity
event-contamination similarity
sector/ETF/index overlap similarity
cache-backed reproducibility similarity
```

---

## v3.16.4 — Robustness Filtering

Add:

```text
source agreement challenge
identity confidence check
coverage robustness check
event-window contamination check
point-in-time macro check
survivorship-bias check
single-source dependency check
```

---

## v3.16.5 — Portfolio Intelligence

Add:

```text
ETF/index constituent context
sector context
issuer/asset family context
source-lineage overlap
network concentration from holdings/constituents
portfolio candidate overlap warnings
```

---

## v4.x — Shadow Trading

Add:

```text
shadow source freshness parity
identity mapping parity
cache-vs-live data drift
real-time source health
source latency diagnostics
```

Use only after candidates exist.

---

## v5.x — Paper Trading

Add:

```text
paper degradation by source context
paper degradation by event context
paper degradation by identity/source mismatch
source latency and freshness effect analysis
execution-adjusted source reliability context
```

---

## v6.x — Live Trading

Add only after validation and explicit approval:

```text
source health may inform live risk context
source outage may support kill-switch context
identity mismatch may block live action
source/cached data may not directly create trades
source/cached data may not bypass whitelist/reconciliation/kill switches
vendor/API availability may not control capital allocation
```

---

# 9. Source Status Lifecycle

Use a strict lifecycle for every source.

```text
candidate
→ manual_research_only
→ staging
→ quality_gated
→ active_read_only
→ deprecated
→ blocked
```

Allowed transitions:

```text
candidate → manual_research_only
manual_research_only → staging
staging → quality_gated
quality_gated → active_read_only
active_read_only → deprecated
active_read_only → blocked
staging → blocked
quality_gated → blocked
```

Blocked transitions:

```text
candidate → active_read_only
manual_research_only → active_read_only
staging → hypothesis_seed_input without quality gates
active_read_only → trade_signal_source
any_source → live_capital_authority
```

Lifecycle rules:

```text
Every promotion requires manifest completeness.
Every promotion requires passing quality gates.
Every promotion requires allowed_use and forbidden_use fields.
Every deprecation/block must preserve historical source lineage.
```

---

# 10. Not Allowed

Add this explicit section to Addendum 3.

```text
Not allowed before explicit future roadmap approval:

- treating external data as alpha
- source-only candidate promotion
- vendor API as source of truth without QRE validation
- paid data feeds
- vendor alpha signals
- commercial signal libraries
- private alternative-data vendors
- social/X/Reddit scraping as hypothesis input
- LLM-based source quality decisions
- LLM-based routing, retry, status or cache-validity decisions
- automated trading from Financial Datasets MCP or similar MCP sources
- OpenBB as canonical source without underlying source manifests
- options/OPRA/Cboe paid-data integration before approval
- Kafka/streaming stack in v3.x research core
- real-time data hoarding before shadow/paper need exists
- cache-backed trade signals
- stale cache usage without freshness checks
- identity-ambiguous hypothesis escalation
- source agreement failures ignored silently
- source quality gate failures hidden from operator
- throughput optimizations that skip validation
- distributed compute before local bottlenecks are measured
- mutation of research_latest.json
- mutation of strategy_matrix.csv
- live/paper/shadow/risk/broker/execution changes in v3.x
- capital allocation from source, cache or throughput signals
```

---

# 11. Definition of Done for This Addendum

Roadmap v6 + Addendum 1 + Addendum 2 are successfully extended when:

```text
1. Addendum 3 is explicitly named as a follow-up to Addendum 1 and Addendum 2.

2. Roadmap v6 includes Source Identity, Data Quality & Throughput Intelligence
   as a refinement of External Intelligence Intake.

3. Source Candidate Registry exists conceptually as the place for future sources
   before they become active QRE inputs.

4. Source Identity & Symbology Layer is mapped to instrument identity,
   alias resolution, source symbol mapping and universe validation.

5. Source Manifest & Quality Gate Layer is mapped to mandatory source metadata,
   freshness, coverage, missing-data, timestamp, duplicate, outlier,
   source-agreement and license/terms checks.

6. Local Data Cache & Throughput Layer is mapped to Parquet/DuckDB/Polars-style
   reproducible research throughput, not live execution.

7. Source Usefulness Ledger is mapped to source utility, false positives,
   quality failures, cache hit rate, compute savings and API-cost reduction.

8. OpenFIGI is reserved for instrument identity and symbology, not alpha.

9. FRED/ALFRED are mapped to revision-aware macro regime context.

10. CFTC COT and EIA are mapped to positioning, crowding, energy, commodity
    and macro-regime context.

11. OpenBB is allowed only as staging/prototyping connector until source-specific
    manifests and quality gates exist.

12. Financial Datasets MCP is allowed only as manual/staging research context
    unless later quality-gated.

13. Binance public bulk data and CoinGecko context data are mapped to crypto
    cache, dominance, metadata and regime context.

14. Event calendars, ETF/index constituents and sector context are mapped to
    event contamination control, network diagnostics and portfolio intelligence.

15. Options/volatility surface data is reserved for later volatility/event-risk
    context, not v3.x core trading.

16. Parquet cache, DuckDB catalog and selective Polars processing are allowed
    as throughput infrastructure.

17. Dask/Ray/Celery/Dagster/Prefect-style systems are reserved until local
    throughput and native queue limits are measured.

18. All new outputs go to sidecar artifacts.

19. Frozen contracts remain protected.

20. Source, identity, cache and throughput systems are prohibited from direct
    trading, live capital allocation, broker behavior, execution mutation or
    policy bypass.

21. The operator-light/no-touch intent is preserved through deterministic,
    artifact-driven, inspectable and policy-governed source intelligence.
```

---

# 12. One-Sentence Addendum Summary

```text
Roadmap v6 Addendum 3 extends Addendum 1 and Addendum 2 by adding source identity,
source candidate governance, source quality gates, reproducible local caching,
source usefulness tracking and throughput infrastructure so the QRE can ingest,
normalize, validate, cache and scale external intelligence without becoming a
vendor-data aggregator, cache-backed trading system or throughput-over-quality engine.
```
