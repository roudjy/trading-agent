# Workloop Runtime Digest — Schema v1

> Module: `reporting.workloop_runtime`
> Module version: `v3.15.15.22`
> Schema version: `1`
> Artifact path (gitignored): `logs/workloop_runtime/latest.json`
> Timestamped copies: `logs/workloop_runtime/<UTC>.json`
> Append-only history: `logs/workloop_runtime/history.jsonl`

## Top-level fields

| field | type | values | notes |
|---|---|---|---|
| `schema_version` | int | `1` | bump on breaking changes |
| `report_kind` | string | `"workloop_runtime_digest"` | constant |
| `runtime_version` | string | `"v3.15.15.22"` | source-of-truth |
| `generated_at_utc` | string | RFC3339 UTC | seconds resolution |
| `run_id` | string | `"wl_<sha8>"` | deterministic over `generated_at_utc` + `iteration` |
| `mode` | enum | `"once"` / `"loop"` | matches the CLI flag |
| `iteration` | int | `0..max_iterations - 1` | zero-based |
| `max_iterations` | int | clamped to `MAX_ITERATIONS_LIMIT` (24) | |
| `interval_seconds` | int \| null | clamped to `[30, 21600]` | only set in loop mode |
| `next_run_after_utc` | string \| null | RFC3339 UTC | only set in loop mode |
| `duration_ms` | int | wall-clock for the iteration | |
| `safe_to_execute` | bool | **always `false` in v3.15.15.22** | runtime never grants execute rights |
| `loop_health` | object | see "loop_health" | |
| `sources` | array | see "Source result" | one per supervised source |
| `counts` | object | aggregate state counts | |
| `final_recommendation` | string | see "final_recommendation" | |

## `loop_health` object

```json
{
  "iterations_completed": 7,
  "iterations_failed": 1,
  "last_success_utc": "2026-05-02T10:00:00Z",
  "last_failure_utc": "2026-05-02T09:30:00Z",
  "consecutive_failures": 0
}
```

`consecutive_failures` survives process restarts (read from
`latest.json`). Three or more consecutive failed iterations promote
the runtime to `runtime_halt` in the approval inbox.

## Source result

One entry per supervised reporter. The catalog of supervised
sources is **closed** — adding a new source requires a new release
plus an ADR.

| field | type | notes |
|---|---|---|
| `source` | string | short name (e.g. `"governance_status"`) |
| `module` | string | dotted module path (e.g. `"reporting.governance_status"`) |
| `state` | enum | see "State enum" |
| `duration_ms` | int | wall-clock per source |
| `summary` | string | length-capped human-readable note |
| `artifact_path` | string | repo-relative path of the upstream artifact (informational) |
| `error_class` | string \| null | `type(e).__name__` on a `failed` source |

### Closed source catalog

| source | module | needs gh? | notes |
|---|---|---|---|
| `governance_status` | `reporting.governance_status` | no | always in-process |
| `agent_audit_summary` | `reporting.agent_audit_summary` | no | reads today's ledger |
| `autonomous_workloop` | `reporting.autonomous_workloop` | no | dry-run only |
| `github_pr_lifecycle` | `reporting.github_pr_lifecycle` | yes | dry-run only; degrades to `not_available` when gh missing |
| `proposal_queue` | `reporting.proposal_queue` | no | dry-run only |
| `approval_inbox` | `reporting.approval_inbox` | no | dry-run only |
| `execute_safe_controls` | `reporting.execute_safe_controls` | no | catalog-only (eligibility planning, never execution) |

## State enum

| value | meaning |
|---|---|
| `ok` | source returned a valid envelope and its envelope-inspector classified it as healthy |
| `degraded` | source ran but its envelope reports a non-fatal problem (e.g. audit chain broken) |
| `not_available` | source returned but a required upstream is missing (e.g. gh not installed) |
| `failed` | source raised an exception OR its inner result tripped the credential-value guard |
| `timeout` | source did not return within the per-source wall-clock budget |
| `skipped` | reserved for future opt-out flows; not emitted in v3.15.15.22 |
| `unknown` | the supervisor could not classify; never elevated to `ok` |

