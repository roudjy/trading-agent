# Roadmap item execution protocol — operator runbook

Module: `reporting.roadmap_execution_protocol`
Version: v3.15.15.28
Schema: `docs/governance/roadmap_item_execution_protocol/schema.v1.md`
Sibling docs: `agent_handoff_protocol.md`,
`high_risk_approval_policy.md`,
`approval_exception_inbox.md`, `roadmap_proposal_queue.md`,
`mobile_agent_control_pwa.md`.

## TL;DR

Read-only protocol module that converts a roadmap item into a
**fully-specified execution plan** without running any code.
Implementation never happens here. The operator decides whether
to start a real branch + PR by hand using the plan's
deterministic outputs (proposed branch name, required tests,
acceptance criteria, agent assignments, merge requirements,
post-merge checks).

This release does NOT implement a roadmap item. It creates the
protocol and artefacts that make future roadmap item execution
controlled and repeatable.

## Roadmap item flow (16 steps)

```
1. Intake
2. Classification               (this module)
3. Proposal                     (proposal_queue + this module)
4. Agent assignment             (this module)
5. Plan                         (this module)
6. Approval gate if needed      (approval_inbox + operator)
7. Branch                       (operator-led git checkout -b ...)
8. Implementation               (operator + Implementation Agent on branch)
9. Tests                        (the required_tests list)
10. Self-review                 (Implementation Agent)
11. Guardian review             (architecture / ci / security guardians)
12. PR                          (operator-led gh pr create)
13. CI                          (the existing 16 GitHub checks)
14. Merge                       (operator-led gh pr merge --squash)
15. Post-merge verification     (the post_merge_checks list)
16. Metrics/dashboard update    (workloop_runtime + autonomy_metrics)
```

The protocol module owns steps 2–5; everything else is operator
or sibling-module territory.

## Core principle

A roadmap item must NEVER trigger direct execution. The plan is
a proposal; only the operator may approve a branch open / PR
merge. HIGH and UNKNOWN items are blocked by construction.

## CLI

```
python -m reporting.roadmap_execution_protocol --describe
python -m reporting.roadmap_execution_protocol \
    --plan-item path/to/item.json --dry-run
python -m reporting.roadmap_execution_protocol \
    --plan-item '{"title": "Add docs", "summary": "..."}' --dry-run
python -m reporting.roadmap_execution_protocol --status
```

`--plan-item` REQUIRES `--dry-run`. The CLI refuses any other
mode in this release (`parser.error`). `--describe` prints the
agent role catalogue + statuses + item types + merge
requirements as a deterministic JSON document.

`--status` reads the latest plan from
`logs/roadmap_execution_protocol/latest.json`.

## Item types and their fates

Open to implementation (when the policy says
`allowed_read_only`):

* `docs_only`
* `frontend_read_only`
* `reporting_read_only`
* `test_only`
* `observability_addition`

Always route to operator review:

* `tooling_intake` (HIGH-shape variants block; LOW-shape
  variants need_human via the existing tooling-intake policy)
* `dependency_floor_bump` (CI guardian must confirm no SHA pin
  downgrade)
* `ci_hardening` (`touches_ci_or_tests` -> blocked from
  auto-implementation by approval_policy)

Always blocked:

* `governance_change`
* `canonical_roadmap_adoption`
* `live_paper_shadow_risk`
* `external_account_or_secret`
* `telemetry_or_data_egress`
* `paid_tool`

`unknown` -> `unknown_state` -> operator inspects.

## Approval rules

The protocol delegates risk decisions to
`reporting.approval_policy.decide()` and embeds the verbatim
`PolicyDecision` in the plan's `approval_policy_decision` field.
Rules:

* LOW / MEDIUM may proceed only if policy says so.
* HIGH / UNKNOWN must route to `needs_human`.
* Canonical roadmap adoption requires human approval.
* Live / paper / shadow / risk requires human approval.
* Secrets / external / paid / telemetry require human approval.
* Protected / frozen / governance weakening blocked.
* Missing evidence => UNKNOWN, never a permissive default.

## PR lifecycle protocol

A roadmap-item PR must satisfy:

* one roadmap item per branch (branch name is deterministic
  from `proposed_branch`);
* no direct main push;
* no force push;
* no `gh pr merge --admin`;
* PR body must include:
  * release id
  * roadmap item id
  * scope summary
  * files changed
  * risk class
  * approval decision
  * tests run
  * frozen-hash check result
  * screenshots for frontend / PWA changes
  * confirmation of the `forbidden_scope` list
  * rollback note
* merge only when ALL of:
  * CI green
  * local gates green
  * frozen hashes unchanged
  * policy says not HIGH / UNKNOWN executable
  * no protected-path / live-path / governance-weakening touch
  * no test/CI weakening
  * no unresolved approval-inbox row tied to the same `item_id`.

