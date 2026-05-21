# Roadmap Scope Status — canonical active vs deferred index

> **Status:** governance index. Read-only operational decision aid for
> ADE, planner, product-owner, and human operators.
>
> **Authority:** declares which roadmap documents are in active
> execution scope and which are deferred. Does **not** grant
> implementation, runtime, trading, paper, shadow, broker, risk, or
> live authority. Hard governance (ADR-014, ADR-015, ADR-017,
> [`no_touch_paths.md`](no_touch_paths.md),
> [`execution_authority.md`](execution_authority.md),
> [`autonomy_ladder.md`](autonomy_ladder.md)) is preserved unchanged.
>
> **Effective date:** 2026-05-21.
> **Reset reference:** [`docs/adr/_drafts/ADR-018-roadmap-execution-reset.md`](../adr/_drafts/ADR-018-roadmap-execution-reset.md).

## 1. Why this document exists

The Roadmap v6 stack now contains three addendums that, taken
together, planned ~25 new sub-layers and dozens of new sidecar
artifacts. None of those layers has yet produced a single
paper-ready candidate under the doctrine they introduced.

This index reclassifies the addendums from **active execution
scope** to **deferred reference doctrine** so the project can
optimise for one outcome:

> Can the current architecture, with minimal additions, produce one
> robust paper-ready candidate under strict research-quality
> discipline?

Every queue item, ADR, sidecar, and diagnostic must justify itself
against that question until a paper-ready candidate exists.

## 2. Active vs deferred — canonical table

| Roadmap document | Status | Allowed use |
|---|---|---|
| [`docs/roadmap/Roadmap v6.md`](../roadmap/Roadmap%20v6.md) — base phases v3.15.16 → v3.15.19 (minimal slices) | **DONE** | Completed minimal slices. Historical active execution scope. |
| [`docs/roadmap/Roadmap v6.md`](../roadmap/Roadmap%20v6.md) — base phases v3.15.20 and v3.16.x (minimal slices) | **ACTIVE** | Active execution scope under [`ADR-021`](../adr/ADR-021-roadmap-v6-core-path-reactivation.md). Minimal slices only (see §3). |
| [`docs/roadmap/Roadmap v6.md`](../roadmap/Roadmap%20v6.md) — v4.x, v5.x, v6.x and non-minimal v3.16.x expansion | **DEFERRED** | Reference doctrine. Not active execution scope. |
| [`docs/roadmap/Roadmap v6 Addendum.md`](../roadmap/Roadmap%20v6%20Addendum.md) | **DEFERRED (reference-only)** | Doctrine + §10 "Not Allowed" remain binding project-wide. Implementation sections are not active execution scope. |
| [`docs/roadmap/Roadmap v6 Addendum 2 - State Sequential Knowledge Retrieval.md`](../roadmap/Roadmap%20v6%20Addendum%202%20-%20State%20Sequential%20Knowledge%20Retrieval.md) | **DEFERRED (reference-only)** | Same as Addendum 1. |
| [`docs/roadmap/Roadmap v6 Addendum 3 - Source Identity Data Quality and Throughput Intelligence.md`](../roadmap/Roadmap%20v6%20Addendum%203%20-%20Source%20Identity%20Data%20Quality%20and%20Throughput%20Intelligence.md) | **DEFERRED (reference-only)** | Same as Addendum 1. |
| [`docs/roadmap/autonomous_development.txt`](../roadmap/autonomous_development.txt) — ADE base (A1–A24) | **ACTIVE** | Unchanged; ADE governance/queue/release-gate stays. |
| [`docs/roadmap/autonomous_development.txt`](../roadmap/autonomous_development.txt) — Step 5 broad implementation | **BLOCKED** | Permanently blocked per ADR-017 and [`step5_design.md`](step5_design.md). Unchanged. |

## 3. Active execution order (minimal Roadmap v6 path)

