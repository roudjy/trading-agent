# QRE Diagnostics Package

## Purpose

`packages/qre_diagnostics` is the target package boundary for QRE diagnostic
read models, health evidence, and research observability helpers.

## Current Status

Status: scaffold-only. Current diagnostics remain under `research/diagnostics/`
and related research observability modules.

## Source of Truth / Authority Boundary

Existing diagnostics modules remain authoritative. Diagnostics are read-only
evidence surfaces and do not own trade decisions or execution behavior.

## Allowed Future Contents

- Diagnostic path contracts and read models.
- Deterministic health and observability evidence helpers.
- Read-only diagnostic adapters for the control plane.

## Forbidden Contents

- Strategy selection, registry mutation, or research orchestration.
- Dashboard route handlers.
- Live, paper, shadow, risk, broker, order-execution, or capital-allocation
  behavior.

## Migration Preconditions

- Diagnostics imports remain free of execution-domain dependencies.
- Existing observability static import tests continue to pass.
- Control-plane consumers use read-only contracts.

## Current Compatibility Policy

Existing `research/diagnostics/` imports remain authoritative. This scaffold
exports no runtime API.

## Activation Status

Activation status: scaffold-only.
