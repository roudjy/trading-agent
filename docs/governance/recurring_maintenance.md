# Recurring Maintenance — Operator Runbook

> Module: `reporting.recurring_maintenance`
> Release: v3.15.15.23
> Schema: [`recurring_maintenance/schema.v1.md`](recurring_maintenance/schema.v1.md)
> Sits on top of: `reporting.workloop_runtime` (v3.15.15.22),
> `reporting.proposal_queue` (v3.15.15.19),
> `reporting.approval_inbox` (v3.15.15.20),
> `reporting.github_pr_lifecycle` (v3.15.15.17).

This is the operator-facing runbook for the v3.15.15.23 recurring
safe-maintenance scheduler. It is a **typed, whitelisted,
deterministic** loop that runs five low-risk maintenance jobs on a
schedule. The Dependabot execute-safe job is **disabled by default**
and requires explicit CLI opt-in.

## TL;DR

```sh
# List the registry + persisted state, no execution.
python -m reporting.recurring_maintenance --list-jobs

# Show which jobs are due now (no execution).
python -m reporting.recurring_maintenance --plan

# Run a specific job by name.
python -m reporting.recurring_maintenance \
    --run-once refresh_workloop_runtime_once

# Run every job whose next_run_after_utc has passed, exactly once.
python -m reporting.recurring_maintenance --run-due-once

# Bounded loop. Honors the standard clamps.
python -m reporting.recurring_maintenance --loop \
    --interval-seconds 600 --max-iterations 4

# Read latest.json without re-running.
python -m reporting.recurring_maintenance --status

# Opt in to running the Dependabot LOW/MEDIUM execute-safe job.
# Without this flag, the job is ALWAYS skipped, regardless of its
# enabled flag in state.json.
python -m reporting.recurring_maintenance --run-due-once \
    --enable-dependabot-execute-safe
```

## Hard guarantees (enforced by code AND tests)

| guarantee | enforcement |
|---|---|
| Closed job registry — exactly five entries | `test_job_registry_contains_only_approved_types` |
| Unknown job types refused at boundary | `test_unknown_job_type_is_refused` |
| No `--command`/`--argv`/`--shell`/`--cmd` CLI flags | `test_cli_does_not_accept_freeform_command_flags` |
| No `subprocess` / `shell=True` / `os.system` / `Popen` | `test_module_does_not_invoke_subprocess_directly` |
| `--max-iterations` clamped to 24 | `test_loop_clamps_max_iterations` |
| `--interval-seconds` clamped to `[30, 21600]` | `test_loop_clamps_interval_seconds` |
| One failing job does NOT crash others | `test_one_failing_job_does_not_crash_others` |
| Per-job timeout produces `state="timeout"` | `test_job_timeout_classified_as_timeout` |
| JSON write is atomic (`tmp` + `os.replace`) | `test_json_write_is_atomic` |
| `history.jsonl` appends one line per run | `test_history_jsonl_appends_one_record_per_run` |
| `safe_to_execute` is always `false` | `test_safe_to_execute_is_always_false` |
| Job state survives process restarts via state.json | `test_job_state_persists_across_runs` |
| Disabled job → `state=skipped` | `test_disabled_job_skipped` |
| Dependabot job disabled by default | `test_dependabot_job_disabled_by_default` |
| Dependabot job requires `--enable-dependabot-execute-safe` | `test_dependabot_job_requires_cli_opt_in` |
| Dependabot job delegates HIGH-risk refusal to lifecycle module | (covered by lifecycle module tests) |
| Approval inbox surfaces failed/blocked jobs | `test_runtime_halt_after_consecutive_failures`, `test_failed_jobs_emit_failed_automation` |
| Frozen-contract sha256 unchanged around runs | `test_frozen_contracts_byte_identical_around_run` |

## Job types

| job_type | risk | needs gh? | default interval | default enabled | what it does |
|---|---|---|---|---|---|
| `refresh_workloop_runtime_once` | LOW | no | 15 min | ✓ | runs `workloop_runtime.run_once()` in-process |
| `refresh_proposal_queue` | LOW | no | 60 min | ✓ | refreshes `proposal_queue` dry-run artifact |
| `refresh_approval_inbox` | LOW | no | 15 min | ✓ | refreshes `approval_inbox` dry-run artifact |
| `refresh_github_pr_lifecycle_dry_run` | LOW | yes | 30 min | ✓ | refreshes `github_pr_lifecycle` dry-run artifact |
| `dependabot_low_medium_execute_safe` | MEDIUM | yes | 60 min | **✗** | delegates to `github_pr_lifecycle` execute-safe path |

## Dependabot execute-safe — two-layer opt-in

The Dependabot LOW/MEDIUM execute-safe job is the **only** job that
can mutate GitHub state (post `@dependabot rebase` comments,
squash-merge LOW/MEDIUM Dependabot PRs). It is gated by **two
independent flags**:

