# Roadmap item execution protocol — schema v1

Module: `reporting.roadmap_execution_protocol` (v3.15.15.28)
Schema version: `1`
Stability: stable; additions are SemVer minor, removals are
breaking.

This is the machine-readable description of the roadmap-item
execution plan emitted by `python -m reporting.roadmap_execution_protocol --plan-item ... --dry-run`.

## Top-level shape

```json
{
  "schema_version": 1,
  "report_kind": "roadmap_execution_plan",
  "module_version": "v3.15.15.28",
  "generated_at_utc": "2026-05-03T08:00:00Z",
  "item_id": "r_xxxxxxxx",
  "source": "docs/roadmap/v3.15.16.md#item-3",
  "source_type": "markdown_heading",
  "title": "...",
  "summary": "...",
  "roadmap_reference": "docs/roadmap/v3.15.16.md",
  "proposed_release_id": "v3.15.16.0",
  "proposed_branch": "fix/v3-15-16-r-xxxxxxxx-...",
  "item_type": "<one of ITEM_TYPES>",
  "risk_class": "LOW | MEDIUM | HIGH | UNKNOWN",
  "decision": "<one of approval_policy.DECISIONS>",
  "approval_policy_decision": { ...PolicyDecision.to_dict()... },
  "requires_human": bool,
  "executable": false,
  "implementation_allowed": bool,
  "affected_areas": [string],
  "forbidden_actions": [string],
  "required_tests": [string],
  "expected_artifacts": [string],
  "rollback_plan": [string],
  "acceptance_criteria": [string],
  "agent_assignments": [AgentRole.to_dict()...],
  "guardian_reviews_required": [string],
  "merge_requirements": [string],
  "post_merge_checks": [string],
  "status": "<one of STATUSES>",
  "blocked_reason": "..." | null,
  "policy": {
    "module_version": "v3.15.15.24",
    "schema_version": 1,
    "high_or_unknown_is_executable": false
  },
  "safe_to_execute": false
}
```

## ITEM_TYPES (closed)

```
docs_only
frontend_read_only
reporting_read_only
test_only
dependency_floor_bump
ci_hardening
observability_addition
tooling_intake
governance_change
canonical_roadmap_adoption
live_paper_shadow_risk
external_account_or_secret
telemetry_or_data_egress
paid_tool
unknown
```

## STATUSES (closed)

```
proposed
needs_human
blocked
unknown_state
```

## ITEM_TYPES open to implementation

A plan with `implementation_allowed=true` is restricted to:

```
docs_only
frontend_read_only
reporting_read_only
test_only
observability_addition
```

Every other type routes to `needs_human` or `blocked` regardless
of policy decision.

## Agent role catalogue

Eight roles, every plan surfaces all eight in `agent_assignments`
in the canonical handoff order:

1. `product_owner` — Product Owner Agent
2. `strategic_advisor` — Strategic Advisor
3. `planner` — Planner Agent
4. `implementation_agent` — Implementation Agent
5. `architecture_guardian` — Architecture Guardian
6. `ci_guardian` — CI Guardian
7. `security_governance_guardian` — Security / Governance Guardian
8. `operator` — Operator (Joery)

Each role is described by:

```
{
  "name": string,
  "title": string,
  "responsibilities": [string],
  "allowed_actions": [string],
  "forbidden_actions": [string],
  "handoff_input": [string],
  "handoff_output": [string],
  "required_evidence": [string]
}
```

## guardian_reviews_required

Always populated (even on blocked plans) so the operator can
audit which guardian would block:

```
architecture_guardian
ci_guardian
security_governance_guardian
```

## merge_requirements

Closed list, returned verbatim per release:

```
all required GitHub checks green
local governance_lint OK
local pytest tests/smoke OK
frozen contract sha256 unchanged
approval_policy decision is not HIGH/UNKNOWN executable
no protected-path / live-path / governance-weakening touch
no test/CI weakening
no unresolved approval inbox row tied to the same item_id
```

## post_merge_checks

```
pull main
verify final main SHA
rerun python -m reporting.workloop_runtime --once
rerun python -m reporting.autonomy_metrics --collect
verify approval_inbox does not surface a new runtime_halt for the merged item
verify frozen contract sha256 unchanged
```

## Determinism

* `agent_assignments` is always returned in the canonical role
  order.
* `guardian_reviews_required` / `merge_requirements` /
  `post_merge_checks` are deterministic per release.
* `proposed_branch` is a deterministic slug:
  `fix/<release_slug>-<item_slug>-<title_slug>`.
* `generated_at_utc` is the only clock-derived field; pin via
  `--frozen-utc` for tests.
* `item_id` defaults to `r_<sha256(title|summary)[:8]>` when not
  declared upstream.

## Atomic writes

Plans are written via `tmp` + `os.replace` to
`logs/roadmap_execution_protocol/`:

* `latest.json` — the most recent plan
* `<utc>.json` — timestamped copy (byte-identical to latest)
* `history.jsonl` — append-only log of all plans

## Hard constraints

* Stdlib-only. No subprocess, no `gh`, no `git`, no network.
* `--plan-item` requires `--dry-run`; the protocol never
  implements.
* `safe_to_execute` is hard-coded `false` at the digest level.
* `executable` is hard-coded `false` on every plan.
* `implementation_allowed` is True only for the closed
  `ITEM_TYPES_OPEN_TO_IMPLEMENTATION` set AND
  `decision == allowed_read_only`.
* No credential-shaped values are emitted (verified by
  `approval_policy.assert_no_credential_values`).
