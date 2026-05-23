# QRE Diagnostics Package

## Purpose

`packages/qre_diagnostics` is the target package boundary for QRE diagnostic
read models, health evidence, and research observability helpers.

## Current Status

Status: active read-only boundary. The canonical diagnostics path contract
lives in `packages/qre_diagnostics/paths.py`. ADE-QRE-006 adds
`packages/qre_diagnostics/research_diagnostics_loop.py`, a read-only
diagnostics-loop digest over existing sidecars. Other diagnostics remain under
`research/diagnostics/` and related research observability modules.

## Source of Truth / Authority Boundary

The canonical diagnostics path contract is authoritative under
`packages.qre_diagnostics.paths`. The ADE-QRE-006 diagnostics loop is
authoritative under `packages.qre_diagnostics.research_diagnostics_loop`.
Existing diagnostics builders remain authoritative in `research/diagnostics/`.
Diagnostics are read-only evidence surfaces and do not own trade decisions or
execution behavior.

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

`research.diagnostics.paths` remains a compatibility import path that re-exports
the canonical `packages.qre_diagnostics.paths` public contract.

## Activation Status

Activation status: active read-only diagnostics boundary only.
