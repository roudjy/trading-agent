# Task Board — operator runbook

> Module: `reporting.task_board`
> Release: v3.15.16.6
> Sibling docs: `roadmap_priority.md`, `recurring_maintenance.md`,
> `roadmap_item_execution_protocol.md`, `approval_exception_inbox.md`.

## TL;DR

A pure, deterministic, read-only state-machine projection over the
roadmap-item lifecycle. For every proposal in the proposal queue
this module emits a typed kanban record carrying:

* `current_state` — one of eight closed states
* `next_state` — what the lifecycle progresses to under nominal
  conditions
* `transition_reason` — a deterministic string explaining the
  current state classification
* `owner_agent` — one of the eight canonical agent roles already
  enumerated in `reporting.roadmap_execution_protocol`
* `retry_count` — placeholder for the v3.15.16.11 actuator
* `last_update` — placeholder for the v3.15.16.11 actuator

Writes the result to `logs/task_board/latest.json`. The autonomous
loop's actuation layer (v3.15.16.11) consumes the `next_state`
field directly so it never has to re-derive transition logic.

## Closed state vocabulary

| state | meaning |
| --- | --- |
| `backlog` | proposal exists, not yet classified for execution |
| `refined` | proposal_queue has classified the item with a non-UNKNOWN risk_class |
| `todo` | proposal appears in roadmap_priority's eligible candidates list |
| `in_progress` | a matching open PR exists in github_pr_lifecycle |
| `review` | open PR with all required CI green AND merge state CLEAN |
| `done` | matching PR has merged |
| `blocked` | a blocker is recorded (HIGH risk, protected path, dependency unmet, …) |
| `human_needed` | explicit operator review required (proposal status, approval-inbox row, or requires_human plan flag) |

## Closed state-transition precedence

The `_derive_state` function is rule-based, first-match wins:

1. matching merged PR detected → **done**
2. open PR with `checks_state == "passed"` AND `merge_state == "clean"` → **review**
3. open PR (any other shape) → **in_progress**
4. proposal `status == "needs_human"` OR matching critical/high inbox row → **human_needed**
5. proposal `status == "blocked"` OR priority filtered with blocked-shaped reason OR matching blocked inbox row → **blocked**
6. proposal in `roadmap_priority.candidates` → **todo**
7. proposal classified with `risk_class != "UNKNOWN"` → **refined**
8. anything else → **backlog**

## Closed owner-agent vocabulary

Mirrors the eight canonical roles in
`reporting.roadmap_execution_protocol._AGENT_ROLES`:
`product_owner`, `strategic_advisor`, `planner`,
`implementation_agent`, `architecture_guardian`, `ci_guardian`,
`security_governance_guardian`, `operator`.

Mapping of state → canonical owner:

| state | owner |
| --- | --- |
| `backlog` | `product_owner` |
| `refined` | `planner` |
| `todo` | `implementation_agent` |
| `in_progress` | `implementation_agent` |
| `review` | `ci_guardian` |
| `done` | `operator` |
| `blocked` | `operator` |
| `human_needed` | `operator` |

## Hard guarantees

| guarantee | enforcement |
| --- | --- |
| Stdlib-only | no subprocess, no `gh`, no `git`, no network — pinned by source-text test |
| `safe_to_execute` is always `false` | hard-coded literal in source; pinned by unit test |
| Missing source ≠ silently OK | `final_recommendation == "not_available"` |
| Determinism | two runs on the same input produce a byte-identical `tasks` list (modulo `generated_at_utc`) |
| Stable ordering | tasks sorted by `item_id` ascending |
| Atomic writes | `tmp` + `os.replace`, mirrors the rest of `reporting/` |
| No mutation of upstream | every input artifact is byte-identical before/after a `collect_snapshot` + `write_outputs` cycle (pinned) |
| Output scope | writes only under `logs/task_board/` |

## CLI

```
# Default: dry-run, write the digest, print to stdout.
python -m reporting.task_board

# Inspection only (no file write).
python -m reporting.task_board --no-write

# Read the latest digest without re-running.
python -m reporting.task_board --status

# Pin the timestamp (deterministic tests).
python -m reporting.task_board --frozen-utc 2026-05-05T10:30:00Z
```

There is **no execute mode**. The CLI rejects any `--mode` other
than `dry-run`. The execute path is intentionally absent — this
release projects, the v3.15.16.11 engine acts under the
v3.15.16.10 governance.

## Integration with the recurring scheduler

`reporting.recurring_maintenance` (v3.15.15.23) gains one new
closed job entry in v3.15.16.6:

| `job_type` | risk | needs `gh`? | default interval | default enabled | what it does |
| --- | --- | --- | --- | --- | --- |
| `refresh_task_board` | LOW | no | 30 min | ✓ | runs `task_board.collect_snapshot()` + `write_outputs()` |

The new job inherits all the supervisor-level safety rails of the
existing typed scheduler: per-job timeout, atomic state, failed /
blocked job projection into `approval_inbox`.

## Operator workflow

1. Refresh the upstream artifacts (proposal_queue,
   roadmap_priority, github_pr_lifecycle, approval_inbox) — happens
   automatically on every merge via the v3.15.16.3 deploy hook.
2. Inspect the task board:
   ```
   python -m reporting.task_board --status
   ```
3. The PWA Status card already surfaces the
   `recurring_maintenance` row pill from the scheduler's
   `final_recommendation`; if the new task_board job ever flips to
   `failed`, it surfaces in the existing approval-inbox card with
   `severity: high`.

## What this module is NOT

* It is **not** an autonomous starter. It does not create a
  branch, open a PR, run tests, or invoke `gh`.
* It is **not** a risk arbiter. Risk classification belongs to
  `roadmap_execution_protocol`. The state machine mirrors the
  protocol's verdicts.
* It is **not** an approval surface. Approvals go through
  `reporting.approval_inbox`.

## Files added by v3.15.16.6

```
reporting/task_board.py
reporting/recurring_maintenance.py        (one new closed job entry)
tests/unit/test_task_board.py
tests/unit/test_recurring_maintenance.py  (registry + per-job assertion)
docs/governance/task_board.md             (this file)
docs/governance/recurring_maintenance.md  (job table + cross-reference)
```

No new dependency. No `dashboard/dashboard.py` change. No
`.claude/` change. No frontend change. No frozen-contract change.
No live / paper / shadow / risk path touch. No test weakening.

## Cross-references

* `reporting/roadmap_priority.py` — supplies `eligible` and
  `filtered_out` lists.
* `reporting/proposal_queue.py` — supplies the proposal records
  themselves.
* `reporting/github_pr_lifecycle.py` — supplies open / merged PR
  state.
* `reporting/approval_inbox.py` — supplies critical / high inbox
  rows that override the state machine to `human_needed`.
* `reporting/roadmap_execution_protocol.py` — owner-agent role
  vocabulary.
