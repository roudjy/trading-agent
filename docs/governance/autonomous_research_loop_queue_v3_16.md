# Autonomous Research Loop Queue v3.16.x

> Status: active queue record for the next safe autonomous research
> loop path.
>
> Authority: supplements `roadmap_scope_status.md` and
> `queue_reactivation_2026_05_21.md`. It does not activate v4.x
> Shadow, v5.x Paper, v6.x Live, broker, risk, or execution scope.

## Operating Boundary

QRE is moving from human-directed research tooling toward a closed
autonomous research loop:

market/context insights -> hypothesis generation or update -> prior
research outcomes -> failure attribution and no-candidate diagnostics
-> research state transition -> next-best research action -> synthesis
eligibility gate -> sandbox strategy generation when allowed ->
isolated validation -> candidate alert and daily report -> operator
approval only for paper, shadow, or live progression.

Autonomous research is allowed. Autonomous strategy synthesis is
allowed only after explicit gates pass and only inside isolated
research sandbox paths. Autonomous paper, shadow, live, broker, risk,
or execution modification remains forbidden.

Generated strategies must be derived from explicit market/context
insights, hypothesis state, prior campaign-level research evidence,
and attributed failure causes. Generated strategy code may not touch
trading execution paths and may never overwrite production strategies.

The operator-facing steady state is daily research reports and
candidate alerts. Paper, shadow, and live progression remains
operator-gated.

Addendum 1, Addendum 2, Addendum 3, v4.x Shadow, v5.x Paper, and v6.x
Live remain deferred and inactive.

## Queue

| Order | Queue Item | Status | Purpose | Key Output |
|---:|---|---|---|---|
| 1 | v3.16.x-state - Research Decision State & Attribution Engine | ready | Convert controlled_eval, campaign registry/ledger, sprint progress, policy decisions, information gain, viability, stop conditions, spawn proposals, and missing artifacts into explicit research states. | `research/research_state_latest.v1.json`, `research/research_state_latest.md` |
| 2 | v3.16.x-action - Research Action Planner | blocked | Generate bounded automatic, operator-gated, and forbidden research actions from research state. | `research/research_action_plan_latest.v1.json`, `research/research_action_plan_latest.md` |
| 3 | v3.16.x-policy - Explain No-Candidate Policy Filters | blocked | Explain template, preset, cooldown, duplicate, budget, worker, family, and terminal-state exclusions behind idle_noop/no_candidates. | `research/policy_filter_diagnostics_latest.v1.json`, `research/policy_filter_diagnostics_latest.md` |
| 4 | v3.16.x-screening - Screening Drop-Reason Attribution | blocked | Make degenerate_no_survivors actionable by classifying candidate drop reasons. | `research/screening_failure_attribution_latest.v1.json`, `research/screening_failure_attribution_latest.md` |
| 5 | v3.16.x-synthesis-gate - Strategy Synthesis Eligibility Gate | blocked | Decide whether sandbox synthesis is allowed from hypothesis plausibility, linked insight, exhausted preset variants, attribution, policy clarity, and evaluability. | `research/synthesis_gate_latest.v1.json`, `research/synthesis_gate_latest.md` |
| 6 | v3.16.x-synthesis - Strategy Synthesis Sandbox | blocked | Generate strategy variants only inside `research/sandbox/generated_strategies/` when the synthesis gate allows it. | `research/sandbox/synthesis_candidates_latest.v1.json`, `research/sandbox/synthesis_report_latest.md` |
| 7 | v3.16.x-sandbox-eval - Generated Strategy Validation Harness | blocked | Validate generated sandbox strategies with static checks, smoke tests, bounded historical evaluation, and overfit guardrails. | `research/sandbox/generated_strategy_eval_latest.v1.json`, `research/sandbox/generated_strategy_eval_latest.md` |
| 8 | v3.16.x-reporting - Daily Research Report and Candidate Alerts | blocked | Summarize market/context insights, research state, action plan, campaign outcomes, diagnostics, synthesis gate, generated candidates, and required operator actions. | `research/daily_research_report_latest.v1.json`, `research/daily_research_report_latest.md`, `research/candidate_alert_latest.v1.json` when a candidate appears |
| 9 | v3.16.x-scheduler - Bounded Autonomous Research Scheduler | blocked | Schedule only allowed automatic research actions, write daily reports, emit candidate alerts, and stop on governance blockers. | Scheduler sidecars only; no trading progression |

## Item 1 Acceptance Notes

The first eligible item must classify hypothesis, preset, policy,
evidence quality, failure attribution, instrumentation gaps,
next allowed actions, disallowed actions, synthesis gate, and
next-best test.

Required interpretations:

- `idle_noop/no_candidates` is policy evidence, not hypothesis
  failure.
- `degenerate_no_survivors` is screening or evaluability failure
  unless drop reasons are known.
- `completed_no_survivor` is more informative than
  `degenerate_no_survivors`, but still does not falsify a hypothesis.
- Sprint `observed_total > 0` with viability `campaign_count == 0`
  is `viability_window_misaligned`.
- Strategy synthesis remains blocked when attribution is insufficient,
  policy-only failure is unresolved, or evaluability is the primary
  blocker.
- Next-best tests must be diagnostic, such as policy filter
  diagnostics, screening drop-reason attribution, gate diagnostics, or
  evidence-window alignment checks.

## Hard Denials

This queue does not permit:

- paper, shadow, or live trading activation;
- broker, risk, or execution behavior changes;
- strategy promotion to trading;
- direct deployment of generated strategies;
- mutation of frozen contracts `research/research_latest.json` or
  `research/strategy_matrix.csv`;
- bypassing hooks, force-pushing, admin merges, or direct commits to
  `main`.
