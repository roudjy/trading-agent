# Execute-Safe Controls — Operator Runbook

> Module: `reporting.execute_safe_controls`
> + `dashboard.api_execute_safe_controls` (read-only GET route)
> + `frontend/src/routes/AgentControl.tsx` (Execute-safe card)
> Release: v3.15.15.21
> Schema: [`execute_safe_controls/schema.v1.md`](execute_safe_controls/schema.v1.md)

This is the operator-facing runbook for the v3.15.15.21 execute-safe
controls layer. Execute-safe is the **first release** that lets an
agent (or operator) run a small, typed set of actions that may
mutate GitHub state — but only along the narrow channels proven in
prior pilots and only behind a closed list.

## Core design principle

> A UI / control action is only allowed if it maps to a typed,
> whitelisted, auditable action with deterministic eligibility checks.
>
> **Unknown state is never safe.**
>
> **HIGH risk remains human approval only and is not executable in
> this release.**

## TL;DR

```sh
# Emit the catalog (read-only).
python -m reporting.execute_safe_controls --mode dry-run

# Run a refresh action (no GitHub mutation; just regenerates a
# JSON digest). Repeat for the other refresh actions.
python -m reporting.execute_safe_controls \
  --action refresh_proposal_queue_dry_run

# Run the Dependabot execute-safe path. Requires the literal
# --confirm token because this action CAN merge LOW/MEDIUM PRs.
python -m reporting.execute_safe_controls \
  --action run_dependabot_execute_safe_low_medium \
  --confirm dependabot-execute-safe
```

## Allowed action classes (closed list)

The catalog is exactly four entries. The module rejects unknown
action types at the boundary. Adding a new action requires a new
release plus an ADR.

| action_type | risk | needs gh? | what it does |
|---|---|---|---|
| `refresh_github_pr_lifecycle_dry_run` | LOW | yes | runs `python -m reporting.github_pr_lifecycle --mode dry-run` |
| `refresh_proposal_queue_dry_run` | LOW | no | runs `python -m reporting.proposal_queue --mode dry-run` |
| `refresh_approval_inbox_dry_run` | LOW | no | runs `python -m reporting.approval_inbox --mode dry-run` |
| `run_dependabot_execute_safe_low_medium` | MEDIUM | yes | runs `python -m reporting.github_pr_lifecycle --mode execute-safe` |

The argv list per action is constructed entirely from constants in
the module. **No operator-supplied tokens, no shell, no
`shell=True`, no `os.system`, no `Popen`.** Every subprocess
invocation has a bounded timeout (60s for refresh actions, 600s
for the Dependabot path).

## Hard guarantees (enforced by code AND tests)

| guarantee | enforcement |
|---|---|
| Stdlib-only — no shell, no free-form command input | `test_argv_recipes_are_constant_and_dont_use_shell`, `test_module_does_not_construct_argv_from_user_input` |
| Catalog is closed; unknown action types are refused | `test_unknown_action_type_is_refused_at_planner`, `test_unknown_action_type_is_refused_at_executor` |
| HIGH-risk actions are NEVER eligible | `test_no_high_risk_action_in_catalog_is_eligible` |
| Dirty working tree blocks execution | `test_dirty_working_tree_blocks_planning`, `test_executor_blocks_when_planner_says_blocked` |
| Known runtime artifacts (`research/discovery_sprints/`, `frontend/src/`) do not falsely block | `test_known_runtime_untracked_does_not_falsely_block` |
| Unknown untracked path DOES block | `test_unknown_untracked_path_blocks` |
| `gh` unavailable → blocked for gh-dependent actions | `test_gh_unavailable_blocks_gh_dependent_action` |
| `gh` unauthenticated → blocked | `test_gh_unauthenticated_blocks_gh_dependent_action` |
| `gh` status `unknown` → eligibility `unknown`, never elevated | `test_gh_unknown_yields_unknown_eligibility` |
| Frozen-contract sha256 captured before AND after every executable action | `test_executor_detects_frozen_contract_drift` |
| `run_dependabot_execute_safe_low_medium` requires literal `--confirm` token | `test_executor_dependabot_requires_confirm_token` |
| Subprocess exit non-zero → action result `failed` | `test_executor_marks_subprocess_failure` |
| No argv recipe invokes `git push`, `--force`, `--admin`, `rm -rf`, `shutdown` | `test_no_action_argv_invokes_destructive_git_or_gh`, `test_no_argv_recipe_invokes_git_or_gh_or_destructive_flag` |
| GET-only API on the dashboard surface (POST/PUT/PATCH/DELETE → 405) | `test_mutation_verbs_are_rejected` |
| PWA card has no execute / approve / merge button | uses interaction-shaped test from v3.15.15.18 |

## Eligibility decision precedence

The planner is **pure** — same input always produces the same
verdict. Decision order — first-match wins:

1. Action type not in the catalog → `ineligible`, reason `unknown_action_type`.
2. `risk_class == "HIGH"` → `blocked`, reason `HIGH-risk actions are never executable in v3.15.15.21`.
3. Working tree dirty (excluding known runtime untracked paths) → `blocked`.
4. Action needs `gh` and `gh status` is `not_available` / `not_authenticated` / unrecognized → `blocked`.
5. Action needs `gh` and `gh status` is `unknown` / empty → `unknown` (never elevated to `eligible`).
6. Otherwise → `eligible`.

