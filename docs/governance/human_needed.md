# human_needed — operator runbook

> Module: `reporting.human_needed`
> Release: v3.15.16.8
> Sibling docs: `task_board.md`, `agent_flow.md`,
> `approval_exception_inbox.md`, `recurring_maintenance.md`,
> `roadmap_priority.md`.

## TL;DR

Pure, deterministic, read-only blocker detector. For every blocker
that requires operator action, emits a structured event with:

* `event_id` — deterministic hash.
* `reason` — closed enum.
* `blocking_component` — the file / module / capability that is blocked.
* `required_action` — short imperative for the operator.
* `proposed_patch` — literal text patch when derivable; `null` otherwise.
* `impact` — closed enum: LOW / MEDIUM / HIGH / CRITICAL.
* `priority` — closed enum: LOW / MEDIUM / HIGH / CRITICAL.
* `related_item` — task_board `item_id` when applicable.
* `evidence` — dict of supporting context.

Writes the result to `logs/human_needed/latest.json`. Each event
also surfaces as a row in the existing approval-inbox PWA card via
the new `_build_from_human_needed` projection — so the operator
sees blockers without any new UI.

**Future push notifications trigger only on these events.** This
release pins the canonical schema; the delivery mechanism lands in
v3.15.17.x.

## Closed `reason` vocabulary

| reason | when |
| --- | --- |
| `governance_bootstrap_required` | a wiring gap detected (e.g. v3.15.16.5 dashboard.py); operator must open a tiny bootstrap PR |
| `no_touch_path_blocks_wiring` | a task touches a no-touch path; engine cannot proceed without operator |
| `allowlist_blocks_completion` | a task touches a path outside any agent allowlist |
| `release_gate_blocks_progression` | a release-gate review is blocking |
| `system_cannot_proceed_safely` | engine retried N times and still fails; operator triage required |
| `decision_cannot_be_inferred` | task in `human_needed` state with no derivable patch |

## Wiring-gap auto-detection (the canonical use case)

`reporting.human_needed` scans every `dashboard/api_*.py` file
(skipping `api_execute_safe_controls.py` which is intentionally
unwired per v3.15.15.27) for top-level `register_*_routes(`
function definitions and cross-references each against
`dashboard/dashboard.py`. A module is considered wired iff
`dashboard/dashboard.py` contains BOTH:

* `from <module> import <fn>` (single-line OR multi-line
  parenthesised — handled by a regex that allows whitespace and
  newlines inside the parens);
* `<fn>(app)` substring.

For each gap, an event is emitted with:

* `reason: governance_bootstrap_required`
* `blocking_component: dashboard/dashboard.py:<fn_name>`
* `proposed_patch:` literal text the operator can paste into a
  one-shot bootstrap PR
* `priority: HIGH`

The v3.15.16.5 `register_roadmap_priority_routes` wiring gap is
the canonical first-detection case (pinned by a unit test).

## Hard guarantees

| guarantee | enforcement |
| --- | --- |
| Stdlib-only | no subprocess, no `gh`, no `git`, no network — pinned by source-text test |
| `safe_to_execute` is always `false` | hard-coded literal in source; pinned |
| `proposed_patch` field is text only | pinned by source-text test that forbids `git apply`, `patch -`, `subprocess.run`, `subprocess.Popen` in the module |
| Closed reason vocabulary | exactly six entries; pinned |
| Closed impact / priority vocabulary | exactly four entries each; pinned |
| Determinism | byte-identical events across runs (modulo `generated_at_utc`); pinned |
| Stable ordering | events sorted by `(priority_rank, reason, event_id)` |
| Atomic writes | `tmp` + `os.replace`, output limited to `logs/human_needed/` |

## Approval-inbox integration

`reporting.approval_inbox` gains `_build_from_human_needed` —
maps each open event to one inbox row:

| reason | inbox category | risk_class |
| --- | --- | --- |
| `governance_bootstrap_required` | `failed_automation` | HIGH (priority HIGH/CRITICAL) or MEDIUM otherwise |
| `no_touch_path_blocks_wiring` | `failed_automation` | HIGH or MEDIUM |
| `release_gate_blocks_progression` | `failed_automation` | HIGH or MEDIUM |
| `system_cannot_proceed_safely` | `failed_automation` | HIGH or MEDIUM |
| `allowlist_blocks_completion` | `manual_route_wiring_required` | MEDIUM |
| `decision_cannot_be_inferred` | `unknown_state` | MEDIUM |

The existing `_build_manual_route_wiring_items` legacy detector
remains in place — both fire on a wiring gap, which is fine: the
operator sees a tracked row regardless of which detection path
runs first.

## CLI

```
python -m reporting.human_needed
python -m reporting.human_needed --no-write
python -m reporting.human_needed --status
python -m reporting.human_needed --frozen-utc 2026-05-05T11:30:00Z
```

There is **no execute mode**.

## Integration with the recurring scheduler

`reporting.recurring_maintenance` (v3.15.15.23) gains:

| `job_type` | risk | needs `gh`? | default interval | default enabled | what it does |
| --- | --- | --- | --- | --- | --- |
| `refresh_human_needed` | LOW | no | 30 min | ✓ | runs `human_needed.collect_snapshot()` + `write_outputs()` |

## Files added by v3.15.16.8

```
reporting/human_needed.py
reporting/approval_inbox.py            (+_build_from_human_needed projection)
reporting/recurring_maintenance.py     (one new closed job entry)
tests/unit/test_human_needed.py
tests/unit/test_approval_inbox.py      (3 new tests for the projection)
tests/unit/test_recurring_maintenance.py (registry + per-job assertion)
docs/governance/human_needed.md        (this file)
docs/governance/approval_exception_inbox.md (cross-reference update)
docs/governance/recurring_maintenance.md (job table + section)
docs/roadmap/Roadmap v6.md
```

No new dependency. No `dashboard/dashboard.py` change. No
`.claude/` change. No frontend change. No frozen-contract change.
No live / paper / shadow / risk path touch. No test weakening.

## Cross-references

* `reporting/task_board.py` — supplies the per-task input rows.
* `reporting/agent_flow.py` — orchestration projection (downstream
  consumer).
* `reporting/governance_bootstrap.py` (v3.15.16.9) — synthesizes
  copy-paste-able bootstrap-PR templates from these events.
