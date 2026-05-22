# PACKAGE-MIGRATION-003 - Control-Plane Read-Only Adapter Boundary

Status: implemented
Date: 2026-05-22
Builds on:

- `docs/architecture/PACKAGE-MIGRATION-001-target-layout-skeleton.md`
- `docs/architecture/PACKAGE-MIGRATION-002-ade-governance-read-only-contracts.md`
- `docs/architecture/EXTRACT-001-control-plane-qre-adapter-contract.md`
- `docs/architecture/EXTRACT-002-ade-governance-import-contracts.md`
- `packages/control_plane_qre_adapter_contract/`
- `packages/ade_governance/`
- `reporting/architecture_import_scan.py`

## Purpose and Scope

PACKAGE-MIGRATION-003 migrates one bounded control-plane package-boundary
slice toward the target app layout by introducing a read-only adapter boundary
inside `apps/control-plane`.

This unit does not migrate all `dashboard/`, move all `apps/control-plane`,
move QRE runtime modules, change runtime dashboard route wiring, change frozen
contracts, add dashboard mutation routes, or activate live, paper, shadow,
risk, broker, or execution behavior.

## Selected Migration Slice

Selected slice:

```text
apps/control-plane/read_only_adapter_boundary.py
```

The module consumes the canonical adapter contract:

```text
packages.control_plane_qre_adapter_contract
```

and exposes a single non-routed boundary helper:

```text
describe_read_only_adapter_boundary()
```

## Why This Slice Was Selected

Inspection showed that existing dashboard read-only API modules still import
QRE artifact path constants directly under exact legacy/report-only scanner
allowlists. Migrating one of those runtime consumers now would require either a
new QRE facade package or dashboard route wiring changes, which is broader than
this unit.

The safer bounded slice is therefore the control-plane app boundary itself:
create one scanner-visible, non-routed consumer of the already extracted
adapter contract. This proves the target control-plane boundary can depend on
the adapter contract package without importing QRE runtime modules and without
moving dashboard routes.

## Exact Files/Modules Migrated or Introduced

- `apps/control-plane/read_only_adapter_boundary.py`
- `apps/control-plane/README.md`
- `tests/architecture/test_package_migration_001_target_layout.py`
- `tests/architecture/test_package_migration_003_control_plane_read_only_adapter_boundary.py`
- `docs/architecture/PACKAGE-MIGRATION-003-control-plane-read-only-adapter-boundary.md`

## New Canonical Namespace

No new importable Python namespace is introduced because the target app path is
the filesystem boundary `apps/control-plane/`.

The canonical adapter contract remains:

```text
packages.control_plane_qre_adapter_contract
```

## Old Compatibility Path

The existing compatibility import path remains:

```text
reporting.control_plane_qre_adapter_contract
```

It continues to re-export the canonical adapter contract objects. The new
control-plane boundary imports the canonical package directly.

## What Did Not Move

- No dashboard route module moved.
- No `dashboard/` runtime registration changed.
- No QRE research, strategy, registry, orchestration, or artifact writer moved.
- No ADE governance runtime implementation moved.
- No execution, live, paper, shadow, risk, broker, or order behavior moved.
- No frozen research output moved or regenerated.

## Runtime Behavior and Equivalence Statement

No runtime behavior changed. The new boundary module is not imported or wired by
dashboard runtime code. It exposes the same deterministic
`AdapterContractDescription` returned by the canonical
`packages.control_plane_qre_adapter_contract.describe_contract()` function.

## Frozen Contract Status

No frozen research outputs were changed. `research/research_latest.json`,
`strategy_matrix.csv`, frozen schemas, and regression pins are not modified.

No `.claude/**` files were changed.

## Dashboard Mutation Route Status

No dashboard mutation routes were added. The new boundary module contains no
Flask import, route decorator, HTTP method declaration, or dashboard route
wiring.

## Live/Paper/Shadow/Risk/Broker/Execution Status

No live, paper, shadow, risk, broker, or execution behavior was changed. The new
boundary module imports only the canonical read-only adapter contract package.

## Scanner Classification

The existing scanner classifications remain:

```text
apps/control-plane/ -> control-plane
packages/control_plane_qre_adapter_contract/ -> adapter-contract
packages/ade_governance/ -> ADE
```

The new boundary creates one visible mixed-domain edge from control-plane to
adapter-contract. It creates no control-plane-to-QRE, ADE-to-QRE, or
QRE-to-execution hard forbidden edge.

## Validation Commands

```powershell
pytest tests/architecture/test_package_migration_003_control_plane_read_only_adapter_boundary.py -q
pytest tests/architecture/test_package_migration_001_target_layout.py -q
pytest tests/architecture/test_control_plane_qre_adapter_contract.py -q
pytest tests/architecture/test_domain_boundary_smoke.py -q
pytest tests/architecture/test_domain_import_scanner.py -q
pytest tests/architecture -q
pytest tests/unit/test_ci_path_classifier.py -q
python -m reporting.architecture_import_scan --format summary
```

## Rollback Plan

Revert the PACKAGE-MIGRATION-003 commit. That removes the non-routed
`apps/control-plane/read_only_adapter_boundary.py` module and restores
`apps/control-plane` to the previous scaffold-only status without changing
dashboard runtime routes, QRE runtime modules, frozen outputs, or execution
behavior.

## Package Migration Decision

Selected value: `PACKAGE_MIGRATION_CONTINUES_WITH_BOUNDED_NEXT_UNIT`

Rationale: The control-plane boundary now has one scanner-visible read-only
adapter contract consumer while dashboard runtime migration remains deferred.
The next safest bounded package migration is the QRE diagnostics read-only
package boundary, because current dashboard observability imports are
diagnostics read-only path constants and can be evaluated as a narrow
diagnostics facade without moving execution-sensitive behavior.

Exact next recommended unit:
PACKAGE-MIGRATION-004 - Migrate QRE Diagnostics Read-Only Package Boundary.