These are emitted verbatim under `merge_requirements` on every
plan so a guardian can read them off the digest.

## How the operator is notified

* When `status == "needs_human"` or `status == "blocked"`, the
  approval inbox surfaces the plan via the existing inbox
  category mapping.
* When `safety.high_or_unknown_executable_count > 0` would ever
  flip in `autonomy_metrics`, the metrics digest reports
  `unsafe_state_detected` — by construction this should never
  happen for a roadmap-item plan because `executable=false`.
* The Agent Control PWA Status card surfaces a `roadmap protocol`
  row pulled from the projection on
  `/api/agent-control/status`.

## Examples

### LOW docs-only item -> implementation_allowed

Input:

```json
{
  "item_id": "r_docs_aaaa",
  "title": "Add operator runbook for the new metrics module",
  "summary": "Document the v3.15.15.27 staleness threshold semantics in docs/governance/autonomy_metrics.md and link from observability_security_hardening.md",
  "affected_files": ["docs/governance/autonomy_metrics.md"],
  "risk_class": "LOW"
}
```

Plan (excerpt):

```
item_type: docs_only
risk_class: LOW
decision: allowed_read_only
status: proposed
implementation_allowed: true
proposed_branch: fix/v3-15-16-x-r-docs-aaaa-add-operator-runbook-...
required_tests: governance_lint, smoke, frozen-hash, doc presence
guardian_reviews_required: architecture_guardian, ci_guardian, security_governance_guardian
```

### MEDIUM PWA read-only item -> implementation_allowed

Input:

```json
{
  "item_id": "r_pwa_bbbb",
  "title": "PWA Status card: render a roadmap protocol row",
  "summary": "Read-only display of logs/roadmap_execution_protocol/latest.json on the Status card",
  "affected_files": [
    "frontend/src/routes/AgentControl.tsx",
    "frontend/src/api/agent_control.ts"
  ],
  "risk_class": "MEDIUM"
}
```

Plan (excerpt):

```
item_type: frontend_read_only
risk_class: MEDIUM
decision: allowed_read_only
status: proposed
implementation_allowed: true
required_tests: ..., npm --prefix frontend test -- --run, npm --prefix frontend run build
acceptance_criteria:
  - the new UI is visible on phone-portrait at /agent-control
  - no execute / approve / reject / merge buttons added
  - no mutation fetch verbs in frontend code
```

### HIGH live/risk item -> blocked

Input:

```json
{
  "item_id": "r_live_cccc",
  "title": "Switch broker_kraken.py to use the live API",
  "summary": "Update execution/live/broker_kraken.py to set use_live=True",
  "affected_files": ["execution/live/broker_kraken.py"],
  "risk_class": "HIGH"
}
```

Plan (excerpt):

```
item_type: live_paper_shadow_risk
risk_class: HIGH
decision: blocked_live_paper_shadow_risk
status: blocked
implementation_allowed: false
blocked_reason: approval_policy: blocked_live_paper_shadow_risk (...)
forbidden_actions: includes "execute live broker", "place real-money order"
```

### UNKNOWN item -> blocked_unknown

Input:

```json
{
  "item_id": "r_unknown_dddd",
  "title": "(unknown source)"
}
```

Plan (excerpt):

```
item_type: unknown
risk_class: UNKNOWN
decision: blocked_unknown
status: unknown_state
implementation_allowed: false
blocked_reason: unknown_item_type: routes to operator inspection
```

## What remains forbidden

Everything in `approval_policy.UNIVERSAL_FORBIDDEN_AGENT_ACTIONS`
plus per-decision extras, surfaced verbatim on every plan.

The protocol module itself never:

* opens a branch
* opens a PR
* merges a PR
* runs tests
* writes outside `logs/roadmap_execution_protocol/`
* runs subprocess / `gh` / `git`
* makes network calls
* mutates frozen contracts
* mutates `.claude/**`
* enables Dependabot execute-safe
* surfaces credential-shaped values

## Cross-references

* Schema: `docs/governance/roadmap_item_execution_protocol/schema.v1.md`
* Agent handoff: `docs/governance/agent_handoff_protocol.md`
* Approval policy: `docs/governance/high_risk_approval_policy.md`
* Approval inbox: `docs/governance/approval_exception_inbox.md`
* Proposal queue: `docs/governance/roadmap_proposal_queue.md`
* PR lifecycle: `docs/governance/github_pr_lifecycle_integration.md`
* PWA: `docs/governance/mobile_agent_control_pwa.md`
* No-touch paths: `docs/governance/no_touch_paths.md`
