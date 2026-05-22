# PACKAGE-MIGRATION-008 - QRE Research Read-Only Package Boundary

## Purpose and Scope

This unit migrates one bounded QRE research contract into the target package
layout by making the research universe boundary canonical under
`packages.qre_research`.

The scope is intentionally limited to the existing universe module. It does not
move research orchestration, strategy registration, strategy implementations,
research artifact writing, diagnostics, policy, or execution behavior.

## Selected Migration Slice

Selected slice: `research.universe` as the read-only QRE research universe
contract.

## Why This Slice Was Selected

The universe module is a bounded research contract surface already separated
from strategy implementation and orchestration. It resolves configured and
preset-driven asset universes and returns deterministic snapshot objects. It
does not fetch data, write artifacts, add dashboard routes, place orders, or
change authority semantics.

This makes it the smallest viable QRE research package boundary after the QRE
policy and QRE data read-only boundaries.

## Exact Files/Modules Migrated or Introduced

- `packages/qre_research/__init__.py`
- `packages/qre_research/universe.py`
- `research/universe.py`
- `packages/qre_research/README.md`
- `tests/architecture/test_package_migration_001_target_layout.py`
- `tests/architecture/test_package_migration_008_qre_research_read_only_boundary.py`
- `docs/architecture/PACKAGE-MIGRATION-008-qre-research-read-only-boundary.md`

## New Canonical Namespace

`packages.qre_research.universe`

## Old Compatibility Path

`research.universe`

The old path remains available as a compatibility shim that imports the
canonical implementation. Existing callers keep their import path and public
objects are identity-preserved for the migrated contract names.

## What Did Not Move

- `research/run_research.py`
- `research/presets.py`
- `research/registry.py`
- `registry.py`
- `agent/backtesting/strategies.py`
- `strategies/`
- `data/` other than previously completed PACKAGE-MIGRATION-007 work
- `dashboard/`
- `reporting/`
- `execution/`
- `live/`
- `paper/`
- `shadow/`
- `risk/`
- `broker/`
- `.claude/**`

## Runtime Behavior Equivalence

No runtime behavior was intentionally changed. The implementation was moved to
`packages.qre_research.universe`, and `research.universe` remains as a
compatibility import path.

Existing unit tests for universe resolution and preset-driven universe
selection pass through the compatibility path, and the PM008 architecture test
pins canonical and compatibility object identity for the public universe
contract names.

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

- `python -m pytest tests/architecture/test_package_migration_008_qre_research_read_only_boundary.py -q`
- `python -m pytest tests/architecture/test_package_migration_001_target_layout.py -q`
- `python -m pytest tests/unit/test_universe.py tests/unit/test_run_research_preset_universe_v3_14_1.py -q`
- `python -m pytest tests/architecture/test_domain_boundary_smoke.py -q`
- `python -m pytest tests/architecture/test_domain_import_scanner.py -q`
- `python -m pytest tests/unit/test_ci_path_classifier.py -q`
- `python -m pytest tests/architecture -q`
- `python -m reporting.architecture_import_scan --format summary`

## Rollback Plan

Revert this migration commit. That restores `research.universe` as the
implementation path, removes `packages.qre_research.universe`, removes the
PM008 architecture tests and document, and returns `packages/qre_research` to
its previous scaffold-only status.

## Package Migration Decision

Selected value:
`PACKAGE_MIGRATION_CONTINUES_WITH_BOUNDED_NEXT_UNIT`

Rationale:
The QRE research package now has a bounded read-only universe boundary, but the
future-only execution-sim package still needs an explicit guard validation
before the package-migration lane can close or return to QRE Feature Build
Track. The next unit is bounded because it should validate package guards and
documentation for an inactive future-only package, not migrate execution
behavior.

Exact next recommended unit:
`PACKAGE-MIGRATION-009 - Validate Execution-Sim Future-Only Package Guards`

This is necessary before returning to QRE Feature Build Track because the target
architecture includes `packages/qre_execution_sim`, and its inactive/future-only
status must be pinned before package migration closure can be evaluated.
