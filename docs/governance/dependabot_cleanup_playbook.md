# Dependabot Cleanup Playbook

> Module: `reporting.github_pr_lifecycle` (v3.15.15.17)
> Architecture: `docs/governance/github_pr_lifecycle_integration.md`
> Schema: `docs/governance/github_pr_lifecycle/schema.v1.md`

This is the operator-facing runbook. It tells you exactly how to
process an open Dependabot queue safely, mirroring the proven pilot
that landed final main SHA `bd206ba9ea0eeb4c696a30d5778d97cdc7107926`
with 10/10 PRs merged, zero direct pushes, and zero force-pushes.

## TL;DR

```sh
# 1. Make sure the local baseline is green.
git checkout main
git pull --ff-only origin main
python scripts/governance_lint.py
pytest tests/smoke -q
sha256sum research/research_latest.json research/strategy_matrix.csv

# 2. See what's in the queue (read-only).
python -m reporting.github_pr_lifecycle --mode dry-run

# 3. Act on the queue (rebases + LOW/MEDIUM merges only).
python -m reporting.github_pr_lifecycle --mode execute-safe
```

`execute-safe` only:

* posts `@dependabot rebase` on `BEHIND` PRs,
* squash-merges `LOW` / `MEDIUM` PRs whose mergeStateStatus is `CLEAN`
  and whose checks are `passed`.

It never:

* merges anything classified `HIGH`,
* pushes to `main`,
* force-pushes any branch,
* mutates anything when the local baseline is red.

## Prerequisites

| requirement | how to check |
|---|---|
| `gh` on PATH and authenticated | `gh auth status` exits 0 |
| Repo detected by `gh` | `gh repo view --json nameWithOwner` returns the repo |
| Local working tree clean | `git status --short` shows no tracked changes |
| Frozen contracts intact | `sha256sum research/research_latest.json research/strategy_matrix.csv` matches the canonical hashes |

If any of these fails, run the module in `dry-run` first — the
snapshot will report the specific blocker (`provider_status`,
`baseline_status`).

## Risk policy

The classifier in this module pins the policy to a single source of
truth so all operators apply it the same way:

| class | examples |
|---|---|
| **LOW** | GH Actions patch/minor updates whose diff is workflow-only; frontend dev-only patch |
| **MEDIUM** | GH Actions 0.x minor (semver-unstable in 0.x); Python production dep `>=` floor bumps; CI tooling minor; mixed-or-unknown diff |
| **HIGH** | major-version bumps; `numpy`, `pandas`, `pyarrow`, `scipy`, `sklearn`, `pydantic`, `FastAPI`, `SQLAlchemy`; Docker / build / runtime base changes; conflicts; failing checks; **any** diff touching frozen / no-touch / live paths |

`HIGH` is **inspect-only** in v3.15.15.17 even when all gates are
green. The pilot merged some HIGH PRs after human reasoning; that
reasoning is not yet formalized for the planner.

## Decision matrix

The planner returns one of these decisions per PR. The schema doc
has the full enum; this is the operator-facing summary.

| decision | meaning | what the runner does |
|---|---|---|
| `merge_allowed` | LOW/MEDIUM, CLEAN, checks passed, baseline ok | `gh pr merge --squash --delete-branch` |
| `wait_for_rebase` | BEHIND main | `gh pr comment <n> --body "@dependabot rebase"` |
| `wait_for_checks` | CLEAN but checks pending | nothing (re-run later) |
| `blocked_failing_checks` | one or more checks failed | nothing |
| `blocked_conflict` | DIRTY merge state | nothing |
| `blocked_high_risk` | HIGH risk class | nothing (inspect-only this release) |
| `blocked_protected_path` | diff touches frozen / no-touch / live path | nothing |
| `blocked_unknown` | mergeStateStatus or checks state not safe | nothing |
| `needs_human` | non-Dependabot, non-main base, draft, or local baseline red | nothing |

## BEHIND PRs — canonical rebase flow

When `git pull` (or branch protection) reports a PR is behind `main`,
the playbook DOES NOT force-push the branch. The rebase is requested
through Dependabot's own comment trigger, exactly as the pilot did:

```sh
gh pr comment <number> --body "@dependabot rebase"
```

