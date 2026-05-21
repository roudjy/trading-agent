# ADR-019 — Hypothesis Discovery doctrine and scoring spec

Status: **Accepted** — 2026-05-21
Predecessor: ADR-014 (truth authority settlement), ADR-018
(roadmap execution reset).
Gates: v3.15.19 minimal Hypothesis Discovery slice.

## Context

Roadmap v6 v3.15.19 introduces autonomous Hypothesis Discovery —
the first layer that decides *what* deserves research, not just
how to execute research. The roadmap text illustrates
`opportunity_probability_score` with a JSON example but does not
axiomatise it. Without axioms, the score can drift into hidden
ranking authority.

The risk is concrete: a "score" that consumes diagnostic outputs,
retrieved context, and source-usefulness ledgers will, by default,
become the de-facto promotion rank. The roadmap doctrine
("Discovery proposes; the funnel/policy promotes") then exists
only in prose.

This ADR settles the doctrine and the score's axioms so the v3.15.19
implementation cannot drift.

## Decision

### Discovery is proposal-only

Hypothesis Discovery emits **seeds**, never candidates and never
promotions. A seed is a structured proposal that names:

- a behaviour family;
- a strategy mapping;
- a feasible preset mapping;
- an exploration priority;
- the diagnostics that should challenge it;
- the null-model the seed must beat to escalate.

A seed has no execution authority, no promotion authority, and no
capital authority. Seeds become candidates only via the funnel
policy
([`research/campaign_funnel_policy.py`](../../research/campaign_funnel_policy.py)
and ADR-014 §A) and the existing campaign mechanics, which this
ADR does **not** modify.

### `opportunity_probability_score` axioms

The score, when implemented, must satisfy all of the following.

1. **Deterministic.** For identical inputs (data window,
   diagnostic outputs, preset universe, retrieval context), the
   score is byte-identical across runs.
2. **Bounded.** The score is in the closed interval `[0, 1]`. No
   raw probabilities, no log-odds, no unbounded transforms at the
   public boundary.
3. **Monotone in stated inputs.** Increasing any *positive*
   input variable (e.g., null-model beat margin, evidence quorum
   count) and holding others fixed must not decrease the score.
   Increasing any *negative* input variable (e.g., entropy in a
   directional regime, left-tail fragility) and holding others
   fixed must not increase the score.
4. **Independent of execution-side state.** The score consumes
   research-side artifacts only. It must not read from
   `research/research_latest.json`, `research/strategy_matrix.csv`,
   broker / live / paper / shadow / execution state, or any
   capital-allocation surface.
5. **Inspectable.** The score's inputs and intermediate transforms
   are emitted to a scoring-reason record
   ([`research_quality_sprint_plan.md`](../governance/research_quality_sprint_plan.md)
   §10).
6. **Falsifiable on noise.** Under the null-pipeline integration
   test
   ([`research_quality_sprint_plan.md`](../governance/research_quality_sprint_plan.md)
   §8), the score distribution on surrogate data must be
   statistically indistinguishable from the score distribution on
   random shuffles of the surrogate. The test pins this as a
   property test.
7. **Score ≠ probability.** The number is *expected research
   value*, not prediction certainty, alpha certainty, or ML
   confidence. Any downstream consumer that treats it as a
   probability is in doctrinal violation; the consumer is
   responsible, not the score.

### What Discovery may consume

Only the **three active diagnostics** declared in
[`roadmap_scope_status.md`](../governance/roadmap_scope_status.md)
§5.1: null-model, tail asymmetry, entropy structure. Diagnostics
beyond those three are deferred and must not feed Discovery until
they pass the promote-or-retire rule.

Discovery may also consume:

- the existing preset universe ([`research/presets.py`](../../research/presets.py));
- the existing strategy hypothesis catalog
  ([`research/strategy_hypothesis_catalog.py`](../../research/strategy_hypothesis_catalog.py));
- the multiplicity ledger
  ([`research_quality_sprint_plan.md`](../governance/research_quality_sprint_plan.md)
  §6);
- the diagnostic utility ledger (planned as part of the v3.15.19
  slice).

### What Discovery may NOT consume

- Knowledge graph outputs (Addendum 2; deferred).
- Hybrid retrieval / RRF / cross-encoder rerank outputs
  (Addendum 2; deferred).
- State / sequential model outputs (Addendum 2; deferred).
- Source Usefulness Ledger (Addendum 3; deferred).
- Any external/public data not flowing through the existing three
  active sources.
- Any execution-side artifact.
- Frozen contracts.

### Seed contract

A seed emitted by Discovery is a JSON record under
`logs/hypothesis_discovery/seeds/` (or an equivalent path defined
by the v3.15.19 implementation PR). Minimum fields:

```text
seed_id                     # deterministic hash of (inputs_digest, kind, family)
generated_at_utc
behavior_family             # closed vocab (defined in v3.15.19)
strategy_mapping_ref        # pointer to registry/catalog
preset_feasibility_ref      # pointer
opportunity_probability_score # bounded [0, 1]
required_diagnostics        # which diagnostics must challenge this
required_null_model         # which null model must be beaten
multiplicity_ledger_event_id  # the multiplicity_ledger entry written
                              # by Discovery for this seed
scoring_reason_record_id    # the reason record
schema_version: "v1"
```

### Promotion contract

A seed promotes to candidate only via the existing funnel policy
+ campaign mechanics. This ADR does not modify the funnel /
campaign / candidate-lifecycle authorities defined in ADR-014 §A.

### Tests required (when v3.15.19 implementation lands)

- Score-axiom property tests (one test per axiom in this §).
- Null-pipeline integration test must remain green with
  Discovery enabled.
- Append-only test on the seed log.
- Determinism test (two runs on the same inputs produce
  byte-identical seed sets).

## Hard constraints preserved

- ADR-014 unchanged.
- ADR-015 unchanged.
- ADR-017 unchanged; Step 5 remains permanently blocked.
- No frozen-contract mutation.
- No live / paper / shadow / risk / broker / execution behaviour
  change.
- No hidden ML; no stochastic routing; no adaptive scoring.

## Consequences

Positive:

- The most consequential v3.x layer ships under doctrinal
  constraint, not implicit authority.
- Score axioms become testable; the null-pipeline integration test
  becomes a real falsifier.
- Operator can reason about Discovery in one paragraph.

Negative / accepted:

- The score's expressive power is bounded by the three active
  diagnostics. This is acceptable: more breadth is added only on
  KPI evidence.

## Promotion

This ADR was promoted from `docs/adr/_drafts/` to
`docs/adr/ADR-019-hypothesis-discovery-doctrine.md` on
**2026-05-21** via the operator-driven governance-bootstrap PR
that gates the v3.15.19 minimal Hypothesis Discovery slice.
Status was flipped from **Draft** to **Accepted** at the same
time; the doctrine and scoring-axiom content above is unchanged
from the draft.

## Cross-references

- [`docs/governance/roadmap_scope_status.md`](../governance/roadmap_scope_status.md)
- [`docs/governance/research_quality_sprint_plan.md`](../governance/research_quality_sprint_plan.md)
- [`docs/governance/research_quality_kpis.md`](../governance/research_quality_kpis.md)
- [`docs/adr/_drafts/ADR-018-roadmap-execution-reset.md`](_drafts/ADR-018-roadmap-execution-reset.md)
- [`docs/adr/_drafts/ADR-020-paper-shadow-live-separation.md`](_drafts/ADR-020-paper-shadow-live-separation.md)
- [`docs/adr/ADR-014-truth-authority-settlement.md`](ADR-014-truth-authority-settlement.md)
