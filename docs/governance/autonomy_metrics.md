# Autonomy metrics — operator runbook

Module: `reporting.autonomy_metrics`
Version: v3.15.15.27 (introduced in v3.15.15.25; stale-artifact
detection added in v3.15.15.27)
Schema: `docs/governance/autonomy_metrics/schema.v1.md`

## TL;DR

Read-only digest that aggregates the JSON artifacts produced by
the existing reporting modules into one snapshot. The digest
answers the questions: how much work is the system doing, how
much still needs Joery, where are blockers accumulating, are the
autonomous jobs reliable, and is anything unsafe leaking through
the safety net.

The collector does not expand any execution authority. It does
not add buttons, mutation endpoints, browser push, scheduling, or
new automation. It reads and projects.

## Hard guarantees

* Stdlib-only. No subprocess, no `gh`, no `git`, no network.
* Output limited to `logs/autonomy_metrics/`.
* Atomic writes (tmp + os.replace), history is append-only.
* Narrow credential-value redaction.
* Missing / malformed artifacts are COUNTED, not coerced to ok.
* Deterministic for a fixed set of input artifacts.
* `safety.high_or_unknown_executable_count` is expected to be 0.
  A non-zero value flips `final_recommendation` to
  `unsafe_state_detected`.

## Source artifacts

| source                    | path                                          |
| ------------------------- | --------------------------------------------- |
| workloop_runtime          | `logs/workloop_runtime/latest.json`           |
| recurring_maintenance     | `logs/recurring_maintenance/latest.json`      |
| proposal_queue            | `logs/proposal_queue/latest.json`             |
| approval_inbox            | `logs/approval_inbox/latest.json`             |
| github_pr_lifecycle       | `logs/github_pr_lifecycle/latest.json`        |
| execute_safe_controls     | `logs/execute_safe_controls/latest.json`      |

History (best-effort) for trend windows:

* `logs/workloop_runtime/history.jsonl`
* `logs/recurring_maintenance/history.jsonl`

A missing history is reported as
`{ "status": "not_available", "reason": "no_history" }` — never
guessed.

## Metric meanings (which are actionable)

### Throughput (informational)
`proposals_total`, `inbox_items_total`, `pr_lifecycle_*`,
`recurring_jobs_*`, `runtime_sources_*`,
`execute_safe_actions_total`. Use these to track whether the
autonomous loop is processing work, not as alarm signals.

### Operator burden (actionable)
`needs_human_total` and `estimated_operator_actions_total` are
the primary "go look at the inbox" signal. If these grow over
time without corresponding throughput, the system is queuing up
work the operator has not cleared.

`high_risk_blocked_total` and `unknown_state_total` should both
trend toward zero — non-zero values mean an upstream module
classified something HIGH or UNKNOWN and is waiting for review.

`top_operator_action_categories` is the focus list — the five
inbox categories with the most rows.

### Reliability (actionable)
`runtime_consecutive_failures` ≥ 3 → workloop runtime is in a
soft halt. Inspect `last_failure_at_utc` and the workloop runtime
artifact for the failing source.

`recurring_consecutive_failures_max` reports the worst per-job
consecutive failure count. Same threshold as runtime.

`source_failure_rate` and `job_failure_rate` are 0..1 fractions
over the most recent observed run.

`missing_artifact_count` and `malformed_artifact_count` count
upstream artifacts that did not parse cleanly. Both ≥ 1 is a
sign the loop is running but producing bad output.

### Safety (actionable; must remain zero)
`high_or_unknown_executable_count` MUST be 0. A non-zero value
means the cross-check between approval_policy and
execute_safe_controls broke — investigate immediately.

The `*_risk_count` metrics surface the per-category counts of
inbox rows that the operator has not yet cleared. They are
expected to be small but non-zero is normal.

## Interpreting `final_recommendation`

