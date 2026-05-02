# Workloop Runtime — Operator Runbook

> Module: `reporting.workloop_runtime`
> Release: v3.15.15.22
> Schema: [`workloop_runtime/schema.v1.md`](workloop_runtime/schema.v1.md)
> Sibling reporters consumed: `governance_status`, `agent_audit_summary`,
> `autonomous_workloop`, `github_pr_lifecycle`, `proposal_queue`,
> `approval_inbox`, `execute_safe_controls`.

This is the operator-facing runbook for the v3.15.15.22 long-running
workloop runtime. The runtime is an **observe / classify / report**
supervisor — never an autonomous executor.

## TL;DR

```sh
# Single iteration, write artifact, exit. This is the default.
python -m reporting.workloop_runtime --once

# Bounded loop. Clamped to MAX_ITERATIONS_LIMIT=24 and an interval
# of [30, 21600] seconds. Tests rely on this clamping.
python -m reporting.workloop_runtime --loop \
    --interval-seconds 300 --max-iterations 3

# Read the most recent artifact without re-running.
python -m reporting.workloop_runtime --status
```

The runtime is **stdlib-only**. It calls the seven supervised
reporting modules in-process, captures their results into a single
JSON envelope, and writes the envelope atomically.

## Hard guarantees (enforced by code AND tests)

| guarantee | enforcement |
|---|---|
| Stdlib-only — no subprocess / `gh` / `git` / network | `test_module_does_not_invoke_subprocess_or_gh_or_git` |
| `--once` runs exactly one iteration | `test_once_mode_writes_one_artifact` |
| `--loop` honours `--max-iterations` (clamped to 24) | `test_loop_mode_respects_max_iterations` |
| `--interval-seconds` clamped to `[30, 21600]` | `test_loop_clamps_interval_seconds` |
| One failing source does not crash the loop or other sources | `test_one_failing_source_does_not_crash_others` |
| Per-source wall-clock timeout produces `state="timeout"` | `test_timeout_classified_as_timeout` |
| Missing source returns `not_available` (never silently OK) | `test_missing_source_classified_not_available` |
| Malformed JSON in upstream artifact does not crash the supervisor | `test_malformed_json_handled_safely` |
| JSON write is atomic (`tmp` + `os.replace`) | `test_json_write_is_atomic` |
| `history.jsonl` appends one line per iteration | `test_history_jsonl_appends_one_record_per_run` |
| Credential-value patterns (sk-ant-, ghp_, ...) are caught at every layer | `test_credential_value_in_source_is_classified_failed` |
| `safe_to_execute` is always `false` | `test_safe_to_execute_is_always_false` |
| KeyboardInterrupt produces graceful stop | `test_keyboard_interrupt_exits_gracefully` |
| Schema is stable | `test_top_level_shape`, `test_every_source_carries_required_fields` |

## What the runtime does NOT do

* No Dependabot execute-safe scheduling.
* No recurring maintenance automation.
* No browser push notifications.
* No POST/PUT/PATCH/DELETE API.
* No approve/reject/merge/execute buttons.
* No arbitrary shell command runner.
* No GitHub mutation.
* No `git push`, force-push, admin merge, direct main push.
* No live/paper/shadow/trading/risk behavior changes.
* No frozen-contract changes.
* No `.claude/**` changes.
* No CI/test weakening.
* No paid/external telemetry/signup/secrets.
* No new `dashboard.py` wiring (the runtime status flows through
  the already-wired `/api/agent-control/status` endpoint).

## Source catalog (closed)

| source | needs gh? | typical state |
|---|---|---|
| `governance_status` | no | `ok` |
| `agent_audit_summary` | no | `ok` if today's ledger exists, else `not_available` |
| `autonomous_workloop` | no | `ok` (may be `degraded` if blocked items) |
| `github_pr_lifecycle` | yes | `ok` if gh authenticated, else `not_available` |
| `proposal_queue` | no | `ok` |
| `approval_inbox` | no | `ok` |
| `execute_safe_controls` | no | `ok` (catalog-only) |

Each source is called in-process; per-source wall-clock timeout
defaults to 60s. Adding a new source requires a new release plus
an ADR.

