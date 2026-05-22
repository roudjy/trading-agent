# QRE Research Package

## Purpose

`packages/qre_research` is the target package boundary for Quant Research
Engine hypothesis execution, strategy research orchestration, and research
run-domain contracts.

## Current Status

Status: scaffold-only. Current QRE research runtime remains in `research/`,
`agent/backtesting/`, `strategies/`, and `registry.py`.

## Source of Truth / Authority Boundary

`registry.py` remains the single source of truth for strategy registration,
strategy implementations remain in `agent/backtesting/strategies.py`, and
research orchestration remains in `research/run_research.py` until explicitly
migrated.

## Allowed Future Contents

- Bounded QRE research contracts and read-only facades.
- Research orchestration modules only after frozen-output compatibility gates.
- Hypothesis lifecycle code selected by a named migration unit.

## Forbidden Contents

- New strategy families or brute-force parameter expansion.
- Dashboard route handlers or ADE governance authority.
- Data fetchers, artifact writers, diagnostics, policy, and execution behavior
  unless separately authorized for this package.
- Live, paper, shadow, risk, broker, or order-execution behavior.

## Migration Preconditions

- Research outputs remain deterministic and schema-compatible.
- Strategy registry authority remains singular.
- Import scanner findings are understood for the selected module.
- Frozen contracts and regression pins are unchanged.

## Current Compatibility Policy

Existing QRE imports under `research/`, `agent/backtesting/`, `strategies/`,
and `registry.py` remain authoritative. This scaffold exports no runtime API.

## Activation Status

Activation status: scaffold-only.
