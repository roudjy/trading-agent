# Approval / Exception Inbox — Operator Runbook

> Module: `reporting.approval_inbox`
> + `dashboard.api_approval_inbox` (read-only GET route)
> + `frontend/src/routes/AgentControl.tsx` (Inbox card)
> Release: v3.15.15.20
> Schema: [`approval_inbox/schema.v1.md`](approval_inbox/schema.v1.md)

This is the operator-facing runbook. The approval inbox is the
**single read-only surface** that aggregates every needs_human /
blocked / high-risk / unknown item from the upstream governance
reporters (proposal queue, GitHub PR lifecycle, autonomous
workloop, governance status). It does not approve, reject, or
mutate anything.

## Core design principle

> The system may **prepare** decisions, evidence, and recommended
> next actions.
>
> Only the operator can **approve** strategic / canonical / HIGH /
> protected actions.
>
> **Unknown state is never safe.**

## TL;DR

```sh
# Build the inbox digest (reads upstream artifacts under logs/, runs
# governance_status in-process; writes logs/approval_inbox/latest.json).
python -m reporting.approval_inbox --mode dry-run

# Or just see the digest without persisting.
python -m reporting.approval_inbox --mode dry-run --no-write

# Triage:
jq -r '.final_recommendation' logs/approval_inbox/latest.json
jq '[.items[] | select(.severity == "critical")] | length' \
   logs/approval_inbox/latest.json
```

The CLI defaults to `dry-run`. **It is the only allowed mode in
v3.15.15.20** — any other mode is refused at the boundary so we
never write outside the gitignored digest.

## Hard guarantees (enforced by code AND tests)

| guarantee | enforcement |
|---|---|
| Stdlib-only — no subprocess / no `gh` / no `git` / no network | `test_no_subprocess_or_gh_or_git_in_module` |
| Reads upstream artifacts only; never modifies them | `test_frozen_contracts_byte_identical_around_snapshot` |
| `dry-run` is the only allowed mode | `test_non_dry_run_mode_is_refused` |
| Strategic roadmap proposal → `roadmap_adoption_required` | `test_roadmap_adoption_proposal_becomes_inbox_item` |
| HIGH PR from PR lifecycle → `high_risk_pr` | `test_high_risk_pr_becomes_inbox_item` |
| Diff touching `.claude/` etc. → `protected_path_change` | `test_protected_path_proposal_becomes_protected_path_change`, `test_pr_with_protected_paths_becomes_protected_path_change` |
| Diff touching frozen contracts → `frozen_contract_risk` (severity: critical) | `test_frozen_contract_proposal_becomes_frozen_contract_risk`, `test_workloop_contract_risk_row_becomes_frozen_contract_risk` |
| Diff touching live/trading → `live_paper_shadow_risk_change` (severity: critical) | `test_live_trading_proposal_becomes_live_paper_shadow_risk_change`, `test_workloop_trading_risk_row_becomes_live_paper_shadow_risk_change` |
| Tooling intake with API key / OAuth / signup → `external_account_or_secret_required` | `test_high_tooling_proposal_becomes_correct_external_subcategory` (4 parametrized cases) |
| Tooling intake with telemetry → `telemetry_or_data_egress_required` | same parametrized fixture |
| Tooling intake with paid plan / SaaS → `paid_tool_required` | same parametrized fixture |
| Free / dev-only tooling does **not** create an inbox item | `test_low_tooling_proposal_does_not_create_inbox_item` |
| `blocked_unknown` → `unknown_state` | `test_blocked_unknown_proposal_becomes_unknown_state` |
| Failing checks → `blocked_checks` | `test_failing_checks_pr_becomes_blocked_checks` |
| BEHIND PR → `blocked_rebase` | `test_behind_pr_becomes_blocked_rebase` |
| Conflict → `failed_automation` | `test_pr_conflict_becomes_failed_automation` |
| Broken audit chain → `security_alert` (severity: critical) | `test_broken_audit_chain_becomes_security_alert` |
| Missing source → `unknown_state` item | `test_missing_proposal_queue_becomes_unknown_state_item`, `test_all_sources_missing_yields_only_unknown_state_items` |
| Three known pending route wirings emit `manual_route_wiring_required` items | `test_manual_route_wiring_items_default_on` |
| `item_id` is deterministic | `test_item_id_is_deterministic` |
| Every item carries the universal `forbidden_agent_actions` list | `test_every_item_carries_required_fields` |

## Categories at a glance

The eighteen categories split naturally into five groups:

| group | categories |
|---|---|
| **Strategic / governance** | `roadmap_adoption_required`, `governance_change`, `protected_path_change` |
| **PR lifecycle** | `high_risk_pr`, `blocked_checks`, `blocked_rebase`, `failed_automation` |
| **External dependencies** | `tooling_requires_approval`, `external_account_or_secret_required`, `telemetry_or_data_egress_required`, `paid_tool_required` |
| **Risk / safety** | `frozen_contract_risk` (critical), `live_paper_shadow_risk_change` (critical), `ci_or_test_weakening_risk`, `security_alert` (critical), `runtime_halt` (critical) |
| **Operational** | `unknown_state`, `manual_route_wiring_required` |

