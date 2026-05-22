# ARCH-004 - Control-Plane/QRE Boundary Hardening

Status: enforcement hardening
Date: 2026-05-22
Branch: `arch/004-control-plane-qre-boundary-hardening`
Builds on:

- `docs/architecture/ARCH-000-architecture-diagnosis-gate.md`
- `docs/architecture/ARCH-002-import-boundary-baseline.md`
- `docs/architecture/ARCH-003-import-boundary-enforcement-gate.md`
- `reporting/architecture_import_scan.py`

## 1. Purpose and Scope

ARCH-004 hardens the control-plane/QRE import boundary without moving files,
renaming packages, extracting packages, changing runtime behavior, changing
frozen contracts, or adding dashboard mutation routes.

The unit turns the current dashboard-to-QRE direct imports into an audited
legacy/report-only exception set and keeps all future non-allowlisted
control-plane-to-QRE imports as hard failures. It also defines the adapter path
needed before later package extraction readiness can be decided.

This is architecture enforcement and planning only. It does not activate
Addendum 1, Addendum 2, Addendum 3, shadow, paper, live, broker, risk, or
execution work.

## 2. Current Boundary Problem

ARCH-002 measured 18 direct control-plane-to-QRE edges:

- 16 `dashboard` to `research` findings;
- 2 `dashboard` to `data` findings.

These imports make the dashboard/control-plane layer depend directly on QRE
artifact paths, presets, diagnostics paths, and research intelligence modules.
They are acceptable as legacy read/report surfaces in the current monorepo, but
they are not package-extraction-ready boundaries.

The target shape is:

```text
direct import -> read-only adapter/facade -> contract tests -> package extraction readiness decision
```

No file move is authorized by ARCH-004. No runtime behavior change is
authorized by ARCH-004. No dashboard mutation route is authorized by ARCH-004.

## 3. Legacy/Report-Only Direct Imports

The following exact imports are legacy/report-only exceptions. They remain
visible in scanner reports and do not broad-fail the current repository.

| Source | Target | Why tolerated now | Sunset condition |
|---|---|---|---|
| `dashboard.api_campaigns` | `research.campaign_budget` | Campaign dashboard reads a QRE artifact path. | Replace with read-only campaign artifact facade contract. |
| `dashboard.api_campaigns` | `research.campaign_digest` | Campaign dashboard reads a QRE artifact path. | Replace with read-only campaign artifact facade contract. |
| `dashboard.api_campaigns` | `research.campaign_family_policy` | Campaign dashboard reads a QRE artifact path. | Replace with read-only campaign artifact facade contract. |
| `dashboard.api_campaigns` | `research.campaign_policy` | Campaign dashboard reads a QRE artifact path. | Replace with read-only campaign artifact facade contract. |
| `dashboard.api_campaigns` | `research.campaign_preset_policy` | Campaign dashboard reads a QRE artifact path. | Replace with read-only campaign artifact facade contract. |
| `dashboard.api_campaigns` | `research.campaign_queue` | Campaign dashboard reads a QRE artifact path. | Replace with read-only campaign artifact facade contract. |
| `dashboard.api_campaigns` | `research.campaign_registry` | Campaign dashboard reads a QRE artifact path. | Replace with read-only campaign artifact facade contract. |
| `dashboard.api_observability` | `research.diagnostics.paths` | Observability API reads QRE diagnostics artifact locations. | Replace with read-only diagnostics artifact facade contract. |
| `dashboard.api_research_intelligence` | `research.dead_zone_detection` | Research intelligence API reads a QRE artifact path. | Replace with read-only intelligence artifact facade contract. |
| `dashboard.api_research_intelligence` | `research.funnel_spawn_proposer` | Research intelligence API reads a QRE artifact path. | Replace with read-only intelligence artifact facade contract. |
| `dashboard.api_research_intelligence` | `research.information_gain` | Research intelligence API reads a QRE artifact path. | Replace with read-only intelligence artifact facade contract. |
| `dashboard.api_research_intelligence` | `research.research_evidence_ledger` | Research intelligence API reads a QRE artifact path. | Replace with read-only intelligence artifact facade contract. |
| `dashboard.api_research_intelligence` | `research.stop_condition_engine` | Research intelligence API reads a QRE artifact path. | Replace with read-only intelligence artifact facade contract. |
| `dashboard.api_research_intelligence` | `research.viability_metrics` | Research intelligence API reads a QRE artifact path. | Replace with read-only intelligence artifact facade contract. |
| `dashboard.dashboard` | `data.contracts` | Dashboard reads market metadata types for display paths. | Replace with read-only market metadata facade contract. |
| `dashboard.dashboard` | `data.repository` | Dashboard reads market repository types for display paths. | Replace with read-only market metadata facade contract. |
| `dashboard.dashboard` | `research.presets` | Dashboard reads QRE preset metadata for operator display. | Replace with read-only preset metadata facade contract. |
| `dashboard.research_runner` | `research.run_state` | Dashboard runner reads QRE run-state persistence helpers. | Replace with read-only run-state facade contract. |