| value                       | meaning                                                          |
| --------------------------- | ---------------------------------------------------------------- |
| `healthy`                   | no missing/malformed sources, no operator burden, no unsafe state |
| `action_required`           | operator has rows to clear but the system is otherwise fine      |
| `degraded_missing_sources`  | ≥ 2 source artifacts are missing                                 |
| `degraded_failures`         | malformed source(s) or runtime consecutive_failures ≥ 3          |
| `unsafe_state_detected`     | `high_or_unknown_executable_count > 0` — STOP                    |
| `not_available`             | no source artifacts present at all                               |

## What should trigger human attention

* `final_recommendation == unsafe_state_detected` — page Joery.
* `runtime_consecutive_failures >= 3`.
* `recurring_consecutive_failures_max >= 3`.
* `high_or_unknown_executable_count != 0`.
* `frozen_contract_risk_count != 0`.
* `live_paper_shadow_risk_count != 0`.
* `secret_or_external_account_required_count != 0`.
* `paid_tool_required_count != 0`.

## Metrics that MUST remain zero

* `safety.high_or_unknown_executable_count`.
* All `safety.*_risk_count` metrics over a long enough horizon
  (transients during operator review are expected).
* `policy.high_or_unknown_is_executable` is False by construction;
  if the projection ever flips to True, the safety contract
  broke.

## CLI

```
python -m reporting.autonomy_metrics --collect
python -m reporting.autonomy_metrics --collect --no-write
python -m reporting.autonomy_metrics --collect --frozen-utc 2026-05-03T12:00:00Z
python -m reporting.autonomy_metrics --collect --stale-threshold-seconds 300
python -m reporting.autonomy_metrics --status
```

`--collect` reads the source artifacts and writes a digest.
`--status` prints the latest digest from
`logs/autonomy_metrics/latest.json`.

`--no-write` is for dry-run / CI.

`--frozen-utc` pins `generated_at_utc` for deterministic tests.

`--stale-threshold-seconds` overrides the staleness threshold for
this collection (see "Stale-artifact detection" below).

## Stale-artifact detection (operator runbook)

This section documents the v3.15.15.27 stale-artifact detection
surface from the operator's point of view. The mechanics are
already covered in
`docs/governance/observability_security_hardening.md` §1; this
section answers the operator-facing questions: *which knobs do I
have, when do I turn them, and what do I look at afterwards*.

### Why a staleness signal exists

Until v3.15.15.27 a source artifact that parsed cleanly was
treated as "ok" forever. If the workloop stopped writing fresh
output the digest kept reporting the same numbers indefinitely
and the operator only noticed when something else broke. The
staleness signal closes that gap without expanding execution
authority — it adds a per-source freshness annotation and one
counter, nothing else.

### Knobs

The threshold is set, in order of precedence:

1. `--stale-threshold-seconds <int>` on the
   `python -m reporting.autonomy_metrics --collect` CLI
   invocation. Wins over the env var. Must be a positive integer.
2. `AUTONOMY_METRICS_STALE_THRESHOLD_SECONDS` environment variable
   at collect time. Read once per `--collect`. Must parse to a
   positive integer; otherwise the default applies.
3. Compiled-in default
   `reporting.autonomy_metrics.STALE_THRESHOLD_SECONDS_DEFAULT =
   24 * 3600` (24 hours).

The threshold is in **seconds**. There is no unit suffix; passing
`--stale-threshold-seconds 24h` is rejected by argparse.

### Choosing a threshold

The default of 24 hours is deliberately conservative. It is the
right answer for a workloop that is *expected* to run at least
once per calendar day. Operators who run the loop on a tighter
cadence should tighten the threshold so a stuck loop surfaces
sooner; operators running a deliberately slow cadence (for
example a research-only operator who only collects evidence on
weekdays) should loosen it so weekend gaps do not flap.