1. **State-file enabled flag** — defaults to `false`. Operators who
   want it scheduled must edit `logs/recurring_maintenance/state.json`
   and set `enabled: true` for that job.
2. **CLI opt-in** — even when `enabled=true` in state, the CLI must
   pass `--enable-dependabot-execute-safe` for the run to actually
   invoke the lifecycle path. Without that flag, the job is
   `blocked` with `blocked_reason: missing_dependabot_cli_opt_in`.

This double-gate exists so a stray `cron` invocation cannot
accidentally start merging PRs just because the scheduler exists.

When both flags are set, the job calls
`reporting.github_pr_lifecycle.execute_safe_actions(...)`. That
module owns every Dependabot precondition:

* PR author is `dependabot[bot]`.
* PR base is `main`, not draft.
* PR risk class is LOW or MEDIUM (HIGH is NEVER merged).
* `mergeStateStatus == "CLEAN"`.
* Every required GitHub check is `passed`.
* No protected paths in the diff.
* No frozen-contract files in the diff.
* No live/paper/shadow/trading/risk paths.
* No CI/test weakening.

The maintenance scheduler does NOT re-implement those checks — it
just refuses to invoke the path unless the operator opts in.

## Status semantics

| value | meaning |
|---|---|
| `not_run` | job has never run on this checkout |
| `succeeded` | last run completed cleanly |
| `skipped` | job was disabled in state, OR not yet due |
| `blocked` | preconditions failed |
| `failed` | executor raised an exception |
| `timeout` | executor exceeded the per-job wall-clock budget |
| `not_available` | executor returned a non-dict (upstream reshape) |

## Reading the JSON artifact

```sh
# Latest digest:
jq '.final_recommendation' logs/recurring_maintenance/latest.json

# Per-job last_status + interval:
jq '.jobs[] | {job_type, last_status, schedule, enabled}' \
   logs/recurring_maintenance/latest.json

# History (append-only):
tail -n 10 logs/recurring_maintenance/history.jsonl | jq -c '.iteration, .counts'
```

## Approval-inbox integration

`reporting.approval_inbox` reads
`logs/recurring_maintenance/latest.json` and emits:

* `consecutive_failures >= 3` on any job → one `runtime_halt` item
  (severity: critical).
* Each job with `last_status in {failed, timeout}` → one
  `failed_automation` item (severity: high).
* Each job with `last_status == blocked` → one `unknown_state`
  item (severity: medium).

Clean runs (every job `succeeded` / `not_run` / `skipped`) emit
zero items.

## Status-card integration

The PWA Status card on `/agent-control` shows a
`recurring_maintenance` row with a pill (`ok` / `warn` / `danger` /
`unknown`) derived from the digest's `final_recommendation`. The
PWA continues to consume only the existing `/api/agent-control/status`
endpoint — no new dashboard.py wiring.

## Operator workflow

1. **Bring up the scheduler**: `python -m reporting.recurring_maintenance --list-jobs`
   to see the registry and current state.
2. **Plan**: `python -m reporting.recurring_maintenance --plan`
   to see which jobs are due.
3. **Run-due-once**: `python -m reporting.recurring_maintenance --run-due-once`
   for a one-shot pass.
4. **Loop**: `python -m reporting.recurring_maintenance --loop --max-iterations 4 --interval-seconds 600`
   for a bounded recurring run.
5. **Triage**: `python -m reporting.approval_inbox --mode dry-run`
   to see whether any maintenance failure has surfaced as an inbox
   item. Or open the Agent Control PWA Status card.

## Forward roadmap (not shipped here)

| release | adds |
|---|---|
| **v3.15.15.23 (this)** | typed scheduler, registry, loop driver, inbox + status integration, read-only PWA card |
| v3.15.15.24 | per-job audit-ledger linkage (populated `audit_refs`) |
| v3.15.15.25 | metrics dashboards on top of `history.jsonl` |
| later | systemd service / cron wrapper around the loop driver |

## Files added by v3.15.15.23

```
reporting/recurring_maintenance.py
docs/governance/recurring_maintenance/schema.v1.md
docs/governance/recurring_maintenance.md          (this file)
tests/unit/test_recurring_maintenance.py
```

Plus extensions:

```
reporting/approval_inbox.py                       (+_build_from_recurring_maintenance)
dashboard/api_agent_control.py                    (+_recurring_maintenance_summary)
frontend/src/api/agent_control.ts                 (extended Status type)
frontend/src/routes/AgentControl.tsx              (Status card maintenance row)
frontend/src/test/AgentControl.test.tsx           (maintenance row mock + assertion)
tests/unit/test_approval_inbox.py                 (maintenance projection tests)
tests/unit/test_dashboard_api_agent_control.py    (maintenance block test)
```

No new dependencies. No write to `dashboard/dashboard.py`. No write
to `.claude/**`. Frozen-contract hashes unchanged.
