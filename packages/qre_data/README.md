# QRE Data Package

## Purpose

`packages/qre_data` is the target package boundary for research data contracts,
market-data access abstractions, and deterministic data-source metadata.

## Current Status

Status: active read-only seed plus ADE-QRE-003 local cache manifest helper and
ADE-QRE-004 source quality readiness helper. The package owns the immutable
market and macro data contract types in `packages.qre_data.contracts`, the
deterministic read-only cache manifest in `packages.qre_data.cache_manifest`,
and the manifest-only readiness report in
`packages.qre_data.source_quality_readiness`. Current data repositories,
adapters, fetchers, cache behavior, and dashboard consumers remain in their
existing paths.

## Source of Truth / Authority Boundary

`packages.qre_data.contracts` is the canonical namespace for immutable data
contract types historically exposed by `data.contracts`.

Existing `data/` repositories, adapters, fetchers, cache files, and dashboard
consumers remain the source of truth until each surface is migrated by a
bounded unit.

`packages.qre_data.cache_manifest` is a read-only reporter over existing local
cache files only. It does not fetch, backfill, modify cache files, or change
research output contracts.

`packages.qre_data.source_quality_readiness` is a read-only reporter over the
cache manifest only. It does not activate vendor sources, infer alpha, fetch
data, modify cache files, or change research output contracts.

## Allowed Future Contents

- Data contract types and metadata.
- Read-only repository abstractions and adapter interfaces.
- Deterministic data validation helpers.
- Read-only local cache manifests and coverage summaries.
- Read-only source identity and source quality readiness summaries over
  existing manifest data.

## Forbidden Contents

- Strategy logic, registry definitions, or research orchestration.
- Dashboard route handlers or ADE governance authority.
- Artifact schema mutation without artifact-package approval.
- Live broker connections, order placement, capital allocation, or live risk
  behavior.

## Migration Preconditions

- Data consumers and producers are inventoried.
- External IO behavior remains unchanged or is isolated behind compatibility
  imports.
- Deterministic tests cover migrated contracts.

## Current Compatibility Policy

Existing imports from `data.contracts` remain compatible for the immutable
data contract types. The compatibility module imports and re-exports the
canonical package classes.

Other existing `data/` imports remain authoritative until migrated by a
separate bounded unit.

## Activation Status

Activation status: read-only data contract seed, read-only local cache
manifest, and read-only source quality readiness only.
