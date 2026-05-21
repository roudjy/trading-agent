# ADR-018 — Roadmap Execution Reset (Addendum 1/2/3 → Deferred)

Status: **Draft** — 2026-05-21
Predecessor: ADR-014 (truth authority settlement),
ADR-015 (Claude agent governance),
ADR-017 (Step 5 autonomous implementation loop; remains permanently
disabled at Level 6).
Reset reference: [`docs/governance/roadmap_scope_status.md`](../../governance/roadmap_scope_status.md).

## Context

Roadmap v6 + Addendum 1 + Addendum 2 + Addendum 3 collectively plan
~25 new sub-layers and dozens of new sidecar artifacts:

- Addendum 1 introduces 14 mechanistic diagnostic families and an
  external-intelligence intake.
- Addendum 2 introduces state / sequential / knowledge / retrieval
  intelligence (Markov, HMM, Semi-Markov, FSM, queueing, ontology,
  entity resolution, knowledge graph, hybrid retrieval, RRF,
  cross-encoder reranker, Bayesian networks, ToT-bounded).
- Addendum 3 introduces source identity, ~10 source adapters, a
  Source Candidate Registry, a Source Usefulness Ledger, a Local
  Data Cache & Throughput Layer (Parquet / DuckDB / Polars), and a
  Source Manifest & Quality Gate Layer.

Each addendum is internally consistent. Each addendum's doctrine
(`Diagnostics do not trade`, `Retrieval is context, not authority`,
`Knowledge graphs are lineage, not truth`, `Source adapters do not
trade`, `External data is not alpha`) is sound and correctly
gates the negative space.

The risk surfaced by a second-pass review is **soft-layer drift**:
the architecture commits to large breadth before producing a single
robust paper-ready candidate under the new doctrine. Specifically:

- No global multiplicity ledger exists to count the multiplied tests
  the addendums create.
- No sequestered hold-out window exists to give final OOS
  validation untouched data.
- No null-pipeline integration test exists to guarantee the stack
  rejects pure noise.
- No Hypothesis Discovery ADR exists; v3.15.19's
  `opportunity_probability_score` is illustrated in JSON, not
  axiomatised.
- No paper-readiness checklist artifact exists beyond a single
  status flag.
- No operator attention budget exists; ~30 planned sidecars will
  saturate operator review.
- No diagnostic utility ledger exists; diagnostics are added but
  never retired.

Without those primitives, more architecture cannot prove research
quality. The risk is finishing v3.15.x with an elaborate stack and
zero better candidates.

## Decision

Reclassify the implementation sections of Roadmap v6 Addendum 1,
Addendum 2, and Addendum 3 from **active execution scope** to
**deferred reference doctrine**.

The doctrine (positive layer separation and negative §10
"Not Allowed" lists) remains binding project-wide.

Adopt the minimal Roadmap v6 execution order declared in
[`docs/governance/roadmap_scope_status.md`](../../governance/roadmap_scope_status.md)
§3:

1. Research-Quality Hardening Sprint (docs/specs/ADRs only).
2. Minimal v3.15.16 Intelligent Routing slice.
3. Minimal v3.15.17 Sampling Intelligence slice.
4. Minimal v3.15.18 Observability slice.
5. Foundational implementations (multiplicity ledger, hold-out
   hook, null-pipeline test, reason-record writers, paper-readiness
   checklist writer).
6. Minimal v3.15.19 Hypothesis Discovery slice (only after ADR-019
   is accepted).
7. Staged diagnostic rollout under promote-or-retire.
8. First paper-readiness assessment.
9. Reactivation review of Addendums 1/2/3 — only on KPI evidence.

## Hard constraints preserved

This reset:

- does **not** modify ADR-014 (truth-authority settlement).
- does **not** modify ADR-015 (agent governance / autonomy ladder).
  Level 6 remains permanently disabled.
- does **not** modify ADR-017 (Step 5 design + readiness).
- does **not** modify [`docs/governance/no_touch_paths.md`](../../governance/no_touch_paths.md).
- does **not** modify [`docs/governance/execution_authority.md`](../../governance/execution_authority.md).
- does **not** modify [`docs/governance/autonomy_ladder.md`](../../governance/autonomy_ladder.md).
- does **not** delete any roadmap document or addendum content.
- does **not** modify the existing canonical roadmap
  [`docs/roadmap/Roadmap v6.md`](../../roadmap/Roadmap%20v6.md) body
  (the reset is captured by [`docs/governance/roadmap_scope_status.md`](../../governance/roadmap_scope_status.md);
  only the addendum files carry new `Execution Status` headers).
