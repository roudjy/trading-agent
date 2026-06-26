# QRE Research Package

## Purpose

`packages/qre_research` is the target package boundary for Quant Research
Engine hypothesis execution, strategy research orchestration, and research
run-domain contracts.

## Current Status

Status: active read-only boundary seed plus ADE-QRE-005 research memory helper
and ADE-QRE-014J retrieval-coverage reporter.
The canonical research universe contract now lives in
`packages.qre_research.universe`; deterministic local artifact indexing and
retrieval live in `packages.qre_research.research_memory`; current QRE
research orchestration remains in `research/`, `agent/backtesting/`,
`strategies/`, and `registry.py`.
The ADE-QRE-017L behavior thesis registry lives in
`research.qre_behavior_thesis_registry` and remains a read-only governance /
research-intelligence registry rather than an execution authority.
The ADE-QRE-017M thesis-evidence surface lives in
`research.qre_behavior_thesis_evidence` and keeps supporting,
contradicting, and unresolved thesis evidence explicit with provenance.

## Source of Truth / Authority Boundary

`registry.py` remains the single source of truth for strategy registration,
strategy implementations remain in `agent/backtesting/strategies.py`, and
research orchestration remains in `research/run_research.py` until explicitly
migrated. The universe contract is canonical in `packages.qre_research.universe`
with `research.universe` retained as the compatibility import path.

`packages.qre_research.research_memory` is a read-only local artifact index and
retrieval helper. It does not use embeddings, LLM authority, graph databases,
network calls, subprocess calls, campaign mutation, routing mutation, or
strategy generation.

`packages.qre_research.retrieval_coverage` measures whether trusted-loop
reasons, failures, blockers, and actions can be retrieved with explicit local
links. It is an operator-readable coverage report only; retrieval remains
context, not authority.

## Allowed Future Contents

- Bounded QRE research contracts and read-only facades.
- Deterministic read-only research memory over existing local artifacts.
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
and `registry.py` remain authoritative except for the bounded universe contract,
which is now canonical at `packages.qre_research.universe`. The historical
`research.universe` path remains a compatibility shim and must preserve the
public API.

## Activation Status

Activation status: read-only universe boundary and read-only research memory
active; research orchestration and strategy authority remain unmigrated.