## State enum

| value | meaning |
|---|---|
| `ok` | source ran healthily |
| `degraded` | source ran but reports non-fatal trouble |
| `not_available` | source ran but a required upstream is missing |
| `failed` | source raised an exception or leaked a credential value |
| `timeout` | source did not return within the wall-clock budget |
| `skipped` | reserved (not emitted in v3.15.15.22) |
| `unknown` | supervisor could not classify; never elevated |

## Approval-inbox integration

`reporting.approval_inbox` reads `logs/workloop_runtime/latest.json`
and emits inbox items per the rules in
[`schema.v1.md`](workloop_runtime/schema.v1.md):

* `loop_health.consecutive_failures >= 3` → one `runtime_halt`
  item (severity: critical).
* Each source with `state in {failed, timeout}` → one
  `failed_automation` item (severity: high).
* Each source with `state == unknown` → one `unknown_state` item
  (severity: medium).

A clean runtime artifact (every source `ok` or only
`not_available`) produces zero new inbox items. The
`not_available` source generates a separate "missing source" item
the way it always did.

## Status-card integration

The Status card on the Agent Control PWA gains:

* a runtime pill (`ok` / `warn` / `danger`) derived from
  `loop_health.consecutive_failures` and `final_recommendation`;
* a row showing the runtime's `final_recommendation` string when
  the artifact is available.

The card consumes the existing GET-only
`/api/agent-control/status` endpoint, which in turn calls
`reporting.workloop_runtime.read_latest_snapshot()` in-process. No
new dashboard.py wiring is required.

## Reading the JSON artifact

```sh
# Latest snapshot:
jq '.final_recommendation' logs/workloop_runtime/latest.json

# Per-source state:
jq '.sources[] | {source, state, summary}' logs/workloop_runtime/latest.json

# Loop health across iterations:
jq '.loop_health' logs/workloop_runtime/latest.json

# Append-only history (one line per iteration):
tail -n 5 logs/workloop_runtime/history.jsonl | jq -c '.run_id, .counts'
```

## Operator workflow

1. **One-shot debugging**: `python -m reporting.workloop_runtime --once`
   to refresh upstream artifacts in-process and see which sources
   are healthy.
2. **Bounded loop**: `python -m reporting.workloop_runtime --loop
   --max-iterations 6 --interval-seconds 600` to run 6 iterations
   over an hour. The CLI exits 0 when the loop completes; SIGINT
   exits 130 (graceful).
3. **Inspect**: `python -m reporting.workloop_runtime --status` or
   open the Agent Control PWA Status card.
4. **Triage failures**: any `failed` / `timeout` source produces a
   `failed_automation` inbox item the next time
   `python -m reporting.approval_inbox` runs (or the next time the
   PWA refreshes its inbox endpoint).

## Forward roadmap (not shipped here)

| release | adds |
|---|---|
| **v3.15.15.22 (this)** | observe-only runtime, schema, inbox + status integration, read-only PWA card |
| v3.15.15.23 | browser push for `needs_human` / `runtime_halt` items |
| v3.15.15.25 | metrics / observability dashboards on top of `history.jsonl` |

## Files added by v3.15.15.22

```
reporting/workloop_runtime.py
docs/governance/workloop_runtime/schema.v1.md
docs/governance/workloop_runtime.md          (this file)
tests/unit/test_workloop_runtime.py
```

Plus extensions:

```
reporting/approval_inbox.py                  (+_build_from_workloop_runtime)
dashboard/api_agent_control.py               (+_workloop_runtime_summary)
frontend/src/api/agent_control.ts            (extended Status type)
frontend/src/routes/AgentControl.tsx         (Status card runtime row)
frontend/src/test/AgentControl.test.tsx      (runtime row mock + assertion)
tests/unit/test_approval_inbox.py            (+ runtime-projection tests)
tests/unit/test_dashboard_api_agent_control.py (+ workloop_runtime block test)
```

No new dependencies. No write to `dashboard/dashboard.py`. No write
to `.claude/**`. Frozen-contract hashes unchanged.
