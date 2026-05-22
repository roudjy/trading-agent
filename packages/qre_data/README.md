# QRE Data Package

## Purpose

`packages/qre_data` is the target package boundary for research data contracts,
market-data access abstractions, and deterministic data-source metadata.

## Current Status

Status: active read-only seed. The package owns the immutable market and macro
data contract types in `packages.qre_data.contracts`. Current data
repositories, adapters, fetchers, cache behavior, and dashboard consumers
remain in their existing paths.

## Source of Truth / Authority Boundary

`packages.qre_data.contracts` is the canonical namespace for immutable data
contract types historically exposed by `data.contracts`.

Existing `data/` repositories, adapters, fetchers, cache files, and dashboard
consumers remain the source of truth until each surface is migrated by a
bounded unit.

## Allowed Future Contents

- Data contract types and metadata.
- Read-only repository abstractions and adapter interfaces.
- Deterministic data validation helpers.

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

Activation status: read-only data contract seed only.
