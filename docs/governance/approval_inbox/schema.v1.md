# Approval / Exception Inbox Digest — Schema v1

> Module: `reporting.approval_inbox`
> Module version: `v3.15.15.20`
> Schema version: `1`
> Artifact path (gitignored): `logs/approval_inbox/latest.json`
> Timestamped copies: `logs/approval_inbox/<UTC>.json`

## Top-level fields

| field | type | values | notes |
|---|---|---|---|
| `schema_version` | int | `1` | bump on breaking changes |
| `report_kind` | string | `"approval_inbox_digest"` | constant |
| `module_version` | string | `"v3.15.15.20"` | source-of-truth |
| `generated_at_utc` | string | RFC3339 UTC | seconds resolution |
| `mode` | string | `"dry-run"` | only mode allowed in v3.15.15.20 |
| `sources` | object | per-source envelope | one entry per upstream reporter |
| `items` | array | see "Item" | one row per approval / exception |
| `counts` | object | totals + by-category / by-severity / by-status | aggregate view |
| `final_recommendation` | string | see below | summary verdict |
| `status` (optional) | string | `"refused"` if a non-dry-run mode was requested | only present in refused responses |

## `sources` object

```json
{
  "proposal_queue":   {"status": "ok|not_available", "path": "logs/proposal_queue/latest.json",   "reason": null|string},
  "pr_lifecycle":     {"status": "ok|not_available", "path": "logs/github_pr_lifecycle/latest.json", "reason": null|string},
  "workloop":         {"status": "ok|not_available", "path": "logs/autonomous_workloop/latest.json", "reason": null|string},
  "governance_status":{"status": "ok|not_available", "path": "governance_status:in_process", "reason": null|string}
}
```

A `status != "ok"` source produces an `unknown_state` item so the
operator sees the gap explicitly. `unknown` is never silently OK.

## Item

| field | type | notes |
|---|---|---|
| `item_id` | string | `"i_<sha8>"` — deterministic over `source` + `source_type` + `category` + `title` |
| `created_at` | string | RFC3339 UTC; same value for all items in one snapshot |
| `source` | string | e.g. `"proposal_queue:p_abcdef01"`, `"pr_lifecycle:#42"`, `"workloop:..."`, `"manual:..."`, `"missing:<source>"` |
| `source_type` | enum | `"proposal"` / `"pr"` / `"workloop"` / `"governance"` / `"audit"` / `"manual"` |
| `title` | string | trimmed |
| `summary` | string | trimmed and length-capped (480 chars) |
| `category` | enum | see "Categories" |
| `severity` | enum | `"info"` / `"low"` / `"medium"` / `"high"` / `"critical"` |
| `status` | enum | `"open"` / `"acknowledged"` / `"blocked"` / `"resolved"` / `"superseded"` (this release only emits `open` and `blocked`) |
| `risk_class` | enum | `"LOW"` / `"MEDIUM"` / `"HIGH"` / `"UNKNOWN"` |
| `approval_required` | bool | always `true` in this release; field reserved for v3.15.15.21+ when proposed items can land without approval |
| `recommended_operator_action` | string | human-readable next step |
| `forbidden_agent_actions` | array | universal hard-no list, surfaced on every item |
| `evidence` | object | source-specific evidence (proposal_type, decision, url, etc.) |
| `affected_files` | array | from the upstream source, copied verbatim |
| `related_proposal_id` | string \| null | when the item came from `proposal_queue` |
| `related_pr_number` | int \| null | when the item came from `pr_lifecycle` |
| `related_release_id` | string \| null | release tag if known |
| `dependencies` | array | reserved for v3.15.15.21+; always `[]` in this release |
| `stale_after` | string \| null | reserved for future expiry semantics |
| `audit_refs` | array | optional list of audit-ledger sequence ids for traceability |

## Categories (18)

