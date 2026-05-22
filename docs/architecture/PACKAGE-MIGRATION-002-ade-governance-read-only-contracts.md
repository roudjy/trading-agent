# PACKAGE-MIGRATION-002 - ADE Governance Read-Only Contracts

Status: implemented
Date: 2026-05-22
Builds on:

- `docs/architecture/PACKAGE-MIGRATION-001-target-layout-skeleton.md`
- `docs/architecture/EXTRACT-002-ade-governance-import-contracts.md`
- `reporting/architecture_import_scan.py`

## Purpose and Scope

PACKAGE-MIGRATION-002 migrates the already-extracted ADE governance read-only
architecture import contracts into the narrower package layout established by
PACKAGE-MIGRATION-001.

This is a bounded migration slice. It does not migrate all `reporting/`, move
dashboard routes, move QRE runtime modules, change execution, live, paper,
shadow, risk, or broker behavior, change frozen contracts, or activate Addendum
1, Addendum 2, or Addendum 3 work.

## Selected Migration Slice

Source contract prepared by EXTRACT-002:

```text
packages/ade_governance/architecture_import_contracts.py
```

New canonical namespace:

```text
packages/ade_governance/import_contracts/architecture_import.py
```

Compatibility import paths:

```text
packages/ade_governance/architecture_import_contracts.py
reporting/architecture_import_scan.py
packages/ade_governance/__init__.py
packages/ade_governance/import_contracts/__init__.py
```

The compatibility paths re-export the exact canonical public objects.

## Files Changed

- `packages/ade_governance/import_contracts/__init__.py`
- `packages/ade_governance/import_contracts/architecture_import.py`
- `packages/ade_governance/architecture_import_contracts.py`
- `packages/ade_governance/__init__.py`
- `packages/ade_governance/README.md`
- `reporting/architecture_import_scan.py`
- `tests/architecture/test_ade_governance_architecture_import_contracts.py`
- `tests/architecture/test_domain_import_scanner.py`
- `tests/architecture/test_package_migration_002_ade_governance_read_only_contracts.py`
- `docs/architecture/PACKAGE-MIGRATION-002-ade-governance-read-only-contracts.md`

## Boundary and Risk Status

No runtime behavior change: scanner traversal, policy evaluation, allowlists,
reporting CLI behavior, dashboard code, QRE runtime code, and execution paths
remain in place.

No frozen research outputs were changed. `research/research_latest.json`,
`strategy_matrix.csv`, frozen schemas, and regression pins are not modified.

No `.claude/**` files were changed.

No dashboard mutation routes were added. No dashboard route, frontend route, or
control-plane runtime route wiring is added.

No live, paper, shadow, risk, broker, or execution behavior was changed.

Legacy/report-only findings remain visible. No broad wildcard allowlist is
added.

## Scanner Classification

`packages/ade_governance/` remains classified as `ADE`.

The new canonical contract module
`packages.ade_governance.import_contracts.architecture_import` is classified as
`ADE`, not QRE, control-plane, or execution.

## Validation Commands

```powershell
pytest tests/architecture/test_package_migration_002_ade_governance_read_only_contracts.py -q
pytest tests/architecture/test_ade_governance_architecture_import_contracts.py -q
pytest tests/architecture/test_domain_boundary_smoke.py -q
pytest tests/architecture/test_domain_import_scanner.py -q
pytest tests/architecture -q
pytest tests/unit/test_ci_path_classifier.py -q
python -m reporting.architecture_import_scan --format summary
```

## Rollback Plan

Revert the PACKAGE-MIGRATION-002 commit. That restores
`packages.ade_governance.architecture_import_contracts` as the direct
implementation and removes the narrower `import_contracts` namespace without
changing dashboard, QRE runtime, frozen artifact, or execution behavior.

## Package Migration Decision

Selected value: `PACKAGE_MIGRATION_CONTINUES_WITH_BOUNDED_NEXT_UNIT`

Rationale: ADE governance read-only contracts now live under the target
package namespace with compatibility preserved and without runtime movement.
The next safest migration is the already-proven control-plane read-only adapter
consumer or package boundary, selected as one bounded unit.

Exact next recommended unit:
PACKAGE-MIGRATION-003 - Migrate Control-Plane Read-Only Adapter Consumer or Package Boundary.
