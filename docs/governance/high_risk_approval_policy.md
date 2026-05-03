# High-Risk Approval Policy — operator runbook

Module: `reporting.approval_policy`
Version: v3.15.15.24
Schema: `docs/governance/high_risk_approval_policy/schema.v1.md`

## TL;DR

Every governance / lifecycle module in the repository imports a
single shared decision function: `approval_policy.decide()`.
That function is pure, deterministic, and stdlib-only. It returns
one of 14 decisions; only ONE of those decisions
(`allowed_low_risk_execute_safe`) can ever carry `executable=true`.

If you came here because you saw a `blocked_*` decision in an inbox
row or a status payload — this document explains what that means
and what action is appropriate.

## Hard guarantees

The policy enforces, by construction:

* `UNKNOWN` is never executable.
* `HIGH` is never executable.
* Frozen contract change overrides LOW / MEDIUM.
* Protected path change overrides LOW / MEDIUM.
* Live / paper / shadow / risk path change overrides LOW / MEDIUM.
* CI / test path change overrides LOW / MEDIUM.
* Governance change is always HIGH.
* Canonical roadmap adoption is always HIGH and routes to the
  operator.
* External account / secret / OAuth / API-key / signup is always
  HIGH.
* Telemetry / data egress is always HIGH.
* Paid plan / hosted SaaS is always HIGH.
* Malformed provider / pending checks / unknown mergeability route
  to UNKNOWN, never LOW.
* Non-Dependabot execute-safe routes to `needs_human`.
* Even Dependabot LOW/MEDIUM execute-safe needs CLEAN merge state
  AND all checks `passed`.

## What agents may do automatically

The agent layer may, without operator approval:

* Read repository state.
* Run read-only reporters (proposal_queue, approval_inbox,
  github_pr_lifecycle dry-run, workloop_runtime,
  recurring_maintenance).
* Surface status payloads on the read-only PWA.
* Refresh upstream artifacts via the supervised reporter chain.
* For **Dependabot LOW/MEDIUM PRs only**, when ALL of the
  following are true:
  * The PR base is `main`.
  * The PR is not a draft.
  * The PR diff does not touch any protected/frozen/live/CI path.
  * The merge state is `CLEAN`.
  * Every required check is `passed`.
  * The state-file flag for `dependabot_low_medium_execute_safe`
    is `enabled=true`.
  * The runtime CLI flag `--enable-dependabot-execute-safe` is
    present.
  the agent may post `@dependabot rebase` and / or perform a
  squash-merge through the supervised
  `reporting.github_pr_lifecycle` flow.

## What agents may only propose

The agent layer may *propose* (write a row to the queue / inbox,
never act) for:

* New tooling / dependencies.
* New observability / testing / UX gaps.
* Scoped release candidates.
* Roadmap diffs (not adoptions — see below).

These are surfaced as `allowed_read_only` rows in the inbox; the
operator reviews and authors any follow-up PR by hand.

## What agents must block

Any of the following inputs route to a `blocked_*` decision and
the agent layer refuses to act, even if every other gate is green:

* `.claude/**` change.
* `AGENTS.md` / `CLAUDE.md` change.
* `.github/CODEOWNERS` change.
* `VERSION` change.
* Frozen contract regen
  (`research/research_latest.json` /
   `research/strategy_matrix.csv`).
* Live / paper / shadow / risk path change
  (`execution/**`, `automation/**`, `agent/risk/**`, etc.).
* CI / test path change
  (`.github/workflows/**`, `tests/regression/**`,
   `scripts/governance_lint.py`, `scripts/release_gate.py`).
* Branch-protection bypass.
* Force push.
* Direct push to `main`.
* `gh pr merge --admin`.
* Arbitrary command execution / `shell=True` / free-form argv.
* Secrets / API keys / OAuth / SSO / account linking.
* Paid tiers / hosted SaaS / subscriptions.
* External telemetry / data egress.
* Canonical roadmap adoption / supersession.
* Governance weakening of any kind.
* Unknown provider / check state.
* Malformed provider output.
* HIGH-risk PR.
* Non-Dependabot PR being asked to execute-safe.
* Protected-path PR.
* Pending / failing / unknown checks.

## What requires Joery approval

Anything in the "must block" list above plus:

* Any `needs_human` decision (e.g. a non-Dependabot author asking
  for execute-safe).
* Any `tooling_intake` HIGH proposal (Datadog, Sentry, etc.).
* Any roadmap adoption proposal.
* Any release candidate that the operator has not pre-approved.
* Any change to the policy module itself
  (`reporting/approval_policy.py`).
* Any change to this runbook or to `schema.v1.md`.

## Examples of HIGH

* "Bump numpy from 1.24.0 to 2.0.0" — major bump on a numerical
  dep -> HIGH.
* "Add Datadog APM with API key auth" — telemetry + secret -> HIGH.
* "Rewrite roadmap to v4 canonical plan" — canonical roadmap
  adoption -> HIGH.
* "Modify .github/workflows/ci.yml to skip slow tests" — CI
  weakening -> HIGH.
* "Update execution/live/broker_kraken.py timeout" — live trading
  path -> HIGH.
* "Edit .claude/settings.json to add new agent allowlist" —
  governance / protected -> HIGH.

## Examples of UNKNOWN

* `gh pr list` returns malformed JSON -> UNKNOWN.
* A required check is still pending -> UNKNOWN.
* Mergeability state reports as `BEHIND` (or empty / unknown) ->
  UNKNOWN.
* A proposal source file is unparseable -> UNKNOWN.

UNKNOWN never silently softens to LOW. The agent surfaces the
`unknown_state` inbox category and waits.

## Why HIGH is read-only / proposal-only

The trading agent operates with a 50% drawdown ceiling and a
financial-result-as-consequence principle (see `CLAUDE.md`). A
HIGH-risk action — by definition — has scope to change live
behavior, lose audit-chain integrity, weaken the test net, or
exfiltrate data. Auto-executing any of those would mean the agent
chose to spend operator trust without operator consent.

The policy makes that decision impossible at the function-call
level rather than the review level.

## Cross-references

* Schema: `docs/governance/high_risk_approval_policy/schema.v1.md`
* Proposal queue: `docs/governance/proposal_queue.md`
* Approval inbox: `docs/governance/approval_inbox.md`
* GitHub PR lifecycle: `docs/governance/github_pr_lifecycle.md`
* Execute-safe controls: `docs/governance/execute_safe_controls.md`
* Recurring maintenance:
  `docs/governance/recurring_maintenance.md`
* No-touch paths: `docs/governance/no_touch_paths.md`
* Authority doctrine:
  `docs/adr/ADR-014-truth-authority-settlement.md`

## Governance footnote

This policy is itself a governance surface. Changing
`reporting/approval_policy.py`, `schema.v1.md`, or this runbook is
a `blocked_governance_change` per its own rules. The only way to
modify the policy is via a human-authored PR with CODEOWNERS
review.
