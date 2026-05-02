# Proposal Queue Digest — Schema v1

> Module: `reporting.proposal_queue`
> Module version: `v3.15.15.19`
> Schema version: `1`
> Artifact path (gitignored): `logs/proposal_queue/latest.json`
> Timestamped copies: `logs/proposal_queue/<UTC>.json`

## Top-level fields

| field | type | values | notes |
|---|---|---|---|
| `schema_version` | int | `1` | bump on breaking changes |
| `report_kind` | string | `"proposal_queue_digest"` | constant |
| `module_version` | string | `"v3.15.15.19"` etc. | source-of-truth |
| `generated_at_utc` | string | RFC3339 UTC | seconds resolution |
| `mode` | string | `"dry-run"` | only mode allowed in v3.15.15.19 |
| `sources` | array | list of relative paths | files that produced proposals |
| `missing_sources` | array | `[{path, reason}]` | requested roots that did not exist |
| `proposals` | array | see "Proposal" below | one row per detected unit of work |
| `counts` | object | totals + by-status / by-risk / by-type | aggregate view |
| `final_recommendation` | string | see below | summary verdict |
| `status` (optional) | string | `"refused"` if a non-dry-run mode was requested | only present in refused responses |

## Proposal

One entry per detected proposal.

| field | type | values | notes |
|---|---|---|---|
| `proposal_id` | string | `"p_<sha8>"` | deterministic hash of source + title + line index |
| `created_at` | string | RFC3339 UTC | snapshot timestamp (same for all rows in a snapshot) |
| `source` | string | relative path | the markdown / text file the proposal came from |
| `source_type` | enum | `"markdown_heading"` / `"markdown_preamble"` | how the segment was extracted |
| `title` | string | heading text | trimmed |
| `summary` | string | short summary | first bullet or sentence; truncated to 240 chars |
| `rationale` | string | longer rationale | up to 600 chars |
| `evidence` | object | `{heading_level, line_idx, body_chars}` | structural evidence for the operator |
| `affected_files` | array | list of paths | extracted from backtick-quoted file references in the body |
| `risk_class` | enum | `"LOW"` / `"MEDIUM"` / `"HIGH"` | per the policy below |
| `risk_reason` | string | human-readable rationale | tied to `risk_class` |
| `approval_required` | bool | true / false | true for HIGH risk, blocked, needs_human, or `approval_required` type |
| `blocked_reason` | string \| null | e.g. `"blocked_protected_path: ..."` | only set when `status == blocked` |
| `proposal_type` | enum | see "Proposal types" | first-match classifier |
| `allowed_actions` | array | strings | advisory; the agent + hook layers enforce |
| `forbidden_actions` | array | strings | always lists the universal hard-no actions |
| `required_tests` | array | strings | tests an approval would gate on |
| `suggested_branch_name` | string | e.g. `fix/approval-required-x` | review-only suggestion |
| `suggested_release_id` | string \| null | e.g. `"v3.15.15.20"` | parsed from title if present |
| `status` | enum | `"proposed"` / `"needs_human"` / `"approved"` / `"rejected"` / `"blocked"` / `"superseded"` | this release only emits the first three |
| `parent_proposal_id` | string \| null | reserved for v3.15.15.20+ | always null in this release |
| `dependencies` | array | reserved for v3.15.15.20+ | always empty in this release |
| `operator_notes` | string | reserved for v3.15.15.20+ | always empty in this release |

## Proposal types

| type | meaning |
|---|---|
| `roadmap_adoption` | strategic-shape signal: full new roadmap proposed for canonical |
| `roadmap_diff` | explicit diff against an existing canonical roadmap |
| `release_candidate` | title contains a release tag (`v3.15.15.x`, etc.) |
| `governance_change` | touches `.claude/`, CODEOWNERS, branch protection, governance docs |
| `tooling_intake` | explicit "tool / library / package / dep" mention |
| `ci_hygiene` | GH Actions, workflows, SHA pin, Dependabot |
| `dependency_cleanup` | requirements bump / package-lock / deps cleanup |
| `observability_gap` | observability / logging / metrics / audit log |
| `testing_gap` | missing test, coverage gap, no tests |
| `ux_gap` | UX / UI / frontend gap |
| `approval_required` | catch-all when the segment looks like a proposal |
| `blocked_unknown` | unparseable source (missing / unreadable / not_a_file) |

