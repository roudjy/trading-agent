# Active Queue Rebuild — 2026-05-21

> **Status:** operational record of the queue rebuild that landed
> alongside the roadmap reset (ADR-018 draft).
>
> **Authority:** read-only record. Declares the active queue at the
> reset point, what was rebuilt, what was deferred, and what is
> blocked-by-what. Cross-references the canonical seed file.
>
> **Cross-refs:**
> [`roadmap_scope_status.md`](roadmap_scope_status.md) (canonical
> active vs deferred index — §3 declares the 6-item queue),
> [`research_quality_sprint_plan.md`](research_quality_sprint_plan.md)
> (next active item),
> [`research_quality_kpis.md`](research_quality_kpis.md)
> (release-gate KPIs),
> [`development_work_queue.md`](development_work_queue.md)
> (the A8 queue module owning the seed schema),
> [`docs/adr/_drafts/ADR-018-roadmap-execution-reset.md`](../adr/_drafts/ADR-018-roadmap-execution-reset.md)
> (formal reset ADR).

## 1. Why this document exists

PR #264 (merge SHA `ae0a459`) reclassified Addendum 1/2/3 to
**DEFERRED — reference-only** at the doctrinal layer. The active
queue itself, however, was not yet visibly rebuilt — the canonical
operator-authored seed
([`docs/development_work_queue/seed.jsonl`](../development_work_queue/seed.jsonl))
remained empty by default and the deferral was only expressed in
docs.

This follow-up actively rebuilds the queue:

- the six explicit active items are now in `seed.jsonl`;
- they form a sequential `blocked_by` chain;
- the chain ends at a hard STOP / operator review gate;
- no Addendum 1/2/3 item appears as ready/active/in-progress;
- no v3.15.20 Failure→Action item, no v3.16.x adaptive item, no
  v4/v5/v6 shadow/paper/live item appears as active.

## 2. Active queue (six items)

The items are operator-declared via `seed.jsonl`. Item IDs are
deterministic: `dwq_` + first 12 hex chars of
`sha256(title + 0x1F + source_section_or_anchor)`.

| Pos | Item ID | Title | Status | Risk | Blocked by | Owner |
|---|---|---|---|---|---|---|
| 1 | `dwq_fd761566e6ac` | Research-Quality Hardening Sprint | ready | LOW | — | planner |
| 2 | `dwq_b2d3fd99ed4d` | Minimal v3.15.16 Intelligent Routing slice | blocked | MEDIUM | item 1 | implementation_agent |
| 3 | `dwq_6f473157910e` | Minimal v3.15.17 Sampling Intelligence slice | blocked | MEDIUM | item 2 | implementation_agent |
| 4 | `dwq_41f06488d897` | Minimal v3.15.18 Research Observability Expansion slice | blocked | MEDIUM | item 3 | implementation_agent |
| 5 | `dwq_a56275670169` | Minimal v3.15.19 Hypothesis Discovery Engine slice | blocked | MEDIUM | item 4 | implementation_agent |
| 6 | `dwq_1b8568898b42` | STOP — operator review gate after minimal v3.15.19 | blocked (`human_needed=true`, `architecture_crossroads`) | LOW | item 5 | human_operator |

Counts derived by `python -m reporting.development_work_queue
--no-write`:

```text
counts.total                       = 6
counts.by_status.ready             = 1
counts.by_status.blocked           = 5
counts.by_category.governance      = 2  (items 1, 6)
counts.by_category.reporting       = 3  (items 2, 3, 5)
counts.by_category.observability   = 1  (item 4)
counts.by_role.planner             = 1  (item 1)
counts.by_role.implementation_agent= 4  (items 2-5)
counts.by_role.human_operator      = 1  (item 6)
counts.protected_surface           = 0  (none touch protected paths)
counts.ready_for_autonomous_action = 0  (operator-gated)
validation_warnings                = []
note                               = "explicit_seed_items_present"
```

The pinned test
[`tests/unit/test_development_work_queue.py::test_default_seed_file_in_repo_carries_minimal_v3_15_x_active_queue`](../../tests/unit/test_development_work_queue.py)
asserts these invariants on `main`.

## 3. What was actively rebuilt

| Surface | Before | After |
|---|---|---|
| `docs/development_work_queue/seed.jsonl` | empty (0 bytes) | 6 operator-declared items, sequential chain, STOP gate at the end |
| `tests/unit/test_development_work_queue.py::test_default_seed_file_in_repo_yields_zero_items_by_default` | asserted the seed must be empty | renamed and strengthened to assert the 6-item active queue exists with the correct shape |
| [`roadmap_scope_status.md`](roadmap_scope_status.md) §3 | nine-item narrative path | explicit 6-item active queue with STOP gate; cross-reference to the seed file and the pinned test |
| [`roadmap_scope_status.md`](roadmap_scope_status.md) §9 (update history) | one entry (2026-05-21 reset) | two entries (reset + queue rebuild) |
| This document | did not exist | operational record of the rebuild |

## 4. What was deferred (cross-reference, unchanged from PR #264)

