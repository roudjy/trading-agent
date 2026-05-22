# Control Plane App

## Purpose

`apps/control-plane` is the target application boundary for operator-facing
control-plane UI and API surfaces.

## Current Status

Status: scaffold-only. Current runtime dashboard and frontend code remains in
`dashboard/` and `frontend/`.

## Source of Truth / Authority Boundary

Dashboard routes, API schemas, and frontend behavior remain in their existing
locations until a bounded migration unit explicitly moves them. This scaffold
does not own QRE research logic, ADE governance decisions, or execution
behavior.

## Allowed Future Contents

- Control-plane route shells after route-specific migration approval.
- Read-only adapters to ADE and QRE package contracts.
- Frontend application code after a dedicated control-plane migration unit.

## Forbidden Contents

- New dashboard mutation routes.
- QRE strategy, registry, research orchestration, or artifact-generation logic.
- ADE governance authority implementations.
- Live, paper, shadow, risk, broker, or order-execution behavior.

## Migration Preconditions

- Existing route behavior and response schemas are pinned by tests.
- The target route has a documented source and owner.
- Scanner classification for the moved path is explicit.
- Frozen research outputs and protected paths remain unchanged.

## Current Compatibility Policy

Existing `dashboard/` and `frontend/` imports remain authoritative. This
directory provides no compatibility import and no executable runtime surface.

## Activation Status

Activation status: scaffold-only.
