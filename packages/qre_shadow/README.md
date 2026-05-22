# QRE Shadow Package

## Purpose

`packages/qre_shadow` is the target package boundary for future shadow-mode
observation contracts.

## Current Status

Status: future-only and inactive until Roadmap v4.x.

## Source of Truth / Authority Boundary

No shadow runtime authority is transferred by this scaffold. Shadow behavior is
not active in this package and must remain inactive until a Roadmap v4.x unit
explicitly authorizes it.

## Allowed Future Contents

- Shadow observation contracts after Roadmap v4.x authorization.
- Read-only shadow evidence schemas.
- Compatibility shims selected by a named shadow migration unit.

## Forbidden Contents

- Paper trading, live trading, broker mutation, order placement, or capital
  allocation.
- Live risk behavior.
- Dashboard mutation routes.
- QRE strategy or registry definitions.

## Migration Preconditions

- Roadmap v4.x shadow readiness is active and approved.
- Shadow contracts are read-only and deterministic.
- Execution-sensitive scanner classification remains explicit.

## Current Compatibility Policy

No compatibility import exists. This scaffold exports no runtime API.

## Activation Status

Activation status: future-only and inactive until Roadmap v4.x.
