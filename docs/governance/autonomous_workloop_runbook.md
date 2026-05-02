# Autonomous Workloop — Operator Runbook

`reporting.autonomous_workloop` (v3.15.15.16) is the local-state
planner. It classifies open PRs, Dependabot bumps, and roadmap items;
runs local gates; emits a digest pair (markdown + JSON). It does
**not** call GitHub, push to `main`, merge anything, or recommend
`safe_to_merge` in this release.

## Quickstart

```sh
# Default — dry-run, prints JSON to stdout, writes nothing.
python -m reporting.autonomous_workloop

# Same, but write the digest pair to disk.
python -m reporting.autonomous_workloop --mode execute-safe

# View the most recent digest as markdown:
cat docs/governance/autonomous_workloop/latest.md

# Or as JSON (frontend-consumable):
cat logs/autonomous_workloop/latest.json | jq .next_recommended_item
```

## Modes

| mode | reads | writes | runs gates? | side effects |
|---|---|---|---|---|
| `plan` | git read-only, roadmap docs | nothing | no | none |
| `dry-run` *(default)* | git read-only, roadmap docs, ledger | nothing | no | none |
| `execute-safe` | same as dry-run | digest pair | no (yet) | digest files only |
| `continuous --max-cycles N` | same | digest pair, N times | no | digest files only |
| `digest` | minimal | digest pair | no | digest files only |

> v3.15.15.16 keeps `execute-safe` deliberately narrow: the only
> mutation is writing the digest pair. Test/gate runs and any future
> branch-creation are gated on later releases (v3.15.15.21
> dashboard execute-safe controls).

## What you read first

The digest's **`next_recommended_item`** field tells you what to look
at next. It is `"unknown"` if nothing is ready.

The **`pr_queue`** table lists every open feature branch, classified.
For each row check `risk_class`, then `decision`, then `next_action`.

The **`dependabot_queue`** is separated. Every row in v3.15.15.16
classifies as one of:

* `dependabot_patch_safe_candidate` / `dependabot_minor_safe_candidate`
  — operator confirms green checks before clicking merge;
* `dependabot_major_framework_risk` — needs a compatibility branch
  and an upgrade plan; never auto-merge;
* `unknown` — branch shape unparseable.

The **`roadmap_queue`** is recommendation-only. The controller never
opens a roadmap implementation branch by itself.

## What `risk_class` means

See the schema at
[`schema.v1.md`](autonomous_workloop/schema.v1.md). The most important
points:

* **`safe_to_merge` is reserved but unreachable in v3.15.15.16.**
  No code path produces this label until external check evidence is
  available (v3.15.15.19 / .23).
* `waiting_for_checks` means the diff is clean but the controller
  cannot confirm CI status from `git` alone.
* `needs_human_*` is always operator-driven. The reason field tells
  you which dimension was tripped (governance / contract / trading).
* `blocked_*` blocks the merge until the underlying problem is fixed.

## When to escalate

| signal | action |
|---|---|
| `audit_chain_status: broken` | Stop and run `python -m reporting.agent_audit verify logs/agent_audit.<UTC>.jsonl`. Investigate the first corrupt index. |
| `governance_lint_passed: false` | Run `python scripts/governance_lint.py` directly and read the violation list. |
| `frozen_contracts.<...>.sha256` differs from your last digest | A frozen v1 contract changed. This is *always* a needs-human event; investigate the regen path. |
| `next_recommended_item: unknown` | All open work is blocked or needs human; nothing is ready to pick up. |

## What the controller cannot do (hard guarantees)

1. **No `git push origin main`.** Doctrine 8.
2. **No `gh pr merge` / `gh pr create`.** No GitHub API. No PAT.
3. **No `safe_to_merge` recommendation.** This release reserves the
   label but never emits it.
4. **No write to `.claude/**`, `automation/**`, `execution/**`,
   `orchestration/**`, `research/**`, `strategies/**`, `agent/**`,
   frozen contracts, or `VERSION`.**
5. **No `unknown` treated as `ok`.** Any field that should report
   green but cannot be confirmed reports `unknown` or
   `not_available` instead.

## The 10 final-report statements (always present)

The controller embeds these verbatim in every digest's
`limitations[]`:

1. v3.15.15.16 is not full PR automation.
2. gh / API not available — checks/mergeability are `not_available`.
3. `merges_performed`: 0.
4. Operator-click merge is still required.
5. Roadmap execution is recommendation-only.
6. Dependabot safe candidates are not safe to merge without green
   checks.
7. Writer-level subagent attribution is gated by ADR-016 bootstrap.
8. Inferred attribution is convenience-only, not source-of-truth.
9. Next technical milestone for true autonomy is GitHub-backed
   PR/check integration (v3.15.15.19).
10. Frontend should consume JSON artifacts, not markdown.

## Where it fits

| Release | Layer |
|---|---|
| v3.15.15.13 | governance status snapshot |
| v3.15.15.14 | operator-friendly audit summary |
| v3.15.15.15 | inferred subagent attribution + ADR-016 proposal |
| **v3.15.15.16** | **local workloop planner (this runbook)** |
| **v3.15.15.17** | **GitHub-backed PR lifecycle + Dependabot cleanup playbook (`reporting.github_pr_lifecycle`)** — pulled forward from the original v3.15.15.19 slot after a 10/10 pilot. Read-only by default; `execute-safe` mode comments `@dependabot rebase` and squash-merges LOW/MEDIUM Dependabot PRs only. HIGH stays inspect-only. |
| **v3.15.15.18** | **Mobile-first read-only Agent Control PWA** (`dashboard.api_agent_control` + `frontend/src/routes/AgentControl.tsx`). Five cards backed by existing reporters / artifacts; installable; service-worker offline-capable; no execute / approve / merge buttons in the rendered DOM. See [`mobile_agent_control_pwa.md`](mobile_agent_control_pwa.md). |
| v3.15.15.19 | roadmap queue + agent proposal intake (was vacated; reclaimed) |
| v3.15.15.20 | operator approval & exception inbox |
| v3.15.15.21 | dashboard execute-safe controls |
| v3.15.15.22 | long-running runtime |
| v3.15.15.23 | safe PR automerge (HIGH unlocks behind formalized rules) + browser push notifications for needs-human events only |

See the canonical roadmap at
[`frontend_agent_control_layer_roadmap.md`](frontend_agent_control_layer_roadmap.md).

## Sibling: GitHub PR Lifecycle (v3.15.15.17)

`reporting.autonomous_workloop` (this module) is read-only and does
not call GitHub. Its sibling `reporting.github_pr_lifecycle` is the
GitHub-backed module that codifies the v3.15.15.17 Dependabot
cleanup pilot. Use the autonomous workloop for local-state planning
and the lifecycle module for any cycle that touches GitHub.

* Architecture: [`github_pr_lifecycle_integration.md`](github_pr_lifecycle_integration.md)
* Operator runbook: [`dependabot_cleanup_playbook.md`](dependabot_cleanup_playbook.md)
* JSON schema: [`github_pr_lifecycle/schema.v1.md`](github_pr_lifecycle/schema.v1.md)

Both modules share governance constants (frozen contracts, no-touch
globs, live-trading globs) but do not import each other. JSON
artifacts are independent and can be consumed side-by-side by a
future dashboard.