## Confirmation tokens

| action | required token |
|---|---|
| `refresh_*_dry_run` | none |
| `run_dependabot_execute_safe_low_medium` | exact string `dependabot-execute-safe` |

The token is checked AFTER eligibility, so a missing token on a
blocked action still surfaces the underlying block reason. The
token is intentionally not derived from the operator's identity —
it's a *defense in depth* signal that the operator typed the
literal string, not that they authenticated. Stronger
authentication is gated on the auth surface that lands in
v3.15.15.22+.

## Frozen-contract drift detection

Every executable action snapshots `sha256` of every entry in
`FROZEN_CONTRACTS` BEFORE the subprocess runs and AGAIN after it
exits. A mismatch is a **CRITICAL failure**:

```json
{
  "result_status": "failed",
  "result_summary": "FROZEN-CONTRACT DRIFT: sha256 changed during action execution; investigate before any further action",
  "evidence": {
    "frozen_before": {...},
    "frozen_after":  {...},
    "rc": 0
  }
}
```

A non-zero subprocess `rc` together with a frozen-hash drift is
treated as the more severe of the two — drift always wins.

## PWA integration

`dashboard/api_execute_safe_controls.py` exposes one GET-only route:

```
GET /api/agent-control/execute-safe
```

Returns the live catalog as a JSON envelope. **No POST endpoint is
shipped in v3.15.15.21** — actual execution remains CLI-only because
the dashboard surface lacks per-operator auth / CSRF / typed
confirmation flow. The auth surface lands in v3.15.15.22+ and a
gated POST endpoint may follow.

The PWA's Execute-safe card renders:

* the git-clean and gh-provider status pills,
* one row per action with eligibility pill and risk class label,
* a "execution remains CLI-only — no buttons in v3.15.15.21" note.

There is exactly **one button** on the entire AgentControl page:
the Vernieuw (refresh) button. The Execute-safe card adds zero
buttons.

## Wiring step (approved by the operator)

`dashboard/dashboard.py` is on the no-touch list. The v3.15.15.21
release brief explicitly approved wiring **three** read-only route
modules (the v3.15.15.18 / .19 / .20 surfaces). The operator
landed exactly that block in the governance-bootstrap commit on
this release:

```python
# v3.15.15.21 — read-only Agent Control PWA surface (operator approved).
from dashboard.api_agent_control import register_agent_control_routes
from dashboard.api_proposal_queue import register_proposal_queue_routes
from dashboard.api_approval_inbox import register_approval_inbox_routes

register_agent_control_routes(app)
register_proposal_queue_routes(app)
register_approval_inbox_routes(app)
```

The fourth route module (`dashboard.api_execute_safe_controls`)
ships in this release but is **intentionally not wired in
production** — its PWA card renders `not_available` until a
v3.15.15.22+ release wires it after the auth surface lands. This
is the correct posture: the execute-safe catalog endpoint is a
read-only diagnostic, but the gated POST endpoint that actually
runs an action is the v3.15.15.22 milestone, and the two should
land together.

The approval inbox auto-clears `manual_route_wiring_required`
items as soon as `dashboard.py` contains both the import and the
register call for a known module — verified by
`tests/unit/test_approval_inbox.py::test_manual_route_wiring_items_clear_when_dashboard_wires_them`.
The inbox's wiring detection is automatic — the items disappear as
soon as `dashboard.py` contains both the `from … import` and the
`register_…(app)` call.

## What this is NOT

* This release does NOT add a POST endpoint on the dashboard.
* This release does NOT execute HIGH-risk actions.
* This release does NOT accept free-form command strings.
* This release does NOT bypass the upstream lifecycle module's own
  gates — it strictly delegates.
* This release does NOT add browser push notifications.
* This release does NOT add long-running runtime.
* This release does NOT add recurring automation.

## Forward roadmap (not shipped here)

| release | adds |
|---|---|
| **v3.15.15.21 (this)** | typed action catalog, planner, executor, GET-only catalog endpoint, read-only PWA card |
| v3.15.15.22 | per-operator auth + CSRF surface; gated POST endpoint for the four whitelisted actions |
| v3.15.15.23 | browser push for `needs_human` / critical inbox items; first WRITE-button on the PWA only after auth lands |
| v3.15.15.25 | metrics / observability dashboards |

## Files added by v3.15.15.21

```
reporting/execute_safe_controls.py
dashboard/api_execute_safe_controls.py
docs/governance/execute_safe_controls/schema.v1.md
docs/governance/execute_safe_controls.md          (this file)
frontend/src/api/agent_control.ts                 (extended)
frontend/src/routes/AgentControl.tsx              (Execute-safe card)
frontend/src/test/AgentControl.test.tsx           (2 execute-safe tests)
tests/unit/test_execute_safe_controls.py          (24 cases)
tests/unit/test_dashboard_api_execute_safe_controls.py (8 cases)
```

Plus `dashboard/dashboard.py` is updated by the operator with the
9-line wiring block (3 imports + 1 import for execute-safe + 4
register calls). That edit is the **first authorized
no-touch-path edit** in the release stream and is the only path
for activating the PWA's read-only surfaces in production.
