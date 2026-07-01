# QRE Empirical Research Flywheel

## Purpose

This flow closes the bounded QRE research loop for generated hypotheses without
activating paper, shadow, live, broker, risk, capital, or deployment paths.

The chain is:

1. generated hypothesis lifecycle materialization
2. canonical orchestration replay
3. empirical campaign execution on an already-admitted preregistered cell
4. canonical empirical evidence pack materialization
5. synthesis readiness reassessment
6. bounded research-only strategy synthesis or fail-closed next action

## Entrypoints

- Hypothesis lifecycle: `packages/qre_research/hypothesis_lifecycle.py`
- Empirical evidence pack: `packages/qre_research/empirical_evidence_pack.py`
- Empirical flywheel: `packages/qre_research/empirical_research_flywheel.py`
- Synthesis readiness: `research/synthesis_gate.py`
- Bounded synthesis: `packages/qre_research/bounded_strategy_synthesis.py`

## Current canonical behavior

- Generated hypothesis feasibility, routing, and sampling now bridge to the
  authoritative readiness artifacts instead of relying only on stale generation
  snapshots.
- The first generated hypothesis, `cross_sectional_momentum_v0`, resolves to:
  feasibility `ready`, routing `ready`, sampling `blocked`,
  blocker `usable_history_below_minimum_policy_span`,
  next action `launch_data_oos_capacity_expansion`.
- The canonical empirical evidence pack is derived from the existing bounded
  preregistered campaign executor and never fabricates empirical support.
- Synthesis remains fail-closed unless the empirical evidence pack disposition
  is `READY_FOR_SYNTHESIS`.

## Safety invariants

- Generated strategy candidates remain disabled:
  `enabled=false`, `bundle_active=false`, `active_discovery=false`,
  `paper_ready=false`, `shadow_ready=false`, `live_eligible=false`.
- Frozen public contracts remain untouched:
  `research/research_latest.json`, `research/strategy_matrix.csv`.
- No new trading authority is introduced.
- No new network, subprocess code generation, or arbitrary execution path is
  introduced.

## Functional interpretation

On current repository data the flywheel can:

- evaluate the generated hypothesis chain to the exact blocker;
- execute one bounded empirical campaign on the existing ready cell;
- materialize a reusable evidence pack;
- return `INELIGIBLE_EVIDENCE` for synthesis when the campaign still ends with
  `NEEDS_MORE_EVIDENCE`.

This is a valid research outcome. It means the next bounded action is data/OOS
capacity expansion, not forced synthesis.
