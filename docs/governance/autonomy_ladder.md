# Autonomy Ladder

The agent permission system declares six numbered levels of capability.
Every agent in `.claude/agents/` declares a `max_autonomy_level` in its
frontmatter; a session can never exceed that cap.

This document is the operative source. ADR-015 §Doctrine 1 is the
architectural mirror.

---

## Levels

| Level | Capability | Status in this project |
|---|---|---|
| 0 | **Plan / read only**. Agent reads, plans, asks. No writes. | Always available |
| 1 | **Docs + tests + frontend**. Writes inside `docs/` (excl. `docs/governance/**` and `docs/adr/ADR-*.md`), `tests/{smoke,unit,integration,resilience,functional}/`, `frontend/`. | Available after v3.15.15.12.3 active (this PR) |
| 2 | **Observability + CI**. Writes inside `reporting/`, `dashboard/api_observability.py`, `.github/workflows/**` (only via `ci-hardening` task with operator approval per change). | Available after v3.15.15.12.4 active |
| 3 | **Backend non-core**. Writes inside `dashboard/` (excl. observability core), `agent/agents/<non-core>` — allowlist-only, never denylist. | **NOT enabled** in this version. Re-evaluated per ADR amendment. |
| 4 | **Merge recommendation**. Agent recommends merge; human merges. | Locked. Requires ≥30 days L1–3 stable + ADR-015 amendment. |
| 5 | **Deploy recommendation**. Agent recommends deploy; human deploys. | Locked. Requires ≥60 days L1–4 stable + ADR-015 amendment. |
| 6 | **Autonomous merge / deploy**. | **Permanently disabled** in this project. |

## Why Level 6 stays disabled

Live-trading risk is asymmetric: an unwanted merge or deploy can lose
real money in real time. The cost of keeping a human in the loop is
small (a click); the cost of removing them is unbounded. Level 6 is
not a matter of "when we're stable enough"; it is a matter of "what
risk profile this project will tolerate", and the answer is documented
as "never".

ADR-015 §Forward-looking amend triggers explicitly states: an
amendment proposing Level 6 must be merged by humans deliberately
overriding the release-gate-agent's auto-block recommendation.

## Per-agent caps (current)

| Agent | Cap |
|---|---|
| product-owner | 1 |
| strategic-advisor | 0 |
| quant-research-architect | 0 |
| planner | 1 |
| architecture-guardian | 0 |
| ci-guardian | 2 |
| implementation-agent | 3 (not enabled until L3 opens) |
| frontend-agent | 1 |
| test-agent | 1 |
| determinism-guardian | 0 |
| evidence-verifier | 0 |
| observability-guardian | 2 |
| deployment-safety-agent | 0 |
| adversarial-reviewer | 0 |
| release-gate-agent | 0 |

The cap is enforced by the agent's own frontmatter and by reviewer
discipline; no per-action runtime check exists today. A future hook
may compute this from frontmatter at PreToolUse time.

## Unlocking Level 4 / 5

Each unlock is a separate ADR amendment that must:

1. Cite at least 30 (L4) or 60 (L5) consecutive days of clean operation
   at the level below.
2. Include zero unresolved governance regressions in
   `docs/backlog/agent_backlog.md` for the relevant period.
3. Include a fresh rollback drill (digest-based) within the prior 14 days.
4. Include CODEOWNERS approval and an updated forward-looking amend
   trigger entry.

Once Level 4 is enabled, the release-gate-agent may emit
`merge: recommend yes` on PRs that meet its checklist, but humans still
merge. Level 5 raises that to deploy-recommendation; humans still deploy.
