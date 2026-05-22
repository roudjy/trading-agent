# ARCH-002 - Import Boundary Baseline Report

Status: baseline report  
Date: 2026-05-22  
Branch: `docs/arch-002-import-boundary-baseline`  
Builds on: `docs/architecture/ARCH-000-architecture-diagnosis-gate.md`,
`reporting/architecture_import_scan.py`

## 1. Purpose and Scope

ARCH-002 converts the ARCH-001 domain import scanner into a reviewable
baseline of current direct import edges before enforcement is expanded.

This report is measurement and reporting only. It authorizes no file moves, no
package renames, no package extraction, no runtime behavior changes, no frozen
contract changes, and no dashboard mutation routes.

Package extraction remains future work. ARCH-000 recommended
`PHASED_PACKAGE_EXTRACTION`, but explicitly not direct file moves yet. This
baseline documents the current import graph so later hardening can be selected
deliberately.

The live, paper, shadow, risk, broker, and execution paths remain out of scope
for ARCH-002. They are measured only when direct imports appear in the static
scanner output; no behavior in those paths is modified or authorized here.

## 2. Commands Used

Baseline summary command:

```powershell
python -m reporting.architecture_import_scan --format summary
```

Full deterministic text report, available for review without adding a large
generated artifact:

```powershell
python -m reporting.architecture_import_scan --format text
```

Full deterministic JSON edge dump, intentionally not committed because it is
large and noisy:

```powershell
python -m reporting.architecture_import_scan --format json
```

The scanner enumerates tracked Python files with `git ls-files "*.py"` and
parses imports with `ast`. It does not import target modules and does not scan
untracked local files.

## 3. Baseline Summary

ARCH-002 summary output on this branch:

| Metric | Count |
|---|---:|
| Direct import edges | 5279 |
| Hard forbidden-edge failures | 0 |
| Legacy/report-only findings | 74 |

Current domain import edge categories:

| Source domain | Target domain | Edges |
|---|---|---:|
| ADE | ADE | 171 |
| ADE | QRE | 2 |
| ADE | unknown | 769 |
| QRE | ADE | 2 |
| QRE | QRE | 350 |
| QRE | execution | 11 |
| QRE | unknown | 719 |
| control-plane | ADE | 36 |
| control-plane | QRE | 18 |
| control-plane | control-plane | 21 |
| control-plane | unknown | 135 |
| execution | ADE | 1 |
| execution | QRE | 1 |
| execution | execution | 8 |
| execution | unknown | 24 |
| governance tooling | ADE | 3 |
| governance tooling | unknown | 92 |
| tests | ADE | 260 |
| tests | QRE | 566 |
| tests | control-plane | 52 |
| tests | execution | 27 |
| tests | tests | 25 |
| tests | unknown | 1931 |
| unknown | QRE | 7 |
| unknown | execution | 1 |
| unknown | unknown | 47 |

Test imports are reported in the edge categories but are exempt from production
boundary failures. Unknown targets are mostly standard library or third-party
imports and are not treated as domain-boundary findings.

## 4. Known Legacy and Mixed-Domain Findings

Legacy/report-only findings by rule and domain:

| Rule | Source domain | Target domain | Findings |
|---|---|---|---:|
| `ade-to-qre` | ADE | QRE | 2 |
| `control-plane-to-qre` | control-plane | QRE | 18 |
| `mixed-domain` | QRE | ADE | 2 |
| `mixed-domain` | QRE | execution | 11 |
| `mixed-domain` | control-plane | ADE | 36 |
| `mixed-domain` | execution | ADE | 1 |
| `mixed-domain` | execution | QRE | 1 |
| `mixed-domain` | governance tooling | ADE | 3 |

Legacy/report-only findings by source and target root:

