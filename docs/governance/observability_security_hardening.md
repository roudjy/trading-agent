# Observability / logging / security hardening sweep — v3.15.15.27

> Release: v3.15.15.27 (sweep release on top of v3.15.15.26)
> Sibling docs: `high_risk_approval_policy.md`,
> `autonomy_metrics.md`, `recurring_maintenance.md`,
> `workloop_runtime.md`, `mobile_agent_control_pwa.md`,
> `approval_inbox.md`.

## TL;DR

This release does **not** expand execution authority. It tightens
the observability and security invariants of the existing
read-only governance/autonomy stack. The hardening is enforced
by code AND by tests; future regressions trip a unit-test-level
guard rather than waiting for a runtime incident.

## Hardening areas

### 1. Stale-artifact detection (autonomy_metrics)

Before this release, `reliability.stale_artifact_count` was wired
but never bumped because "stale" was treated as a synonym for
`STATE_UNREADABLE`. After v3.15.15.27 the metrics digest annotates
every ok-parsing source row with:

* `age_seconds: int | null` — difference between the digest's
  `generated_at_utc` and the source artifact's
  `generated_at_utc`.
* `is_stale: bool` — true when `age_seconds` exceeds the
  staleness threshold.

Threshold: `STALE_THRESHOLD_SECONDS_DEFAULT = 86400` (24 hours).
Override via the `AUTONOMY_METRICS_STALE_THRESHOLD_SECONDS` env
var or the new `--stale-threshold-seconds` CLI flag. A stale row
bumps `reliability.stale_artifact_count` and surfaces in the
existing `degraded_failures` recommendation evaluator.

This makes "the workloop ran an hour ago" visibly different from
"the workloop hasn't run today" without changing the digest's
top-level shape.

> **Operator runbook:** see
> [`autonomy_metrics.md` §"Stale-artifact detection (operator
> runbook)"](autonomy_metrics.md#stale-artifact-detection-operator-runbook)
> for the threshold-precedence rules, the per-cadence
> threshold-selection table, and the playbook for triaging
> `reliability.stale_artifact_count > 0`.

### 2. Boundary exception-handler invariant

Every dashboard route module that surfaces JSON to the operator
PWA already redacts caught exceptions to `type(e).__name__` —
the v3.15.15.27 sweep adds a **source-text guard** so a future
regression cannot reintroduce `str(e)`, `repr(e)`,
`f"{e}"`, `e.args`, or `traceback.format_exc()` into any of:

* `dashboard/api_agent_control.py`
* `dashboard/api_approval_inbox.py`
* `dashboard/api_proposal_queue.py`
* `dashboard/api_execute_safe_controls.py`

The guard lives in
`tests/unit/test_observability_security_invariants.py` and is
parametrised over the four files. It scans the raw module source
because runtime patching cannot defeat a regex over the file
bytes.

### 3. GET-only verb sweep

Same set of files: every `methods=[...]` list is parsed; if any
contains `POST`, `PUT`, `PATCH`, or `DELETE` the test fails. This
prevents an accidental verb expansion from sneaking into a route
file even if `dashboard.dashboard` continues to wire it under
`register_*_routes`.

### 4. `api_execute_safe_controls` remains UNWIRED

`dashboard/dashboard.py` is asserted to NOT contain
`register_execute_safe_routes`. The execute-safe API stays
intentionally unwired until the operator approves a separate
release — the test prevents a future bootstrap commit from
quietly wiring it.

### 5. v3.15.15.25.1 path-reference allowlist preserved

The narrow credential-VALUE redaction in:

* `reporting.agent_audit_summary.assert_no_secrets`
* `reporting.governance_status.assert_no_secrets`
* `reporting.approval_policy.assert_no_credential_values`

is verified at unit-test level. Adding a new
`_SENSITIVE_FRAGMENTS` substring rule that re-rejects path
references would re-introduce the v3.15.15.25 false positive
that halted the approval inbox runtime — the tests fail loudly
in that case.

### 6. End-to-end credential-leak scan

`/api/agent-control/status` is exercised with monkeypatched empty
artifacts; the response body is scanned for the canonical
credential fragments (`sk-ant-`, `ghp_`, `github_pat_`, `AKIA`,
`BEGIN PRIVATE KEY`). If any of those appear, the test fails.

