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
| `refresh_roadmap_priority` | LOW | no | 30 min | ✓ | refreshes `roadmap_priority` read-only digest (v3.15.16.2) |
| `refresh_task_board` | LOW | no | 30 min | ✓ | refreshes `task_board` state-machine digest (v3.15.16.6) |
| `refresh_agent_flow` | LOW | no | 30 min | ✓ | refreshes `agent_flow` orchestration digest (v3.15.16.7) |
| `refresh_human_needed` | LOW | no | 30 min | ✓ | refreshes `human_needed` blocker-detection digest (v3.15.16.8) |
| `refresh_governance_bootstrap` | LOW | no | 30 min | ✓ | refreshes `governance_bootstrap` PR-template digest (v3.15.16.9) |
| `refresh_merge_preflight` | LOW | no | 30 min | ✓ | refreshes `development_merge_preflight` dry-run digest (v3.15.16.N5b.phase1; pure stdlib projector over A22 + A23; never merges, never calls `gh`, never deploys, never mints/verifies approval tokens; failure-non-fatal when upstream A22/A23 artefacts are absent) |

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

## Task board projection (v3.15.16.6)

A new closed job entry — `refresh_task_board` — runs the
read-only state-machine projection
(`reporting.task_board.collect_snapshot` + `write_outputs`) every
30 minutes by default. The projection is a pure function over
`logs/proposal_queue/latest.json`,
`logs/roadmap_priority/latest.json`,
`logs/github_pr_lifecycle/latest.json`,
`logs/approval_inbox/latest.json`. It writes the deterministic
kanban digest into `logs/task_board/latest.json`.

Hard guarantees re-asserted at this layer:

* LOW risk; `needs_gh = False`; default-enabled.
* `safe_to_execute` is hard-coded `false` in the digest schema
  and pinned by a unit test.
* The job never starts a branch, never opens a PR, never merges,
  never invokes `gh`. It is observability only.
* See `docs/governance/task_board.md` for the closed state /
  owner-agent vocabularies, the rule precedence, and the operator
  workflow.

## Agent flow projection (v3.15.16.7)

A new closed job entry — `refresh_agent_flow` — runs the
read-only orchestration projection
(`reporting.agent_flow.collect_snapshot` + `write_outputs`) every
30 minutes by default. Reads `logs/task_board/latest.json` and
emits per-task handoff records carrying `responsible_agent`,
`next_agent`, `next_action_proposed` (closed eight-element enum),
`blocking_reason`, `handoff_eligible`. The future v3.15.16.11
actuator consumes `next_action_proposed` directly.

Hard guarantees re-asserted at this layer:

* LOW risk; `needs_gh = False`; default-enabled.
* `safe_to_execute` is hard-coded `false` in the digest schema.
* The job never starts a branch, never opens a PR, never merges,
  never invokes `gh`. It is observability only.
* See `docs/governance/agent_flow.md` for the closed action /
  next_agent mappings.

## human_needed blocker detection (v3.15.16.8)

A new closed job entry — `refresh_human_needed` — runs the
read-only blocker-detection projection
(`reporting.human_needed.collect_snapshot` + `write_outputs`)
every 30 minutes by default. Reads
`logs/task_board/latest.json` and statically analyses
`dashboard/api_*.py` + `dashboard/dashboard.py` for wiring gaps.
Each open event surfaces in the existing approval-inbox PWA card
via the `_build_from_human_needed` projection.

Hard guarantees re-asserted at this layer:

* LOW risk; `needs_gh = False`; default-enabled.
* `safe_to_execute` is hard-coded `false` in the digest schema.
* `proposed_patch` is text only; the module contains no
  patch-application call (pinned).
* The job never starts a branch, never opens a PR, never merges,
  never invokes `gh`.

## Governance-bootstrap synthesizer (v3.15.16.9)

A new closed job entry — `refresh_governance_bootstrap` — runs
the read-only PR-template synthesizer
(`reporting.governance_bootstrap.collect_snapshot` +
`write_outputs`) every 30 minutes by default. Reads
`logs/human_needed/latest.json` and writes
`logs/governance_bootstrap/latest.json` with one copy-paste-able
PR template per bootstrappable event. Pinned by tests: the module
contains no patch-application code; produces text only.

