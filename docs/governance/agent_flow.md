# Agent Flow — operator runbook

> Module: `reporting.agent_flow`
> Release: v3.15.16.7
> Sibling docs: `task_board.md`, `roadmap_priority.md`,
> `recurring_maintenance.md`,
> `roadmap_item_execution_protocol.md`.

## TL;DR

Pure, deterministic, read-only orchestration projection over the
v3.15.16.6 task-board state machine. For every task, surfaces:

* `current_stage` — the task-board's `current_state`.
* `responsible_agent` — which canonical agent role owns the
  current stage.
* `next_agent` — which agent receives the handoff at the next
  state.
* `next_action_proposed` — the closed-enum action the v3.15.16.11
  actuator should perform once the v3.15.16.10 governance is in
  place.
* `blocking_reason` — short string when the task is blocked or
  human_needed.
* `handoff_eligible` — boolean: `True` iff the handoff to the
  next agent is mechanically valid.

Writes the result to `logs/agent_flow/latest.json`.

## Closed `next_action_proposed` vocabulary

The v3.15.16.11 actuator consumes this directly:

| action | when | what the actuator does (Phase 1) |
| --- | --- | --- |
| `select_next_task` | stage `backlog` | no-op (waits for product_owner classification) |
| `generate_plan` | stage `refined` | no-op (waits for planner) |
| `implement` | stage `todo` | no-op (waits for me / future LLM agent) |
| `validate` | stage `in_progress` | watch CI, retry flaky checks (max 2) |
| `review` | stage `review` | run merge gates; auto-merge if ALL pass |
| `merge` | stage `review` (synonym for the actuator's merge step) | gh pr merge --squash --delete-branch |
| `escalate_human` | stage `blocked` or `human_needed` | emit human_needed event |
| `no_op` | stage `done` or unknown | nothing |

The closed enum is pinned by a unit test; new actions cannot be
added without an explicit code change here AND a v3.15.16.10
amendment.

## State → next_agent / next_action mapping

| current_stage | next_agent | next_action_proposed | handoff_eligible |
| --- | --- | --- | --- |
| `backlog` | `planner` | `select_next_task` | True |
| `refined` | `implementation_agent` | `generate_plan` | True |
| `todo` | `implementation_agent` | `implement` | True |
| `in_progress` | `ci_guardian` | `validate` | True |
| `review` | `operator` | `merge` | True |
| `done` | `operator` | `no_op` | False |
| `blocked` | `operator` | `escalate_human` | False |
| `human_needed` | `operator` | `escalate_human` | False |

## Hard guarantees

| guarantee | enforcement |
| --- | --- |
| Stdlib-only | no subprocess, no `gh`, no `git`, no network — pinned by source-text test |
| `safe_to_execute` is always `false` | hard-coded literal in source; pinned by unit test |
| Missing source → `not_available` | never silently OK |
| Determinism | two runs on the same input produce a byte-identical handoffs list |
| Stable ordering | handoffs sorted by `item_id` ascending |
| Atomic writes | `tmp` + `os.replace` |
| No mutation of upstream | task_board artifact byte-identical before/after (pinned) |
| Output scope | writes only under `logs/agent_flow/` |
| Closed action vocabulary | every record's `next_action_proposed` is in the eight-element enum (pinned) |

## CLI

```
python -m reporting.agent_flow
python -m reporting.agent_flow --no-write
python -m reporting.agent_flow --status
python -m reporting.agent_flow --frozen-utc 2026-05-05T11:00:00Z
```

There is **no execute mode**.

## Integration with the recurring scheduler

`reporting.recurring_maintenance` (v3.15.15.23) gains one new
closed job entry in v3.15.16.7:

| `job_type` | risk | needs `gh`? | default interval | default enabled | what it does |
| --- | --- | --- | --- | --- | --- |
| `refresh_agent_flow` | LOW | no | 30 min | ✓ | runs `agent_flow.collect_snapshot()` + `write_outputs()` |

## Files added by v3.15.16.7

```
reporting/agent_flow.py
reporting/recurring_maintenance.py        (one new closed job entry)
tests/unit/test_agent_flow.py
tests/unit/test_recurring_maintenance.py  (registry + per-job assertion)
docs/governance/agent_flow.md             (this file)
docs/governance/recurring_maintenance.md  (job table + cross-reference)
```

No new dependency. No `dashboard/dashboard.py` change. No
`.claude/` change. No frontend change. No frozen-contract change.
No live / paper / shadow / risk path touch. No test weakening.

## Cross-references

* `reporting/task_board.py` — supplies the input rows.
* `reporting/roadmap_execution_protocol.py` — owner-agent role
  vocabulary (mirrored).
