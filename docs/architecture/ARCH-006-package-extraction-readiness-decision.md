# ARCH-006 - Package Extraction Readiness Decision

Status: readiness decision
Date: 2026-05-22
Branch: `arch/006-package-extraction-readiness-decision`
Builds on:

- `docs/architecture/ARCH-000-architecture-diagnosis-gate.md`
- `docs/architecture/ARCH-002-import-boundary-baseline.md`
- `docs/architecture/ARCH-003-import-boundary-enforcement-gate.md`
- `docs/architecture/ARCH-004-control-plane-qre-boundary-hardening.md`
- `docs/architecture/ARCH-005-adapter-contract-scaffold.md`
- `reporting/architecture_import_scan.py`
- `reporting/control_plane_qre_adapter_contract.py`

## 1. Purpose and Scope

ARCH-006 closes the dedicated architecture track with a package-extraction
readiness decision. The goal is not to continue architecture documentation. The
goal is to decide the next mode of work after ARCH-000 through ARCH-005:

- start one first physical package extraction slice;
- return to QRE feature work if extraction is not worth the cost;
- or fix one concrete blocker if readiness is blocked.

This unit performs no package extraction. It does not move files, rename
packages, change runtime behavior, change frozen contracts, add dashboard
mutation routes, or activate Addendum 1, Addendum 2, Addendum 3, shadow, paper,
live, broker, risk, or execution work.

## 2. Evidence Inspected

ARCH-000 recommended `PHASED_PACKAGE_EXTRACTION`, but explicitly not direct
file moves at that time. It defined physical package extraction as justified
only when imports are known, ownership is clear, frozen outputs stay stable,
adapters are available, tests pass, and rollback is simple.

ARCH-002 established the import-boundary baseline. The current scanner summary
on this branch reports:

| Metric | Count |
|---|---:|
| Direct import edges | 5289 |
| Hard forbidden-edge failures | 0 |
| Legacy/report-only findings | 74 |
| Control-plane to QRE legacy findings | 18 |
| ADE to QRE legacy findings | 2 |
| QRE to execution mixed-domain findings | 11 |

ARCH-003 added the first selected closed gate: production modules must not
import `tests.*` modules.

ARCH-004 hardened the control-plane/QRE boundary by converting the current
dashboard-to-QRE direct imports into exact legacy/report-only exceptions. New
non-allowlisted control-plane-to-QRE imports are hard failures.

ARCH-005 added the read-only adapter contract scaffold at
`reporting/control_plane_qre_adapter_contract.py`. The scaffold is stdlib-only,
has contract tests, exposes no route surface, imports no QRE or execution
modules, and is not wired into dashboard runtime behavior.

## 3. Readiness Assessment

The repository is not ready for broad QRE, dashboard, `agent`, or execution
package extraction. The known legacy edges are still useful warning signals:

| Area | Readiness | Reason |
|---|---|---|
| Dashboard/control-plane read surfaces | Not first | 18 direct QRE imports remain visible as legacy debt. They need adapter migrations before QRE read models move. |
| ADE reporting helpers | Not first | Two ADE-to-QRE exceptions remain. They are small, but still domain-coupled. |
| QRE research modules | Not first | Research modules include authority surfaces and frozen-output risk. They need narrower candidate selection after an adapter slice proves the workflow. |
| Legacy `agent` and execution-adjacent modules | Not first | Mixed execution/risk imports remain report-only and are high-risk. |
| Adapter contract scaffold | First candidate | It is stdlib-only, test-covered, read-only, has no runtime consumers beyond tests, and is designed to become the stable boundary before QRE read-model movement. |

The adapter contract scaffold is the only candidate that meets the first-slice
criteria without touching frozen outputs, dashboard behavior, QRE authority
surfaces, or execution paths.

## 4. Decision

Decision: `GO_FIRST_EXTRACTION_SLICE`

Rationale:

- Direct import evidence is known enough for the adapter contract candidate.
- The candidate is low-risk and has existing architecture contract tests.
- The candidate is adapter-compatible by definition and does not require moving
  QRE read models yet.
- The current scanner output has zero hard forbidden-edge failures while still
  exposing legacy/report-only debt.
- Frozen contracts and protected execution/live/paper/shadow/risk/broker paths
  do not need to change for the first slice.

## 5. First Extraction Candidate

Candidate: `reporting/control_plane_qre_adapter_contract.py`

The first physical extraction slice should extract this read-only adapter
contract scaffold into a dedicated stdlib-only adapter-contract package
namespace. The extraction slice should preserve a compatibility import at the
current reporting path until downstream consumers are migrated intentionally.

This candidate is deliberately smaller than a dashboard route migration or QRE
read-model move. It proves the package extraction mechanics, scanner
classification, compatibility import, and test lifecycle before any higher-risk
domain code moves.

## 6. Mandatory Gates for the First Extraction Slice

The first extraction PR must satisfy all of these gates:

- only the adapter contract package namespace, compatibility import, and
  architecture tests may change;
- `reporting/control_plane_qre_adapter_contract.py` must remain a compatibility
  import or equivalent stable surface until consumers migrate;
- scanner classification for the new package namespace must be explicit before
  import replacement lands;
- `python -m reporting.architecture_import_scan --format summary` must report
  zero hard forbidden-edge failures;
- existing legacy/report-only findings must remain visible and must not be
  hidden by wildcard allowlists;
- no new non-allowlisted control-plane-to-QRE import may be introduced;
- `pytest tests/architecture/test_domain_boundary_smoke.py -q` must pass;
- `pytest tests/architecture/test_domain_import_scanner.py -q` must pass;
- `pytest tests/architecture -q` must pass;
- adapter contract tests must continue to prove stdlib-only imports,
  read-only method names, no mutation verbs, and no route decorators;
- frozen contracts unchanged: `research_latest.json`, `strategy_matrix.csv`,
  frozen schemas, and regression pins must not change;
- protected paths untouched: `.claude/**` and live/paper/shadow/risk/broker/
  execution behavior paths must not change;
- no dashboard mutation routes may be added;
- no QRE strategy definitions, registry wiring, research orchestration, or
  authority semantics may change.

## 7. Go/No-Go Criteria for That Slice

Proceed only if the extraction remains a mechanical package-boundary move plus
compatibility import. Stop if the slice requires any of the following:

- dashboard route rewiring;
- QRE read-model movement;
- frozen contract updates;
- live, paper, shadow, risk, broker, or execution behavior edits;
- broad scanner allowlists;
- test weakening or fixture churn;
- strategy, registry, preset, campaign lifecycle, or paper-readiness changes.

If any stop condition appears, the next work should be a named blocker fix in
the non-ARCH package-readiness queue, not a continuation of the dedicated ARCH
track.

## 8. Recommended Next Action

Recommended next action: start first package extraction slice: extract
`reporting/control_plane_qre_adapter_contract.py` into a dedicated stdlib-only
adapter-contract package namespace, preserving a compatibility import and the
existing contract tests.

## 9. ARCH Track Closure

ARCH-006 closes the dedicated ARCH track. No further ARCH unit is recommended.
Future work should be the single first extraction slice above, or a named
non-ARCH blocker fix if that slice exposes a concrete blocker.