### 7. Frontend mutation-fetch sweep

`frontend/src/api/agent_control.ts` is checked to never contain
`"POST"`/`"PUT"`/`"PATCH"`/`"DELETE"` literals. The PWA already
uses `fetch(GET)` only; this guard prevents a future PR from
introducing a mutation verb against the agent-control surface.

### 8. Subprocess / network sweep

The four agent-control route files are checked to never contain
`import subprocess`, `Popen(`, or any `urllib.request` /
`requests` import. The dashboard surface stays in-process by
construction.

## Hardening report — gaps found vs fixed

| Area | Pre-sweep state | Post-sweep state |
| --- | --- | --- |
| Stale-artifact detection | Wired field, never bumped | Per-row age + threshold + counter |
| `str(e)` in agent-control boundaries | Already redacted | Source-text guard added |
| GET-only verb invariant | Manual code review only | Source-text test sweep |
| `api_execute_safe_controls` wiring | Manual review | Source-text guard added |
| Path-reference allowlist | Code-level fix in v3.15.15.25.1 | Test-level guards across 3 modules |
| Status-payload credential scan | Existing per-source `assert_no_secrets` | End-to-end Flask test added |
| Frontend mutation fetch | Manual review | Source-text guard added |
| Subprocess/network in dashboard | Already absent | Source-text guard added |

## Remaining intentional limitations

The following are **intentional non-goals** for v3.15.15.27 and
must not be relaxed without an explicit operator brief:

* Browser push notifications — out of scope.
* Approval / reject mutation UI — out of scope.
* `api_execute_safe_controls` production wiring — out of scope.
* HIGH-risk execution — out of scope.
* External telemetry / paid services / signup flows — out of scope.
* Live / paper / shadow / risk behavior changes — out of scope.

## Security invariants now covered by tests

Every invariant below is verified by at least one parametrised
unit test:

* GET-only on agent-control routes.
* No mutation verbs in agent-control route files.
* No `str(e)` / `repr(e)` / `f"{e}"` / `e.args` /
  `traceback.format_exc()` in agent-control boundary handlers.
* No credential-shaped values in `/api/agent-control/status`.
* No `api_execute_safe_controls` wiring in `dashboard.dashboard`.
* Path references like `config/config.yaml` flow through the
  three secret guards (no false positives).
* Credential-shaped values still trip the three secret guards.
* Frontend agent-control API uses no mutation verb literal.
* No `subprocess` / `urllib.request` / `requests` imports in
  agent-control route files.
* `recurring_maintenance` and `execute_safe_controls` artifacts
  are classified as `not_available` rather than `failed` when
  missing.

## Observability signals now available

* `autonomy_metrics.reliability.stale_artifact_count` (real,
  bumped by per-row staleness).
* `autonomy_metrics.source_statuses[].age_seconds` /
  `.is_stale` (per-source freshness annotation).
* `autonomy_metrics.reliability.last_success_at_utc` /
  `last_failure_at_utc` (already present; verified preserved).
* `workloop_runtime.loop_health.consecutive_failures` (already
  present; verified preserved).
* `recurring_maintenance.jobs[].consecutive_failures` (already
  present; verified preserved).
* Approval inbox `runtime_halt` / `failed_automation` /
  `unknown_state` projections from upstream digests (already
  present; verified preserved).

## How to validate locally

```
python scripts/governance_lint.py
pytest tests/smoke -q
pytest tests/unit -q
sha256sum research/research_latest.json research/strategy_matrix.csv
python -m reporting.autonomy_metrics --collect --no-write \
  --frozen-utc 2026-05-03T08:00:00Z \
  --stale-threshold-seconds 300
```

A clean run reports all green gates, frozen hashes unchanged
(`4a567bd6...` / `ff15b8c4...`), and the metrics digest carries
non-null `age_seconds` / `is_stale` annotations on every
ok-state source row.

## Cross-references

* Schema:
  `docs/governance/autonomy_metrics/schema.v1.md`
* Approval policy:
  `docs/governance/high_risk_approval_policy.md`
* Approval inbox:
  `docs/governance/approval_exception_inbox.md`
* PWA UX rebuild:
  `docs/governance/mobile_agent_control_pwa.md`
* No-touch paths:
  `docs/governance/no_touch_paths.md`
