# GitHub PR Lifecycle Protocol (Claude session-start)

> Canonical operator-facing protocol document. Future Claude sessions
> MUST follow this protocol for any branch → PR → CI → merge →
> post-merge work, regardless of whether `gh` is on PATH at session
> start.

## Status

Active. Modifications to this document require operator approval
(`canonical_policy_doc`-class governance change).

## Why this exists

Earlier sessions occasionally fell back to "operator opens the PR
manually" because `gh` was not on PATH in the current shell. That
fallback is **not** acceptable: GitHub CLI portable is installed
locally and has been used successfully through PRs #63–#91. The
absence of `gh` on PATH is **never** sufficient justification to
skip the PR / CI / squash-merge / post-merge flow.

## GitHub CLI portable path

```text
C:\Users\joery.van.rooij\tools\gh\bin\gh.exe
```

- If `gh` is on PATH, use `gh` directly.
- If `gh` is **not** on PATH, use the explicit portable path above.
- Always invoke through a quoted absolute path on Windows shells.

### Bash (Git Bash / MSYS) examples

```bash
"/c/Users/joery.van.rooij/tools/gh/bin/gh.exe" auth status
"/c/Users/joery.van.rooij/tools/gh/bin/gh.exe" pr create ...
```

### PowerShell example

```powershell
& "C:\Users\joery.van.rooij\tools\gh\bin\gh.exe" auth status
& "C:\Users\joery.van.rooij\tools\gh\bin\gh.exe" pr create ...
```

## Required preflight (every session, before any PR action)

```bash
"/c/Users/joery.van.rooij/tools/gh/bin/gh.exe" auth status
"/c/Users/joery.van.rooij/tools/gh/bin/gh.exe" repo view roudjy/trading-agent
```

Both must succeed. The expected output of `auth status` includes a
`Logged in to github.com account roudjy (keyring)` line and a
non-empty token-scopes list (`repo` scope is required for PR
creation/merge).

If preflight fails, **stop** and instruct the operator to run:

```bash
"/c/Users/joery.van.rooij/tools/gh/bin/gh.exe" auth login
```

with these answers:

- GitHub.com
- HTTPS
- Login with a web browser

After the operator completes the browser flow, re-run the preflight.

## Permitted GitHub CLI surface

For ordinary feature work, Claude may use these subcommands:

| Subcommand | Use |
|---|---|
| `gh auth status` | Preflight only |
| `gh repo view roudjy/trading-agent` | Preflight only |
| `gh pr create` | Open a PR for a non-main branch |
| `gh pr view <num>` | Read a PR's metadata / status |
| `gh pr checks <num> --watch` | Watch CI to completion |
| `gh pr merge <num> --squash --delete-branch` | Squash-merge after CI green |
| `gh pr list --state open` | Operator-visible queue |
| `gh api repos/roudjy/trading-agent/...` | Read-only metadata only |

## Forbidden GitHub CLI surface

These are governance-level boundaries, not just style preferences:

- `gh pr merge --admin` — bypasses branch protection. **PERMANENTLY_DENIED**.
- `gh pr merge --merge` / `--rebase` — squash is the only allowed merge
  strategy in this repo.
- Direct push to `main` (no `gh push --branch main` either; use the PR
  flow).
- Force push to **any** branch (`gh ... --force` / `git push --force`).
- Token scraping / credential extraction — see "Credentials" below.
- Editing `.github/branch_protection_*.yml` — `PERMANENTLY_DENIED`.
- Editing `.github/workflows/**` from a generic agent — `NEEDS_HUMAN`
  (only the `ci-guardian` agent may propose workflow edits, and only
  in a dedicated CI-hardening task).

## Credentials

- **Do not** extract credentials from the OS credential manager.
- **Do not** read `~/.gitconfig` / `~/.ssh/` for tokens.
- **Do not** call `git credential fill` to harvest tokens for
  programmatic auth.
- **Do not** run any `gh` subcommand whose purpose is to display the
  raw token (`gh auth token` is acceptable to confirm a token exists,
  but the value must never be echoed to chat or written to a file).
- If `gh auth status` fails, stop and ask the operator to re-run
  `gh auth login` interactively.

## End-to-end PR flow (canonical)

