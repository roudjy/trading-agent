# Research-Quality Hardening Sprint — plan and specs

> **Status:** active. The sprint declared by the 2026-05-21 roadmap
> reset. Docs/specs-only; no runtime code lands in this sprint.
>
> **Authority:** governance plan. Declares the work order, expected
> artifacts, exit criteria, and out-of-scope items for the sprint
> that must complete before any v3.15.16+ feature work resumes.
>
> **Cross-refs:**
> [`roadmap_scope_status.md`](roadmap_scope_status.md),
> [`docs/adr/_drafts/ADR-018-roadmap-execution-reset.md`](../adr/_drafts/ADR-018-roadmap-execution-reset.md),
> [`docs/adr/_drafts/ADR-019-hypothesis-discovery-doctrine.md`](../adr/_drafts/ADR-019-hypothesis-discovery-doctrine.md),
> [`docs/adr/_drafts/ADR-020-paper-shadow-live-separation.md`](../adr/_drafts/ADR-020-paper-shadow-live-separation.md),
> [`research_quality_kpis.md`](research_quality_kpis.md).

## 1. Purpose

Before adding more intelligence breadth (more diagnostics, more
sources, more retrieval surfaces, more sidecars, more state
machines), the project must establish measurable, deterministic,
inspectable research quality. This sprint produces the
specifications and ADRs that gate every subsequent v3.15.16+
implementation slice.

The sprint deliberately ships no runtime code. Each implementation
artifact named here lands in its own scoped follow-up PR after the
specs merge.

## 2. Sprint scope (9 items, all docs/specs/ADRs)

### S1. ADR-018 — Roadmap Execution Reset

- File: [`docs/adr/_drafts/ADR-018-roadmap-execution-reset.md`](../adr/_drafts/ADR-018-roadmap-execution-reset.md).
- Records the reset decision (Addendum 1/2/3 → DEFERRED), the
  reactivation gates, and the active execution order.
- Promotion to `docs/adr/ADR-018-*.md` is a separate operator-driven
  governance PR.

### S2. ADR-019 — Hypothesis Discovery doctrine and scoring spec

- File: [`docs/adr/_drafts/ADR-019-hypothesis-discovery-doctrine.md`](../adr/_drafts/ADR-019-hypothesis-discovery-doctrine.md).
- Specifies `opportunity_probability_score` axioms (deterministic,
  bounded, monotone in stated inputs, independent of execution-side
  state).
- Specifies the falsifier (Discovery does not promote candidates).
- Specifies the seed-emission contract.
- Gates v3.15.19 minimal Hypothesis Discovery slice.

### S3. ADR-020 — Paper/Shadow/Live separation doctrine

- File: [`docs/adr/_drafts/ADR-020-paper-shadow-live-separation.md`](../adr/_drafts/ADR-020-paper-shadow-live-separation.md).
- Promotes the existing implicit separation to ADR form.
- Adds explicit clauses: no diagnostic / no retrieval / no source /
  no knowledge-graph / no score output ever feeds live order
  placement; v4/v5/v6 each require their own readiness ADR.

### S4. Global multiplicity ledger — spec

- File: this document, §6 below (consolidated). Future detailed
  schema may land at `docs/governance/multiplicity_ledger.md` and
  `docs/governance/multiplicity_ledger/schema.v1.md` in a scoped
  follow-up.
- Defines an append-only ledger that counts every effective
  hypothesis test (diagnostic invocation that influences survivor
  status, candidate scoring event, OOS evaluation event, null-model
  evaluation event).
- Defines how Deflated Sharpe consumes the ledger.

### S5. Sequestered hold-out discipline — spec

- File: this document, §7 below (consolidated). Future detailed
  schema may land at `docs/governance/holdout_discipline.md` and
  `state/holdout_manifest.v1.json` in a scoped follow-up.
- Defines the hold-out window, the manifest schema, the
  hook-enforced read-deny, and the red-team review process.

### S6. Null-pipeline integration test — spec

- File: this document, §8 below (consolidated). Implementation
  lands as `tests/integration/test_null_pipeline.py` in a scoped
  follow-up.
- Defines the test: run the full active stack on shuffled /
  surrogate returns; assert zero candidates pass the cost-adjusted
  promotion gate; assert score distributions are indistinguishable
  from null at chosen confidence.

