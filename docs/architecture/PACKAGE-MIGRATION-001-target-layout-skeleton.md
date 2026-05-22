# PACKAGE-MIGRATION-001 - Target Layout Skeleton

Status: implemented
Date: 2026-05-22
Builds on:

- `docs/architecture/ARCH-000-architecture-diagnosis-gate.md`
- `docs/architecture/ARCH-006-package-extraction-readiness-decision.md`
- `docs/architecture/EXTRACT-001-control-plane-qre-adapter-contract.md`
- `docs/architecture/EXTRACT-002-ade-governance-import-contracts.md`
- `reporting/architecture_import_scan.py`

## Purpose and Scope

PACKAGE-MIGRATION-001 starts the package-migration lane by creating the target
package/app layout skeleton and the migration governance rules for later
bounded moves.

This unit creates README-only scaffolds and scanner classifications. It does
not broadly move runtime modules, migrate dashboard routes, migrate QRE
research modules, change ADE governance runtime behavior, change frozen
contracts, add dashboard mutation routes, or activate live, paper, shadow,
risk, broker, or execution behavior.

## Why ARCH and EXTRACT Are Complete

ARCH-000 through ARCH-006 established the architecture diagnosis, import
scanner, boundary enforcement gates, adapter contract scaffold, and package
extraction readiness decision. ARCH-006 explicitly closed the dedicated ARCH
track and selected a first extraction slice instead of continuing architecture
documentation.

EXTRACT-001 moved the control-plane/QRE read-only adapter contract into an
extracted package while preserving the reporting compatibility import.
EXTRACT-002 moved immutable ADE governance import-scan contracts into
`packages/ade_governance` and ended the EXTRACT series with
`EXTRACT_SERIES_COMPLETE_READY_FOR_PACKAGE_MIGRATION`.

Because those tracks are closed, PACKAGE-MIGRATION-001 does not create
ARCH-007 and does not reopen EXTRACT work.

## Target Layout

The target package/app layout is:

```text
apps/control-plane/
packages/ade_governance/
packages/qre_research/
packages/qre_data/
packages/qre_artifacts/
packages/qre_diagnostics/
packages/qre_policy/
packages/qre_execution_sim/
packages/qre_shadow/
packages/qre_paper/
packages/qre_live/
```

Existing extracted seed content remains in:

```text
packages/control_plane_qre_adapter_contract/
packages/ade_governance/architecture_import_contracts.py
```

`packages/control_plane_qre_adapter_contract/` remains a proven adapter-contract
package from EXTRACT-001. It is not renamed or moved by this unit.

## Package Ownership Map

| Target | Owner Domain | Status | Authority Boundary |
|---|---|---|---|
| `apps/control-plane/` | Control plane | scaffold-only | Future operator UI/API boundary; current authority remains in `dashboard/` and `frontend/`. |
| `packages/ade_governance/` | ADE governance | active extracted seed content | Governance contracts only; runtime authority remains in `reporting/` until bounded moves. |
| `packages/qre_research/` | QRE research | scaffold-only | Strategy registration remains in `registry.py`; orchestration remains in `research/run_research.py`. |
| `packages/qre_data/` | QRE data | scaffold-only | Current source remains `data/`. |
| `packages/qre_artifacts/` | QRE artifacts | scaffold-only | Frozen outputs and schemas remain in current paths. |
| `packages/qre_diagnostics/` | QRE diagnostics | scaffold-only | Current source remains `research/diagnostics/` and read-only observability modules. |
| `packages/qre_policy/` | QRE policy | scaffold-only | ADR-014 authority surfaces remain in current `research/` modules. |
| `packages/qre_execution_sim/` | Execution-sensitive simulation | future-only inactive | No broker, live, paper, or external mutation authority. |
| `packages/qre_shadow/` | Execution-sensitive shadow | future-only inactive until Roadmap v4.x | No shadow runtime activation. |
| `packages/qre_paper/` | Execution-sensitive paper | future-only inactive until Roadmap v5.x | No paper runtime activation. |
| `packages/qre_live/` | Execution-sensitive live | hard-disabled until Roadmap v6.x and explicit operator approval | No live order placement, broker mutation, capital allocation, or live risk behavior. |