Wait for the rebase + CI to complete (typically a few minutes), then
re-run the playbook. The next snapshot will show the PR as `CLEAN`
and `merge_allowed`.

This is the only correct path because:

* `git push --force-with-lease` is denied by the local hook layer
  (`deny_dangerous_bash.py`).
* Branch protection on `main` requires up-to-date branches.
* Dependabot owns the branch and re-runs CI on rebase.

## Modes

### `dry-run` (default)

* Reads provider state, lists open PRs, classifies, plans.
* Writes a JSON digest to `logs/github_pr_lifecycle/latest.json` (and
  a timestamped copy). Nothing else.
* Safe to run any time.

### `execute-safe`

* Runs the full baseline (governance_lint + smoke + frozen hashes).
  If any gate is red, aborts before any mutation and emits an
  `actions_taken: [{kind: "abort", outcome: "refused", ...}]` row.
* For each row:
    * `wait_for_rebase` → posts the `@dependabot rebase` comment.
    * `merge_allowed` → re-checks every gate one more time, then
      squash-merges with `--delete-branch`.
    * Anything else → no mutation.
* Records every action in `actions_taken` (per-row and at the
  snapshot top level).

### Additional CLI flags

```
--no-write    Do not persist the JSON digest to logs/.
--no-smoke    Skip smoke tests in dry-run only (execute-safe always
              runs the full baseline).
--indent N    JSON pretty-print indent (default 2; 0 = compact).
```

## Walking through a real cycle

Snapshot of the pilot, condensed:

| step | action | result |
|---|---|---|
| 1 | `dry-run` after a clean main | 10 open Dependabot PRs found; 1 LOW CLEAN, 4 LOW BEHIND, 2 MEDIUM CLEAN, 2 MEDIUM BEHIND, 2 HIGH BEHIND |
| 2 | `execute-safe` cycle 1 | merged the 1 CLEAN LOW; commented `@dependabot rebase` on the 4 BEHIND LOW |
| 3 | wait for Dependabot rebase + CI | PRs flip to `CLEAN` |
| 4 | `execute-safe` cycle 2 | merges the now-CLEAN LOW PRs |
| ... | ... | ... |
| N | `execute-safe` cycle N | nothing mergeable left; final HIGH PRs reported as `blocked_high_risk` |

The cycle never makes a single force-push or direct main push.

## Escalation paths

* **Provider unavailable / not authenticated**: install `gh`, run
  `gh auth login`, re-run the playbook.
* **Frozen-contract hash drift**: stop. Investigate manually. Do not
  proceed until the drift is explained — the snapshot's
  `frozen_hashes` field shows which file changed.
* **`blocked_high_risk` you actually want to merge**: do it manually
  with extra inspection. The pilot's HIGH-merge reasoning lives in
  the pilot run notes; until that's formalized, HIGH stays manual.
* **Unexpected `blocked_protected_path`**: the diff touches
  `.claude/**`, `automation/live_gate.py`, frozen contracts,
  `Dockerfile`, etc. Treat as a real signal — Dependabot should not
  touch those files.
* **Persistent `wait_for_rebase` after multiple cycles**: Dependabot
  may have flagged the bump as un-rebaseable. Use
  `gh pr comment <n> --body "@dependabot recreate"` manually.

## Reading the queue table from the digest

```sh
jq -r '
  .prs[] |
  [.number, .risk_class, .merge_state, .checks_state, .decision] |
  @tsv
' logs/github_pr_lifecycle/latest.json | column -t
```

## What the playbook does NOT do

The playbook is deliberately narrow:

* Does not handle non-Dependabot PRs. They become `needs_human`.
* Does not handle PRs targeting branches other than `main`.
* Does not poll/wait inside a single run. Re-run for each cycle.
* Does not Slack / email anyone. The JSON artifact is the contract.
* Does not bump `VERSION` (no-touch).
* Does not modify any `.claude/**` files.

## Auditability

Every cycle writes a timestamped JSON artifact under
`logs/github_pr_lifecycle/`. The directory is gitignored (runtime
state only). The schema (`schema_version: 1`) is stable per the
schema doc; downstream tools (dashboard, autonomous workloop) can
consume it directly.

The pilot's full evidence is in
`docs/governance/github_pr_lifecycle_integration.md` under "Pilot
evidence".