| Operator cadence              | Suggested threshold | Why |
| ----------------------------- | ------------------- | --- |
| Continuous workloop_runtime   | `300` (5 min)       | A 5-minute gap is already meaningful; tighter than this is noisy. |
| Hourly recurring_maintenance  | `3600` (1 h)        | One missed run is the smallest signal worth surfacing. |
| Daily operator review         | `86400` (default)   | Matches the compiled-in default; do not override. |
| Weekend-paused workloop       | `259200` (3 days)   | Avoid flapping on Saturday/Sunday gaps; revisit Monday. |

The threshold is **not** a kill-switch. A row tagged
`is_stale=true` continues to surface its real metric values; the
single side effect is that `reliability.stale_artifact_count` is
bumped and `final_recommendation` may flip to
`degraded_failures`.

### What the operator sees

After a `--collect`, every source row that parsed cleanly carries
two new fields:

* `age_seconds: int | null` — `digest.generated_at_utc -
  source.generated_at_utc`. `null` when the source did not parse,
  was missing, or did not expose a `generated_at_utc`.
* `is_stale: bool` — `true` when `age_seconds` is non-null and
  exceeds the threshold for this `--collect`.

Aggregate signal:

* `reliability.stale_artifact_count` — number of source rows
  where `is_stale` is true. Expected to be `0` on a healthy
  system. A non-zero count feeds `final_recommendation`
  (`degraded_failures` if the loop is otherwise running).

### Operator playbook

When `reliability.stale_artifact_count > 0`:

1. Run `python -m reporting.autonomy_metrics --status` and read
   the per-row `age_seconds` / `is_stale` fields to identify
   *which* sources are stale.
2. Cross-check the freshest `last_success_at_utc` /
   `last_failure_at_utc` on the workloop runtime artifact. If
   `consecutive_failures >= 3` the loop is in a soft halt; treat
   the staleness as a downstream symptom of the soft halt, not as
   a separate incident.
3. If the workloop is healthy but a single source is stale, the
   upstream module that writes that source has stopped — go look
   at it (for example `recurring_maintenance` if the recurring
   row is the stale one).
4. Do not "fix" staleness by widening the threshold. Widen the
   threshold only when the operator-cadence row above explicitly
   recommends a different value for the current operating mode.

### Determinism note

The threshold is read once per `--collect`. Subsequent reads via
`--status` print the digest as-written and do not re-evaluate
staleness. If the operator wants a fresh staleness verdict, they
must run `--collect` again — `--status` is a viewer, not a
re-evaluator. This matches the rest of the digest's freshness
guarantees and keeps the schema deterministic for tests.

## Known limitations

* No clock-aware liveness check on `latest.json` itself; if
  upstream reporters stop running, the digest reports the same
  numbers indefinitely. The freshness signal lives on
  `last_success_at_utc` / `last_failure_at_utc` which come from
  the workloop runtime and not from this module.
* `high_or_unknown_executable_count` is computed from the
  `execute_safe_controls` action list; if that artifact is
  missing the count is 0 (accurate, not safe-by-default — the
  overall state is still flagged via `not_available`).
* History is best-effort: lines that fail to parse are skipped,
  not counted as malformed (the freshness comes from the
  per-line `generated_at_utc` rather than schema validity).

## Cross-references

* Schema: `docs/governance/autonomy_metrics/schema.v1.md`
* Workloop runtime: `docs/governance/workloop_runtime.md`
* Recurring maintenance: `docs/governance/recurring_maintenance.md`
* High-risk approval policy:
  `docs/governance/high_risk_approval_policy.md`
* Approval inbox: `docs/governance/approval_inbox.md`
* Proposal queue: `docs/governance/proposal_queue.md`
* GitHub PR lifecycle: `docs/governance/github_pr_lifecycle.md`
* Mobile Agent Control PWA:
  `docs/governance/agent_control_pwa.md`

## Governance footnote

The autonomy metrics module is read-only. The PWA Status card
surfaces a compact projection but never offers a button. To
materially change the metrics shape, open a human-authored PR
that updates schema.v1.md and adds a metrics_version bump.