### S7. Research-quality KPI definitions

- File: [`research_quality_kpis.md`](research_quality_kpis.md).
- Declares the seven KPIs, how they are computed, and reporting
  cadence.

### S8. Paper-readiness checklist artifact — spec

- File: this document, §9 below (consolidated). Future detailed
  schema may land at `docs/governance/paper_readiness_checklist.md`
  and `docs/governance/paper_readiness_checklist/schema.v1.md`.
- Replaces the current single readiness flag with a per-candidate
  YES/NO checklist that records multiplicity-adjusted Deflated
  Sharpe, null-beat, cost-adjusted edge, OOS on hold-out review,
  regime checks, and single-source-dependency check.

### S9. Routing / sampling / scoring reason-record schemas

- File: this document, §10 below (consolidated). Future detailed
  schemas may land at
  `docs/governance/routing_reason_records.md`,
  `docs/governance/sampling_reason_records.md`, and
  `docs/governance/scoring_reason_records.md` (or under a unified
  `reason_records` family).
- Append-only schemas; one record per decision; deterministic;
  hashable.

## 3. Sprint exit criteria

All of the following must hold to leave the sprint:

1. ADR-018, ADR-019, ADR-020 exist as drafts under `docs/adr/_drafts/`.
2. [`roadmap_scope_status.md`](roadmap_scope_status.md) is consistent
   with the reset and is the canonical active-vs-deferred index.
3. This plan ([`research_quality_sprint_plan.md`](research_quality_sprint_plan.md))
   and the KPI doc ([`research_quality_kpis.md`](research_quality_kpis.md))
   exist and cross-reference each other.
4. Addendum 1/2/3 headers carry the `Execution Status: DEFERRED`
   block.
5. The active execution queue (planner / product-owner / operator
   selection) carries only items from the active scope per
   [`roadmap_scope_status.md`](roadmap_scope_status.md) §3.
6. No frozen contract was mutated; no protected path was touched.

## 4. Out of scope for the sprint

- Any v3.15.16+ feature implementation.
- Any diagnostic implementation.
- Any source-adapter work.
- Any retrieval / KG / state implementation.
- Any addendum implementation.
- Any change to the code-level catalog
  ([`reporting/roadmap_task_catalog.py`](../../reporting/roadmap_task_catalog.py)),
  the unit decomposition
  ([`reporting/roadmap_task_units.py`](../../reporting/roadmap_task_units.py)),
  the unit authority post-process
  ([`reporting/roadmap_unit_authority.py`](../../reporting/roadmap_unit_authority.py)),
  or any pinned test that references those modules. Retiring the
  `addendum_1` / `addendum_2` / `addendum_3` phases from the
  code-level mandate is a separate operator-approved follow-up PR.

## 5. Risk register (sprint-internal)

| Risk | Likelihood | Mitigation |
|---|---|---|
| Sprint slows feature work | Medium | Sprint is intentionally short; specs are intentionally minimal. |
| Operator wants to merge addendum work mid-sprint | Low | Reactivation gates in [`roadmap_scope_status.md`](roadmap_scope_status.md) §4 block this without an explicit ADR. |
| Drift between specs and follow-up implementations | Medium | Each implementation PR must reference and quote the spec; CI tests pin the schema. |
| Multiplicity ledger underbuilt at spec stage | Medium | This document §6 names the minimum required fields and invariants. |
| Hold-out hook accidentally locks out development | Low | Manifest excludes the development sandbox; the hook is scoped to the named sequestered window. |

## 6. Consolidated spec — Global multiplicity ledger (S4)

### 6.1 Purpose

Count every effective hypothesis test so Deflated Sharpe and other
false-discovery corrections operate on a true `N`. Without the
ledger, multiplicity correction is decorative.

### 6.2 Append-only schema (minimum required fields)

```text
multiplicity_ledger.v1.jsonl
  - ts_utc                    # ISO8601
  - event_id                  # deterministic hash of (kind, scope, payload)
  - event_kind                # closed vocab: diagnostic_evaluation,
                              # hypothesis_emission, candidate_scoring,
                              # oos_evaluation, null_model_evaluation,
                              # robustness_check
  - scope                     # candidate_id or seed_id or family_id
  - inputs_digest             # hash of relevant inputs (data window,
                              # diagnostic name, parameters)
  - outputs_digest            # hash of relevant outputs (score,
                              # decision)
  - decision_kind             # filtered / kept / null / undecided
  - notes                     # short free text; cap at 200 chars
  - schema_version            # "v1"
```

