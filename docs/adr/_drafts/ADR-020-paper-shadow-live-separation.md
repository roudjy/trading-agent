# ADR-020 — Paper / Shadow / Live separation doctrine

Status: **Draft** — 2026-05-21
Predecessor: ADR-014 (truth authority settlement),
ADR-015 (Claude agent governance; Level 6 permanently disabled),
ADR-017 (Step 5 design + readiness; Step 5 implementation remains
blocked), ADR-018 (roadmap execution reset).
Reaffirms: every constraint already enforced by
[`no_touch_paths.md`](../../governance/no_touch_paths.md),
[`execution_authority.md`](../../governance/execution_authority.md),
[`strategic_roadmap_execution_mandate.md`](../../governance/strategic_roadmap_execution_mandate.md),
and `automation/live_gate.py`. Adds doctrine; subtracts nothing.

## Context

The QRE today separates paper / shadow / live correctly in code
and hooks. The separation is enforced by multiple layers
(no-touch, agent allowlist, execution-authority classifier,
branch-protection, CODEOWNERS, autonomy ladder, ADR-017 Step 5
block). But the doctrinal expression of *why* the separation
exists, and *what may never feed live*, is scattered across
several docs.

As Addendum 1/2/3 surfaces accumulate (even as deferred reference
doctrine), an implicit risk grows: a future agent / operator / PR
might wire a diagnostic / retrieval / source / knowledge-graph /
score output into the paper or live order path, on the grounds
that "the doctrine doesn't say it can't". The doctrine should say
it cannot.

## Decision

### Three separations, three readiness ADRs

Paper, shadow, and live are three separate maturity stages. Each
requires its own readiness ADR before any QRE/ADE surface may
feed it.

- **Paper** (v5.x): requires a future
  `ADR-021-paper-readiness.md` that includes the paper-readiness
  checklist artifact spec (this PR ships the spec at
  [`research_quality_sprint_plan.md`](../../governance/research_quality_sprint_plan.md)
  §9), the cost realism criteria, and the drift kill-switch
  definitions.
- **Shadow** (v4.x): requires a future
  `ADR-022-shadow-readiness.md` that defines real-time signal
  parity, timing-drift tolerance, and shadow exit criteria
  ("graduate to paper" and "kill candidate").
- **Live** (v6.x): requires a future
  `ADR-023-live-readiness.md` that defines tiny-capital deployment
  gates, live anomaly detection, and the explicit operator
  authorisation surface. Level 6 autonomy remains permanently
  disabled.

### Cross-cutting doctrine

The following clauses are doctrinal invariants. They hold whether
or not any of Addendums 1/2/3 are reactivated.

1. **Diagnostics never feed live orders.** Any output of a
   diagnostic family (the three active diagnostics plus any
   future reactivated ones) is research context only. It may not
   be read by `automation/live_gate.py`, `automation/**`,
   `broker/**`, `agent/execution/**`, `live/**`, `paper/**`,
   `shadow/**`, `trading/**`, or `execution/**`.
2. **Retrieval never feeds live orders.** Knowledge graph
   outputs, hybrid-retrieval outputs, RRF outputs, cross-encoder
   outputs, ToT-bounded outputs may not be read by any of the
   paths above. This holds even when these surfaces become active
   after a reactivation ADR.
3. **State / sequential models never feed live orders.** Markov,
   HMM, Semi-Markov, particle filter, FSM, queueing outputs may
   not be read by any of the paths above.
4. **Source identity / quality / cache / usefulness never feed
   live orders.** Source manifests, identity maps, cache health,
   throughput metrics may not be read by any of the paths above.
5. **`opportunity_probability_score` never feeds live orders.**
   ADR-019 already requires the score to be independent of
   execution-side state; this ADR adds the converse: the score is
   never read by execution-side state.
6. **The funnel policy is the only path from research to paper.**
   `research/campaign_funnel_policy.py` and the canonical
   authority mapping in ADR-014 §A remain the only authorised
   path. Any diagnostic / retrieval / source / state / score
   output influences this path *through evidence ledgers and
   sidecar artifacts only*, never through direct execution-side
   coupling.