The **active queue** is canonically declared in
[`docs/development_work_queue/seed.jsonl`](../development_work_queue/seed.jsonl)
under the strict JSONL schema enforced by
[`reporting/development_work_queue.py`](../../reporting/development_work_queue.py)
and pinned by
[`tests/unit/test_development_work_queue.py`](../../tests/unit/test_development_work_queue.py)
(`test_default_seed_file_in_repo_carries_reactivated_minimal_core_queue`).

The chain is sequential: each item is blocked by the previous one.
After the v3.16.x implementation PR, all operator-authorized minimal
core-path items are `status: done`. No Addendum 1/2/3 item and no
v4/v5/v6 item is active.

1. **Research-Quality Hardening Sprint** (priority 1, status: done,
   LOW risk, governance category, owner: planner). Multiplicity
   ledger spec, sequestered hold-out discipline, null-pipeline
   integration test, research-quality KPI definitions, paper-
   readiness checklist artifact spec, routing/sampling/scoring
   reason-record specs, Hypothesis Discovery doctrine (ADR-019
   draft), paper/shadow/live separation (ADR-020 draft). Docs/
   specs/ADRs only — no v3.15.16+ feature code lands here.
2. **Minimal v3.15.16 Intelligent Routing slice** (priority 2,
   status: done, MEDIUM risk, reporting category,
   owner: implementation_agent). Routing by expected information
   gain over existing presets, dead-zone suppression, routing-
   reason records. No diagnostic-aware, state-aware, source-
   quality-aware, retrieval-aware, or knowledge-aware routing.
3. **Minimal v3.15.17 Sampling Intelligence slice** (priority 2,
   status: done, MEDIUM risk, reporting category,
   owner: implementation_agent). Stratified sampling over existing
   coverage, null-baseline control sampling, sampling-reason
   records. No tail / entropy / phase-transition / barrier /
   resonance / network / post-shock sampling families.
4. **Minimal v3.15.18 Research Observability Expansion slice**
   (priority 2, status: done, MEDIUM risk,
   observability category, owner: implementation_agent). Candidate-
   quality dashboard panel exposing the seven KPIs from
   [`research_quality_kpis.md`](research_quality_kpis.md);
   operator-attention-budget enforcement; surfaces for routing /
   sampling / scoring reason records; multiplicity-ledger summary
   surface; hold-out lineage surface. No KG visualisation, no
   retrieval debug surfaces, no full lineage UI, no source-quality
   dashboards.
5. **Minimal v3.15.19 Hypothesis Discovery Engine slice** (priority
   2, status: done, MEDIUM risk, reporting category,
   owner: implementation_agent). Begins **only after ADR-019 is
   promoted out of `_drafts/`**. `behavior_catalog`,
   `behavior_hypotheses`, `opportunity_scoring` (axiomatised per
   ADR-019), `preset_feasibility`, `campaign_seed_proposer`. Three
   active diagnostics (null-model, tail, entropy) used as
   **filters**, not seeds. No `external_intelligence_catalog`, no
   `physics_behavior_catalog`, no `mechanistic_behavior_catalog`,
   no `state_hypothesis_adapter`, no `knowledge_context_adapter`,
   no `retrieval_context_adapter`, no `source_context_adapter`.
6. **STOP — operator review gate after minimal v3.15.19** (priority
   2, status: done, LOW risk, governance category,
   owner: human_operator, `human_needed_reason:
   architecture_crossroads`). **Hard STOP.** Operator reviews KPIs
   (`research_quality_kpis.md` §3) and decides: proceed with staged
   diagnostic rollout, simplify further, or halt. The autonomous PR
   runner may not advance past this item without explicit operator
   authorisation. Reactivation of any deferred Addendum subsection
   requires an explicit operator-approved ADR per §4.
7. **Minimal v3.15.20 Failure to Action Mapping slice** (priority 2,
   status: done, MEDIUM risk, reporting category, owner:
   implementation_agent). Deterministic failure taxonomy, bounded
   next-action recommendations, and read-only reason records. No
   adaptive feedback loop, no strategy mutation, no executable
   strategy generation, and no paper / shadow / live behavior.
