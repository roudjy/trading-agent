# Governance Bootstrap — operator runbook

> Module: `reporting.governance_bootstrap`
> Release: v3.15.16.9
> Sibling docs: `human_needed.md`, `task_board.md`,
> `agent_flow.md`, `recurring_maintenance.md`,
> `approval_exception_inbox.md`.

## TL;DR

Pure read-only text synthesizer. Reads `logs/human_needed/latest.json`
(v3.15.16.8) and produces copy-paste-able bootstrap-PR templates
the operator can apply in seconds. Writes
`logs/governance_bootstrap/latest.json`.

The synthesizer **never** opens a branch, opens a PR, calls `gh`,
calls `git`, or applies any patch. Pinned by source-text test.

## What each template contains

| field | contents |
| --- | --- |
| `template_id` | `gb_<short>` deterministic from the source event_id |
| `source_event_id` | the v3.15.16.8 event this template was synthesized from |
| `source_reason` | the v3.15.16.8 reason (e.g. `governance_bootstrap_required`) |
| `branch_name` | `governance-bootstrap/<event_id>` |
| `commit_message` | `governance-bootstrap: <short summary>` |
| `file_diff` | byte-identical copy of the upstream `proposed_patch` |
| `pr_title` | `governance-bootstrap: <short summary>` |
| `pr_body` | operator-facing markdown body with cross-references |
| `validation_checklist` | five-item canonical checklist |

## Bootstrappable reasons

The synthesizer emits a template for events whose reason is in:

```
governance_bootstrap_required
no_touch_path_blocks_wiring
allowlist_blocks_completion
add_no_touch_carveout
```

`decision_cannot_be_inferred` and `system_cannot_proceed_safely`
events are NOT auto-templated — they require human triage and
have no deterministic patch.

## Three template-shape cross-references

* [Wiring `dashboard.py`](bootstrap_templates/wiring_dashboard_py.md) — the v3.15.16.5 case.
* [Extend an agent allowlist](bootstrap_templates/extend_agent_allowlist.md) — the future v3.15.16.4 / v3.15.17.0 case.
* [Add a no-touch carveout](bootstrap_templates/add_no_touch_carveout.md) — when a new path needs to be exempted from a no-touch rule.

## Hard guarantees

| guarantee | enforcement |
| --- | --- |
| Stdlib-only | no subprocess, no `gh`, no `git`, no network — pinned by source-text test |
| Text only | the module contains no `git apply`, `patch -`, `subprocess.run`, `subprocess.Popen` (pinned) |
| `safe_to_execute` is always `false` | hard-coded literal in source; pinned |
| Determinism | byte-identical `templates` list across runs (modulo `generated_at_utc`); pinned |
| Stable ordering | templates sorted by `template_id` ascending |
| Atomic writes | `tmp` + `os.replace` |
| Output scope | writes only under `logs/governance_bootstrap/` |

## CLI

```
python -m reporting.governance_bootstrap
python -m reporting.governance_bootstrap --no-write
python -m reporting.governance_bootstrap --status
python -m reporting.governance_bootstrap --frozen-utc 2026-05-05T12:00:00Z
```

There is **no execute mode**.

## Integration with the recurring scheduler

`reporting.recurring_maintenance` (v3.15.15.23) gains:

| `job_type` | risk | needs `gh`? | default interval | default enabled |
| --- | --- | --- | --- | --- |
| `refresh_governance_bootstrap` | LOW | no | 30 min | ✓ |

## Operator workflow

1. The recurring scheduler tick (every 30 min on every merge via
   the v3.15.16.3 deploy hook) runs:
   * `refresh_human_needed` → emits events
   * `refresh_governance_bootstrap` → synthesizes templates
2. Operator opens the PWA Inbox tab and sees a `failed_automation`
   row referencing a `governance_bootstrap_required` event.
3. Operator opens `logs/governance_bootstrap/latest.json` (or runs
   `python -m reporting.governance_bootstrap --status`) and copies
   the template's `branch_name`, `commit_message`, `file_diff`,
   `pr_title`, `pr_body` into a tiny one-shot bootstrap PR.
4. Operator merges the bootstrap PR after CI passes.
5. Next tick: `human_needed` no longer detects the gap → event
   clears → governance_bootstrap drops the template.
6. Loop continues.

## What this module is NOT

* **Not** an actuator. It produces text only. The v3.15.16.11
  execution engine (out of scope for Phase 1) is the only
  component that may turn templates into actual PRs, and even
  then it never auto-merges governance-bootstrap PRs (operator
  merges those manually per v3.15.16.10 §9).
* **Not** a risk arbiter. Risk classification belongs to
  `roadmap_execution_protocol` and `human_needed`.

## Files added by v3.15.16.9

```
reporting/governance_bootstrap.py
reporting/recurring_maintenance.py        (one new closed job entry)
tests/unit/test_governance_bootstrap.py
tests/unit/test_recurring_maintenance.py  (registry + per-job assertion)
docs/governance/governance_bootstrap.md   (this file)
docs/governance/bootstrap_templates/wiring_dashboard_py.md
docs/governance/bootstrap_templates/extend_agent_allowlist.md
docs/governance/bootstrap_templates/add_no_touch_carveout.md
docs/governance/recurring_maintenance.md  (job table + section)
docs/roadmap/qre_roadmap_v6_1.md
```

No new dependency. No `dashboard/dashboard.py` change. No
`.claude/` change. No frontend change. No frozen-contract change.
No live / paper / shadow / risk path touch. No test weakening.

## Cross-references

* `reporting/human_needed.py` — supplies the events.
* `reporting/approval_inbox.py` — surfaces the corresponding
  inbox row.
