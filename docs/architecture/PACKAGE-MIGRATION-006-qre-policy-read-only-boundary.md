# PACKAGE-MIGRATION-006 - QRE Policy Read-Only Package Boundary

Status: implemented
Date: 2026-05-22
Builds on:

- `docs/architecture/PACKAGE-MIGRATION-001-target-layout-skeleton.md`
- `docs/architecture/PACKAGE-MIGRATION-002-ade-governance-read-only-contracts.md`
- `docs/architecture/PACKAGE-MIGRATION-003-control-plane-read-only-adapter-boundary.md`
- `docs/architecture/PACKAGE-MIGRATION-004-qre-diagnostics-read-only-boundary.md`
- `docs/architecture/PACKAGE-MIGRATION-005-qre-artifacts-read-only-boundary.md`
- `docs/adr/ADR-014-truth-authority-settlement.md`
- `packages/qre_policy/`
- `research/authority_views.py`

## Purpose and Scope

PACKAGE-MIGRATION-006 migrates one bounded QRE policy read-only package
boundary into the target `packages/qre_policy` namespace.

This unit does not migrate all `research/`, move campaign policy modules,
move candidate lifecycle modules, move paper-readiness modules, move dashboard
routes, change dashboard runtime route wiring, change frozen contracts, add
dashboard mutation routes, change execution, live, paper, shadow, risk, or
broker behavior, or activate Addendum 1, Addendum 2, or Addendum 3 work.

## Selected Migration Slice

Selected slice:

```text
research/authority_views.py ADR-014 derived read-only policy predicates
```

New canonical namespace:

```text
packages.qre_policy.authority_views
```

Compatibility import path:

```text
research.authority_views
```

The selected functions are read-only derived policy views over ADR-014
authority sources: `bundle_active`, `active_discovery`, `live_eligible`, and
`render_authority_summary`.

## Why This Slice Was Selected

Inspection showed that QRE policy includes campaign decision modules, funnel
policy, candidate lifecycle, paper readiness, artifact writers, and dashboard
read consumers. Moving those modules would be broader than this unit and would
risk authority semantics or runtime behavior changes.

`research.authority_views` is the safest policy boundary seed because it is
already documented as read-only, diagnostic-only, and side-effect-free. It
derives from existing canonical authorities without mutating them and already
has tests pinning the no-live and no-IO invariants.

## Exact Files/Modules Migrated or Introduced

- `packages/qre_policy/__init__.py`
- `packages/qre_policy/authority_views.py`
- `packages/qre_policy/README.md`
- `research/authority_views.py`
- `tests/architecture/test_package_migration_001_target_layout.py`
- `tests/architecture/test_package_migration_006_qre_policy_read_only_boundary.py`
- `docs/architecture/PACKAGE-MIGRATION-006-qre-policy-read-only-boundary.md`

## Canonical Namespace

```text
packages.qre_policy.authority_views
```

## Old Compatibility Path

```text
research.authority_views
```

The compatibility path imports and re-exports the canonical functions. Public
functions exposed by `research.authority_views` are identity-equivalent to the
canonical package functions.

## What Did Not Move

- No campaign policy, campaign funnel policy, campaign registry, candidate
  lifecycle, paper readiness, strategy registry, preset catalog, or hypothesis
  catalog module moved.
- No dashboard route module moved.
- No dashboard runtime route wiring changed.
- No generated artifact under `research/` or `artifacts/` moved or
  regenerated.
- No execution, live, paper, shadow, risk, broker, or order behavior moved.
- No frozen public output file moved or regenerated.

## Runtime Behavior and Equivalence Statement

Runtime behavior is unchanged. Existing imports from `research.authority_views`
continue to work because `research.authority_views` imports the canonical
functions and exposes the same function identities at the old path. The
canonical implementation still reads the same registry, preset, and hypothesis
catalog inputs and returns the same truth-table values.

No authority semantics changed. The migrated module remains diagnostic-only
and read-only; it does not become a decision-path input.

No dashboard runtime route wiring was changed.

## Frozen Contract Status

No frozen research outputs were changed. `research/research_latest.json`,
`research/strategy_matrix.csv`, frozen schemas, and regression pins are not
modified.

No `.claude/**` files were changed.

## Frozen Schema / Regression Pin Status

No frozen schema or regression pin was changed. The migration preserves the
existing no-live, no-IO, and derived-authority invariants for
`research.authority_views` through compatibility imports.

## Dashboard Mutation Route Status

No dashboard mutation routes were added. The migrated policy contract and
compatibility import contain no Flask import, route decorator, HTTP method
declaration, or dashboard route wiring.

## Live/Paper/Shadow/Risk/Broker/Execution Status

No live, paper, shadow, risk, broker, or execution behavior was changed. The
canonical policy view imports only read-only QRE authority sources
(`research.presets`, `research.registry`, and
`research.strategy_hypothesis_catalog`) plus stdlib typing. The compatibility
path imports only the canonical QRE policy package contract.

## Scanner Classification

The existing scanner classifications remain:

```text
packages/qre_policy/ -> QRE
research/authority_views.py -> QRE
dashboard/ -> control-plane
```

The compatibility import creates no cross-domain edge because both the legacy
and canonical policy modules are QRE-domain modules. Existing legacy/report-only
findings remain visible.

## Validation Commands

```powershell
pytest tests/architecture/test_package_migration_006_qre_policy_read_only_boundary.py -q
pytest tests/architecture/test_package_migration_001_target_layout.py -q
pytest tests/unit/test_authority_views.py -q
pytest tests/regression/test_authority_invariants.py -q
pytest tests/architecture/test_domain_boundary_smoke.py -q
pytest tests/architecture/test_domain_import_scanner.py -q
pytest tests/architecture -q
pytest tests/unit/test_ci_path_classifier.py -q
python -m reporting.architecture_import_scan --format summary
```

## Rollback Plan

Revert the PACKAGE-MIGRATION-006 commit. That restores
`research.authority_views` as the direct implementation and removes the
canonical `packages.qre_policy.authority_views` seed without changing dashboard
routes, policy decision modules, frozen outputs, or execution behavior.

## Package Migration Decision

Selected value: `PACKAGE_MIGRATION_CONTINUES_WITH_BOUNDED_NEXT_UNIT`

Rationale: QRE policy now has one canonical read-only ADR-014 authority view
seed with compatibility preserved and without campaign decision, paper
readiness, dashboard route, frozen output, or execution behavior changes. The
next safest bounded package migration is QRE data because the target data
package remains scaffold-only and can be evaluated for a read-only metadata or
contract seed without moving all data ingestion or dashboard behavior.

Exact next recommended unit:
PACKAGE-MIGRATION-007 - Migrate QRE Data Read-Only Package Boundary.
