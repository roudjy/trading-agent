# Autonomy metrics — schema v1

Module: `reporting.autonomy_metrics` (v3.15.15.25)
Schema version: `1`
Metrics version: `v1`
Stability: stable; additions are SemVer minor, removals are
breaking.

This is the machine-readable description of the autonomy
throughput / observability metrics digest. The collector reads
the existing JSON artifacts from sibling reporting modules and
projects them into a single deterministic snapshot.

## Top-level shape

```json
{
  "schema_version": 1,
  "report_kind": "autonomy_metrics_digest",
  "module_version": "v3.15.15.25",
  "metrics_version": "v1",
  "generated_at_utc": "2026-05-03T08:00:00Z",
  "source_statuses": [...],
  "throughput": {...},
  "operator_burden": {...},
  "reliability": {...},
  "safety": {...},
  "trends": {...},
  "policy": {
    "module_version": "v3.15.15.24",
    "schema_version": 1,
    "high_or_unknown_is_executable": false
  },
  "final_recommendation": "healthy",
  "safe_to_execute": false
}
```

## source_statuses

A deterministic ordered list of source-state records:

```json
{
  "source": "workloop_runtime",
  "artifact_path": "logs/workloop_runtime/latest.json",
  "state": "ok | missing | malformed | unreadable | not_an_object",
  "reason": "missing | malformed: <ErrorClass> | ..."
}
```

Source order:

1. `workloop_runtime`
2. `recurring_maintenance`
3. `proposal_queue`
4. `approval_inbox`
5. `github_pr_lifecycle`
6. `execute_safe_controls`

## throughput

```
proposals_total: int
proposals_by_status: { proposed|needs_human|blocked|approved|...: int }
proposals_by_risk: { LOW|MEDIUM|HIGH|UNKNOWN: int }
proposals_by_type: { tooling_intake|...: int }
inbox_items_total: int
inbox_items_by_category: { high_risk_pr|...: int }
inbox_items_by_severity: { info|low|medium|high|critical: int }
pr_lifecycle_prs_seen: int
pr_lifecycle_merge_allowed: int
pr_lifecycle_blocked: int
pr_lifecycle_needs_human: int
pr_lifecycle_wait_for_rebase: int
pr_lifecycle_wait_for_checks: int
recurring_jobs_total: int
recurring_jobs_succeeded: int
recurring_jobs_blocked: int
recurring_jobs_failed: int
recurring_jobs_skipped: int
recurring_jobs_timeout: int
recurring_jobs_not_run: int
runtime_sources_total: int
runtime_sources_ok: int
runtime_sources_degraded: int
runtime_sources_failed: int
execute_safe_actions_total: int
execute_safe_by_eligibility: { eligible|ineligible|blocked|unknown: int }
execute_safe_by_risk_class: { LOW|MEDIUM|HIGH|UNKNOWN: int }
```

## operator_burden

```
needs_human_total: int
blocked_total: int
approval_required_total: int
manual_route_wiring_required_total: int
high_risk_blocked_total: int
unknown_state_total: int
estimated_operator_actions_total: int
top_operator_action_categories: [{ category: str, count: int }]
by_severity: { info|low|medium|high|critical: int }
```

## reliability

```
runtime_consecutive_failures: int
recurring_consecutive_failures_max: int
source_failure_rate: float (0.0..1.0)
job_failure_rate: float (0.0..1.0)
stale_artifact_count: int
malformed_artifact_count: int
missing_artifact_count: int
last_success_at_utc: str | null
last_failure_at_utc: str | null
```

### Stale-artifact detection (v3.15.15.27)

Each `source_statuses` row whose `state == "ok"` carries:

* `age_seconds: int | null` — the difference between the digest's
  `generated_at_utc` and the source artifact's
  `generated_at_utc`. `null` when the source artifact has no
  `generated_at_utc` field.
* `is_stale: bool` — true when `age_seconds` exceeds the
  staleness threshold.

Staleness threshold:

* default `STALE_THRESHOLD_SECONDS_DEFAULT = 86400` (24 hours);
* env var override:
  `AUTONOMY_METRICS_STALE_THRESHOLD_SECONDS=<positive int>`;
* CLI override:
  `--stale-threshold-seconds <positive int>`.

A stale row bumps `reliability.stale_artifact_count` by 1.

## safety

```
high_or_unknown_executable_count: int     # invariant: 0
frozen_contract_risk_count: int
protected_path_risk_count: int
live_paper_shadow_risk_count: int
ci_or_test_weakening_risk_count: int
secret_or_external_account_required_count: int
telemetry_or_data_egress_count: int
paid_tool_required_count: int
high_risk_proposal_count: int
unknown_risk_proposal_count: int
execute_safe_eligible_count: int
execute_safe_blocked_count: int
execute_safe_high_count: int
policy_version: str   # e.g. "v3.15.15.24"
summary: "ok" | "unsafe_state_detected"
```

`high_or_unknown_executable_count` MUST always be 0. A non-zero
value flips `final_recommendation` to `unsafe_state_detected`.

## trends

```
current: { runtime: <agg>, recurring: <agg> }
last_24h: { runtime: <agg>, recurring: <agg> }
last_7d: { runtime: <agg>, recurring: <agg> }
all_time_from_available_history: { runtime: <agg>, recurring: <agg> }
```

Each `<agg>` is one of:

```
{ "status": "not_available", "reason": "no_history" }
```

or

```
{
  "status": "ok",
  "total_runs": int,
  "succeeded_runs": int,
  "failed_runs": int,
  "degraded_runs": int,
  "consecutive_failures_max": int
}
```

## final_recommendation enum

```
healthy
degraded_missing_sources
degraded_failures
action_required
unsafe_state_detected
not_available
```

Order of evaluation (first match wins):

1. `safety.high_or_unknown_executable_count > 0` → `unsafe_state_detected`
2. all sources missing/not_an_object → `not_available`
3. `reliability.missing_artifact_count >= 2` → `degraded_missing_sources`
4. `reliability.malformed_artifact_count > 0` → `degraded_failures`
5. `reliability.runtime_consecutive_failures >= 3` → `degraded_failures`
6. `operator_burden.estimated_operator_actions_total > 0` → `action_required`
7. else → `healthy`

## Determinism

* All counter dicts emit keys in alphabetical order.
* `top_operator_action_categories` is sorted by count desc, then
  alphabetical, capped at 5.
* `generated_at_utc` is the only clock-derived field. It can be
  pinned via `--frozen-utc` for deterministic tests.

## Atomic writes

Snapshot is written via tmp + os.replace. History is append-only.
Latest is byte-identical to the timestamped copy of the same run.
