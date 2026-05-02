# Execute-Safe Controls Catalog — Schema v1

> Module: `reporting.execute_safe_controls`
> Module version: `v3.15.15.21`
> Schema version: `1`
> Artifact path (gitignored): `logs/execute_safe_controls/latest.json`
> Timestamped copies: `logs/execute_safe_controls/<UTC>.json`

## Top-level fields

| field | type | values | notes |
|---|---|---|---|
| `schema_version` | int | `1` | bump on breaking changes |
| `report_kind` | string | `"execute_safe_controls_catalog"` | constant |
| `module_version` | string | `"v3.15.15.21"` | source-of-truth |
| `generated_at_utc` | string | RFC3339 UTC | seconds resolution |
| `git_clean` | bool | true / false | true iff no tracked changes and no unknown-untracked changes |
| `git_dirty_count` | int | 0..n | number of dirty `git status --porcelain` lines (informational) |
| `gh_provider` | object | provider envelope | mirrors `github_pr_lifecycle.gh_provider_status()` |
| `frozen_hashes` | object | path → sha256 | snapshot at catalog-emit time |
| `actions` | array | see "Action" | one entry per whitelisted action type |
| `counts` | object | totals + by-eligibility / by-risk-class | aggregate view |
| `executed` (optional) | object | see "Action" | populated only when `--action` was specified on the CLI |

## Action

One entry per **whitelisted** action type. The catalog has exactly
four actions in v3.15.15.21; unknown types are refused at the
boundary.

| field | type | values | notes |
|---|---|---|---|
| `action_id` | string | `"a_<sha8>"` | deterministic over `action_type` + `created_at` |
| `action_type` | enum | see "Action types" | closed list |
| `title` | string | human-readable | constant per action_type |
| `summary` | string | human-readable | constant per action_type |
| `risk_class` | enum | `"LOW"` / `"MEDIUM"` / `"HIGH"` | HIGH never eligible in v3.15.15.21 |
| `eligibility` | enum | `"eligible"` / `"ineligible"` / `"blocked"` / `"unknown"` | computed from environmental signals |
| `blocked_reason` | string \| null | non-null when not `eligible` | |
| `required_confirmations` | array | strings | what the operator must do before running |
| `forbidden_side_effects` | array | strings | universal hard-no list, surfaced on every action |
| `allowed_side_effects` | array | strings | per-action positive list |
| `source_refs` | array | strings | governance docs the operator should read |
| `created_at` | string | RFC3339 UTC | snapshot time |
| `stale_after` | string \| null | reserved | always null in this release |
| `audit_event_id` | string \| null | reserved | always null in this release |
| `result_status` | enum | `"not_run"` / `"running"` / `"succeeded"` / `"failed"` / `"blocked"` | `not_run` for catalog emits; populated after `execute_action` |
| `result_summary` | string \| null | populated after execution | |
| `output_artifact_path` | string \| null | typically the log file the action writes | |

## Action types (closed list)

| value | risk | needs gh? | argv |
|---|---|---|---|
| `refresh_github_pr_lifecycle_dry_run` | LOW | yes | `python -m reporting.github_pr_lifecycle --mode dry-run` |
| `refresh_proposal_queue_dry_run` | LOW | no | `python -m reporting.proposal_queue --mode dry-run` |
| `refresh_approval_inbox_dry_run` | LOW | no | `python -m reporting.approval_inbox --mode dry-run` |
| `run_dependabot_execute_safe_low_medium` | MEDIUM | yes | `python -m reporting.github_pr_lifecycle --mode execute-safe` |

The argv list is constructed entirely from constants in the module —
no operator-supplied tokens. Adding a new action requires editing
the module **and** the schema **and** the runbook.

## Eligibility

The planner is a **pure function**. Inputs:

* `git_clean: bool` — derived from `git status --porcelain`,
  ignoring untracked paths in `KNOWN_RUNTIME_UNTRACKED`
  (`research/discovery_sprints/`, `frontend/src/`).
* `git_dirty_lines: list[str]` — for diagnostic surfacing.
* `gh_status: dict` — from `github_pr_lifecycle.gh_provider_status()`.

Decision precedence — first-match wins:

1. Action type not in catalog → `ineligible`, reason `unknown_action_type`.
2. Action `risk_class == "HIGH"` → `blocked`, reason `HIGH-risk actions are never executable in v3.15.15.21`.
3. Working tree dirty → `blocked`, reason cites the line count.
4. Action needs gh and gh status is `not_available` → `blocked`.
5. Action needs gh and gh status is `not_authenticated` → `blocked`.
6. Action needs gh and gh status is `unknown` / `""` → `unknown`.
7. Action needs gh and gh status is anything other than `available` → `blocked`.
8. Otherwise → `eligible`.

## Executor (small, fixed-command-only)

`execute_action(action_type, *, confirm_token=None, ...)`:

* Re-runs the planner with the live environment. If the verdict is
  not `eligible`, returns `result_status="blocked"` with the
  planner's `blocked_reason`.
* For `run_dependabot_execute_safe_low_medium`, requires
  `confirm_token == "dependabot-execute-safe"` (defense in depth on
  top of the lifecycle module's own gates).
* Captures `frozen_hashes` BEFORE and AFTER. A mismatch is a
  CRITICAL failure (`result_status="failed"`,
  `result_summary="FROZEN-CONTRACT DRIFT: ..."`).
* Builds argv from the closed map; runs with a per-action timeout
  (60s for refreshes, 600s for the Dependabot path).
* Never invokes `git push`, `--force`, `--admin`, or any
  destructive shell command.

## Counts object

```json
{
  "total": 4,
  "by_eligibility":  {"eligible": 3, "blocked": 1},
  "by_risk_class":   {"LOW": 3, "MEDIUM": 1}
}
```

## Hard guarantees encoded in the schema

* The catalog is closed — exactly four action types, named here and
  in `_ACTION_ARGV` in the module.
* HIGH-risk actions are NEVER eligible in this release.
* Free-form command strings are NEVER accepted.
* Frozen-contract drift during execution is a critical failure that
  fails the action — the executor never silently accepts.
* `unknown` is never elevated to `eligible` — gh provider state
  must be the literal string `"available"`.
* The PWA never receives any field that hasn't been verified
  against `assert_no_secrets`.

## Wiring with the dashboard

`dashboard/api_execute_safe_controls.py` exposes a single GET-only
route `/api/agent-control/execute-safe`. It calls
`collect_catalog()` in-process (no subprocess) and surfaces the
catalog. Activation requires one operator-led line in
`dashboard/dashboard.py` (no-touch); until that lands, the PWA
renders `not_available`.

## What this is NOT

* This release does NOT add a POST endpoint. Execution remains
  CLI-only because the dashboard surface lacks per-operator auth /
  CSRF / typed confirmation flow.
* This release does NOT execute HIGH-risk actions.
* This release does NOT accept free-form command strings.
* This release does NOT bypass the upstream lifecycle module's own
  gates — it strictly delegates to existing modules with their
  existing safety semantics.
