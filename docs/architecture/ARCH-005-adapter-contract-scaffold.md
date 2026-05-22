# ARCH-005 - Adapter Contract Scaffold

Status: contract scaffold
Date: 2026-05-22
Branch: `arch/005-adapter-contract-scaffold`
Builds on:

- `docs/architecture/ARCH-000-architecture-diagnosis-gate.md`
- `docs/architecture/ARCH-002-import-boundary-baseline.md`
- `docs/architecture/ARCH-003-import-boundary-enforcement-gate.md`
- `docs/architecture/ARCH-004-control-plane-qre-boundary-hardening.md`
- `reporting/architecture_import_scan.py`

## 1. Purpose and Scope

ARCH-005 creates the first read-only adapter/facade contract scaffold for the
control-plane/QRE boundary. It moves the architecture track from diagnosis and
selected enforcement toward a stable dependency shape that future dashboard/API
code can use instead of direct QRE domain imports.

This unit is a scaffold only. It does not move files, rename packages, perform
package extraction, change runtime behavior, change frozen contracts, add
dashboard mutation routes, or activate Addendum 1, Addendum 2, Addendum 3,
shadow, paper, live, broker, risk, or execution work.

## 2. Adapter/Facade Role

The adapter contract is the stable read-only surface between future
control-plane consumers and QRE-owned read models. The control plane should
depend on the contract shape, not on QRE module paths such as `research.*` or
`data.*`.

The initial scaffold lives at:

```text
reporting/control_plane_qre_adapter_contract.py
```

The module is stdlib-only and declares:

- `ControlPlaneQREReadAdapter`
- `ReadModelContract`
- `AdapterContractDescription`
- `describe_contract()`
- stable read-only method names: `list_read_models`, `read_json`,
  `describe_contract`

No dashboard route is wired to this scaffold in ARCH-005.

## 3. What an Adapter May Do

A control-plane/QRE adapter may:

- list available QRE read models;
- read existing QRE JSON-compatible artifacts or snapshots;
- return deterministic contract metadata;
- preserve existing response schemas when a dashboard route is migrated later;
- fail closed when a read model is unavailable.

The adapter must remain read-only. It may expose existing state, but it must not
become an authority surface for changing QRE, ADE, execution, paper, shadow,
live, broker, risk, or dashboard state.

## 4. What an Adapter May Not Do

A control-plane/QRE adapter may not:

- create, update, delete, append, write, save, enqueue, dispatch, execute,
  approve, spawn, trade, order, or mutate state;
- add dashboard mutation routes;
- import live, paper, shadow, risk, broker, or execution paths;
- hide new direct control-plane-to-QRE imports behind wildcard allowlists;
- change `research_latest.json`, `strategy_matrix.csv`, frozen schemas, or
  regression pin contracts;
- duplicate QRE strategy definitions or bypass registry authority.

## 5. Read-Only Contract Expectations

The scaffold uses frozen dataclasses and a runtime-checkable Protocol so future
implementations can be validated without importing QRE modules.

Expected method names are stable for future migration tests:

| Method | Responsibility |
|---|---|
| `list_read_models` | Return available read-only QRE read-model metadata. |
| `read_json` | Return an existing read model as JSON-compatible data. |
| `describe_contract` | Return deterministic contract metadata. |

The contract describes forbidden capabilities explicitly so tests can fail if a
future implementation adds hidden mutation or execution authority.

## 6. No Runtime Behavior Change

ARCH-005 does not wire the adapter into `dashboard/`, Flask routes, API
registration, research orchestration, live/paper/shadow/risk/broker/execution
behavior, or generated research outputs.

Current legacy dashboard-to-QRE imports remain visible as report-only debt under
the ARCH-004 scanner allowlist. The scaffold prepares a future migration path
but does not migrate real imports in this unit.

## 7. No File Move or Package Extraction

ARCH-005 performs no physical package extraction and no package rename. The
target remains package extraction readiness, not a partial package move.

The scaffold is deliberately small so ARCH-006 can decide whether the repo is
ready for the first physical package extraction slice.

## 8. No Frozen Contract Change

Frozen contracts remain unchanged:

- `research_latest.json` is not modified;
- `strategy_matrix.csv` is not modified;
- frozen artifact schemas and regression pin outputs are not modified.

## 9. Contract Test Protection

ARCH-005 adds contract tests under `tests/architecture/` that verify:

- the adapter contract is importable and runtime-checkable;
- contract metadata and method names are stable;
- the scaffold imports only stdlib modules;
- no QRE, dashboard, live, paper, shadow, risk, broker, or execution imports are
  introduced by the scaffold;
- no route decorator or mutation-named public method is exposed;
- a future control-plane import of the adapter contract is not a hard forbidden
  scanner edge;
- a future direct control-plane import of QRE remains a hard
  `control-plane-to-qre` violation unless explicitly allowlisted.

These tests allow migration to proceed one read surface at a time while keeping
legacy/report-only debt from broad-failing the repository.

## 10. ARCH-006 Readiness Link

ARCH-005 provides the minimal contract object that ARCH-006 can use to decide
whether package extraction readiness exists. ARCH-006 should evaluate:

- whether the direct and transitive import graph is known enough;
- whether one low-risk extraction candidate can be identified;
- which adapter contract tests must gate that extraction;
- which frozen outputs and protected paths must remain untouched;
- go/no-go criteria for the first physical package extraction slice.

Exactly one next unit is recommended:

```text
ARCH-006 - Package Extraction Readiness Decision
```

Purpose: decide whether the repo is ready for the first physical package
extraction slice, identify blockers, first extraction candidate, required gates,
and go/no-go criteria.

No ARCH-007+ unit is recommended by ARCH-005.
