# GitHub PR Lifecycle Digest — Schema v1

> Module: `reporting.github_pr_lifecycle`
> Module version: `v3.15.15.17`
> Schema version: `1`
> Artifact path (gitignored): `logs/github_pr_lifecycle/latest.json`
> Timestamped copies: `logs/github_pr_lifecycle/<UTC>.json`

This is the canonical contract for the JSON digest emitted by the
GitHub PR lifecycle module. The dashboard, autonomous workloop, and
release-gate tooling all consume this shape. Field additions are
allowed in a minor revision; field renames or removals require a
new schema version.

## Top-level fields

| field | type | values | notes |
|---|---|---|---|
| `schema_version` | int | `1` | bump on breaking changes |
| `report_kind` | string | `"github_pr_lifecycle_digest"` | constant |
| `module_version` | string | `"v3.15.15.17"` etc. | source-of-truth string |
| `generated_at_utc` | string | RFC3339 UTC | seconds resolution |
| `repo` | string | e.g. `"roudjy/trading-agent"` | `"unknown"` if provider not available |
| `provider_status` | enum | see below | provider availability |
| `provider` | object | see below | full provider probe result |
| `mode` | string | `"dry-run"` / `"execute-safe"` | mirrors CLI |
| `baseline_status` | enum | `"ok"` / `"blocked"` | aggregate |
| `baseline` | object | see below | per-gate detail |
| `frozen_hashes` | object | path → sha256 | mirror of `baseline.frozen_hashes` |
| `prs` | array | see "PR row" below | one row per inspected PR |
| `actions_taken` | array | see "action" below | mutations actually performed |
| `final_recommendation` | string | see "Final recommendation" | summary verdict |

## `provider_status` enum

Stable surface for downstream tooling and dashboards.

| value | meaning |
|---|---|
| `available` | `gh` on PATH, authenticated, repo detected |
| `not_available` | `gh` is not on PATH or `gh --version` failed |
| `not_authenticated` | `gh auth status` returned non-zero |
| `repo_not_detected` | `gh repo view` failed (not in a git repo or no `origin`) |
| `permission_denied` | listing PRs returned an error from `gh` |

## `provider` object

```json
{
  "status": "available",
  "gh_path": "/usr/bin/gh",
  "version": "gh version 2.92.0 (2026-04-28)",
  "account": "roudjy",
  "repo": "roudjy/trading-agent"
}
```

## `baseline` object

Reports the local read-only gate run. The full snapshot refuses any
mutation if `baseline.all_ok` is false.

```json
{
  "governance_lint": {"ok": true, "summary": "Governance lint OK ..."},
  "smoke_tests":     {"ok": true, "summary": "14 passed in 5.20s"},
  "frozen_hashes": {
    "research/research_latest.json": "4a567bd6...",
    "research/strategy_matrix.csv":   "ff15b8c4..."
  },
  "all_ok": true
}
```

## PR row

One entry per Dependabot PR considered.

| field | type | notes |
|---|---|---|
| `number` | int | PR number |
| `title` | string | original Dependabot title |
| `author` | string | lowercased login (`"app/dependabot"`) |
| `base` | string | base branch (`"main"`) |
| `branch` | string | head branch (`"dependabot/..."`) |
| `url` | string | GitHub PR URL |
| `package` | string \| null | parsed package name when applicable |
| `risk_class` | enum | `"LOW"` / `"MEDIUM"` / `"HIGH"` / `"UNKNOWN"` |
| `risk_reason` | string | human-readable rationale |
| `merge_state` | enum | `"clean"` / `"behind"` / `"dirty"` / `"unknown"` |
| `checks_state` | enum | `"passed"` / `"pending"` / `"failed"` / `"unknown"` |
| `protected_paths_touched` | bool | true if any frozen / no-touch / live path appears |
| `files_count` | int | number of files in the diff |
| `additions` | int | from gh `--json files` |
| `deletions` | int | from gh `--json files` |
| `decision` | enum | see "Decision" |
| `reason` | string | rationale tied to `decision` |
| `actions_taken` | array | see "action" |

## `decision` enum

| value | meaning |
|---|---|
| `merge_allowed` | LOW or MEDIUM, CLEAN, all checks passed, baseline ok |
| `wait_for_rebase` | BEHIND main; will request `@dependabot rebase` |
| `wait_for_checks` | CLEAN but checks pending |
| `blocked_failing_checks` | one or more checks failed |
| `blocked_conflict` | merge conflict (DIRTY) |
| `blocked_high_risk` | risk_class is HIGH; never auto-merged in this release |
| `blocked_protected_path` | diff touches frozen / no-touch / live path |
| `blocked_unknown` | mergeStateStatus or checks state is not safe to act on |
| `needs_human` | non-Dependabot, non-main base, or draft |

## `action` object

Each entry in `actions_taken` is shaped:

```json
{
  "kind": "comment_dependabot_rebase",
  "target": "PR#41",
  "outcome": "ok",
  "reason": "comment posted"
}
```

`kind` is one of `comment_dependabot_rebase`, `merge_squash`, or `abort`.

## Final recommendation

A single string summarizing the cycle. Stable values:

* `"no_open_prs"`
* `"merge_<n>_low_or_medium_prs"`
* `"request_rebase_on_<n>_behind_prs"`
* `"all_open_prs_blocked_or_waiting"`
* `"baseline_not_green"`
* `"provider_not_available"`
* `"provider_error"`
* `"needs_human"`

## Risk policy (pinned)

| class | examples (informative; not exhaustive) |
|---|---|
| LOW | GH Actions patch/minor (workflow-only diffs); frontend dev-only patch |
| MEDIUM | GH Actions 0.x minor; Python production-deps `>=` floor bumps; CI tooling minor; mixed-or-unknown diff |
| HIGH | major-version bumps; `numpy` / `pandas` / `pyarrow` / `scipy` / `sklearn` / `pydantic` / `FastAPI` / `SQLAlchemy`; Docker / build / runtime base changes; conflicts; failing checks; protected paths; unknown-state PRs |

Decision precedence: protected-path → live/trading → HIGH-list package
→ major-bump → Docker token → workflow-only LOW/MEDIUM → requirements-only
MEDIUM → frontend-only LOW → mixed/unknown MEDIUM. The first match wins.

## Mutation guarantees

Even when `mode == "execute-safe"` and the planner says
`merge_allowed`, the runner re-checks every gate before acting:

* `risk_class != HIGH`
* `protected_paths_touched == false`
* `merge_state == "clean"`
* `checks_state == "passed"`
* `baseline_status == "ok"`

Any one of these fails → `outcome: "refused"`, no `gh` call made.

## Pilot evidence

The schema is the codification of the v3.15.15.17 pilot, which
processed 10/10 open Dependabot PRs to final main SHA
`bd206ba9ea0eeb4c696a30d5778d97cdc7107926` with zero direct pushes
and zero force-pushes. See
`docs/governance/dependabot_cleanup_playbook.md` for the operator
runbook and `docs/governance/github_pr_lifecycle_integration.md` for
the architecture writeup.
