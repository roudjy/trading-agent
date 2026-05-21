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
| [`docs/roadmap/Roadmap v6.md`](../roadmap/Roadmap%20v6.md) — base phases v3.15.16 → v3.15.19 (minimal slices) | **ACTIVE** | Active execution scope. Minimal slices only (see §3). |
| [`docs/roadmap/Roadmap v6.md`](../roadmap/Roadmap%20v6.md) — base phases v3.15.20, v3.16.x, v4.x, v5.x, v6.x | **DEFERRED** | Reference doctrine. Not active execution scope. |
| [`docs/roadmap/Roadmap v6 Addendum.md`](../roadmap/Roadmap%20v6%20Addendum.md) | **DEFERRED (reference-only)** | Doctrine + §10 "Not Allowed" remain binding project-wide. Implementation sections are not active execution scope. |
| [`docs/roadmap/Roadmap v6 Addendum 2 - State Sequential Knowledge Retrieval.md`](../roadmap/Roadmap%20v6%20Addendum%202%20-%20State%20Sequential%20Knowledge%20Retrieval.md) | **DEFERRED (reference-only)** | Same as Addendum 1. |
| [`docs/roadmap/Roadmap v6 Addendum 3 - Source Identity Data Quality and Throughput Intelligence.md`](../roadmap/Roadmap%20v6%20Addendum%203%20-%20Source%20Identity%20Data%20Quality%20and%20Throughput%20Intelligence.md) | **DEFERRED (reference-only)** | Same as Addendum 1. |
| [`docs/roadmap/autonomous_development.txt`](../roadmap/autonomous_development.txt) — ADE base (A1–A24) | **ACTIVE** | Unchanged; ADE governance/queue/release-gate stays. |
| [`docs/roadmap/autonomous_development.txt`](../roadmap/autonomous_development.txt) — Step 5 broad implementation | **BLOCKED** | Permanently blocked per ADR-017 and [`step5_design.md`](step5_design.md). Unchanged. |

## 3. Active execution order (minimal Roadmap v6 path)

After the research-quality hardening sprint
([`research_quality_sprint_plan.md`](research_quality_sprint_plan.md))
completes, work proceeds in this order:

1. **Research-Quality Hardening Sprint** — multiplicity ledger spec,
   sequestered hold-out discipline, null-pipeline test, research-
   quality KPI definitions, paper-readiness checklist artifact spec,
   routing/sampling/scoring reason-record specs, Hypothesis Discovery
   doctrine (ADR-019 draft), paper/shadow/live separation (ADR-020
   draft). Docs-only sprint.
2. **Minimal v3.15.16 Intelligent Routing slice** — routing by
   expected information gain over existing presets, dead-zone
   suppression, routing-reason records. No diagnostic-aware,
   state-aware, source-quality-aware, retrieval-aware, or
   knowledge-aware routing.
3. **Minimal v3.15.17 Sampling slice** — stratified sampling over
   existing coverage, null-baseline control sampling,
   sampling-reason records. No tail/entropy/phase-transition/barrier/
   resonance/network/post-shock sampling families.
4. **Minimal v3.15.18 Observability slice** — candidate-quality
   dashboard panel, operator-attention-budget enforcement, surfaces
   for routing/sampling/scoring reason records, multiplicity-ledger
   summary surface, hold-out lineage surface. No KG visualisation,
   no retrieval debug surfaces, no full lineage UI, no
   source-quality dashboards.
5. **Foundational implementations** (per sprint specs) — multiplicity
   ledger, hold-out hook, null-pipeline integration test,
   reason-record append-only writers, paper-readiness checklist
   writer.
6. **Minimal v3.15.19 Hypothesis Discovery slice** — only after
   ADR-019 is accepted and the foundational implementations land.
   `behavior_catalog`, `behavior_hypotheses`, `opportunity_scoring`
   (axiomatised per ADR-019), `preset_feasibility`,
   `campaign_seed_proposer`. Three diagnostics (null-model, tail,
   entropy) used as **filters**, not seeds. No
   `external_intelligence_catalog`, no `physics_behavior_catalog`,
   no `mechanistic_behavior_catalog`, no `state_hypothesis_adapter`,
   no `knowledge_context_adapter`, no `retrieval_context_adapter`,
   no `source_context_adapter`.
7. **Staged diagnostic rollout** under promote-or-retire — one
   diagnostic per release, gated by "moved ≥1 survivor's status
   within 30 days".
8. **First paper-readiness assessment** of any survivor against the
   paper-readiness checklist.
9. **Reactivation review of Addendums 1/2/3** — only if measurable
   survivor-quality improvement exists and ≥1 paper-ready candidate
   has cleared the checklist.

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
- [`docs/adr/_drafts/ADR-019-hypothesis-discovery-doctrine.md`](../adr/_drafts/ADR-019-hypothesis-discovery-doctrine.md)
  — gates v3.15.19.
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

- 2026-05-21: initial version. Reclassification of Addendum 1/2/3
  to DEFERRED reference-only. Active execution scope reset to the
  minimal Roadmap v6 path in §3.