Severities default per category (see schema). The operator sees:

* **Critical** rows demand immediate attention before any further action.
* **High** rows block normal release flow until reviewed.
* **Medium** rows are review-when-convenient.
* **Low** rows (e.g. `manual_route_wiring_required`) are housekeeping.
* **Info** is reserved for future use.

## Reading the JSON artifact

```sh
# Triage by severity:
jq -r '.counts.by_severity' logs/approval_inbox/latest.json

# All critical items:
jq '.items[] | select(.severity == "critical") | {item_id, category, title}' \
   logs/approval_inbox/latest.json

# All items related to a specific PR:
jq '.items[] | select(.related_pr_number == 60)' \
   logs/approval_inbox/latest.json
```

## What this is NOT

The release intentionally does NOT ship:

* approve / reject / acknowledge / resolve buttons (release v3.15.15.21);
* any mutation endpoint (`POST` / `PUT` / `PATCH` / `DELETE`);
* any execute-safe controls in the UI (release v3.15.15.21);
* any browser push notification (release v3.15.15.23);
* any subprocess, `gh`, `git`, or network call inside the builder;
* any non-dry-run mode (refused at the CLI boundary);
* any direct route wiring into `dashboard/dashboard.py` (no-touch —
  see "Manual route wiring" below).

The PWA renders the inbox **read-only**. There is exactly one button
on the AgentControl page: the Vernieuw refresh button.

## Source artifacts

| source | path | how it's read |
|---|---|---|
| `proposal_queue` | `logs/proposal_queue/latest.json` | filesystem read; missing → `not_available` envelope |
| `pr_lifecycle` | `logs/github_pr_lifecycle/latest.json` | filesystem read |
| `workloop` | `logs/autonomous_workloop/latest.json` | filesystem read |
| `governance_status` | (in-process) | `reporting.governance_status.collect_status()` |

A source whose envelope is `not_available` becomes a single
`unknown_state` inbox item with `status=blocked` and the failure
reason in `evidence.source_envelope`. The operator always sees the
gap explicitly — there is no silent "everything's fine".

## Manual route wiring

`dashboard/dashboard.py` is on the no-touch list (it reads operator
session and token secrets). Three pending route modules each need
one operator-led line in `dashboard.py`:

```python
# v3.15.15.18: Agent Control PWA routes.
from dashboard.api_agent_control import register_agent_control_routes
register_agent_control_routes(app)

# v3.15.15.19: Proposal queue route.
from dashboard.api_proposal_queue import register_proposal_queue_routes
register_proposal_queue_routes(app)

# v3.15.15.20: Approval inbox route.
from dashboard.api_approval_inbox import register_approval_inbox_routes
register_approval_inbox_routes(app)
```

The approval inbox **emits one `manual_route_wiring_required` item
per pending wiring** so the operator sees them in the same surface.
Each item is severity `low` (no urgency) and pinned to the release
that introduced it.

## Forward roadmap (not shipped here)

| release | adds |
|---|---|
| **v3.15.15.20 (this)** | inbox builder, schema, GET route, read-only PWA card |
| v3.15.15.21 | execute-safe controls (operator approves / rejects / supersedes); `status` emits `acknowledged` / `resolved` / `superseded` |
| v3.15.15.23 | browser push for `needs_human` / critical inbox items |
| v3.15.15.25 | metrics / observability dashboards |

Each subsequent release strictly adds capability; nothing in this
release walks back a guarantee.

## Files added by v3.15.15.20

```
reporting/approval_inbox.py
dashboard/api_approval_inbox.py
docs/governance/approval_inbox/schema.v1.md
docs/governance/approval_exception_inbox.md   (this file)
frontend/src/api/agent_control.ts             (extended)
frontend/src/routes/AgentControl.tsx          (Inbox card)
frontend/src/test/AgentControl.test.tsx       (3 inbox tests)
tests/unit/test_approval_inbox.py             (28 cases)
tests/unit/test_dashboard_api_approval_inbox.py (10 cases)
```

No edits to `dashboard/dashboard.py` (no-touch). No edits to
`.claude/**`. No frozen-contract changes. No live / paper / shadow /
trading / risk behavior changes.

## Constraints respected

- No approve / reject / execute / merge button anywhere.
- No mutation endpoints.
- No POST / PUT / PATCH / DELETE.
- No browser push.
- No long-running runtime.
- No recurring automation.
- No direct `gh` mutations from the inbox.
- No direct `git` operations from the inbox.
- No canonical roadmap adoption.
- No direct route wiring into `dashboard/dashboard.py`.
- No `.claude/**` changes.
- No frozen-contract changes.
- No live / paper / shadow / trading / risk behavior changes.
- No CI / test weakening.
- Unknown / missing / malformed sources render as `not_available` or
  `unknown_state`, never OK.