- All Addendum 1 / 2 / 3 implementation sections — DEFERRED,
  reference-only. Doctrine and §10 "Not Allowed" lists remain
  binding project-wide.
- Roadmap v6 base phases v3.15.20, v3.16.x, v4.x, v5.x, v6.x —
  DEFERRED. Sketched only in `Roadmap v6.md`; not active queue
  scope.
- All diagnostics other than null-model / tail / entropy.
- All retrieval / knowledge graph / state / source-adapter
  expansion / throughput-stack expansion.
- All adaptive learning loops, portfolio intelligence, paper /
  shadow / live promotion automation, hybrid retrieval, RRF,
  HMM / Semi-Markov, Bayesian networks, ToT-bounded,
  Dask / Ray / Dagster / Prefect, new source adapter expansion.
- Step 5 broad implementation. ADR-017 unchanged. Autonomy
  ladder Level 6 permanently disabled per ADR-015.

## 5. What this rebuild does NOT do

- Does not modify
  [`reporting/roadmap_task_catalog.py`](../../reporting/roadmap_task_catalog.py),
  [`reporting/roadmap_task_units.py`](../../reporting/roadmap_task_units.py),
  or [`reporting/roadmap_unit_authority.py`](../../reporting/roadmap_unit_authority.py).
  These code-level catalogs still carry the `addendum_1` /
  `addendum_2` / `addendum_3` phases. Removing those phases is a
  separate operator-approved follow-up PR with CODEOWNERS review.
- Does not promote any ADR draft. ADR-018, ADR-019, ADR-020
  remain under `docs/adr/_drafts/` until separate
  operator-driven governance-bootstrap PRs promote them.
- Does not modify any protected runtime path:
  - no `.claude/**`;
  - no `.github/**`;
  - no `research/**`;
  - no `automation/**`, `broker/**`, `agent/risk/**`,
    `agent/execution/**`, `live/**`, `paper/**`, `shadow/**`,
    `trading/**`, `execution/**`;
  - no `dashboard/dashboard.py`.
- Does not mutate frozen contracts (`research_latest.json`,
  `strategy_matrix.csv`).
- Does not touch writer-restricted governance core docs
  (`agent_governance.md`, `autonomy_ladder.md`,
  `no_touch_paths.md`, `execution_authority.md`,
  `permission_model.md`, `no_test_weakening.md`,
  `hooks_runtime_policy.md`, `provenance.md`, `audit_chain.md`,
  `release_gate.md`, `release_gate_checklist.md`,
  `rollback_drill.md`, `sha_pin_review.md`).
- Does not introduce hidden ML, stochastic routing, adaptive
  loops, or any execution-side coupling.

## 6. Sequencing intent

The chain is deliberately tight:

```text
sprint -> v3.15.16 -> v3.15.17 -> v3.15.18 -> v3.15.19 -> STOP
```

Only one item is `ready` at any time. As each item completes (via
its own scoped PR), the next item in the chain becomes ready. The
operator can drop or simplify items at any point; reactivation of
deferred work requires a separate ADR.

## 7. How the autonomous runner interprets this queue

The autonomous PR runner (`reporting/autonomous_pr_runner.py`)
reads from the code-level catalog
(`reporting/roadmap_task_catalog.py` + `roadmap_task_units.py`),
not from this seed file. The seed file is an operator-facing
governance surface consumed by `reporting/task_board.py` and
similar projections.

At the governance layer:

- The active items 1, 6 are `roadmap_track: sidecar_seed`; they
  have no corresponding catalog unit. The autonomous runner does
  not act on them automatically — they are operator-driven by
  design.
- The active items 2-5 reference `docs/roadmap/Roadmap v6.md` as
  their canonical source. Each must land via a scoped PR whose
  expected files / forbidden files / required tests / stop
  conditions / definition of done are declared at PR-open time
  per [`roadmap_item_execution_protocol.md`](roadmap_item_execution_protocol.md).
- The STOP gate (item 6) is `human_needed: true`. No automated
  surface may advance past it.

## 8. Reactivation gates (cross-reference)

To leave **DEFERRED** status, an addendum subsection (or any
deferred base-phase subsection) must satisfy **all** the gates
in [`roadmap_scope_status.md`](roadmap_scope_status.md) §4:

- ≥1 paper-ready candidate has cleared the paper-readiness
  checklist (`overall=yes`).
- Multiplicity ledger shows multiplicity-adjusted survivor
  signal greater than the null-model baseline.
- Diagnostic utility ledger shows the three active diagnostics
  each changed ≥1 survivor's status at least once.
- Operator attention budget (KPI OAB,
  [`research_quality_kpis.md`](research_quality_kpis.md) §3) is
  not exhausted.
- An operator-approved reactivation ADR explicitly identifies
  the subsection, the promote-or-retire criterion, and the
  definition of done.

## 9. Update history

- 2026-05-21: initial version. Queue actively rebuilt; six items
  seeded into `docs/development_work_queue/seed.jsonl`; pinned
  test strengthened.
