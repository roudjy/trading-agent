# Agent handoff protocol — operator runbook

Module: `reporting.roadmap_execution_protocol`
Version: v3.15.15.28
Sibling docs: `roadmap_item_execution_protocol.md`,
`high_risk_approval_policy.md`, `permission_model.md`.

This is the canonical description of the eight agent roles that
participate in roadmap-item execution. Every role definition is
emitted verbatim by
`python -m reporting.roadmap_execution_protocol --describe`.

## Roles and handoff order

The handoff sequence is fixed; a plan that skips a role is
treated as `unknown_state` by the operator.

```
1. Product Owner Agent
       ↓ (acceptance_criteria, scope_summary, user_value)
2. Strategic Advisor
       ↓ (strategic_fit, deferral_recommendation)
3. Planner Agent
       ↓ (proposed_branch, proposed_release_id, required_tests,
          expected_artifacts, rollback_plan)
4. Implementation Agent (only after operator approval)
       ↓ (PR URL, CI status, self_review_notes)
5. Architecture Guardian            ┐
6. CI Guardian                      ├ parallel reviews
7. Security/Governance Guardian     ┘
       ↓ (per-guardian pass_or_block)
8. Operator (Joery)
       ↓ merge_decision, post_merge_signal
```

## Role contracts (summary)

For each role: responsibilities, allowed actions, forbidden
actions, handoff input, handoff output, required evidence. The
canonical machine-readable form is the `--describe` output;
the prose below mirrors it for operator review.

### 1. Product Owner Agent (`product_owner`)

* Converts a roadmap item into operator-shaped acceptance
  criteria.
* Prevents vague scope; rejects items without measurable value.
* Confirms user value with the operator before any branch is
  opened.
* Cannot open branches / PRs / modify code / modify tests /
  modify governance.

### 2. Strategic Advisor (`strategic_advisor`)

* Checks sequencing and strategic fit against the autonomy
  roadmap.
* Recommends deferral or split when scope is too large.
* Raises authority concerns to the operator.
* Cannot implement directly / approve HIGH-risk items / open or
  merge PRs.

### 3. Planner Agent (`planner`)

* Produces a bounded release plan.
* Defines branch, commit boundaries, tests, rollback.
* Lists expected artefacts and operator-visible changes.
* Cannot implement code / open branches in git / open PRs /
  modify governance / modify `.claude/**`.

### 4. Implementation Agent (`implementation_agent`)

* Implements only the approved scope on the proposed branch.
* Makes no scope changes without re-running the protocol.
* Runs all required tests before opening the PR.
* Cannot expand scope without operator approval, weaken tests /
  governance / CI, force push, admin merge, direct main push,
  modify `.claude/**`, modify frozen contracts, modify
  `automation/live_gate.py`, or wire `api_execute_safe_controls`
  without an explicit operator brief.

### 5. Architecture Guardian (`architecture_guardian`)

* Checks layering, contracts, frozen outputs, no-touch files.
* Verifies no protected-path or live-trading touch.
* Confirms schema-version bumps when a contract changes.
* Cannot rewrite the implementation, merge the PR, or wave
  through HIGH-risk items.

### 6. CI Guardian (`ci_guardian`)

* Verifies required GitHub checks all green.
* Verifies no test was skipped, deleted, or weakened.
* Verifies required smoke + unit + governance_lint coverage.
* Cannot skip or downgrade required checks, merge the PR, or
  modify CI workflows outside a separate ci-hardening release.

### 7. Security / Governance Guardian (`security_governance_guardian`)

* Checks for secret-shaped values, protected paths, mutation
  routes.
* Checks for unsafe automation or governance weakening.
* Checks `approval_policy` compliance for the item.
* Cannot approve HIGH/UNKNOWN items autonomously, merge the PR,
  or weaken redaction or guards.

### 8. Operator (Joery) (`operator`)

* Decides HIGH / UNKNOWN / `needs_human` items.
* Approves external accounts / secrets / paid / telemetry.
* Approves live / paper / shadow / risk changes.
* Approves canonical roadmap adoption.
* Is the trust boundary; the only role with no forbidden
  actions.

## When the chain breaks

If any role's `handoff_output` is missing, the next role refuses
its handoff and the protocol module emits a plan with
`status="unknown_state"` and a deterministic `blocked_reason`.
The operator inspects the plan in
`logs/roadmap_execution_protocol/latest.json` and decides whether
to re-run the protocol or reject the item.

## Examples

### Healthy LOW docs item

```
PO drafts criteria → Strategic confirms scope is bounded →
Planner produces branch/tests/rollback → Operator approves →
Implementation Agent commits docs only → Guardians review →
Operator merges.
```

### Blocked HIGH live-trading item

```
PO drafts criteria → Strategic flags item as live-risk →
approval_policy returns blocked_live_paper_shadow_risk →
plan status = blocked → operator inspects → operator EITHER
accepts the block (item is dropped or re-shaped) OR re-runs
the protocol with a redesigned scope that no longer touches
the live path.
```

### Unknown-evidence item

```
PO cannot articulate user value → no acceptance_criteria →
Strategic / Planner refuse handoff → plan status = unknown_state
→ operator decides whether to discard or refine.
```

## Cross-references

* `docs/governance/roadmap_item_execution_protocol.md`
* `docs/governance/roadmap_item_execution_protocol/schema.v1.md`
* `docs/governance/high_risk_approval_policy.md`
* `docs/governance/permission_model.md`
* `docs/governance/no_touch_paths.md`