## Risk policy (pinned)

Decision order — first-match wins:

1. `affected_files` touches a frozen contract or no-touch path → **HIGH**, `status=blocked`, `blocked_reason="blocked_protected_path: <hit>"`.
2. `affected_files` touches a live / paper / shadow / trading path → **HIGH**, `status=blocked`, `blocked_reason="blocked_high_risk: live/trading path: <hit>"`.
3. `proposal_type == "roadmap_adoption"` → **HIGH**, `status=needs_human`.
4. `proposal_type == "governance_change"` → **HIGH**, `status=needs_human`.
5. `proposal_type == "tooling_intake"` mentioning `api key`, `token`, `signup`, `oauth`, `telemetry`, `hosted service`, `paid plan`, `subscription`, etc. → **HIGH**, `status=needs_human`.
6. `proposal_type == "tooling_intake"` mentioning `dev-only`, `stdlib-only`, `no telemetry`, `no signup`, `MIT license`, etc. → **LOW**, `status=proposed`.
7. `proposal_type` is `tooling_intake` (with no explicit signal), `ci_hygiene`, `dependency_cleanup`, `release_candidate`, `observability_gap`, `testing_gap`, or `ux_gap` → **MEDIUM**, `status=proposed`.
8. `proposal_type == "blocked_unknown"` → **MEDIUM**, `status=blocked`, `blocked_reason="blocked_unknown: ..."`.
9. Anything else → **MEDIUM**, `status=proposed` (conservative).

## `final_recommendation` enum

* `"no_proposals"` — empty queue.
* `"review_<n>_proposed_items"` — only `proposed` items.
* `"needs_human_on_<n>_items"` — at least one `needs_human`.
* `"blocked_on_<n>_items"` — at least one `blocked` (no `needs_human`).
* `"needs_human"` — fallback.

## Counts object

```json
{
  "total": 12,
  "by_status":  {"proposed": 9, "needs_human": 2, "blocked": 1},
  "by_risk":    {"LOW": 1, "MEDIUM": 9, "HIGH": 2},
  "by_type":    {"approval_required": 5, "release_candidate": 4, "tooling_intake": 2, "governance_change": 1}
}
```

## Hard guarantees encoded in the schema

* `proposal_id` is deterministic — re-running with the same source produces the same id.
* `proposals` never embeds raw secrets (the parser only reads the source verbatim; if the operator stores a secret in a roadmap doc the source itself is the bug, not the queue — but the queue truncates at the segment level and never echoes file content beyond `summary` + `rationale`, both length-capped).
* `forbidden_actions` always lists the universal "never" list (push to main, force-push, admin merge, edit `.claude/**`, edit frozen contracts, edit `automation/live_gate.py`, bump `VERSION`).
* `allowed_actions` is empty for `approval_required` proposals (the operator decides what to unlock at approval time).
* `mode != "dry-run"` is refused at the boundary in this release.

## Wiring with the dashboard

`dashboard/api_proposal_queue.py` exposes a single GET-only route
`/api/agent-control/proposals`. It reads
`logs/proposal_queue/latest.json` and returns a `not_available`
envelope when the artifact is missing or malformed — same contract
as the rest of the v3.15.15.18 surface. The PWA Proposal Queue card
consumes this endpoint directly.

## Next-release additions (informative, not part of v1 schema)

Future schema additions are allowed in minor revisions; renames or
removals require a new schema version.

* `parent_proposal_id` / `dependencies` / `operator_notes` will
  populate from v3.15.15.20 (approval inbox).
* `status` may emit `"approved"` / `"rejected"` / `"superseded"`
  starting v3.15.15.20.
* A diffing layer that reports whether a proposal supersedes an
  existing canonical roadmap section lands in v3.15.15.20.
