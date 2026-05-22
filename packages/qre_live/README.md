# QRE Live Package

## Purpose

`packages/qre_live` is the target package boundary for possible future live
trading contracts after all prior governance, shadow, and paper gates pass.

## Current Status

Status: hard-disabled until Roadmap v6.x and explicit operator approval.

## Source of Truth / Authority Boundary

No live runtime authority is transferred by this scaffold. No live order
placement, broker mutation, capital allocation, or live risk behavior is
authorized by this scaffold.

## Allowed Future Contents

- Future live-trading contract stubs only after Roadmap v6.x and explicit
  operator approval.
- Read-only safety documentation for live readiness gates.
- Compatibility shims only after a separately approved live migration unit.

## Forbidden Contents

- Live order placement.
- Broker mutation.
- Capital allocation.
- Live risk behavior.
- Dashboard mutation routes.
- Shadow, paper, or live activation code.
- QRE strategy or registry definitions.

## Migration Preconditions

- Roadmap v6.x is active.
- Explicit operator approval is recorded.
- Shadow and paper gates have completed successfully.
- Live safety, risk, broker, and rollback controls are approved before any
  executable code is introduced.

## Current Compatibility Policy

No compatibility import exists. This scaffold exports no runtime API.

## Activation Status

Activation status: hard-disabled until Roadmap v6.x and explicit operator
approval.