8. **Minimal v3.16.x Adaptive Research Learning path** (priority 2,
   status: done, MEDIUM risk, reporting category,
   owner: implementation_agent). Deterministic campaign feedback
   metrics and evidence-backed read-only learning context only.
   Regime intelligence, candidate clustering, robustness filtering,
   and portfolio intelligence remain read-only context or evidence
   gates unless a future accepted ADR expands scope.

### Out of active queue before ADR-021

- v3.15.20 Failure to Action Mapping (full FSM) was **deferred** at
  reset time. ADR-021 reactivates only the minimal deterministic
  mapping slice.
- v3.16.x adaptive learning, fitness scoring, regime intelligence,
  candidate clustering, robustness filtering (full modules) were
  **deferred** at reset time. ADR-021 reactivates only the minimal
  deterministic, read-only Adaptive Research Learning path.
- v3.16.5 Portfolio Intelligence — **deferred**.
- v4.x Shadow, v5.x Paper, v6.x Live — **deferred** behind
  separate readiness ADRs (see ADR-020 draft).
- All Addendum 1 / 2 / 3 implementation surfaces beyond the three
  active diagnostics — **deferred** per §5.

### What happened after item 6 (STOP gate)

ADR-021 records the operator-authorized reactivation of the next
minimal core path after the STOP gate. Future reactivation ADRs must:

