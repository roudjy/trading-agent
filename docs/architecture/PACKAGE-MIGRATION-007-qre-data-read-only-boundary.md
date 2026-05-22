# PACKAGE-MIGRATION-007 - QRE Data Read-Only Package Boundary

Status: implemented
Date: 2026-05-22
Builds on:

- `docs/architecture/PACKAGE-MIGRATION-001-target-layout-skeleton.md`
- `docs/architecture/PACKAGE-MIGRATION-004-qre-diagnostics-read-only-boundary.md`
- `docs/architecture/PACKAGE-MIGRATION-005-qre-artifacts-read-only-boundary.md`
- `docs/architecture/PACKAGE-MIGRATION-006-qre-policy-read-only-boundary.md`
- `packages/qre_data/`
- `data/contracts.py`

## Purpose and Scope

PACKAGE-MIGRATION-007 migrates one bounded QRE data read-only package boundary
into the target `packages/qre_data` namespace.

This unit does not migrate all `data/`, move repositories, move adapters, move
data fetchers, move cache files, move dashboard routes, change dashboard
runtime route wiring, change frozen contracts, add dashboard mutation routes,
change execution, live, paper, shadow, risk, or broker behavior, or activate
Addendum 1, Addendum 2, or Addendum 3 work.

## Selected Migration Slice

Selected slice:

```text
data/contracts.py immutable market and macro data contract types
```

New canonical namespace:

```text
packages.qre_data.contracts
```

Compatibility import path:

```text
data.contracts
```

The selected classes are read-only data contracts: `AdapterAuthError`,
`Instrument`, `Provenance`, `CanonicalBar`, and `MacroSeriesPoint`.

## Why This Slice Was Selected

Inspection showed that data repositories and adapters include cache IO,
external data fetching, credential handling, dashboard consumers, and runtime
data loading. Moving those modules would be broader than this unit and would
risk data-fetch behavior changes.

`data.contracts` is the safest data boundary seed because it contains immutable
dataclass contract definitions and one exception type only. It has no IO, no
adapter routing, no cache mutation, and no dashboard route wiring.

## Exact Files/Modules Migrated or Introduced

- `packages/qre_data/__init__.py`
- `packages/qre_data/contracts.py`
- `packages/qre_data/README.md`
- `data/contracts.py`
- `tests/architecture/test_package_migration_001_target_layout.py`
- `tests/architecture/test_package_migration_007_qre_data_read_only_boundary.py`
- `docs/architecture/PACKAGE-MIGRATION-007-qre-data-read-only-boundary.md`

## Canonical Namespace

```text
packages.qre_data.contracts
```

## Old Compatibility Path

```text
data.contracts
```

The compatibility path imports and re-exports the canonical classes. Public
classes exposed by `data.contracts` are identity-equivalent to the canonical
package classes.

## What Did Not Move

- No data repository, adapter, fetcher, cache file, bot-detection, or data
  runtime module moved.
- No dashboard route module moved.
- No dashboard runtime route wiring changed.
- No generated artifact under `research/`, `artifacts/`, or `data/cache/`
  moved or regenerated.
- No strategy, registry, research orchestration, campaign, candidate, policy,
  or authority module moved.
- No execution, live, paper, shadow, risk, broker, or order behavior moved.
- No frozen public output file moved or regenerated.

## Runtime Behavior and Equivalence Statement

Runtime behavior is unchanged. Existing imports from `data.contracts` continue
to work because `data.contracts` imports the canonical classes and exposes the
same class identities at the old path. Dataclass frozen behavior, constructor
fields, equality, and `asdict` behavior are preserved.

No repository, adapter, cache, credential, external IO, or dashboard runtime
route wiring was changed.

No dashboard runtime route wiring was changed.

## Frozen Contract Status

No frozen research outputs were changed. `research/research_latest.json`,
`research/strategy_matrix.csv`, frozen schemas, and regression pins are not
modified.

No `.claude/**` files were changed.

## Frozen Schema / Regression Pin Status

No frozen schema or regression pin was changed. The migration preserves the
existing data contract dataclass fields and compatibility import path.

## Dashboard Mutation Route Status

No dashboard mutation routes were added. The migrated data contract and
compatibility import contain no Flask import, route decorator, HTTP method
declaration, or dashboard route wiring.

## Live/Paper/Shadow/Risk/Broker/Execution Status

No live, paper, shadow, risk, broker, or execution behavior was changed. The
canonical data contract imports only stdlib dataclass, datetime, and typing
helpers. The compatibility path imports only the canonical QRE data package
contract.

## Scanner Classification

The existing scanner classifications remain:

```text
packages/qre_data/ -> QRE
data/contracts.py -> QRE
dashboard/ -> control-plane
```

The compatibility import creates no cross-domain edge because both the legacy
and canonical data contract modules are QRE-domain modules. Existing
legacy/report-only findings remain visible.

## Validation Commands

```powershell
pytest tests/architecture/test_package_migration_007_qre_data_read_only_boundary.py -q
pytest tests/architecture/test_package_migration_001_target_layout.py -q
pytest tests/unit/test_data_contracts.py -q
pytest tests/unit/test_adapter_protocols.py -q
pytest tests/unit/test_market_repository.py -q
pytest tests/unit/test_macro_repository.py -q
pytest tests/unit/test_yfinance_adapter.py -q
pytest tests/unit/test_fred_adapter.py -q
pytest tests/architecture/test_domain_boundary_smoke.py -q
pytest tests/architecture/test_domain_import_scanner.py -q
pytest tests/architecture -q
pytest tests/unit/test_ci_path_classifier.py -q
python -m reporting.architecture_import_scan --format summary
```

## Rollback Plan

Revert the PACKAGE-MIGRATION-007 commit. That restores `data.contracts` as the
direct implementation and removes the canonical `packages.qre_data.contracts`
seed without changing repositories, adapters, cache files, dashboard routes,
frozen outputs, or execution behavior.

## Package Migration Decision

Selected value: `PACKAGE_MIGRATION_CONTINUES_WITH_BOUNDED_NEXT_UNIT`

Rationale: QRE data now has one canonical read-only data contract seed with
compatibility preserved and without repository, adapter, cache, dashboard route,
frozen output, or execution behavior changes. The next safest bounded package
migration is QRE research because the target package remains scaffold-only and
can be evaluated for a read-only research contract seed without moving all
research orchestration or strategy logic.

Exact next recommended unit:
PACKAGE-MIGRATION-008 - Migrate QRE Research Read-Only Package Boundary.
