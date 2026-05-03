# Recurring Maintenance Digest — Schema v1

> Module: `reporting.recurring_maintenance`
> Module version: `v3.15.15.23`
> Schema version: `1`
> Artifact paths (gitignored):
> * `logs/recurring_maintenance/latest.json`
> * timestamped copies: `logs/recurring_maintenance/<UTC>.json`
> * append-only history: `logs/recurring_maintenance/history.jsonl`
> * persisted per-job state: `logs/recurring_maintenance/state.json`

## Top-level fields

| field | type | values | notes |
|---|---|---|---|
| `schema_version` | int | `1` | bump on breaking changes |
| `report_kind` | string | `"recurring_maintenance_digest"` | constant |
| `module_version` | string | `"v3.15.15.23"` | source-of-truth |
| `generated_at_utc` | string | RFC3339 UTC | seconds resolution |
| `mode` | enum | `"list"` / `"plan"` / `"run_once"` / `"run_due_once"` / `"loop"` / `"status"` | mirrors the CLI |
| `iteration` | int | `0..max_iterations - 1` | zero-based |
| `max_iterations` | int | clamped to `MAX_ITERATIONS_LIMIT` (24) | |
| `interval_seconds` | int \| null | clamped to `[30, 21600]` | only set in loop mode |
| `next_run_after_utc` | string \| null | RFC3339 UTC | only set in loop mode |
| `safe_to_execute` | bool | **always `false`** | digest-level guard |
| `jobs` | array | see "Job state" | one entry per registered job_type |
| `actions_taken` | array | see "Action" | empty when no execution happened |
| `counts` | object | aggregate status counts | |
| `final_recommendation` | string | see "final_recommendation" | |
| `due_now` (plan only) | array | list of job_types whose `next_run_after_utc <= now` | only set in `mode=plan` |

## Job state

One entry per registered job. The registry is **closed** —
exactly five entries.

| field | type | notes |
|---|---|---|
| `job_id` | string | `"j_<sha8>"` deterministic over `job_type` |
| `job_type` | enum | see "Job types" |
| `schedule` | object | `{kind: "fixed_interval", interval_seconds: int}` |
| `enabled` | bool | persisted in state.json; defaults from registry |
| `default_enabled` | bool | the registry default for this job_type |
| `risk_class` | enum | `"LOW"` / `"MEDIUM"` |
| `needs_gh` | bool | informational |
| `last_run_at_utc` | string \| null | RFC3339 UTC |
| `next_run_after_utc` | string \| null | RFC3339 UTC; bumped after every run |
| `last_status` | enum | see "Status enum" |
| `last_result_summary` | string \| null | short human-readable note |
| `consecutive_failures` | int | reset to 0 on success |
| `blocked_reason` | string \| null | non-null when last_status is `blocked` |
| `audit_refs` | array | reserved for future audit-ledger linkage |

## Job types (closed list)

| job_type | risk | needs gh? | default interval | default enabled |
|---|---|---|---|---|
| `refresh_workloop_runtime_once` | LOW | no | 15 min | yes |
| `refresh_proposal_queue` | LOW | no | 60 min | yes |
| `refresh_approval_inbox` | LOW | no | 15 min | yes |
| `refresh_github_pr_lifecycle_dry_run` | LOW | yes | 30 min | yes |
| `dependabot_low_medium_execute_safe` | MEDIUM | yes | 60 min | **no** (CLI opt-in required) |

Adding a new job requires a new release plus an ADR.

### Job semantics

* **`refresh_workloop_runtime_once`** — calls `reporting.workloop_runtime.run_once()` in-process. Read-only artifact refresh.
* **`refresh_proposal_queue`** — calls `reporting.proposal_queue.collect_snapshot(mode="dry-run")` + `write_outputs()`. Read-only.
* **`refresh_approval_inbox`** — calls `reporting.approval_inbox.collect_snapshot(mode="dry-run")` + `write_outputs()`. Read-only.
* **`refresh_github_pr_lifecycle_dry_run`** — calls `reporting.github_pr_lifecycle.collect_snapshot(mode="dry-run")` + `write_outputs()`. Read-only.
* **`dependabot_low_medium_execute_safe`** — delegates to the existing `reporting.github_pr_lifecycle` execute-safe path (`collect_snapshot(mode="execute-safe")` + `execute_safe_actions()`). The lifecycle module owns every Dependabot precondition (LOW/MEDIUM only, CLEAN mergeability, all checks green, no protected paths, no live/trading paths, etc.); the maintenance scheduler does not re-implement these — it only refuses to invoke the path unless the operator passes `--enable-dependabot-execute-safe`.

