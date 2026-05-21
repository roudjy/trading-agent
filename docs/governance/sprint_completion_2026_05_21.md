# Research-Quality Hardening Sprint — Completion Record

> **Status:** completion record for queue item 1
> (`dwq_fd761566e6ac` — Research-Quality Hardening Sprint).
>
> **Authority:** read-only operational record. Catalogues the
> sprint's deliverables, exit-criteria evidence, and the
> follow-up implementation queue. Does not transition queue
> state; the operator may move the seed item from
> `status: ready` to `status: review_needed` / `done` in a
> separate operator-driven PR after reviewing this record.
>
> **Cross-refs:**
> [`roadmap_scope_status.md`](roadmap_scope_status.md),
> [`research_quality_sprint_plan.md`](research_quality_sprint_plan.md),
> [`queue_rebuild_2026_05_21.md`](queue_rebuild_2026_05_21.md),
> [`docs/development_work_queue/seed.jsonl`](../development_work_queue/seed.jsonl).

## 1. Scope of this sprint

Per [`research_quality_sprint_plan.md`](research_quality_sprint_plan.md)
§2, the sprint had nine items (S1–S9). The user's "expected
scope" in the active-queue task added two more concrete docs
(cost-adjusted promotion criteria, candidate-quality dashboard).
This record covers all eleven.

| ID | Item | Delivered by | Path |
|---|---|---|---|
| S1 | ADR-018 — Roadmap Execution Reset | PR #264 (`ae0a459`) | [`docs/adr/_drafts/ADR-018-roadmap-execution-reset.md`](../adr/_drafts/ADR-018-roadmap-execution-reset.md) |
| S2 | ADR-019 — Hypothesis Discovery doctrine and scoring spec | PR #264 (`ae0a459`) | [`docs/adr/_drafts/ADR-019-hypothesis-discovery-doctrine.md`](../adr/_drafts/ADR-019-hypothesis-discovery-doctrine.md) |
| S3 | ADR-020 — Paper/Shadow/Live separation doctrine | PR #264 (`ae0a459`) | [`docs/adr/_drafts/ADR-020-paper-shadow-live-separation.md`](../adr/_drafts/ADR-020-paper-shadow-live-separation.md) |
| S4 | Global multiplicity ledger spec | this PR | [`multiplicity_ledger.md`](multiplicity_ledger.md) + [`multiplicity_ledger/schema.v1.md`](multiplicity_ledger/schema.v1.md) |
| S5 | Sequestered hold-out discipline spec | this PR | [`holdout_discipline.md`](holdout_discipline.md) |
| S6 | Null-pipeline integration test spec | this PR | [`null_pipeline_test.md`](null_pipeline_test.md) |
| S7 | Research-quality KPI definitions | PR #264 (`ae0a459`) | [`research_quality_kpis.md`](research_quality_kpis.md) |
| S8 | Paper-readiness checklist artifact spec | this PR | [`paper_readiness_checklist.md`](paper_readiness_checklist.md) + [`paper_readiness_checklist/schema.v1.md`](paper_readiness_checklist/schema.v1.md) |
| S9 | Routing / sampling / scoring reason-record doctrine | this PR | [`reason_records.md`](reason_records.md) + [`reason_records/schema.v1.md`](reason_records/schema.v1.md) |
| Sprint-extra A | Cost-adjusted promotion criteria | this PR | [`cost_adjusted_promotion.md`](cost_adjusted_promotion.md) |
| Sprint-extra B | Candidate-quality dashboard spec | this PR | [`candidate_quality_dashboard.md`](candidate_quality_dashboard.md) |

## 2. Sprint exit criteria (per sprint plan §3)