## Migration Sequence

This unit authorizes only the skeleton and exactly one next bounded unit.

1. PACKAGE-MIGRATION-001 creates the target skeleton and package-migration
   gates.
2. PACKAGE-MIGRATION-002 should migrate ADE Governance Read-Only Contracts.

No additional package-migration sequence is authorized by this document. Later
units must be proposed one at a time with exact source paths, target paths,
compatibility policy, rollback plan, and validation commands.

## What Was Created in This Unit

- README-only scaffolds for the target app and target packages.
- A migration decision document for PACKAGE-MIGRATION-001.
- Explicit scanner classification for the target app/package paths.
- Architecture tests covering skeleton presence, README governance content,
  scanner classification, legacy finding visibility, and non-runtime package
  scaffolding.

## What Was Not Done

- No dashboard routes were moved.
- No QRE runtime modules were moved.
- No ADE governance runtime modules were moved.
- No live, paper, shadow, risk, broker, or execution behavior was changed.
- No dashboard mutation routes were added.
- No frozen research outputs were changed.
- No `.claude/**` files were changed.
- No Addendum 1, Addendum 2, or Addendum 3 work was activated.

## Compatibility Policy

Existing imports remain authoritative until a future package-migration unit
creates a compatibility import or explicitly updates a consumer. README-only
scaffolds export no runtime API and introduce no importable package behavior.

When a future module moves, the old path must remain compatible unless the unit
explicitly proves no consumers remain and the architecture guardian accepts the
removal.

## Migration Gates

Every future package-migration unit must satisfy these gates:

- The unit names exactly one bounded source slice and one target package.
- Runtime behavior, frozen contracts, and output schemas remain unchanged
  unless explicitly scoped.
- The scanner classifies the target path before moved code lands.
- `python -m reporting.architecture_import_scan --format summary` reports zero
  hard forbidden-edge failures.
- Legacy/report-only findings remain visible; wildcard allowlists are not
  introduced.
- No dashboard mutation route is added.
- `.claude/**` and protected execution/live/paper/shadow/risk/broker behavior
  paths remain untouched unless a separately approved unit authorizes them.
- Tests are strengthened or preserved; hooks are not bypassed.
- Rollback is a path/compatibility revert, not a behavior rewrite.

## Scanner Classification

The architecture scanner classifies target paths deterministically:

| Path | Scanner Domain |
|---|---|
| `apps/control-plane/` | `control-plane` |
| `packages/ade_governance/` | `ADE` |
| `packages/qre_research/` | `QRE` |
| `packages/qre_data/` | `QRE` |
| `packages/qre_artifacts/` | `QRE` |
| `packages/qre_diagnostics/` | `QRE` |
| `packages/qre_policy/` | `QRE` |
| `packages/qre_execution_sim/` | `execution` |
| `packages/qre_shadow/` | `execution` |
| `packages/qre_paper/` | `execution` |
| `packages/qre_live/` | `execution` |

`packages/qre_live/` remains hard-disabled despite being
execution-classified. Classification is a safety label, not runtime
activation.

## Package Migration Decision

Selected value: `PACKAGE_MIGRATION_CONTINUES_WITH_BOUNDED_NEXT_UNIT`

Rationale: ARCH and EXTRACT are complete, the target layout is now explicit,
and skeleton-only package governance can proceed without runtime movement. The
next safe step is a read-only ADE governance contract migration because
`packages/ade_governance` already contains extracted seed content from
EXTRACT-002 and can absorb another bounded read-only governance surface without
touching QRE runtime, dashboard routes, or execution behavior.

Exact next recommended unit:
PACKAGE-MIGRATION-002 - Migrate ADE Governance Read-Only Contracts.
