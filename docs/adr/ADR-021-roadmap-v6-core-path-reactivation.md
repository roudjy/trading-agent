# ADR-021: Roadmap v6 Minimal Core Path Reactivation

## Status

Accepted.

## Context

The roadmap reset completed the Research-Quality Hardening Sprint,
minimal v3.15.16 Intelligent Routing, minimal v3.15.17 Sampling
Intelligence, minimal v3.15.18 Observability, and minimal v3.15.19
Hypothesis Discovery. After v3.15.19, the queue intentionally stopped
at the operator review gate.

On 2026-05-21, the operator authorized reactivating the next minimal
Roadmap v6 core path:

1. v3.15.20 minimal Failure to Action Mapping.
2. v3.16.x minimal Adaptive Research Learning.

This ADR records that operator decision as a governance artifact. It
does not activate Addendum 1, Addendum 2, Addendum 3, v4.x, v5.x, or
v6.x.

## Decision

Reactivate only these two queue items:

1. **Minimal v3.15.20 Failure to Action Mapping slice**.
   This item may introduce deterministic failure taxonomies, bounded
   next-action recommendations, and read-only reason records.
2. **Minimal v3.16.x Adaptive Research Learning path**.
   This item may introduce deterministic, evidence-backed campaign
   feedback metrics and read-only learning context. Any scoring must be
   deterministic and evidence-backed.

The v3.15.20 item is the next eligible active item. The v3.16.x item is
blocked by v3.15.20 and may not begin until v3.15.20 is merged and the
queue state is updated.

## Boundaries

The following remain out of scope:

- Addendum 1, Addendum 2, and Addendum 3 implementation activation.
- v4.x shadow trading.
- v5.x paper trading.
- v6.x live trading.
- Retrieval ranking, knowledge graph, HMM, Semi-Markov, Bayesian,
  Tree-of-Thoughts, portfolio expansion, and hidden ML systems unless a
  future accepted ADR explicitly activates them.
- Executable strategy generation.
- Strategy mutation.
- Paper, shadow, live, broker, risk, or execution behavior.
- Frozen contract mutation of `research_latest.json` or
  `strategy_matrix.csv`.

## Consequences

The development work queue seed is updated so that:

- prior minimal v3.15.16 through v3.15.19 work is recorded as done;
- the STOP gate is recorded as satisfied by the operator decision;
- v3.15.20 is the only ready item;
- v3.16.x is blocked by v3.15.20;
- no Addendum 1/2/3 item and no v4/v5/v6 item is active.

Feature PRs that implement the reactivated items must remain minimal,
deterministic, read-only where specified, and independently reviewable.