- does **not** modify the code-level catalog or unit-decomposition
  modules ([`reporting/roadmap_task_catalog.py`](../../../reporting/roadmap_task_catalog.py),
  [`reporting/roadmap_task_units.py`](../../../reporting/roadmap_task_units.py),
  [`reporting/roadmap_unit_authority.py`](../../../reporting/roadmap_unit_authority.py))
  or any of their pinned tests. Removing the `addendum_1`,
  `addendum_2`, `addendum_3` phases from the code-level mandate is
  a separate, operator-approved follow-up PR after this reset
  merges.
- does **not** modify frozen contracts (`research/research_latest.json`,
  `research/strategy_matrix.csv`).

## Reactivation gates

An addendum (or deferred sub-section) may leave **DEFERRED** status
only when **all** of the following hold:

- ≥1 paper-ready candidate has cleared the paper-readiness
  checklist (`overall=yes`).
- The multiplicity ledger shows multiplicity-adjusted survivor
  signal greater than the null-model baseline.
- The diagnostic utility ledger shows the three active diagnostics
  (null-model, tail, entropy) each changed ≥1 survivor's status at
  least once.
- Operator attention budget (KPI OAB,
  [`research_quality_kpis.md`](../../governance/research_quality_kpis.md)
  §3) is not exhausted.
- An operator-approved reactivation ADR explicitly identifies
  *which subsection* of which addendum is being activated, with
  promote-or-retire criteria and an explicit definition of done.

## Consequences

Positive:

- Operator attention is preserved.
- Multiplicity is counted; Deflated Sharpe becomes meaningful.
- Hold-out is sequestered; final OOS is honest.
- Null-pipeline test catches stack-level regressions.
- Diagnostic count stays small; promote-or-retire keeps it small.

Negative / accepted:

- Some addendum work that *would* have improved candidate quality
  is delayed.
- Some operator effort goes into specs and ADRs before runtime
  value lands.
- Catalog code-level pins (`_MANDATE_PHASES`, catalog seeds)
  temporarily carry references to deferred phases; a follow-up
  scoped PR retires those after CODEOWNERS review.

## Tests / verification

This ADR ships in a docs-only PR. The PR verifies:

- governance-lint OK;
- tests/smoke OK;
- the canonical pinned tests for catalog, unit decomposition, and
  unit authority remain green (this PR does not touch those code
  paths);
- no protected path was touched;
- no frozen contract was touched;
- [`roadmap_scope_status.md`](../../governance/roadmap_scope_status.md)
  is self-consistent with this ADR.

## Promotion

This ADR is in `_drafts/`. Promotion to
`docs/adr/ADR-018-roadmap-execution-reset.md` is a separate
operator-driven governance-bootstrap PR after this reset merges
(consistent with how ADR-017 was promoted from `_drafts/` per
[`docs/governance/step5_design.md`](../../governance/step5_design.md)
G8).

## Cross-references

- [`docs/governance/roadmap_scope_status.md`](../../governance/roadmap_scope_status.md)
- [`docs/governance/research_quality_sprint_plan.md`](../../governance/research_quality_sprint_plan.md)
- [`docs/governance/research_quality_kpis.md`](../../governance/research_quality_kpis.md)
- [`docs/adr/ADR-019-hypothesis-discovery-doctrine.md`](../ADR-019-hypothesis-discovery-doctrine.md)
- [`docs/adr/_drafts/ADR-020-paper-shadow-live-separation.md`](ADR-020-paper-shadow-live-separation.md)
- [`docs/adr/ADR-014-truth-authority-settlement.md`](../ADR-014-truth-authority-settlement.md)
- [`docs/adr/ADR-015-claude-agent-governance.md`](../ADR-015-claude-agent-governance.md)
- [`docs/adr/ADR-017-step5-autonomous-implementation-loop.md`](../ADR-017-step5-autonomous-implementation-loop.md)
