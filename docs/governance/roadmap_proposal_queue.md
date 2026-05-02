# Roadmap / Proposal Queue — Operator Runbook

> Module: `reporting.proposal_queue` (parser/classifier/planner)
> + `dashboard.api_proposal_queue` (read-only GET route)
> + `frontend/src/routes/AgentControl.tsx` (Proposals card)
> Release: v3.15.15.19
> Schema: [`proposal_queue/schema.v1.md`](proposal_queue/schema.v1.md)
> Tooling policy: [`tooling_intake_policy.md`](tooling_intake_policy.md)

This is the operator-facing runbook. It explains how the proposal
queue turns large roadmap / spillover / agent-finding documents into
**reviewable, scoped proposals** — never into direct execution.

## Core design principle

> Large roadmap / document upload **never** triggers direct
> execution.
>
> Instead it triggers:
> `intake → diff → proposal queue → approval → small scoped releases.`

The module emits proposals; it does not adopt roadmaps, merge PRs,
modify governance docs, or write to `main`. Adoption / rejection /
release-creation belong to later releases (the approval inbox lands
in v3.15.15.20).

## TL;DR

```sh
# Default: scan docs/roadmap/, docs/backlog/, docs/spillovers/.
python -m reporting.proposal_queue --mode dry-run

# Or point at a specific file or directory.
python -m reporting.proposal_queue --source docs/roadmap/qre_roadmap_v4.md --mode dry-run

# Read the digest without persisting it.
python -m reporting.proposal_queue --mode dry-run --no-write
```

The CLI defaults to `dry-run`. **It is the only allowed mode in
v3.15.15.19** — any other mode is refused at the boundary so we
never write outside the gitignored digest.

## Hard guarantees (enforced by code AND tests)

| guarantee | enforcement |
|---|---|
| Stdlib-only — no subprocess / no `gh` / no `git` / no network | `test_no_subprocess_import_in_module`, `test_no_gh_or_git_invocation_in_module` |
| Reads source files only; never modifies them | `test_frozen_contracts_byte_identical_around_snapshot` |
| Strategic roadmap adoption is HIGH and `needs_human` | `test_strategic_roadmap_adoption_is_high_and_needs_human`, `test_strategic_roadmap_doc_yields_high_needs_human` |
| Tooling proposal mentioning secrets / signup / telemetry → HIGH and `needs_human` | `test_tooling_with_secrets_or_telemetry_is_high`, `test_tooling_intake_marked_secrets_is_high` |
| Free, dev-only, no-telemetry tooling can be LOW and `proposed` | `test_tooling_marked_free_dev_only_is_low`, `test_tooling_intake_marked_free_is_low` |
| Live / paper / shadow / trading scope is `blocked_high_risk` | `test_live_trading_path_is_blocked_high_risk` |
| Frozen / no-touch path is `blocked_protected_path` | `test_protected_path_is_blocked_protected_path`, `test_frozen_contract_path_is_blocked_protected_path` |
| Unknown source → `blocked_unknown` or `not_available` | `test_unknown_source_yields_blocked_unknown_or_missing` |
| Malformed input does not crash | `test_malformed_input_does_not_crash` |
| `proposal_id` is deterministic for the same input | `test_proposal_id_is_deterministic` |
| `dry-run` is the only allowed mode | `test_non_dry_run_mode_is_refused` |

## Proposal types

| type | meaning |
|---|---|
| `roadmap_adoption` | strategic full-roadmap proposal — HIGH / `needs_human` |
| `roadmap_diff` | explicit diff against an existing canonical roadmap — MEDIUM |
| `release_candidate` | title contains a release tag (`v3.15.15.x`) — MEDIUM |
| `governance_change` | touches `.claude/`, CODEOWNERS, branch protection, governance docs — HIGH / `needs_human` |
| `tooling_intake` | proposed dev tool / dependency — risk depends on telemetry / signup |
| `ci_hygiene` | GH Actions, workflows, SHA pin, Dependabot — MEDIUM |
| `dependency_cleanup` | requirements bump / package-lock — MEDIUM |
| `observability_gap` | observability / logging / metrics gap — MEDIUM |
| `testing_gap` | missing tests / coverage gap — MEDIUM |
| `ux_gap` | UX / UI / frontend gap — MEDIUM |
| `approval_required` | catch-all when the segment looks like a proposal — MEDIUM |
| `blocked_unknown` | unparseable source — `blocked` |

## Risk policy (pinned)

Decision order — first-match wins:

1. `affected_files` touches a frozen contract or no-touch path → **HIGH**, `status=blocked`.
2. `affected_files` touches a live / paper / shadow / trading path → **HIGH**, `status=blocked`.
3. `proposal_type == "roadmap_adoption"` → **HIGH**, `status=needs_human`.
4. `proposal_type == "governance_change"` → **HIGH**, `status=needs_human`.
5. `proposal_type == "tooling_intake"` mentioning secrets / signup / telemetry / hosted service → **HIGH**, `status=needs_human`.
6. `proposal_type == "tooling_intake"` mentioning `dev-only`, `MIT license`, `no telemetry`, etc. → **LOW**, `status=proposed`.
7. `tooling_intake` (no marker) / `ci_hygiene` / `dependency_cleanup` / `release_candidate` / `observability_gap` / `testing_gap` / `ux_gap` → **MEDIUM**, `status=proposed`.
8. `blocked_unknown` → **MEDIUM**, `status=blocked`.

The negation-aware tooling check matters: `"no telemetry"` and
`"no signup"` are explicit free-tool markers, not HIGH triggers.
The substring "telemetry" inside the phrase "no telemetry" is
deliberately NOT counted as a HIGH signal (regex strips
`no <token>` / `no-<token>` before checking HIGH tokens).

## Reading the JSON artifact

```sh
python -m reporting.proposal_queue --mode dry-run
# writes logs/proposal_queue/latest.json + a timestamped copy

# Quick triage: how many proposals would be needs_human right now?
jq '[.proposals[] | select(.status == "needs_human")] | length' \
   logs/proposal_queue/latest.json

# Or just the final recommendation:
jq -r '.final_recommendation' logs/proposal_queue/latest.json
```

## PWA integration

The Agent Control PWA (v3.15.15.18) gains a sixth read-only card:
**Proposals**. It hits `/api/agent-control/proposals` (GET only) and
renders a one-line summary per proposal — `proposal_id`,
`proposal_type`, risk pill — with no approve / reject / merge
button.

### Wiring step (manual, one line)

`dashboard/dashboard.py` is on the no-touch list. Activating the new
GET route requires one operator-led line in `dashboard.py`:

```python
# v3.15.15.19: read-only Proposal Queue route.
from dashboard.api_proposal_queue import register_proposal_queue_routes
register_proposal_queue_routes(app)
```

Until that PR lands, the PWA's Proposals card renders
`not_available` (the route is 404 and the frontend client falls back
gracefully — by design).

## What this is NOT

The release intentionally does NOT ship:

* approve / reject / supersede buttons (release v3.15.15.20);
* execute-safe controls (release v3.15.15.21);
* canonical roadmap adoption — `roadmap_adoption` proposals stay
  `needs_human` forever in this release;
* a diff layer that flags whether a proposal supersedes an existing
  canonical roadmap section (release v3.15.15.20);
* any non-dry-run mode (refused at the CLI boundary);
* any POST / PUT / PATCH / DELETE endpoint;
* any browser push notification.

## Forward roadmap (not shipped here)

| release | adds |
|---|---|
| **v3.15.15.19 (this)** | proposal parser, queue, schema, GET route, read-only PWA card |
| v3.15.15.20 | approval inbox: operator approves / rejects / supersedes; status emits `approved` / `rejected` / `superseded` |
| v3.15.15.21 | execute-safe controls in the dashboard (the first *write* button) |
| v3.15.15.23 | browser push notifications for `needs_human` proposals only |
| v3.15.15.25 | metrics / observability dashboards |

## Files added by v3.15.15.19

```
reporting/proposal_queue.py                              (parser/classifier/planner)
dashboard/api_proposal_queue.py                          (GET-only Flask route)
docs/governance/proposal_queue/schema.v1.md              (JSON schema)
docs/governance/roadmap_proposal_queue.md                (this file)
docs/governance/tooling_intake_policy.md                 (canonical tooling policy)
frontend/src/api/agent_control.ts                        (extended with proposals())
frontend/src/routes/AgentControl.tsx                     (Proposals card added)
frontend/src/test/AgentControl.test.tsx                  (proposals tests)
tests/unit/test_proposal_queue.py                        (39 cases)
tests/unit/test_dashboard_api_proposal_queue.py          (13 cases)
```

No edits to `dashboard/dashboard.py` (no-touch). No edits to
`.claude/**`. No frozen-contract changes. No live / paper / shadow /
trading / risk behavior changes.