7. **Frozen contracts are never written by execution-side
   surfaces.** `research/research_latest.json` and
   `research/strategy_matrix.csv` remain read-only to the paper /
   shadow / live runtime.
8. **`automation/live_gate.py` is the only barrier between paper
   and live.** No future reactivation ADR may relax this. Any
   change to `live_gate.py` is an elevated exception per
   [`strategic_roadmap_execution_mandate.md`](../../governance/strategic_roadmap_execution_mandate.md)
   §4.

### Per-stage readiness gates (cross-reference)

Each future readiness ADR must include, at minimum:

- explicit list of which research-side surfaces feed the stage
  (and via which evidence ledger, not direct coupling);
- explicit list of which surfaces never feed the stage;
- kill-switch criteria;
- exit criteria (both "graduate" and "kill");
- operator authorisation surface and how it is recorded;
- a `<stage>_readiness_checklist.v1.json` artifact spec.

## Hard constraints preserved

- ADR-014 unchanged. The canonical authority mapping continues to
  govern *what* is read and *who* writes.
- ADR-015 unchanged. The autonomy ladder governs *which agents*
  may take which kinds of action. Level 6 remains permanently
  disabled.
- ADR-017 unchanged. Step 5 implementation remains blocked
  behind the readiness gate.
- [`no_touch_paths.md`](../../governance/no_touch_paths.md)
  unchanged.
- [`execution_authority.md`](../../governance/execution_authority.md)
  unchanged.
- ADE may never live trade. ADE remains development workflow
  automation only per
  [`docs/governance/ade_development_lane_doctrine.md`](../../governance/ade_development_lane_doctrine.md).

## Consequences

Positive:

- The implicit separation becomes a doctrinal invariant.
- Future reactivation ADRs cannot quietly wire deferred surfaces
  into live without operator approval.
- The doctrine reads as one paragraph; review is fast.

Negative / accepted:

- A future operator-approved reactivation that *should* feed a
  diagnostic into shadow execution-realism (per Addendum 1 §C
  "Control Theory" mapping) must do so via an evidence ledger /
  sidecar surface, not direct coupling. This is the intended
  rigour; no real capability is lost.

## Tests / verification

This ADR is doctrine. Enforcement is by existing hooks
(`deny_no_touch.py`, `deny_outside_agent_allowlist.py`,
`deny_live_connector.py`, the execution-authority classifier).
This ADR adds no new test. Existing tests already pin:

- the no-touch glob set (`tests/unit/test_hooks_no_touch.py`);
- the execution-authority classifier behaviour
  (relevant `tests/unit/test_execution_authority_*.py` if
  present);
- the autonomy ladder.

## Promotion

This ADR is in `_drafts/`. Promotion to
`docs/adr/ADR-020-paper-shadow-live-separation.md` is a separate
operator-driven governance-bootstrap PR. ADR-021 / 022 / 023 are
future ADRs not authored here.

## Cross-references

- [`docs/governance/roadmap_scope_status.md`](../../governance/roadmap_scope_status.md)
- [`docs/governance/no_touch_paths.md`](../../governance/no_touch_paths.md)
- [`docs/governance/execution_authority.md`](../../governance/execution_authority.md)
- [`docs/governance/autonomy_ladder.md`](../../governance/autonomy_ladder.md)
- [`docs/governance/strategic_roadmap_execution_mandate.md`](../../governance/strategic_roadmap_execution_mandate.md)
- [`docs/governance/ade_development_lane_doctrine.md`](../../governance/ade_development_lane_doctrine.md)
- [`docs/adr/_drafts/ADR-018-roadmap-execution-reset.md`](ADR-018-roadmap-execution-reset.md)
- [`docs/adr/_drafts/ADR-019-hypothesis-discovery-doctrine.md`](ADR-019-hypothesis-discovery-doctrine.md)
- [`docs/adr/ADR-014-truth-authority-settlement.md`](../ADR-014-truth-authority-settlement.md)
- [`docs/adr/ADR-015-claude-agent-governance.md`](../ADR-015-claude-agent-governance.md)
- [`docs/adr/ADR-017-step5-autonomous-implementation-loop.md`](../ADR-017-step5-autonomous-implementation-loop.md)
