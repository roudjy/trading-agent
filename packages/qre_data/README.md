# QRE Data Package

## Purpose

`packages/qre_data` is the target package boundary for research data contracts,
market-data access abstractions, and deterministic data-source metadata.

## Current Status

Status: scaffold-only. Current data modules remain under `data/`.

## Source of Truth / Authority Boundary

Existing `data/` contracts, repositories, adapters, and fetchers remain the
source of truth until a bounded data-package migration is authorized.

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

Existing `data/` imports remain authoritative. This scaffold exports no runtime
API.

## Activation Status

Activation status: scaffold-only.