| # | Criterion | Status |
|---|---|---|
| 1 | ADR-018, ADR-019, ADR-020 exist as drafts under `docs/adr/_drafts/` | **met** (PR #264) |
| 2 | [`roadmap_scope_status.md`](roadmap_scope_status.md) is consistent with the reset and is the canonical active-vs-deferred index | **met** (PR #264 + PR #266) |
| 3 | The sprint plan and the KPI doc exist and cross-reference each other | **met** (PR #264) |
| 4 | Addendum 1/2/3 headers carry the `Execution Status: DEFERRED` block | **met** (PR #264) |
| 5 | The active execution queue carries only items from the active scope per [`roadmap_scope_status.md`](roadmap_scope_status.md) §3 | **met** (PR #266) |
| 6 | No frozen contract was mutated; no protected path was touched | **met** (verified per PR diff-stat review on `ae0a459` and `84f6fdaa`; this PR maintains the property) |

All six sprint exit criteria are satisfied.

## 3. Doctrine introduced (binding)

The sprint's docs introduce these binding rules across the
research surface. Each rule has at least one named test pin in
its respective spec.

| Doctrine | Spec | Test pin |
|---|---|---|
| Multiplicity ledger is append-only, idempotent, deterministic, no execution-side feed | [`multiplicity_ledger.md`](multiplicity_ledger.md) §4 | ML-I1 through ML-I10 |
| Hold-out windows are operator-authored, hook-deny-enforced, single-use per (candidate, window) | [`holdout_discipline.md`](holdout_discipline.md) §4-§6 | HD-I1 through HD-I6 |
| Null-pipeline integration test asserts zero candidates pass on surrogate data | [`null_pipeline_test.md`](null_pipeline_test.md) §5 | NP-A1 through NP-A7 |
| Paper-readiness checklist is derived, not canonical | [`paper_readiness_checklist.md`](paper_readiness_checklist.md) §2 + §8 | PR-I1 through PR-I7 |
| Reason records are append-only, decision-coverage-tested, no execution-side feed | [`reason_records.md`](reason_records.md) §7 | RR-I1 through RR-I10 |
| Cost-adjusted edge gate is deterministic, fail-closed on missing inputs, no execution-side feed | [`cost_adjusted_promotion.md`](cost_adjusted_promotion.md) §8 | CP-I1 through CP-I8 |
| Candidate-quality dashboard is read-only, does not modify `dashboard/dashboard.py`, no execution-side feed | [`candidate_quality_dashboard.md`](candidate_quality_dashboard.md) §7 | CQD-I1 through CQD-I8 |

## 4. Follow-up implementation queue (out of scope for this sprint)

Each spec lists "out of scope (for the spec)" with its
implementation follow-up. The follow-ups land as scoped
implementation PRs **after** this sprint merges and **before**
queue item 2 (Minimal v3.15.16 Intelligent Routing slice)
begins.

Recommended order (smallest blast radius first):

1. **Multiplicity ledger writer** + reader + invariant tests
   (per [`multiplicity_ledger.md`](multiplicity_ledger.md) §8 +
   §10). Lands `reporting/multiplicity_ledger.py` +
   `tests/unit/test_multiplicity_ledger.py`.
2. **Reason-records writers** (one per family) + fused reader
   (per [`reason_records.md`](reason_records.md) §9). Lands
   `reporting/reason_records.py` + tests.
3. **Hold-out hook + manifest** (per
   [`holdout_discipline.md`](holdout_discipline.md) §5). Lands
   `.claude/hooks/deny_holdout_read.py` (operator-authored
   governance-bootstrap PR; the no-touch-hook globs cover hooks
   so the operator opens the bootstrap) +
   `state/holdout_manifest.v1.json` (operator-authored).
4. **Paper-readiness checklist writer** (per
   [`paper_readiness_checklist.md`](paper_readiness_checklist.md)
   §6). Lands `reporting/paper_readiness_checklist.py` +
   tests.
5. **Null-pipeline integration test** (per
   [`null_pipeline_test.md`](null_pipeline_test.md) §2). Lands
   `tests/integration/test_null_pipeline.py`. Adding it to the
   required-checks list is a separate operator-driven CI-
   hardening PR by `ci-guardian`.
6. **Cost-model artifact + gate** (per
   [`cost_adjusted_promotion.md`](cost_adjusted_promotion.md)
   §5). Lands `state/cost_model.v1.json` (operator-authored)
   plus a small reader module.
7. **Candidate-quality dashboard endpoints** (per
   [`candidate_quality_dashboard.md`](candidate_quality_dashboard.md)
   §4 + §10). Lands `dashboard/api_research_quality.py`
   (read-only; the wiring in `dashboard/dashboard.py` is a
   separate operator-driven bootstrap).

Each follow-up is its own scoped PR with its own test plan
already specified in the corresponding spec. None requires a
governance change beyond those already declared by ADR-018 / 019
/ 020 drafts.

## 5. Queue state after this PR

The active queue
([`docs/development_work_queue/seed.jsonl`](../development_work_queue/seed.jsonl))
is unchanged by this PR — the operator transitions the sprint
item from `ready` → `done` (and item 2 from `blocked` →
`ready`) in a small follow-up PR after reviewing this completion
record. That separation preserves the operator's authority over
queue state transitions and avoids re-pinning the seed test in
this PR.

| Pos | Item ID | Title | Current status | Recommended status after this PR merges |
|---|---|---|---|---|
| 1 | `dwq_fd761566e6ac` | Research-Quality Hardening Sprint | `ready` | `review_needed` → operator-driven → `done` |
| 2 | `dwq_b2d3fd99ed4d` | Minimal v3.15.16 Intelligent Routing slice | `blocked` (by 1) | `ready` after the implementation follow-ups in §4 land |
| 3 | `dwq_6f473157910e` | Minimal v3.15.17 Sampling Intelligence slice | `blocked` | unchanged |
| 4 | `dwq_41f06488d897` | Minimal v3.15.18 Observability slice | `blocked` | unchanged |
| 5 | `dwq_a56275670169` | Minimal v3.15.19 Hypothesis Discovery slice | `blocked` | unchanged |
| 6 | `dwq_1b8568898b42` | STOP — operator review gate | `blocked`, `human_needed` | unchanged |

The transition table is **recommendation only**; the operator
performs the seed update.

## 6. Discipline preserved by this PR

This PR ships docs/specs only. The PR:

- Does not modify code under `reporting/`, `research/`,
  `agent/`, `automation/`, `broker/`, `dashboard/dashboard.py`,
  `live/`, `paper/`, `shadow/`, `trading/`, `execution/`,
  `orchestration/`, `strategies/`.
- Does not modify `.claude/**` (hooks, agent defs, settings).
- Does not modify `.github/**` (workflows, CODEOWNERS).
- Does not modify existing ADRs.
- Does not modify writer-restricted governance core docs
  (`agent_governance.md`, `autonomy_ladder.md`,
  `no_touch_paths.md`, `permission_model.md`,
  `no_test_weakening.md`, `hooks_runtime_policy.md`,
  `provenance.md`, `audit_chain.md`, `release_gate.md`,
  `release_gate_checklist.md`, `rollback_drill.md`,
  `sha_pin_review.md`).
- Does not mutate frozen contracts (`research_latest.json`,
  `strategy_matrix.csv`) or any `*_latest.v1.json` /
  `*_latest.v1.jsonl` artifact.
- Does not modify the canonical Roadmap v6 doc or any addendum
  (Addendum 1/2/3 stay deferred reference-only per PR #264).
- Does not touch `tests/regression/**`.
- Does not modify any pinned test in `tests/unit/`.
- Does not modify the active queue's `seed.jsonl` (preserves
  the strengthened pin from PR #266).
- Does not introduce code; pure governance documentation only.

## 7. Update history

- 2026-05-21: initial version (sprint completion record).