| Source root | Target root | Rule | Findings |
|---|---|---|---:|
| `.claude` | `reporting` | `mixed-domain` | 3 |
| `agent` | `agent` | `mixed-domain` | 12 |
| `automation` | `reporting` | `mixed-domain` | 1 |
| `dashboard` | `data` | `control-plane-to-qre` | 2 |
| `dashboard` | `reporting` | `mixed-domain` | 36 |
| `dashboard` | `research` | `control-plane-to-qre` | 16 |
| `reporting` | `research` | `ade-to-qre` | 2 |
| `research` | `reporting` | `mixed-domain` | 2 |

The current scanner result has zero hard forbidden-edge failures because the
known ARCH-000 mixed-domain imports remain allowlisted as report-only legacy
findings. This is intentional: ARCH-002 documents current architecture debt and
must not make the repository fail on all existing legacy edges.

## 5. Report-Only Versus Hard Failures

Report-only findings are direct imports that cross conceptual target domains
but are already known from ARCH-000 or are not yet selected for closed
enforcement. They remain visible in the scanner output and this baseline.

Hard forbidden-edge failures are closed boundaries where new or non-allowlisted
imports must fail. The current closed rules are:

- `control-plane-to-qre`
- `ade-to-qre`
- `qre-to-execution` from `research/**`

Known legacy instances of those rules are still reported, not hidden. New
synthetic violations remain fatal in scanner tests.

## 6. Initial Allowlist Candidate Categories

Initial allowlist candidates should stay category-based and justified before
ARCH-003 expands enforcement:

| Candidate category | Current evidence | Baseline treatment |
|---|---|---|
| Control-plane read surfaces importing QRE modules | 18 `dashboard` to `research`/`data` findings | Temporary report-only legacy; candidate for adapter hardening. |
| Control-plane routes importing ADE reporting modules | 36 `dashboard` to `reporting` findings | Temporary report-only legacy; candidate for read/control adapter definitions. |
| ADE reporting helpers importing QRE modules | 2 `reporting` to `research` findings | Temporary report-only legacy; candidate for explicit QRE adapter or data contract. |
| Legacy `agent` modules importing execution/risk modules | 12 `agent` root findings, including 11 QRE-to-execution domain findings | Report-only until active-runtime ownership is settled. |
| Governance hooks emitting ADE audit records | 3 `.claude` to `reporting` findings | Report-only governance tooling coupling; not part of package extraction. |
| Execution automation reporting audit events | 1 `automation` to `reporting` finding | Report-only until execution/ADE audit boundary is explicitly designed. |

Allowlist entries should include a reason, owner, and sunset condition when
ARCH-003 turns selected categories into closed enforcement.

## 7. First Recommended Hardening Targets

First hardening targets should expand enforcement for selected boundaries only.
They should not move files.

1. Convert the `dashboard` to `research`/`data` read-surface findings into an
   explicit control-plane-to-QRE adapter target. Start with read-only endpoints
   and preserve response schemas.
2. Split the `reporting` to `research` findings into named ADE-to-QRE adapter
   exceptions with sunset criteria, especially `reporting.intelligent_routing`
   and `reporting.hypothesis_discovery_summary`.
3. Keep `research` to `reporting.reason_records` visible as QRE-to-ADE debt and
   decide whether reason-record writing is an ADE service boundary or a QRE
   evidence contract.
4. Leave legacy `agent` to execution/risk findings report-only until the active
   runtime status and extraction owner are proven. This is high-risk and should
   not be the first enforcement expansion.
5. Treat `dashboard` to `reporting` imports as a second-wave adapter hardening
   target after the control-plane-to-QRE read surfaces are pinned.

## 8. Next Unit

Next logical unit:

`ARCH-003 - Import Boundary Enforcement Gate`

ARCH-003 should expand closed enforcement for selected import boundaries using
the ARCH-001 scanner and this ARCH-002 baseline. It should not move files,
rename packages, perform package extraction, activate Addendum work, or modify
live/paper/shadow/risk/broker/execution behavior.