### 6.3 Invariants

- Append-only: no UPDATE, no DELETE, no reordering. Enforced by an
  atomic-write helper that refuses any write that does not append.
- Monotonic timestamps within process; cross-process ordering by
  event_id where ts collisions occur.
- `event_id` is deterministic given inputs; double-writes are
  idempotent.
- Total count of events with a given `event_kind` is callable as a
  pure function of the ledger.

### 6.4 Deflated Sharpe wiring

The Deflated Sharpe estimator consumes the ledger as follows:

- For a survivor `c`, the effective number of trials `N_eff(c)` is
  the count of `event_kind in {candidate_scoring, oos_evaluation,
  null_model_evaluation}` whose `scope` is `c` or `c`'s parent
  family.
- The Sharpe deflation factor uses `N_eff(c)` (not a constant).
- The KPI `multiplicity_adjusted_survivor_quality` (see
  [`research_quality_kpis.md`](research_quality_kpis.md) §3) is the
  median deflation-adjusted Sharpe across active survivors.

### 6.5 Authority

- The ledger is **lineage**, not authority. It does not promote or
  demote candidates. It informs Deflated Sharpe and the
  paper-readiness checklist.
- Write authority is restricted to the diagnostic / scoring /
  evaluation runtime layer. ADE/governance never writes to it.

### 6.6 Tests required (spec)

- Append-only invariant test.
- Idempotence test (double-write of same `event_id` is a no-op).
- Monotonicity test.
- Consistency-with-Deflated-Sharpe test (a synthetic ledger
  produces the expected `N_eff`).

## 7. Consolidated spec — Sequestered hold-out discipline (S5)

### 7.1 Purpose

Keep one untouched data window for final red-team validation of
any candidate. Without sequestration, every later layer that reads
data contaminates final OOS validation.

### 7.2 Manifest

`state/holdout_manifest.v1.json` (planned):

```text
{
  "schema_version": "v1",
  "windows": [
    {
      "window_id": "holdout_2026Q1_crypto_eur",
      "asset_class": "crypto",
      "asset_universe": ["BTC/EUR", "ETH/EUR", "..."],
      "start_utc": "2026-01-01T00:00:00Z",
      "end_utc":   "2026-03-31T23:59:59Z",
      "purpose": "red_team_paper_promotion",
      "read_authorization_required": true,
      "last_authorized_read_ts": null,
      "last_authorized_reader_kind": null
    }
  ]
}
```

### 7.3 Hook-enforced read-deny

A new hook (planned), `deny_holdout_read.py`, reads the manifest
and:

- Denies any read against files / partitions / timestamps within a
  declared hold-out window.
- Allows reads only during an explicit operator-authorised
  red-team review window. The hook treats authorisation as an
  ephemeral flag in `state/`, never as a config file change.

The hook is in the same family as `deny_no_touch.py` and
`deny_outside_agent_allowlist.py`. It runs at `PreToolUse` for
`Read`-like tools. Implementation is a scoped follow-up PR.

### 7.4 Red-team review process

