# PACKAGE-MIGRATION-004 - QRE Diagnostics Read-Only Package Boundary

Status: implemented
Date: 2026-05-22
Builds on:

- `docs/architecture/PACKAGE-MIGRATION-001-target-layout-skeleton.md`
- `docs/architecture/PACKAGE-MIGRATION-002-ade-governance-read-only-contracts.md`
- `docs/architecture/PACKAGE-MIGRATION-003-control-plane-read-only-adapter-boundary.md`
- `packages/qre_diagnostics/`
- `research/diagnostics/paths.py`
- `reporting/architecture_import_scan.py`

## Purpose and Scope

PACKAGE-MIGRATION-004 migrates one bounded QRE diagnostics read-only package
boundary into the target `packages/qre_diagnostics` namespace.

This unit does not migrate all `research/`, move all `research/diagnostics/`,
move dashboard routes, change dashboard runtime route wiring, change frozen
contracts, add dashboard mutation routes, change execution, live, paper,
shadow, risk, or broker behavior, or activate Addendum 1, Addendum 2, or
Addendum 3 work.

## Selected Migration Slice

Selected slice:

```text
research/diagnostics/paths.py
```

New canonical namespace:

```text
packages.qre_diagnostics.paths
```

Compatibility import path:

```text
research.diagnostics.paths
```

The selected module is a read-only diagnostics path contract. It defines
deterministic `Path` constants, string constants, tuples, dictionaries, and a
pure threshold lookup helper. The canonical module imports only `pathlib`.

## Why This Slice Was Selected

Inspection showed that `dashboard.api_observability` already depends on
`research.diagnostics.paths` as a read-only artifact-location contract, while
the rest of `research/diagnostics/` includes builders, CLI entry points, and
artifact writers under `research/observability/`. Moving those builders or
dashboard routes would be broader than this unit.

The path contract is the safest migration boundary because it is already
stdlib-only, has existing path-drift tests, and can be moved with a compatibility
shim without changing dashboard wiring or diagnostics runtime behavior.

## Exact Files/Modules Migrated or Introduced

- `packages/qre_diagnostics/__init__.py`
- `packages/qre_diagnostics/paths.py`
- `packages/qre_diagnostics/README.md`
- `research/diagnostics/paths.py`
- `tests/architecture/test_package_migration_003_control_plane_read_only_adapter_boundary.py`
- `tests/architecture/test_package_migration_001_target_layout.py`
- `tests/architecture/test_package_migration_004_qre_diagnostics_read_only_boundary.py`
- `tests/unit/test_observability_paths.py`
- `tests/unit/test_observability_static_import_surface.py`
- `tests/unit/test_dashboard_api_observability.py`
- `docs/architecture/PACKAGE-MIGRATION-004-qre-diagnostics-read-only-boundary.md`

## Canonical Namespace

```text
packages.qre_diagnostics.paths
```

## Old Compatibility Path

```text
research.diagnostics.paths
```

The compatibility path re-exports the canonical public contract exactly. Public
objects exposed through `__all__` are identity-equivalent between the canonical
and compatibility modules.

## What Did Not Move

- No dashboard route module moved.
- No dashboard runtime route wiring changed.
- No diagnostics builder, CLI, aggregator, artifact-health, failure-mode,
  throughput, system-integrity, clock, or IO module moved.
- No QRE strategy, registry, research orchestration, campaign, candidate,
  policy, or authority module moved.
- No execution, live, paper, shadow, risk, broker, or order behavior moved.
- No frozen research output moved or regenerated.

## Runtime Behavior and Equivalence Statement

Runtime behavior is unchanged. Existing imports of `research.diagnostics.paths`
continue to work through a compatibility shim. The canonical and compatibility
imports expose the same public contract objects.

No dashboard runtime route wiring was changed. `dashboard.api_observability`
continues to import the compatibility path, so endpoint behavior is unchanged.

## Frozen Contract Status

No frozen research outputs were changed. `research/research_latest.json`,
`strategy_matrix.csv`, frozen schemas, and regression pins are not modified.

No `.claude/**` files were changed.

## Dashboard Mutation Route Status

No dashboard mutation routes were added. The migrated path contract and
compatibility shim contain no Flask import, route decorator, HTTP method
declaration, or dashboard route wiring.

## Live/Paper/Shadow/Risk/Broker/Execution Status

No live, paper, shadow, risk, broker, or execution behavior was changed. The
canonical diagnostics path contract imports only `pathlib`, and the
compatibility shim imports only the canonical diagnostics package contract.

## Scanner Classification

The existing scanner classifications remain:

```text
packages/qre_diagnostics/ -> QRE
research/diagnostics/ -> QRE
dashboard/ -> control-plane
```

The compatibility import creates no cross-domain edge because both the legacy
and canonical diagnostics path modules are QRE-domain modules. Existing
legacy/report-only findings remain visible.

## Validation Commands

```powershell
pytest tests/architecture/test_package_migration_004_qre_diagnostics_read_only_boundary.py -q
pytest tests/architecture/test_package_migration_001_target_layout.py -q
pytest tests/unit/test_observability_paths.py -q
pytest tests/unit/test_observability_static_import_surface.py -q
pytest tests/unit/test_dashboard_api_observability.py -q
pytest tests/architecture/test_domain_boundary_smoke.py -q
pytest tests/architecture/test_domain_import_scanner.py -q
pytest tests/architecture -q
pytest tests/unit/test_ci_path_classifier.py -q
python -m reporting.architecture_import_scan --format summary
```

## Rollback Plan

Revert the PACKAGE-MIGRATION-004 commit. That restores
`research.diagnostics.paths` as the direct implementation and removes the
canonical `packages.qre_diagnostics.paths` seed without changing dashboard
routes, diagnostics builders, frozen outputs, or execution behavior.

## Package Migration Decision

Selected value: `PACKAGE_MIGRATION_CONTINUES_WITH_BOUNDED_NEXT_UNIT`

Rationale: QRE diagnostics now has one canonical read-only package-boundary
seed with compatibility preserved and without dashboard route or runtime
behavior changes. The next safest bounded package migration is QRE artifacts
because artifact read models are the next dependency for replacing legacy
report-only dashboard and ADE reads without touching execution-sensitive
behavior.

Exact next recommended unit:
PACKAGE-MIGRATION-005 - Migrate QRE Artifacts Read-Only Package Boundary.
