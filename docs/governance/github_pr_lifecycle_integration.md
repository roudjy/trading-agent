# GitHub PR Lifecycle Integration

> Module: `reporting.github_pr_lifecycle` (v3.15.15.17)
> Schema: `docs/governance/github_pr_lifecycle/schema.v1.md`
> Operator runbook: `docs/governance/dependabot_cleanup_playbook.md`

## What this is

`reporting.github_pr_lifecycle` is a stdlib-only Python module that
turns the v3.15.15.17 Dependabot cleanup pilot — 10/10 PRs processed
to final main SHA `bd206ba9ea0eeb4c696a30d5778d97cdc7107926` with
zero direct pushes — into a reproducible playbook.

It has three layers:

1. **Provider abstraction** — a thin wrapper over the `gh` CLI for
   read operations (PR list / inspect / checks) and the two mutating
   actions actually used by the pilot: `@dependabot rebase` comments
   and `--squash --delete-branch` merges.
2. **Risk classifier** — pure function from PR metadata + diff to one
   of `LOW` / `MEDIUM` / `HIGH`. Encodes the explicit policy the
   pilot ran by hand.
3. **Decision planner** — pure function from `(PR, files, checks,
   risk_class, baseline_ok)` to one of nine documented decisions.

Plus a CLI with two modes (`dry-run` / `execute-safe`) and a JSON
digest contract.

## Architecture (thin layers)

```
                   ┌───────────────────────┐
                   │ collect_snapshot()    │
                   │  • baseline gates     │
                   │  • provider probe     │
                   │  • per-PR loop:       │
                   │    inspect → checks → │
                   │    classify → decide  │
                   └──────────┬────────────┘
                              │ snapshot dict (schema v1)
                              ▼
   dry-run ────────────────►  stdout / logs/.../latest.json
                              │
   execute-safe ──► execute_safe_actions() ──► gh comment / merge
                                                (only LOW/MEDIUM
                                                 with all gates green)
```

Every gh call is dependency-injected (`fetch_inspect`, `fetch_checks`,
`do_comment`, `do_merge`), so the planner is unit-testable without a
real `gh` binary.

## Hard guarantees (enforced by code AND tests)

| guarantee | enforcement |
|---|---|
| No direct push to `main` | this module never invokes `git push` of any kind |
| No force-push | this module never uses `--force` / `--force-with-lease` |
| Never merge HIGH | planner returns `blocked_high_risk`; runner re-checks defensively |
| Never merge with protected-path diff | planner returns `blocked_protected_path`; runner re-checks |
| Never merge with unknown mergeability | `mergeStateStatus` must be `CLEAN` |
| Never merge with pending or failing checks | `aggregate_checks` must return `passed` |
| Never act when local baseline is red | `baseline.all_ok` must be true; runner aborts otherwise |
| `unknown` is never green | empty checks list, unknown conclusion → `unknown` (never `passed`) |
| BEHIND PRs are rebased via canonical comment | `wait_for_rebase` action is `comment_dependabot_rebase`, never a force-push |

The runner re-checks every gate even after the planner clears a row,
because the planner's output is data — defense in depth means the
runner does not trust it.

## Governance interplay

* Module lives under `reporting/`, which is in `observability-guardian`'s
  `allowed_roots` → writeable by an audit-emitting subagent.
* JSON artifacts go under `logs/github_pr_lifecycle/`, which is
  gitignored — same approach as `reporting.autonomous_workloop`.
* Schema and docs live under `docs/governance/`, mirroring the rest
  of the governance layer.
* No `.claude/**` changes; no edits to `automation/live_gate.py`,
  `config/config.yaml`, `VERSION`, or any frozen contract.
* The module reads `PROTECTED_GLOBS` mirroring
  `docs/governance/no_touch_paths.md`. When the canonical list
  changes, sync this constant via release notes.

## How it composes with `autonomous_workloop`

`reporting.autonomous_workloop` (v3.15.15.16) is the local-state
planner: read-only by default, classifies branches without GitHub
visibility. It never calls `gh`.

`reporting.github_pr_lifecycle` (v3.15.15.17) is the GitHub-backed
sibling: it does call `gh`, and it CAN mutate GitHub state when run
in `execute-safe` mode — but only along the narrow channels proven
in the pilot.

The two modules share governance constants (frozen contracts, no-touch
globs, live-trading globs) but do not depend on each other. They can
be invoked independently and their JSON artifacts merged by a future
dashboard.

## Out of scope for this release

The following are deliberately deferred to a later release:

* Auto-merging HIGH-risk PRs even with all checks green. The pilot
  merged some HIGH PRs after human-level reasoning ("Node 24 runtime
  bump only", "floor-bump not pin change"). That reasoning is not yet
  formalized in a way the planner can reproduce, so HIGH stays
  inspect-only here.
* Auto-creating PRs from local feature branches. Not in scope for
  the Dependabot cleanup playbook.
* Polling loops that wait for rebase/CI completion in a single run.
  The current model is single-pass: comment-rebase, exit, re-run later.
* Slack / email notifications.
* Dashboard execute controls (tracked separately under v3.15.15.21).

## Pilot evidence

| metric | value |
|---|---|
| Open Dependabot PRs at start | 10 |
| PRs merged through `gh pr merge --squash --delete-branch` | 10 |
| PRs that needed rebase | 5 |
| Rebase mechanism | `@dependabot rebase` comment (canonical) |
| Force-pushes performed | 0 |
| Direct pushes to `main` | 0 |
| Final main SHA | `bd206ba9ea0eeb4c696a30d5778d97cdc7107926` |
| Docker workflow status post-pilot | `success` (build-grep-push, sbom, scan, provenance all green) |
| Frozen-contract hashes drift | 0 |

## Reading the JSON artifact

```sh
python -m reporting.github_pr_lifecycle --mode dry-run
# writes logs/github_pr_lifecycle/latest.json + a timestamped copy

# Quick triage: how many PRs would be merge-allowed right now?
jq '[.prs[] | select(.decision == "merge_allowed")] | length' \
   logs/github_pr_lifecycle/latest.json

# Or just the final recommendation:
jq -r '.final_recommendation' logs/github_pr_lifecycle/latest.json
```

## When to update this module

* **PROTECTED_GLOBS / FROZEN_CONTRACTS** drift from
  `docs/governance/no_touch_paths.md` → resync.
* **HIGH_RISK_PYTHON_PACKAGES** changes (e.g. add `polars`) →
  update the frozenset and the schema doc.
* **gh CLI** introduces a breaking change to `--json statusCheckRollup`
  → update `pr_checks` and add a regression test.
* **Branch-protection** loosens the "branches must be up to date"
  requirement → `wait_for_rebase` may become unreachable for some
  PRs. The planner stays the same; the schema is unchanged.

Update the schema version (`SCHEMA_VERSION`) only on a *removing or
renaming* change. Field additions are allowed in a minor revision.
