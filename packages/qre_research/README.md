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
The ADE-QRE-017N prior-failure retrieval surface lives in
`research.qre_prior_failure_retrieval` and links theses back to prior
failures, dead zones, and prior actions as provenance-backed context only.
The ADE-QRE-017O opportunity-research-value surface lives in
`research.qre_opportunity_research_value` and combines thesis readiness,
evidence density, prior-failure context, and proposal-only discovery signals
into a deterministic expected-research-value score for prioritization only.
The pure weighting helper for that surface lives in
`packages.qre_research.opportunity_value`.
The ADE-QRE-017P routing-baseline-comparison surface lives in
`research.qre_routing_baseline_comparison` and compares the current
context-only router ordering against trivial deterministic baselines without
granting campaign authority.
ADE-QRE-019 adds the bounded automated research-only generation pipeline in
`packages.qre_research.automated_strategy_generation`. That pipeline writes
only to isolated generated-research surfaces outside `research/**` and does
not grant paper, shadow, live, broker, risk, or deployment authority.
ADE-QRE-020 adds the bounded automated hypothesis-generation pipeline in
`packages.qre_research.automated_hypothesis_generation`. That pipeline writes
only to isolated generated-hypothesis surfaces outside `research/**`,
preserves one resolved thesis catalog, and never generates executable strategy
code directly.

## Source of Truth / Authority Boundary

`registry.py` remains the protected manual source of truth for manually
maintained strategy registration, strategy implementations remain in
`agent/backtesting/strategies.py`, and research orchestration remains in
`research/run_research.py` until explicitly migrated. ADE-QRE-019 adds a
generated-strategy input registry outside `research/**`; a canonical resolved
catalog composes that generated input with the protected manual registry for
research-only consumption. The universe contract is canonical in
`packages.qre_research.universe` with `research.universe` retained as the
compatibility import path.

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
- Deterministic ADE-QRE-019 research-only strategy generation, validation,
  generated-registry admission, and resolved-catalog composition outside
  `research/**`.
- Deterministic ADE-QRE-020 research-only hypothesis generation, admission,
  and resolved-thesis-catalog composition outside `research/**`.

## Forbidden Contents

- New strategy families or brute-force parameter expansion.
- Arbitrary strategy code generation or unconstrained LLM generation.
- Executable strategy generation inside ADE-QRE-020.
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
