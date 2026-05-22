# ADE Governance Package

## Purpose

`packages/ade_governance` is the target package boundary for Autonomous
Development Environment governance contracts, authority vocabulary, and
deterministic governance support surfaces.

## Current Status

Status: active extracted seed content. PACKAGE-MIGRATION-002 re-homed the
immutable architecture import scan contracts under
`packages.ade_governance.import_contracts.architecture_import` while scanner
execution remains in `reporting/architecture_import_scan.py`.

## Source of Truth / Authority Boundary

ADE governance authority remains defined by the governance documents,
`reporting.execution_authority.classify(...)`, and existing reporting modules
until each surface is migrated by a bounded package-migration unit.

## Allowed Future Contents

- Immutable ADE governance contract vocabulary.
- Read-only governance report dataclasses and schema contracts.
- Compatibility-safe governance support modules selected by package migration.

## Forbidden Contents

- QRE strategy definitions, registry entries, research orchestration, or
  artifact generation.
- Dashboard route handlers or frontend behavior.
- Live, paper, shadow, risk, broker, or order-execution behavior.
- Broad runtime moves from `reporting/` without an exact migration unit.

## Migration Preconditions

- Public contracts are compatibility-pinned at the old import path.
- Scanner policy and exact legacy/report-only findings remain visible.
- Governance authority semantics are unchanged.
- Architecture and governance tests pass without weakening hooks.

## Current Compatibility Policy

Existing `reporting/` paths remain compatible surfaces unless a future unit
explicitly replaces them. Current seed content is importable as
`packages.ade_governance`. The EXTRACT-002 module path
`packages.ade_governance.architecture_import_contracts` remains a compatibility
shim.

## Activation Status

Activation status: active extracted seed content.