A candidate may enter the hold-out review only after passing
gates 1-5 of the validation chain
([`research_quality_kpis.md`](research_quality_kpis.md) §5 and
[`paper_readiness_checklist`](#9-consolidated-spec--paper-readiness-checklist-s8)).

The review:

- Is operator-initiated.
- Releases the read-deny only for the named candidate, only for
  the named window, only for one review.
- Produces a single artifact under
  `logs/holdout_reviews/<window_id>/<candidate_id>.v1.json`
  recording the read, the decision, and the candidate's
  multiplicity-adjusted score.

### 7.5 Tests required (spec)

- Manifest schema test.
- Hook read-deny test (covers data files and timestamp filters).
- Authorization-window lifecycle test (authorisation is
  single-use).

## 8. Consolidated spec — Null-pipeline integration test (S6)

### 8.1 Purpose

A CI guarantee that the full active stack rejects pure noise.
Cheapest possible falsifier of the entire architecture.

### 8.2 Test design

`tests/integration/test_null_pipeline.py` (planned):

1. Fixture: deterministic shuffled returns / surrogate price paths
   for the three active assets, generated with a fixed seed.
2. Run the full active stack:
   - routing (v3.15.16 minimal),
   - sampling (v3.15.17 minimal),
   - the three active diagnostics (null-model, tail, entropy),
   - hypothesis discovery (v3.15.19 minimal, once it lands),
   - the validation gate chain
     ([`research_quality_kpis.md`](research_quality_kpis.md) §5).
3. Assert:
   - zero candidates pass the cost-adjusted promotion gate
     (gate 3);
   - zero candidates reach paper-readiness;
   - score distributions are statistically indistinguishable from
     null at chosen confidence (test will use a closed,
     deterministic statistical method documented in the test).

### 8.3 CI placement

Runs in the `integration` test suite. Failure blocks merge to
`main`.

### 8.4 What the test is not

- Not an OOS test. It runs on surrogate data only.
- Not a benchmark. It does not measure throughput.
- Not a substitute for the hold-out red-team review.

## 9. Consolidated spec — Paper-readiness checklist (S8)

### 9.1 Purpose

Replace today's single `paper_readiness_latest.v1.json` flag with
an explicit per-candidate YES/NO checklist that an operator can
read in seconds.

### 9.2 Schema (planned)

```text
paper_readiness_checklist.v1.json
  - schema_version: "v1"
  - candidate_id: <str>
  - generated_at_utc: <iso8601>
  - checks:
      - null_model_beat:                 yes|no|n/a
      - tail_fragility_pass:             yes|no|n/a
      - entropy_regime_compatible:       yes|no|n/a
      - cost_adjusted_edge_positive:     yes|no|n/a
      - multiplicity_adjusted_dsr_pass:  yes|no|n/a
      - multi_asset_robust:              yes|no|n/a
      - multi_timeframe_robust:          yes|no|n/a
      - multi_regime_robust:             yes|no|n/a
      - single_source_dependency_clean:  yes|no|n/a
      - holdout_redteam_review_pass:     yes|no|n/a
  - overall: yes|no
  - multiplicity_n_eff: <int>
  - dsr_value: <float>
  - cost_assumptions_ref: <pointer-to-cost-model-artifact>
  - notes: <str, capped at 400 chars>
```

### 9.3 Authority

The checklist is **derived**, not canonical. The canonical
authority for "this candidate is paper-ready" remains
`paper_readiness_latest.v1.json` per ADR-014 §A; the checklist is
a richer derived view that surfaces *why*. ADR-014 is not
mutated by this spec.

### 9.4 Tests required (spec)

- Schema test.
- Derivation test (given fixture inputs → expected `overall`).
- Idempotence test.

## 10. Consolidated spec — Reason-record schemas (S9)

### 10.1 Purpose

Make routing, sampling, and scoring decisions inspectable and
auditable so that no hidden authority can grow in those surfaces.

### 10.2 Shared schema (planned)

All three reason families share one schema with a `decision_kind`
discriminator.

```text
reason_records.v1.jsonl
  - ts_utc
  - record_id                # deterministic hash
  - decision_kind            # routing | sampling | scoring
  - subject_id               # campaign_id | sampling_plan_id | candidate_id
  - inputs_digest            # hash of relevant inputs
  - decision                 # closed vocab per kind
  - reason_codes             # list of closed vocab tags
  - reason_text              # short free text, capped at 300 chars
  - schema_version: "v1"
```

### 10.3 Decision-kind closed vocabularies (planned)

- routing: `prioritize | dead_zone_suppress | defer | reject`.
- sampling: `stratify | null_baseline | exclude_region | downsample | upsample`.
- scoring: `keep | filter_tail | filter_entropy | filter_null | filter_cost | undecided`.

### 10.4 Authority

Reason records are lineage, not authority. They do not change the
routing / sampling / scoring decision itself; they record it.

### 10.5 Tests required (spec)

- Schema test.
- Append-only invariant test.
- Closed-vocab test for every `decision_kind` enum.

## 11. Update history

- 2026-05-21: initial version, written as part of the roadmap
  reset.
