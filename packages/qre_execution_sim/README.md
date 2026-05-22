# QRE Execution Simulation Package

## Purpose

`packages/qre_execution_sim` is the target package boundary for future
research-only execution simulation contracts.

## Current Status

Status: future-only and inactive. Current execution-adjacent simulation code
remains in existing `execution/`, `research/`, and legacy `agent/` paths.
This package is intentionally README-only until a separately approved migration
unit authorizes a specific read-only contract.

## Source of Truth / Authority Boundary

No execution simulation authority is transferred by this scaffold. Existing
paper simulation and execution protocol modules remain authoritative until a
separate execution-simulation migration unit is approved.

## Allowed Future Contents

- Deterministic simulation contracts for research replay.
- Non-broker simulation adapters with no external mutation.
- Compatibility shims selected by a named migration unit.

## Forbidden Contents

- Live order placement, broker mutation, or capital allocation.
- Live risk behavior or production trading controls.
- Dashboard mutation routes.
- QRE strategy or registry definitions.

## Migration Preconditions

- Simulation behavior is proven deterministic and isolated from broker/live
  paths.
- Execution-sensitive scanner classification remains explicit.
- Paper, shadow, and live activation gates remain inactive.

## Current Compatibility Policy

Existing execution simulation imports remain authoritative. This scaffold
exports no runtime API. Adding importable Python modules under
`packages/qre_execution_sim` requires a named package-migration unit and tests
proving no broker, live, paper, shadow, risk, or order-execution behavior was
activated.

## Activation Status

Activation status: future-only and inactive.