| value | source | severity (default) | meaning |
|---|---|---|---|
| `roadmap_adoption_required` | proposal | high | strategic full-roadmap proposal — manual adoption only |
| `high_risk_pr` | pr | high | HIGH-risk PR; the lifecycle module never auto-merges these |
| `protected_path_change` | proposal / pr / workloop | high | diff touches `.claude/`, frozen contract, no-touch path |
| `governance_change` | proposal | high | CODEOWNERS / branch protection / governance docs |
| `tooling_requires_approval` | proposal / pr | medium | tooling intake without explicit free / dev-only marker, or generic HIGH catch-all |
| `external_account_or_secret_required` | proposal | high | tooling intake mentions API key / OAuth / signup / token |
| `telemetry_or_data_egress_required` | proposal | high | tooling intake mentions telemetry / Datadog / Sentry / Segment.io |
| `paid_tool_required` | proposal | high | tooling intake mentions paid plan / SaaS / hosted service |
| `frozen_contract_risk` | proposal / pr / workloop | critical | diff would touch `research/research_latest.json` or `research/strategy_matrix.csv` |
| `live_paper_shadow_risk_change` | proposal / pr / workloop | critical | diff touches live / paper / shadow / trading-flow paths |
| `ci_or_test_weakening_risk` | (reserved) | high | future: any proposal that would weaken CI gates or tests |
| `unknown_state` | any | medium | upstream source missing / malformed / unparseable; or a row with `risk_class="unknown"` |
| `failed_automation` | pr / workloop | high | conflict, automation halt, governance lint failure |
| `blocked_rebase` | pr | medium | PR is BEHIND main; canonical rebase via `@dependabot rebase` comment |
| `blocked_checks` | pr | medium | PR has failing required checks |
| `runtime_halt` | (reserved) | critical | future: long-running runtime stopped unexpectedly |
| `security_alert` | governance / audit | critical | audit chain broken, hook violation, secret-scan finding |
| `manual_route_wiring_required` | manual | low | one-line `register_*_routes` PR needed in `dashboard/dashboard.py` (no-touch) |

## Severity scale

```
info < low < medium < high < critical
```

Severity is per-category and intentional: `frozen_contract_risk` and
`live_paper_shadow_risk_change` are always **critical**;
`manual_route_wiring_required` is always **low** (no urgency);
`unknown_state` defaults to **medium** (operator inspection
warranted but not a fire).

## Status (read-only emitter)

| value | emitted by v3.15.15.20? |
|---|---|
| `open` | yes — default for actionable items |
| `acknowledged` | no — reserved for v3.15.15.21 (operator UI marks acknowledged) |
| `blocked` | yes — for items whose upstream status is `blocked` |
| `resolved` | no — reserved for v3.15.15.21 |
| `superseded` | no — reserved for v3.15.15.21 |

The schema declares all five values so frontend / downstream
consumers can render them when they appear in v3.15.15.21+.

## Final recommendation

Stable values:

* `"no_items"`
* `"critical_on_<n>_items"`
* `"high_severity_on_<n>_items"`
* `"review_<n>_open_items"`
* `"needs_human"` (fallback for refused responses)

## Hard guarantees encoded in the schema

* No item is silently OK; everything that survives upstream review
  flows through one of 18 explicit categories.
* `forbidden_agent_actions` is the same universal hard-no list on
  every item — the operator can rely on it regardless of category.
* `approval_required` is `true` for every item in this release.
* `mode != "dry-run"` is refused at the boundary.
* `item_id` is deterministic — same input always produces the
  same id.

## Wiring with the dashboard

`dashboard/api_approval_inbox.py` exposes a single GET-only route
`/api/agent-control/approval-inbox`. It reads
`logs/approval_inbox/latest.json` and returns `not_available` for
missing / malformed artifacts — same contract as the rest of the
v3.15.15.18 surface. The PWA Approval Inbox card consumes this
endpoint directly. Activation requires one operator-led line in
`dashboard/dashboard.py` (no-touch); until then the card renders
`not_available`.

## Next-release additions (informative, not part of v1 schema)

* v3.15.15.21: status emits `acknowledged` / `resolved` /
  `superseded` once the operator UI exposes those transitions.
* v3.15.15.21: `dependencies` populates with `item_id` references
  when an inbox row needs another item resolved first.
* v3.15.15.23: a `notification_pushed_at` timestamp lands once
  browser push for needs-human items goes live.
