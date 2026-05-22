# ARCH-003 - Import Boundary Enforcement Gate

Status: enforcement gate
Date: 2026-05-22
Branch: `test/arch-003-import-boundary-enforcement-gate`
Builds on: `docs/architecture/ARCH-000-architecture-diagnosis-gate.md`,
`docs/architecture/ARCH-002-import-boundary-baseline.md`,
`reporting/architecture_import_scan.py`

## 1. Purpose and Scope

ARCH-003 adds the first narrow closed import-boundary gate after the ARCH-002
baseline. It uses the ARCH-001 static scanner and does not move files, rename
packages, perform package extraction, change runtime behavior, change frozen
contracts, or activate Addendum 1, Addendum 2, Addendum 3, shadow, paper, or
live work.

The gate is enforcement-hardening only. Existing mixed-domain dashboard,
reporting, research, governance-tooling, and legacy `agent` findings remain
report-only unless a later architecture unit explicitly selects them for
closed enforcement.

## 2. Selected Closed Boundary

Selected boundary:

```text
production-to-tests
```

Rule:

```text
No non-test Python module may directly import a tracked tests.* module.
```

Evidence supporting this as the first closed gate:

- The ARCH-001 scanner already classifies tracked test files as the `tests`
  domain.
- The ARCH-002 baseline reported test imports separately and exempted test
  source files from production boundary failures.
- A repo-local text probe found `tests.*` imports only inside test files.
- The gate does not depend on generated artifacts and does not touch frozen
  research outputs.
- The gate does not intersect the known legacy dashboard-to-QRE,
  control-plane-to-ADE, ADE-to-QRE, or legacy `agent` execution findings.

This boundary prevents production code from taking a dependency on test
helpers, fixtures, or regression-only modules. Test-to-test imports remain
allowed.

## 3. Enforcement Mechanism

`reporting/architecture_import_scan.py` now treats any direct import edge with:

```text
source_domain != tests
target_domain == tests
```

as a hard forbidden edge with rule `production-to-tests`.

The scanner remains static and deterministic:

- it scans tracked Python files only;
- it parses imports with `ast`;
- it does not import target modules;
- it keeps the existing deterministic sort order;
- it exits non-zero only when hard forbidden edges are present.

## 4. Report-Only Legacy Status

The ARCH-002 report-only legacy categories remain report-only:

| Category | ARCH-003 treatment |
|---|---|
| Dashboard/control-plane to QRE direct imports | Report-only legacy unless a new non-allowlisted closed edge is introduced. |
| Dashboard/control-plane to ADE reporting imports | Report-only mixed-domain debt. |
| ADE reporting helpers to QRE imports | Report-only legacy unless a new non-allowlisted closed edge is introduced. |
| QRE to ADE reason-record imports | Report-only mixed-domain debt. |
| Legacy `agent` imports of execution/risk modules | Report-only until active-runtime ownership is settled. |
| Governance tooling to ADE reporting imports | Report-only governance-tooling coupling. |
| Execution automation to ADE reporting imports | Report-only until an execution/ADE audit boundary is designed. |

No new allowlist entry is required for `production-to-tests` because the current
tracked repository has no production-to-tests imports.

## 5. Validation Expectations

ARCH-003 validation should include:

```powershell
pytest tests/architecture/test_domain_boundary_smoke.py -q
pytest tests/architecture/test_domain_import_scanner.py -q
pytest tests/architecture -q
python -m reporting.architecture_import_scan --format summary
```

The summary should continue to show zero hard forbidden-edge failures while
preserving the ARCH-002 legacy/report-only finding count unless unrelated
mainline changes alter the measured import graph.

## 6. Next Unit

Next recommended unit:

```text
ARCH-004 - Control-Plane/QRE Adapter Boundary Plan
```

Purpose: define the adapter boundary for dashboard/control-plane read surfaces
that currently import QRE modules directly, starting from the documented
ARCH-002 dashboard-to-`research` and dashboard-to-`data` findings.

ARCH-004 should still avoid file moves. It should produce an evidence-based
adapter plan, identify read-only endpoint candidates, document response-schema
preservation requirements, and keep dashboard mutation routes and execution,
live, paper, shadow, risk, and broker behavior out of scope.
