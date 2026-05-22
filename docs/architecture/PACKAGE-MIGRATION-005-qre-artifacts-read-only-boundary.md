# PACKAGE-MIGRATION-005 - QRE Artifacts Read-Only Package Boundary

Status: implemented
Date: 2026-05-22
Builds on:

- `docs/architecture/PACKAGE-MIGRATION-001-target-layout-skeleton.md`
- `docs/architecture/PACKAGE-MIGRATION-002-ade-governance-read-only-contracts.md`
- `docs/architecture/PACKAGE-MIGRATION-003-control-plane-read-only-adapter-boundary.md`
- `docs/architecture/PACKAGE-MIGRATION-004-qre-diagnostics-read-only-boundary.md`
- `packages/qre_artifacts/`
- `research/results.py`
- `reporting/architecture_import_scan.py`

## Purpose and Scope

PACKAGE-MIGRATION-005 migrates one bounded QRE artifacts read-only package
boundary into the target `packages/qre_artifacts` namespace.

This unit does not migrate all `research/`, move all `artifacts/`, move
artifact producers broadly, move dashboard routes, change dashboard runtime
route wiring, change frozen contracts, add dashboard mutation routes, change
execution, live, paper, shadow, risk, or broker behavior, or activate Addendum
1, Addendum 2, or Addendum 3 work.

## Selected Migration Slice

Selected slice:

```text
research/results.py public output schema/path constants
```

New canonical namespace:

```text
packages.qre_artifacts.public_outputs
```

Compatibility import path:

```text
research.results
```

The selected constants are read-only public artifact contracts: the frozen
`strategy_matrix.csv` row schema, `research_latest.json` top-level and summary
schemas, and the existing repo-relative output paths. Artifact writer functions
remain in `research.results`.

## Why This Slice Was Selected

Inspection showed that existing artifact modules include many writer-heavy
research producers, dashboard read routes, campaign/candidate lifecycle modules,
and frozen schema guards. Moving those producers or dashboard consumers would
be broader than this unit.

The public output schema/path constants are the safest artifacts boundary seed
because they are immutable contract data, already protected by regression tests,
and can move under `packages.qre_artifacts` while preserving the existing
`research.results` import surface used by writers and tests.

## Exact Files/Modules Migrated or Introduced

- `packages/qre_artifacts/__init__.py`
- `packages/qre_artifacts/public_outputs.py`
- `packages/qre_artifacts/README.md`
- `research/results.py`
- `tests/architecture/test_package_migration_001_target_layout.py`
- `tests/architecture/test_package_migration_005_qre_artifacts_read_only_boundary.py`
- `docs/architecture/PACKAGE-MIGRATION-005-qre-artifacts-read-only-boundary.md`

## Canonical Namespace

```text
packages.qre_artifacts.public_outputs
```

## Old Compatibility Path

```text
research.results
```

The compatibility path imports and re-exports the canonical public contract
objects. Public schema/path constants exposed by `research.results` are
identity-equivalent to the canonical package objects.

## What Did Not Move

- No dashboard route module moved.
- No dashboard runtime route wiring changed.
- No artifact writer function moved.
- No generated artifact under `research/` or `artifacts/` moved or regenerated.
- No QRE strategy, registry, research orchestration, campaign, candidate,
  policy, or authority module moved.
- No execution, live, paper, shadow, risk, broker, or order behavior moved.
- No frozen public output file moved or regenerated.

## Runtime Behavior and Equivalence Statement

Runtime behavior is unchanged. Existing imports from `research.results` continue
to work because `research.results` imports the canonical constants and exposes
the same object identities at the old path. The writer functions
`write_results_to_csv` and `write_latest_json` remain in `research.results` and
use the same schema/path values.

No dashboard runtime route wiring was changed.

## Frozen Contract Status

No frozen research outputs were changed. `research/research_latest.json`,
`research/strategy_matrix.csv`, frozen schemas, and regression pins are not
modified.

No `.claude/**` files were changed.

## Dashboard Mutation Route Status

No dashboard mutation routes were added. The migrated artifact contract and
compatibility import contain no Flask import, route decorator, HTTP method
declaration, or dashboard route wiring.

## Live/Paper/Shadow/Risk/Broker/Execution Status

No live, paper, shadow, risk, broker, or execution behavior was changed. The
canonical artifacts contract imports only `__future__`, and the compatibility
path imports the canonical artifacts package contract.

## Scanner Classification

The existing scanner classifications remain:

```text
packages/qre_artifacts/ -> QRE
research/results.py -> QRE
dashboard/ -> control-plane
```

The compatibility import creates no cross-domain edge because both the legacy
and canonical public output contract modules are QRE-domain modules. Existing
legacy/report-only findings remain visible.

## Validation Commands

```powershell
pytest tests/architecture/test_package_migration_005_qre_artifacts_read_only_boundary.py -q
pytest tests/architecture/test_package_migration_001_target_layout.py -q
pytest tests/regression/test_research_schema_guard.py -q
pytest tests/regression/test_public_output_contract.py -q
pytest tests/architecture/test_domain_boundary_smoke.py -q
pytest tests/architecture/test_domain_import_scanner.py -q
pytest tests/architecture -q
pytest tests/unit/test_ci_path_classifier.py -q
python -m reporting.architecture_import_scan --format summary
```

## Rollback Plan

Revert the PACKAGE-MIGRATION-005 commit. That restores the public output
schema/path constants as direct definitions in `research.results` and removes
the canonical `packages.qre_artifacts.public_outputs` seed without changing
dashboard routes, artifact writers, frozen outputs, or execution behavior.

## Package Migration Decision

Selected value: `PACKAGE_MIGRATION_CONTINUES_WITH_BOUNDED_NEXT_UNIT`

Rationale: QRE artifacts now has one canonical read-only public output contract
seed with compatibility preserved and without dashboard route, artifact writer,
frozen output, or execution behavior changes. The next safest bounded package
migration is QRE policy because ADR-014 policy/authority surfaces remain the
next target package boundary and can be evaluated as read-only contracts without
touching strategy expansion or execution-sensitive behavior.

Exact next recommended unit:
PACKAGE-MIGRATION-006 - Migrate QRE Policy Read-Only Package Boundary.