## Status enum

| value | meaning |
|---|---|
| `not_run` | job has never run on this checkout |
| `succeeded` | last run completed cleanly |
| `skipped` | job was disabled in state, or not yet due |
| `blocked` | preconditions failed (unknown job_type, missing CLI opt-in, etc.) |
| `failed` | executor raised an exception |
| `timeout` | executor exceeded the per-job wall-clock budget |
| `not_available` | executor returned a non-dict (upstream module reshape) |

## Action

```json
{
  "kind": "run_job",
  "target": "refresh_proposal_queue",
  "outcome": "succeeded",
  "reason": "proposal_queue review_3_proposed_items (duration_ms=210)"
}
```

`kind` is `"run_job"` for executions and `"refused"` for unknown
job types.

## `final_recommendation` enum

Stable values:

* `"all_jobs_ok"` — every job last_status is succeeded / not_run / skipped.
* `"degraded_failed_<n>"` — at least one job is in `failed`/`timeout`.
* `"degraded_blocked_<n>"` — at least one job is `blocked`.
* `"runtime_halt_after_<n>_consecutive_failures"` — any job has `consecutive_failures >= 3`.

## Hard guarantees encoded in the schema

* `safe_to_execute` is **always `false`** at the digest level.
* The Dependabot execute-safe job is **disabled by default** AND
  requires `--enable-dependabot-execute-safe` at the CLI even when
  enabled in state.json. Two layers of opt-in.
* No arbitrary command runner. The CLI does not accept `--command`,
  `--argv`, `--shell`, `--cmd`, or any equivalent flag.
* `--max-iterations` and `--interval-seconds` are clamped at the
  CLI boundary so a runaway loop is impossible.
* JSON write is atomic (`tmp` + `os.replace`).
* `history.jsonl` is append-only.
* Per-job wall-clock timeout (cross-platform thread-join).
* One failing job does NOT crash other jobs in the same iteration.
* Credential-VALUE patterns (sk-ant-, ghp_, github_pat_, AKIA,
  BEGIN PRIVATE KEY) refused at the snapshot boundary. Sensitive-
  PATH fragments are intentionally allowed in metadata so
  legitimate no-touch references flow through.

## Wiring with the rest of the system

| consumer | how it consumes the artifact |
|---|---|
| `reporting.approval_inbox` | reads `logs/recurring_maintenance/latest.json`. `consecutive_failures >= 3` → `runtime_halt`; each `failed` / `timeout` job → `failed_automation`; each `blocked` job → `unknown_state`. |
| `dashboard.api_agent_control._status_payload` | reads via `read_latest_snapshot()` and surfaces a compact `recurring_maintenance` block under `status`. |
| `frontend/src/routes/AgentControl.tsx::StatusCard` | renders a recurring-maintenance pill + final-recommendation row inside the existing Status card. No new endpoint. |

No new dashboard route is wired in v3.15.15.23 — the maintenance
status flows through the already-wired `/api/agent-control/status`
endpoint.

## Forbidden in v3.15.15.23

* HIGH-risk PR merge.
* Unknown-risk execution.
* Arbitrary shell commands.
* Free-form argv/command input.
* Browser push notifications.
* Approve/reject/merge buttons in the PWA.
* Approval status mutation.
* POST/PUT/PATCH/DELETE API.
* Live/paper/shadow/trading/risk behavior changes.
* Frozen-contract changes.
* `.claude/**` changes.
* CI/test weakening.
* Paid/external telemetry/signup/secrets.
* Wiring `api_execute_safe_controls` (intentionally unwired).
* Modifying `dashboard/dashboard.py`.
