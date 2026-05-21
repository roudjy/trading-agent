# Queue Reactivation - 2026-05-21

> **Status:** operational record for the operator-authorized
> reactivation after the v3.15.19 STOP gate.
>
> **Authority:** ADR-021 and `roadmap_scope_status.md`.

## Decision

The operator authorized reactivating only the next minimal Roadmap v6
core path:

1. Minimal v3.15.20 Failure to Action Mapping.
2. Minimal v3.16.x Adaptive Research Learning.

This record does not reactivate Addendum 1, Addendum 2, Addendum 3,
v4.x, v5.x, or v6.x.

## Queue State

The canonical seed at
[`docs/development_work_queue/seed.jsonl`](../development_work_queue/seed.jsonl)
now records:

| Item | Status |
|---|---|
| Research-Quality Hardening Sprint | done |
| Minimal v3.15.16 Intelligent Routing slice | done |
| Minimal v3.15.17 Sampling Intelligence slice | done |
| Minimal v3.15.18 Research Observability Expansion slice | done |
| Minimal v3.15.19 Hypothesis Discovery Engine slice | done |
| STOP - operator review gate after minimal v3.15.19 | done |
| Minimal v3.15.20 Failure to Action Mapping slice | ready |
| Minimal v3.16.x Adaptive Research Learning path | blocked by v3.15.20 |

Only v3.15.20 is ready for the next implementation PR.

## Preserved Boundaries

- Addendum 1/2/3 implementation sections remain deferred/reference-only.
- v4/v5/v6 remain deferred/reference-only.
- No shadow, paper, or live execution scope is active.
- Protected runtime paths remain out of scope.
- Frozen contracts remain unchanged:
  `research_latest.json` and `strategy_matrix.csv`.
