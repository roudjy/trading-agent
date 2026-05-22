# PACKAGE-MIGRATION-009 - Execution-Sim Future-Only Package Guards

## Purpose and Scope

This unit validates and pins the future-only guardrails for
`packages/qre_execution_sim` before package-migration closure can be evaluated.

The scope is intentionally limited to README guard text, architecture tests, and
path-aware CI classification. It does not move execution code, introduce a
runtime API, add package modules, add dashboard routes, or activate any
live/paper/shadow/risk/broker behavior.

## Selected Migration Slice

Selected slice: future-only guard validation for `packages/qre_execution_sim`
and conservative path-aware CI classification for future execution-sensitive
package prefixes.

## Why This Slice Was Selected

PACKAGE-MIGRATION-008 created the first bounded QRE research package boundary
and recommended validating `packages/qre_execution_sim` before the migration
lane can close. The target architecture includes `packages/qre_execution_sim`,
but that package must remain inactive until a separate approved unit authorizes
a specific deterministic research simulation contract.

Guarding the package now prevents future package files under execution-sensitive
prefixes from being treated as ordinary package-only changes.

## Exact Files/Modules Migrated or Introduced

- `packages/qre_execution_sim/README.md`
- `scripts/ci_path_classifier.py`
- `tests/unit/test_ci_path_classifier.py`
- `tests/architecture/test_package_migration_009_execution_sim_future_only_guards.py`
- `docs/architecture/PACKAGE-MIGRATION-009-execution-sim-future-only-guards.md`

## New Canonical Namespace

None. No importable execution-simulation namespace was introduced.

## Old Compatibility Path

None. No existing module moved, so no compatibility shim was needed.

## What Did Not Move

- `execution/`
- `agent/execution/`
- `agent/risk/`
- `automation/live_gate`
- `broker/`
- `live/`
- `paper/`
- `shadow/`
- `risk/`
- `research/`
- `dashboard/`
- `.claude/**`

## Runtime Behavior Equivalence

No runtime behavior was changed. PM009 is guard-only: it strengthens README
constraints, verifies scanner classification, and makes path-aware CI classify
future execution package prefixes as execution-sensitive.

## Frozen Contract Statement

No frozen research outputs were changed.

No `.claude/**` files were changed.

## Frozen Schema and Regression Pin Statement

No frozen schemas or regression pins were changed.

## Dashboard Mutation Route Statement

No dashboard mutation routes were added.

No dashboard runtime route wiring was changed.

## Live/Paper/Shadow/Risk/Broker/Execution Statement

No live, paper, shadow, risk, broker, or execution behavior was changed.

## Validation Commands

- `python -m pytest tests/architecture/test_package_migration_009_execution_sim_future_only_guards.py -q`
- `python -m pytest tests/architecture/test_package_migration_001_target_layout.py -q`
- `python -m pytest tests/unit/test_ci_path_classifier.py -q`
- `python -m pytest tests/architecture/test_domain_boundary_smoke.py -q`
- `python -m pytest tests/architecture/test_domain_import_scanner.py -q`
- `python -m pytest tests/architecture -q`
- `python -m reporting.architecture_import_scan --format summary`

## Rollback Plan

Revert this migration commit. That restores the previous
`packages/qre_execution_sim` README text, removes PM009 architecture coverage
and documentation, and restores the previous CI path classifier behavior.

## Package Migration Decision

Selected value:
`PACKAGE_MIGRATION_CONTINUES_WITH_BOUNDED_NEXT_UNIT`

Rationale:
The execution-sim package guard is now pinned, and the remaining package
migration work should be a closure decision rather than another package move.
The next unit is bounded because it should inspect the completed package
skeleton and read-only boundaries, validate terminal readiness, and choose
whether the package-migration lane can return to QRE Feature Build Track.

Exact next recommended unit:
`PACKAGE-MIGRATION-010 - Package Migration Closure Decision`

This is necessary before returning to QRE Feature Build Track because the lane
needs a documented terminal decision after the target package skeleton and
bounded read-only boundaries have been established.
