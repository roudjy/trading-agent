# ADE-QRE-027 Bounded Hypothesis-To-Strategy Synthesis

This document describes the bounded research-only lifecycle added for
generated QRE hypotheses. It does not authorize strategy registration,
paper, shadow, live, broker, risk, capital allocation, or deployment.

## Scope

The lifecycle is intentionally fail-closed:

1. bounded hypothesis generation writes governed hypothesis artifacts
2. orchestration executes the generator as a first-class work class
3. trusted-loop lifecycle sidecars materialize feasibility, routing,
   sampling, reasons, evidence gaps, failure actions, and memory
4. synthesis readiness evaluates generated-hypothesis evidence and
   reports exact missing empirical evidence
5. bounded strategy synthesis may only produce a disabled research-only
   candidate when readiness is `ELIGIBLE`

## Canonical Surfaces Used

- `packages/qre_research/automated_hypothesis_generation.py`
- `packages/qre_research/autonomous_orchestration.py`
- `packages/qre_research/hypothesis_lifecycle.py`
- `packages/qre_research/bounded_strategy_synthesis.py`
- `research/synthesis_gate.py`
- `generated_research/hypotheses/**`
- `generated_research/strategies/**`

## Safety Properties

- hypothesis generation is deterministic, bounded, and idempotent
- duplicate suppression happens before governed persistence
- trusted-loop artifacts preserve fixture-proof versus empirical-evidence
  separation
- synthesis readiness never upgrades missing empirical evidence to success
- research-only strategy candidates stay:
  - `enabled: false`
  - `bundle_active: false`
  - `active_discovery: false`
  - `paper_ready: false`
  - `shadow_ready: false`
  - `live_eligible: false`
- no writes occur to `registry.py` or `agent/backtesting/strategies.py`
- no paper, shadow, live, broker, risk, execution, capital, or
  deployment paths are touched

## Current Limitation

Generated-hypothesis readiness can materialize the exact missing
evidence, but fixture or repository-structure proof is not treated as
empirical validation. When OOS, transaction-cost, null-model, stability,
or regime evidence is missing, synthesis remains
`INELIGIBLE_EVIDENCE`.