## `final_recommendation` enum

| value | meaning |
|---|---|
| `"all_sources_ok"` | every supervised source returned `ok` |
| `"degraded_not_available_<n>"` | at least one source is `not_available` (no failures) |
| `"degraded_failed_<f>_timeout_<t>"` | at least one source `failed` or timed out |
| `"runtime_halt_after_<n>_consecutive_failures"` | three or more consecutive iterations failed; the inbox emits a `runtime_halt` item |

## `counts` object

```json
{
  "total": 7,
  "by_state": {"ok": 5, "degraded": 1, "not_available": 1}
}
```

## Hard guarantees encoded in the schema

* `safe_to_execute` is **always `false`** in this release.
* The supervisor never invokes `git`, `gh`, `subprocess`, or any
  arbitrary command. Each source is called in-process.
* Per-source wall-clock timeout. Cross-platform (thread-join).
* One failing source does NOT crash the loop or other sources.
* JSON write is atomic (`tmp` + `os.replace`).
* `history.jsonl` is append-only.
* `_assert_no_credential_values` (sk-ant-, ghp_, github_pat_, AKIA,
  BEGIN PRIVATE KEY) runs over every source's inner snapshot AND
  the final outer snapshot. Sensitive-path fragments are intentionally
  NOT checked at the runtime layer because supervised snapshots
  legitimately echo path-shaped strings (`config/config.yaml` in
  no-touch metadata, `state/*.secret` glob references, etc.) —
  those are metadata, not leaks.
* `MAX_ITERATIONS_LIMIT` (24) and `[MIN_INTERVAL_SECONDS=30,
  MAX_INTERVAL_SECONDS=21600]` are clamped at the CLI boundary so a
  runaway loop is impossible.

## Loop semantics

* `--once` runs exactly one iteration, writes the artifact, and
  exits 0. This is the default and what tests use.
* `--loop` runs up to `--max-iterations` iterations with
  `--interval-seconds` between them. Both flags are clamped.
* `KeyboardInterrupt` causes a graceful exit — the partial snapshot
  list is preserved on disk; the loop does not crash mid-write.
* Loop health (`iterations_completed`, `iterations_failed`,
  `consecutive_failures`) survives process restarts because each
  iteration reads `latest.json` before writing the new one.

## CLI flags

```
--once                      single iteration (default)
--loop                      bounded loop
--status                    print latest.json contents and exit
--interval-seconds N        clamped to [30, 21600]
--max-iterations N          clamped to 24
--timeout-per-source-seconds N
--no-write                  stdout only
--indent N                  JSON indent (0 = compact)
```

`--once` / `--loop` / `--status` are mutually exclusive.

## Wiring with the rest of the system

| consumer | how it consumes the runtime artifact |
|---|---|
| `dashboard.api_agent_control._status_payload` | calls `read_latest_snapshot()` in-process and surfaces a compact projection under `status.workloop_runtime` |
| `reporting.approval_inbox._build_from_workloop_runtime` | maps `loop_health.consecutive_failures >= 3` → `runtime_halt`, each `failed`/`timeout` source → `failed_automation`, each `unknown` source → `unknown_state` |
| `frontend/src/routes/AgentControl.tsx::StatusCard` | renders a runtime pill + final-recommendation row inside the existing Status card; no new endpoint |

No new dashboard route is wired in v3.15.15.22 — the runtime
status flows through the already-wired
`/api/agent-control/status` endpoint.

## Forbidden in v3.15.15.22

* Dependabot execute-safe scheduling.
* Recurring maintenance automation.
* Browser push notifications.
* POST/PUT/PATCH/DELETE on the dashboard surface.
* Approve/reject/merge/execute buttons.
* Arbitrary shell command runner.
* GitHub mutation, git push, force-push, admin merge, direct main push.
* `safe_to_execute=true`.

The next release (v3.15.15.23) introduces browser push for
`needs_human` / critical inbox items including `runtime_halt`. The
runtime itself stays read-only.