The ADE-to-QRE reporting exceptions remain legacy/report-only:

- `reporting.hypothesis_discovery_summary` -> `research.hypothesis_discovery.campaign_seed_proposer`
- `reporting.intelligent_routing` -> `research.presets`

They are not control-plane/QRE imports, but they remain visible because the
scanner uses one exact legacy allowlist for closed architecture rules.

## 4. Newly Forbidden Imports

Any new non-test source edge with:

```text
source_domain == control-plane
target_domain == QRE
```

is a hard `control-plane-to-qre` failure unless it is added as an exact
legacy/report-only exception with a reason and sunset condition in the scanner.

ARCH-004 removes stale exact exceptions that were not present in the current
tracked import graph. This prevents future dashboard imports of additional QRE
modules from passing only because an old unused exception existed.

The gate does not use wildcard allowlists. Synthetic new control-plane/QRE
imports must fail with the violating source, target, and domain in the scanner
text output.

## 5. Selected Enforcement Expansion

ARCH-003 added the `production-to-tests` closed rule. ARCH-004 expands
enforcement depth for the existing `control-plane-to-qre` closed rule:

- exact allowlist entries now carry `legacy/report-only` status, reason, and
  sunset criteria;
- the allowlist is tested against the current tracked control-plane/QRE graph;
- stale unused exceptions are removed;
- synthetic future control-plane/QRE imports fail the scanner;
- legacy exceptions remain reported and do not broad-fail the repository.

This keeps the hard boundary meaningful without failing every known legacy edge.

## 6. Adapter/Facade Direction

The migration sequence is:

1. Keep current direct imports visible as report-only legacy debt.
2. Introduce read-only adapter/facade modules for one control-plane read
   surface at a time.
3. Add contract tests that pin response schema compatibility and read-only
   authority.
4. Replace dashboard direct imports with adapter calls.
5. Decide package extraction readiness only after direct and transitive edges,
   contract tests, and frozen outputs are stable.

Adapter contracts must be read-only. They must not mutate campaign state,
research state, approval state, paper state, shadow state, live state, risk
state, broker state, or execution state.

## 7. Frozen Contract and Protected Path Status

Frozen contracts remain unchanged:

- `research_latest.json` is not modified;
- `strategy_matrix.csv` is not modified;
- frozen artifact schemas and regression pin contracts are not modified.

Protected paths remain untouched:

- `.claude/**`;
- live, paper, shadow, risk, broker, and execution behavior paths;
- dashboard mutation routes.

## 8. Convergence

The ARCH track should converge by ARCH-006. The target exit is package
extraction readiness, not an open-ended architecture documentation sequence.

Exactly one next unit is recommended:

```text
ARCH-005 - Adapter Contract Scaffold
```

Purpose: define the read-only adapter/facade contract and contract tests for
control-plane/QRE separation. ARCH-005 should not perform package extraction.

The targeted exit remains:

```text
ARCH-006 - Package Extraction Readiness Decision
```
