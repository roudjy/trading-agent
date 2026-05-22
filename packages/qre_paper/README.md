# QRE Paper Package

## Purpose

`packages/qre_paper` is the target package boundary for future paper-trading
contracts and paper readiness implementation.

## Current Status

Status: future-only and inactive until Roadmap v5.x.

## Source of Truth / Authority Boundary

No paper runtime authority is transferred by this scaffold. Existing paper
readiness and ledger concepts remain in their current modules until Roadmap
v5.x authorizes a bounded paper migration.

## Allowed Future Contents

- Paper-trading contracts after Roadmap v5.x authorization.
- Paper ledger schemas and deterministic paper-readiness adapters.
- Compatibility shims selected by a named paper migration unit.

## Forbidden Contents

- Live order placement, broker mutation, capital allocation, or live risk
  behavior.
- Shadow runtime activation before Roadmap v4.x.
- Dashboard mutation routes.
- QRE strategy or registry definitions.

## Migration Preconditions

- Roadmap v5.x paper readiness is active and approved.
- Paper behavior is deterministic and separated from live broker mutation.
- Execution-sensitive scanner classification remains explicit.

## Current Compatibility Policy

No compatibility import exists. This scaffold exports no runtime API.

## Activation Status

Activation status: future-only and inactive until Roadmap v5.x.