```bash
# 0. Confirm working tree clean and on a feature branch.
git status
git branch --show-current   # must NOT be main

# 1. Preflight.
GH="/c/Users/joery.van.rooij/tools/gh/bin/gh.exe"
"$GH" auth status
"$GH" repo view roudjy/trading-agent

# 2. Push the feature branch.
git push -u origin "$(git branch --show-current)"

# 3. Open the PR.
"$GH" pr create --base main \
  --head "$(git branch --show-current)" \
  --title "<concise feat/fix/chore title>" \
  --body "$(cat <<'EOF'
## Summary
...
EOF
)"

# 4. Watch CI to completion.
PR=<number>
"$GH" pr checks "$PR" --watch --interval 20

# 5. Confirm mergeability.
"$GH" pr view "$PR" --json mergeStateStatus,mergeable,reviewDecision

# 6. Squash-merge and delete the branch (only if mergeable + CLEAN).
"$GH" pr merge "$PR" --squash --delete-branch

# 7. Sync local main and run post-merge gates.
git checkout main
git pull --ff-only origin main
python scripts/governance_lint.py
python -m pytest tests/smoke -q
# Plus any feature-specific targeted tests.

# 8. Record the merge SHA in the relevant roadmap / governance doc.
git log --oneline -1
```

## Branch protection invariants (mandatory)

- **No direct push to main.** Always go through a PR.
- **No `--no-verify`.** Pre-commit and pre-push hooks run on every
  commit and push.
- **No force push** to any branch.
- **No CI weakening.** Skipping or relaxing checks requires an
  operator-authored governance PR.
- **Squash-merge only.** This keeps the main history linear and
  audit-friendly.
- **Delete branch on merge.** Stale branches are removed by
  `--delete-branch` on merge.

## Post-merge verification (mandatory after every merge)

After `gh pr merge ... --squash --delete-branch` succeeds:

1. `git checkout main && git pull --ff-only origin main`.
2. `python scripts/governance_lint.py` — must end with `OK`.
3. `python -m pytest tests/smoke -q` — must end with `passed`.
4. If the PR added/changed unit tests, run them locally on `main`.
5. Confirm diff scope by inspecting `git show --stat <merge_sha>`:
   - **No** changes under `research/**` (frozen contracts, IR
     artifacts, scoring).
   - **No** changes under `automation/`, `broker/`, `agent/risk/`,
     `agent/execution/`, `live/`, `paper/`, `shadow/`, `trading/`.
   - **No** changes under `dashboard/dashboard.py`.
   - **No** changes under `.claude/**` unless the PR was an
     operator-authored governance-bootstrap PR (separate flow).
   - **No** changes under `.github/workflows/**` unless the PR was a
     `ci-guardian` CI-hardening PR.
6. Update the roadmap entry that drove the work, recording:
   - PR number;
   - merge SHA;
   - CI: green;
   - post-merge gates: green;
   - status: `Complete` (only after every box ticks).

## Failure modes and recovery

| Symptom | Recovery |
|---|---|
| `gh: command not found` on PATH | Use the explicit portable path above. |
| `gh auth status` fails | Stop. Instruct operator to run `gh auth login` (browser flow). Do not attempt programmatic auth. |
| PR `mergeStateStatus=BLOCKED` after CI green | Investigate (review required, branch out of date, etc.). Do **not** force or admin-merge. |
| CI fails | Diagnose the root cause; fix on the same feature branch with a new commit. Do not skip hooks or weaken tests. |
| Merge succeeds but post-merge gates fail | Stop. Open a follow-up branch + PR with the fix. Do not flip the roadmap entry to `Complete` until the fix lands. |
| Diff scope inspection finds a protected-path change | Treat as a governance incident. Open a `revert` branch + PR; do not flip the roadmap entry to `Complete`. |

## Relationship to Execution Authority

The Execution Authority classifier
(`reporting.execution_authority.classify`) gates **what** Claude may
do; this protocol gates **how** Claude does it once an action is
authorised. The relevant action types are:

- `branch_create` (auto-allowed)
- `commit_create` (auto-allowed when every touched path is auto-allowed)
- `branch_push` (auto-allowed under the same composite rule)
- `pr_open` (auto-allowed under the same composite rule)
- `pr_squash_merge` (auto-allowed when CI is green and every touched
  path was auto-allowed)
- `pr_force_push` — `PERMANENTLY_DENIED`
- `main_direct_push` — `PERMANENTLY_DENIED`
- `branch_protection_bypass` — `PERMANENTLY_DENIED`

Any operator-authored PR (e.g. canonical_policy_doc / canonical_roadmap
edit) follows the same flow — the operator opens / approves; the agent
may still run preflight, watch CI, and run post-merge gates.

## Update history

- 2026-05-07: initial version, written alongside the A8 PR (#132)
  squash-merge (SHA `09bb439`).
