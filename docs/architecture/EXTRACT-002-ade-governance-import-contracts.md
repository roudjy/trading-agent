# EXTRACT-002 - ADE Governance Import Contracts Package

Status: implemented
Date: 2026-05-22
Builds on:

- `docs/architecture/ARCH-006-package-extraction-readiness-decision.md`
- `docs/architecture/EXTRACT-001-control-plane-qre-adapter-contract.md`
- `reporting/architecture_import_scan.py`
- `packages/control_plane_qre_adapter_contract/`

## Selected Slice

EXTRACT-002 selects one small architecture-support package-boundary slice:
move the immutable architecture import scanner contract vocabulary and frozen
report dataclasses into the canonical ADE governance package namespace.

New canonical namespace:

```text
packages/ade_governance/architecture_import_contracts.py
```

Compatibility path:

```text
reporting/architecture_import_scan.py
```

The scanner continues to expose the same public constants and dataclasses from
the reporting path by importing and re-exporting the canonical package objects.

## Why This Slice Was Selected

This slice is adjacent to EXTRACT-001 because both changes extract stdlib-only
contract/support surfaces before any runtime migration. It is bounded because
it moves only immutable scanner vocabulary and data shapes:

- domain constants;
- execution-domain prefix constants;
- frozen dataclasses for import edges, boundary findings, reports, and legacy
  allowlist entries.

Scanner traversal, scanner policy evaluation, exact legacy allowlists, CLI
behavior, dashboard code, QRE runtime code, and frozen artifacts remain in their
current locations.

## Exact Files and Modules

Introduced:

- `packages/ade_governance/__init__.py`
- `packages/ade_governance/architecture_import_contracts.py`
- `tests/architecture/test_ade_governance_architecture_import_contracts.py`
- `docs/architecture/EXTRACT-002-ade-governance-import-contracts.md`

Updated:

- `reporting/architecture_import_scan.py`
- `tests/architecture/test_domain_import_scanner.py`

## Boundary and Risk Status

No runtime behavior change: the scanner CLI and scan/evaluation functions remain
in `reporting.architecture_import_scan`.

No frozen contract change: `research_latest.json`, `strategy_matrix.csv`, frozen
schemas, and regression pins are not modified.

No dashboard mutation route: no dashboard route or API module is changed.

No live/paper/shadow/risk/broker/execution change: no module in those behavior
paths is modified, and the new canonical package imports only stdlib modules.

No authority semantics change: the closed scanner rules and exact
legacy/report-only allowlist entries remain in `reporting.architecture_import_scan`.

Legacy/report-only findings remain visible. No broad wildcard allowlist is added.

## Validation Commands

```powershell
pytest tests/architecture/test_ade_governance_architecture_import_contracts.py -q
pytest tests/architecture/test_domain_boundary_smoke.py -q
pytest tests/architecture/test_domain_import_scanner.py -q
pytest tests/architecture -q
python -m reporting.architecture_import_scan --format summary
```

## Rollback Plan

Revert this EXTRACT-002 commit. That restores the scanner constants and
dataclasses to `reporting/architecture_import_scan.py` and removes the
`packages/ade_governance` support namespace without changing dashboard, QRE,
runtime, frozen artifact, or execution behavior.

## EXTRACT Series Decision

Selected value:
`EXTRACT_SERIES_COMPLETE_READY_FOR_PACKAGE_MIGRATION`

Rationale: EXTRACT-001 established the read-only control-plane/QRE adapter
contract package, and EXTRACT-002 establishes the minimal ADE governance support
contract package needed before package migration planning. Continuing extraction
only because additional small modules exist would violate the EXTRACT-series
clarity rule.

Exactly one next recommended action: start PACKAGE-MIGRATION-001 to plan the
first bounded migration step using the package namespaces proven by EXTRACT-001
and EXTRACT-002.