Hard guarantees re-asserted at this layer:

* LOW risk; `needs_gh = False`; default-enabled.
* `safe_to_execute` is hard-coded `false` in the digest schema.
* The job never starts a branch, never opens a PR, never merges,
  never invokes `gh`, never applies a patch.

See `docs/governance/governance_bootstrap.md` for the synthesizer
contract and the three template-shape cross-references.

## Deploy-hook integration (v3.15.16.3)

`scripts/deploy_vps_dashboard.sh` runs a **best-effort, non-fatal**
post-deploy step that calls
`python3 -m reporting.recurring_maintenance --run-due-once` on
the VPS host after every successful merge to `main`. This drives
the typed scheduler once per merge so every Agent-Control-facing
read-only artifact (`logs/proposal_queue/latest.json`,
`logs/approval_inbox/latest.json`,
`logs/github_pr_lifecycle/latest.json`,
`logs/roadmap_priority/latest.json`,
`logs/workloop_runtime/latest.json`) is refreshed without manual
SSH or operator commands.

Hard guarantees re-asserted at this call site:

* The deploy script does **not** pass
  `--enable-dependabot-execute-safe`, so the only execute-capable
  job (`dependabot_low_medium_execute_safe`) is classified
  `blocked` with reason `missing_dependabot_cli_opt_in`. By
  construction at this call site, the deploy hook can never
  trigger a Dependabot mutation.
* The step is wrapped in `if ...; then ... else ... fi` so a
  non-zero exit is non-fatal — `set -e` does not trip on
  commands inside `if` conditions, and the deploy still exits 0
  even if the recurring tick fails.
* Failures project into the existing approval-inbox surface
  (`failed_automation` row on first failure,
  `runtime_halt` row after 3 consecutive failures), which the
  operator sees on the PWA without any new code.

This is the **merge-driven cadence**. Between-merge ongoing
freshness — running the same scheduler every 10–30 min via a
systemd timer on the VPS — requires the operator-authored
governance-bootstrap that adds `ops/systemd/*` to an agent's
`allowed_roots` union, and is the explicit scope of a separate
later release. See `docs/governance/vps_deploy.md`
§"Post-deploy recurring maintenance refresh (v3.15.16.3)" for
the deploy-hook contract in full.

## Roadmap priority projection (v3.15.16.2)

A new closed job entry — `refresh_roadmap_priority` — runs the
read-only prioritizer (`reporting.roadmap_priority.collect_snapshot`
+ `write_outputs`) every 30 minutes by default. The prioritizer
is a pure projection over `logs/proposal_queue/latest.json`; it
calls `reporting.roadmap_execution_protocol.plan_item` on each
proposal to obtain the per-item decision and writes the
deterministic `chosen_next_up` candidate into
`logs/roadmap_priority/latest.json`.

Hard guarantees re-asserted at this layer:

* LOW risk; `needs_gh = False`; default-enabled.
* `safe_to_execute` is hard-coded `false` in the digest schema
  and pinned by a unit test.
* The job never starts a branch, never opens a PR, never merges,
  never invokes `gh`. It is observability only.
* See `docs/governance/roadmap_priority.md` for the eligibility
  filters, ranking policy, and operator workflow.

## VPS-side automation (v3.15.16.1)

`reporting.github_pr_lifecycle --mode dry-run --no-smoke` is now
**also** invoked as a best-effort post-deploy step at the end of
`scripts/deploy_vps_dashboard.sh`. This refreshes
`logs/github_pr_lifecycle/latest.json` on the VPS after every
merge to `main`, so `/api/agent-control/pr-lifecycle` and the
Agent Control PWA's PRs tab always have data without any manual
SSH step.

The post-deploy refresh is **non-fatal** — a failure logs a
single line and the deploy still exits 0. The recurring
maintenance scheduler in this module continues to be the
canonical, scheduled refresh path; the deploy hook is an
additive freshness guarantee that pins "fresh on every merge"
specifically.

See `docs/governance/vps_deploy.md` §"Post-deploy PR lifecycle
artifact refresh (v3.15.16.1)" for the detailed contract.

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