- name the specific deferred subsection being activated;
- state the promote-or-retire criterion (e.g., "moved ≥1
  survivor's status within 30 days");
- state the definition of done;
- show evidence that all reactivation gates in §4 are satisfied.

The ADR is operator-driven. ADE/planner/product-owner may **not**
author it without operator initiation.

## 4. Reactivation gates

An addendum (or any deferred sub-section of a base phase) may leave
**DEFERRED** status only when **all** of the following hold:

- ≥1 paper-ready candidate has cleared the paper-readiness checklist.
- The multiplicity ledger shows multiplicity-adjusted survivor signal
  greater than the null-model baseline.
- The diagnostic utility ledger shows the three active diagnostics
  each changed ≥1 survivor's status at least once.
- Operator attention budget is not exhausted.
- An **operator-approved ADR** explicitly identifies *which
  subsection* of which addendum is being activated, with
  promote-or-retire criteria and an explicit definition of done.

Until those gates are satisfied:

- ADE may not derive queue items from any addendum.
- The autonomous PR runner may not select implementation units
  whose `expected_files` correspond to addendum surfaces beyond the
  minimal v3.15.16–v3.15.19 slices.
- Planner and product-owner may not promote addendum-derived
  candidates.
- New ADRs that reference addendum sections must clearly mark them
  as deferred context.

## 5. Active vs deferred — by surface

### 5.1 Diagnostics (active set)

- `null_model` — random-walk / shuffled-returns / surrogate baselines.
- `tail_asymmetry` — tail-alpha + right/left asymmetry + left-tail
  fragility flag.
- `entropy_structure` — Shannon-style entropy + market-orderliness
  + noise-dominance flag.

Used as **filters**, not seeds. Each diagnostic must demonstrate
within 30 calendar days of activation that it changed ≥1 survivor's
status, or be retired (promote-or-retire).

### 5.2 Diagnostics (deferred)

All other diagnostic families from Addendum 1: criticality, barrier,
resonance, network, adversarial, control, seismic, turbulence,
quorum, language. All state/sequential diagnostics from Addendum 2:
Markov, HMM, Semi-Markov, higher-order sequence, particle filters,
FSM helpers, queueing. All source-quality diagnostics from
Addendum 3 beyond the minimum inline manifest checks for the three
active sources.

### 5.3 Sources (active set)

The three sources the QRE already depends on:

- The existing core price/history source (yfinance/Stooq equivalent
  currently in use).
- One macro source (FRED non-revision-aware; ALFRED deferred).
- One crypto source (existing Bitvavo/Binance public candles
  pipeline).

Inline source manifests (per Addendum 3 §4.3 *Core quality gates*
only — freshness, missing-data, timestamp-monotonicity, duplicate-
bar, outlier, coverage, source-agreement-where-possible,
identity-mapping-where-possible, license-terms-present,
schema-version) are sufficient for v3.15.x. No new sidecar registry
is introduced.

### 5.4 Sources (deferred)

OpenFIGI, CFTC COT, EIA, OpenBB ODP, Financial Datasets MCP,
CoinGecko context, earnings/events calendars, ETF/index constituents,
options/OPRA/Cboe. Source Candidate Registry, Source Identity &
Symbology Layer, Local Data Cache & Throughput Layer, Source
Usefulness Ledger — all deferred as sidecar/module work.

Social/X/Reddit and paid vendor alpha remain **permanently blocked**
until an explicit future ADR. This is unchanged.

### 5.5 Retrieval / knowledge / state (all deferred)

Deferred in their entirety until reactivation:

- Hybrid retrieval, Reciprocal Rank Fusion (RRF), cross-encoder
  rerankers, Bayesian Networks, Tree-of-Thoughts (bounded),
  Graph-of-Thoughts.
- Knowledge graph, ontology, entity resolution module.
- HMM, Semi-Markov, particle filters, higher-order Markov.
- Adaptive Research Learning loops (v3.16.0+).

Keyword + metadata retrieval over existing artifacts is the only
allowed retrieval surface during the reset.

### 5.6 Throughput / orchestration (all deferred)

Parquet snapshots, DuckDB catalog, Polars, Dask, Ray, Celery,
Dagster, Prefect, Airflow, Kafka — deferred until a measured local
throughput bottleneck justifies them.

### 5.7 Permanent denials (unchanged)

Reaffirmed by this reset:

- Paid vendor alpha; vendor signal libraries; private
  alternative-data vendors.
- Genetic programming; RLAIF; GNN price prediction; RNN/LSTM/
  Transformer/SSM-Mamba for price prediction.
- Hidden ML, stochastic routing, opaque scoring, hidden ranking
  authority.
- Live trading from any QRE/ADE surface.
- Step 5 autonomous merge / deploy (Level 6 permanently disabled
  per ADR-015).
- Mutation of frozen contracts: `research_latest.json`,
  `strategy_matrix.csv`.

## 6. Doctrine that remains binding from each deferred addendum

Deferred status applies to **implementation sections only**. The
following doctrine remains binding project-wide regardless of
execution status:

From Addendum 1:

> Diagnostics do not trade.
> External/public data is not alpha.

From Addendum 2:

> State models do not trade.
> Retrieval is context, not authority.
> Knowledge graphs are lineage, not truth.

From Addendum 3:

> Source adapters do not trade.
> Source identity is infrastructure, not alpha.
> Source quality gates are mandatory.
> Throughput infrastructure is not permission to lower standards.

The §10 "Not Allowed" sections of each addendum remain active
project-wide independent of activation status.

## 7. Interaction with the existing catalog and conveyor

Until a future, explicitly-scoped catalog-contraction PR retires
addendum phases from
[`reporting/roadmap_task_catalog.py`](../../reporting/roadmap_task_catalog.py)
and
[`reporting/roadmap_task_units.py`](../../reporting/roadmap_task_units.py),
the autonomous PR runner's behaviour is constrained at the
governance layer:

- Planner / product-owner / operator selections must respect this
  document's active vs deferred mapping. No addendum-derived unit
  is to be picked up.
- The mandate phases `addendum_1`, `addendum_2`, `addendum_3` in
  `reporting/roadmap_unit_authority.py:_MANDATE_PHASES` remain in
  code for replay/determinism, but no addendum-derived unit may be
  promoted to `STRATEGICALLY_PREAPPROVED` execution as a matter of
  governance until a reactivation ADR exists.
- A follow-up scoped PR (post-reset) may retire those phases from
  the code-level mandate after CODEOWNERS review.

This separation keeps the docs-only reset from breaking
determinism pins on
[`tests/unit/test_roadmap_task_catalog.py`](../../tests/unit/test_roadmap_task_catalog.py),
[`tests/unit/test_roadmap_task_units.py`](../../tests/unit/test_roadmap_task_units.py),
and
[`tests/unit/test_roadmap_unit_authority.py`](../../tests/unit/test_roadmap_unit_authority.py).
Removal of the addendum phases from those seeds is a separate,
operator-approved follow-up that will update those pins.

## 8. Cross-references

- [`docs/adr/_drafts/ADR-018-roadmap-execution-reset.md`](../adr/_drafts/ADR-018-roadmap-execution-reset.md)
  — formal ADR for this reset.
- [`docs/adr/ADR-019-hypothesis-discovery-doctrine.md`](../adr/ADR-019-hypothesis-discovery-doctrine.md)
  — gates v3.15.19.
- [`docs/adr/ADR-021-roadmap-v6-core-path-reactivation.md`](../adr/ADR-021-roadmap-v6-core-path-reactivation.md)
  — reactivates only minimal v3.15.20 and minimal v3.16.x.
- [`docs/adr/_drafts/ADR-020-paper-shadow-live-separation.md`](../adr/_drafts/ADR-020-paper-shadow-live-separation.md)
  — makes the implicit separation a doctrinal invariant.
- [`docs/governance/research_quality_sprint_plan.md`](research_quality_sprint_plan.md)
  — the active sprint plan (the next queue item).
- [`docs/governance/research_quality_kpis.md`](research_quality_kpis.md)
  — measurable success criteria.
- [`docs/adr/ADR-014-truth-authority-settlement.md`](../adr/ADR-014-truth-authority-settlement.md)
  — canonical authority mapping (unchanged).
- [`docs/adr/ADR-015-claude-agent-governance.md`](../adr/ADR-015-claude-agent-governance.md)
  — autonomy ladder; Level 6 permanently disabled (unchanged).
- [`docs/adr/ADR-017-step5-autonomous-implementation-loop.md`](../adr/ADR-017-step5-autonomous-implementation-loop.md)
  — Step 5 design + readiness (unchanged).
- [`docs/governance/strategic_roadmap_execution_mandate.md`](strategic_roadmap_execution_mandate.md)
  — A22 mandate (unchanged at code level; reset constrains its
  applicability at the governance level until reactivation ADR).
- [`docs/governance/no_touch_paths.md`](no_touch_paths.md) — no
  changes.
- [`docs/governance/execution_authority.md`](execution_authority.md)
  — no changes.

## 9. Update history

- 2026-05-21: initial version (PR #264, merge SHA `ae0a459`).
  Reclassification of Addendum 1/2/3 to DEFERRED reference-only.
  Active execution scope reset to the minimal Roadmap v6 path
  in §3.
- 2026-05-21: queue rebuild follow-up. §3 expanded to the explicit
  6-item active queue with sequential `blocked_by` chain; STOP /
  operator review gate added as item 6. Six items seeded into
  [`docs/development_work_queue/seed.jsonl`](../development_work_queue/seed.jsonl).
  Cross-reference:
  [`queue_rebuild_2026_05_21.md`](queue_rebuild_2026_05_21.md).
- 2026-05-21: operator-authorized queue reactivation recorded in
  ADR-021. Minimal v3.15.20 became active as the single ready item;
  minimal v3.16.x was blocked by v3.15.20. Addendums 1/2/3 and
  v4/v5/v6 remain deferred/reference-only.
- 2026-05-21: minimal v3.15.20 implementation PR updates the queue
  state so v3.15.20 is done and minimal v3.16.x is the single ready
  item.
- 2026-05-21: minimal v3.16.x implementation PR completes the
  operator-authorized minimal core path. No next active v4/v5/v6 or
  Addendum item is introduced.
