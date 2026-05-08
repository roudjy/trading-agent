# Markdown Modernization — Operator Handoff (2026-05-08)

> Hand-off document for the operator-authored portion of the
> `docs/markdown-modernization-cleanup` work. Records the exact
> agent-allowlist hook outcomes, the in-scope edits already landed,
> and the precise patch text the operator can paste verbatim into
> the three root-level files that the agent layer is correctly
> blocked from editing (`CLAUDE.md`, `AGENTS.md`, `INSTALLATIEGIDS.md`).
>
> This document is itself docs-only and lands inside the agent-
> writable surface. It does **not** authorise any other change, does
> **not** flip any flag, and does **not** modify QRE behavior.

## Status

`operator_handoff_pending`. Agent-side cleanup (this PR) covers two
files. Three root-level files require an operator-authored governance-
bootstrap PR.

## Audit metadata

- **handoff_date_utc**: 2026-05-08
- **branch**: `docs/markdown-modernization-cleanup`
- **base**: `main @ 89dac05` (post-PR #148 Step 5 design)
- **predecessors**: PR #146 audit, PR #147 readiness review, PR #148 Step 5 design.
- **trigger**: operator request to land the smallest safe governance-bootstrap docs cleanup PR.

## Hook probe — confirmed blocked targets (per `deny_outside_agent_allowlist.py`)

The following Edit attempts were issued from the main session against
`main @ 89dac05` and **denied** by the hook layer. The denial messages
are reproduced verbatim so the operator can verify the constraint is
real and binding, not a self-reported claim.

```
Target:   C:\Users\joery.van.rooij\trading-agent\CLAUDE.md
Hook:     .claude/hooks/deny_outside_agent_allowlist.py
Outcome:  DENIED
Reason:   outside_agent_allowlist: target
          'C:\\Users\\joery.van.rooij\\trading-agent\\CLAUDE.md'
          (normalized: 'claude.md') is not under any agent's
          allowed_roots. If a legitimate agent should be writing
          here, add the path to that agent's frontmatter via a
          governance-bootstrap PR.
```

```
Target:   C:\Users\joery.van.rooij\trading-agent\AGENTS.md
Hook:     .claude/hooks/deny_outside_agent_allowlist.py
Outcome:  DENIED
Reason:   outside_agent_allowlist: target
          'C:\\Users\\joery.van.rooij\\trading-agent\\AGENTS.md'
          (normalized: 'agents.md') is not under any agent's
          allowed_roots.
```

```
Target:   C:\Users\joery.van.rooij\trading-agent\INSTALLATIEGIDS.md
Hook:     .claude/hooks/deny_outside_agent_allowlist.py
Outcome:  DENIED
Reason:   outside_agent_allowlist: target
          'C:\\Users\\joery.van.rooij\\trading-agent\\INSTALLATIEGIDS.md'
          (normalized: 'installatiegids.md') is not under any agent's
          allowed_roots.
```

The denial is correct behavior. Per `docs/governance/agent_governance.md`
and ADR-015 §Doctrine 2 ("No-touch path doctrine") + the Revision-5
default-deny union semantics, root-level human-facing docs must come
through an operator-authored governance-bootstrap PR. The audit in
PR #146 already flagged this constraint; this handoff makes it
operationally actionable.

## What this PR landed (agent-side, docs-only)

Two in-scope files modernized inside this PR:

### A. `docs/RESEARCH_CONTEXT.md`

Added a top "Status: historical / superseded" header that:

- Removes the misleading `# CLAUDE.md` mismatched title (retitled to "RESEARCH CONTEXT (historical pre-v3.15 note)").
- Marks the strategy-family verdicts (`mean_reversion ❌`, etc.) as historical and not authoritative.
- Points readers at the canonical authorities: `research/registry.py`, `research/strategy_hypothesis_catalog.py`, ADR-014, `research/authority_views.py`, Roadmap v6.
- Wraps the original content under a `## Historical content (pre-v3.15)` section so inbound links do not 404.

No content was deleted.

### B. `docs/governance/frontend_agent_control_layer_roadmap.md`

Added a top "Status: paused / historical" stamp that:

- States the v3.15.15.17 → .23 frontend control-layer sequence is paused after ADE A1–A13 and Step 5 design.
- Explicitly notes that none of the dashboard surfaces below have been implemented in production.
- Cross-references the Step 5 design doc and the documentation audit.

No body content was changed.

## Operator-authored portion (separate governance-bootstrap PR)

The three root-level files (`CLAUDE.md`, `AGENTS.md`, `INSTALLATIEGIDS.md`)
remain on `main` exactly as they were before this PR. The operator
should land the patches below in a follow-up governance-bootstrap PR.
Suggested branch name:

```
docs/operator-root-doc-modernization
```

Class: `canonical_policy_doc` (touches `CLAUDE.md` / `AGENTS.md`).
Reviewer: CODEOWNERS.

The patches are intentionally minimal — they correct the most
load-bearing inaccuracies (stale roles, missing pointers, missing
QRE/ADE split, missing Step 5 status) without rewriting the files.

### Patch 1 — `CLAUDE.md`

Insert the following block immediately after the existing line:

```
Authority doctrine: `docs/adr/ADR-014-truth-authority-settlement.md` …
```

(currently line 10 in `CLAUDE.md`).

```markdown

Agent governance doctrine: `docs/adr/ADR-015-claude-agent-governance.md`
— authority chain for Claude / agent code-modification capability
(no-touch paths, autonomy ladder L0–L6, audit ledger). Level 6
(autonomous merge / deploy) is permanently disabled.

Session-start protocol for any branch → PR → CI → squash-merge →
post-merge work: `docs/governance/github_pr_lifecycle.md`.
GitHub CLI portable: `C:\Users\joery.van.rooij\tools\gh\bin\gh.exe`.
No `--admin` merges, no force push, no direct push to `main`, no
hook bypass, no test weakening, no `.claude/**` writes.

Project split:

- **QRE** (Quant Research Engine) — research execution platform
  under `research/`. Roadmap: `docs/roadmap/Roadmap v6.md`.
- **ADE** (Autonomous Development Engine) — governance + work queue
  + release gate + bugfix loop + delegation + operational digest +
  E2E proof under `reporting/development_*.py`. Roadmap:
  `docs/roadmap/autonomous_development.txt`.

ADE A1–A13 are complete. Step 5 design is complete
(`docs/governance/step5_design.md`,
`docs/adr/_drafts/ADR-017-step5-autonomous-implementation-loop.md`).
**Step 5 implementation remains blocked** behind explicit operator
authorisation, the autonomy-ladder ceiling, and the readiness gate
(`docs/governance/step5_design.md` §12).

Allowed surfaces and forbidden surfaces are listed in
`docs/governance/no_touch_paths.md`. Per-action authority decisions
follow `docs/governance/execution_authority.md`. Autonomy levels
follow `docs/governance/autonomy_ladder.md`.
```

Then, optionally, demote the existing 30-day "Dag 1-30" roadmap
(lines 344–438 in the current file) by inserting a single line
**immediately before** that block:

```markdown

## Historical (pre-v3.15) — superseded by Roadmap v6 + autonomous_development.txt
```

Do not delete the historical block. The cross-link from
`docs/governance/documentation_audit.md` AB-0008 should still
resolve.

### Patch 2 — `AGENTS.md`

Replace §4 ("AI Tooling Roles" — currently the "Claude / Codex CLI /
Claude Code" three-actor model) with the following pointer block.
The replacement is shorter than the original and more accurate:

```markdown
## 4. Agent roles and authority

Agent role separation has moved from the original "Claude / Codex CLI
/ Claude Code" three-actor model to the v3.15.15.12 governance layer's
sixteen-role model, plus the eight canonical handoff roles defined in
`reporting.roadmap_execution_protocol`. The full mapping lives in:

- `docs/governance/agent_handoff_protocol.md` — eight canonical
  handoff roles (product_owner, strategic_advisor, planner,
  implementation_agent, architecture_guardian, ci_guardian,
  security/governance_guardian, human_operator).
- `docs/governance/autonomy_ladder.md` — six autonomy levels (L0–L6).
  Level 6 is permanently disabled.
- `docs/adr/ADR-015-claude-agent-governance.md` — authority chain.
- `.claude/agents/` — per-agent frontmatter with `allowed_roots`,
  `tools`, and `max_autonomy_level`.

Agent capability is bounded at every layer (policy, hooks,
CODEOWNERS, branch protection). No agent role overrides
`reporting.execution_authority.classify(...)`. Step 5 design (the
future autonomous implementation loop) is documented in
`docs/governance/step5_design.md` and remains implementation-blocked.

The original "Claude / Codex CLI / Claude Code" three-actor model is
**superseded** and should not be cited as current. Cross-reference
`docs/governance/agent_governance.md` for the public-facing overview.
```

Replace §5 ("Execution Workflow") with:

```markdown
## 5. Execution workflow

The canonical execution workflow is defined in:

- `docs/governance/roadmap_item_execution_protocol.md` — protocol
  per roadmap item.
- `docs/governance/agent_flow.md` — closed `next_action_proposed`
  vocabulary.
- `docs/governance/task_board.md` — read-only state-machine
  projection.
- `docs/governance/github_pr_lifecycle.md` — branch → PR → CI →
  squash-merge → post-merge protocol.

No agent may bypass `reporting.execution_authority.classify(...)`
or skip the GitHub PR lifecycle. The previous prose ("Claude
designs → Codex implements → Human validates") is superseded.
```

Replace §11 ("Git Workflow") with:

```markdown
## 11. Git workflow

Canonical: `docs/governance/github_pr_lifecycle.md`.

- Never commit directly to `main`.
- Branch naming: `feature/`, `feat/`, `fix/`, `chore/`, `docs/`,
  `refactor/` per the existing repo convention.
- Merge strategy: squash-merge only (`gh pr merge --squash
  --delete-branch`).
- No `--admin` merge.
- No force push.
- No hook bypass (`--no-verify`, `--no-gpg-sign`, etc.).
- Pre-commit and pre-push hooks run on every commit and push.
- CI must be green before merge; post-merge gates must pass before
  a roadmap entry is flipped to `Complete`.

The GitHub CLI portable lives at
`C:\Users\joery.van.rooij\tools\gh\bin\gh.exe`. Absence of `gh` on
PATH is **never** justification to fall back to manual PRs.
```

Keep §3 (Source of Truth + ADR-014 cross-ref) unchanged. Keep all
other sections unchanged unless a future cleanup phase explicitly
covers them.

### Patch 3 — `INSTALLATIEGIDS.md`

Append the following note to the bottom of §STAP 7 ("Paper trading
fase"), just before the existing horizontal rule:

```markdown

> **Current paper-readiness criteria** are now defined by the
> v3.15+ paper-validation engine, not by the simple `win-rate >55%
> over 50 trades` threshold above. The full closed-vocabulary
> readiness gate is documented in:
>
> - `research/paper_readiness.py` — closed blocking-reason taxonomy.
> - `docs/handoffs/v3.15-to-v3.16.md` §2 — narrative summary.
>
> The threshold above is kept as a simple human-readable signpost;
> the authoritative criteria are the ones in the paper-readiness
> gate. Treat the section above as the "comfort milestone", not the
> live-trading authorisation gate.
```

No other changes are required to `INSTALLATIEGIDS.md` for the
modernization scope. A full rewrite is **not** in scope and is
**not** required.

## Validation expected after the operator PR lands

- `python scripts/governance_lint.py` — `OK`.
- `python -m pytest tests/smoke -q` — `18 passed`.
- Diff scope: only `CLAUDE.md`, `AGENTS.md`, `INSTALLATIEGIDS.md` touched.
- No changes under `research/`, `automation/`, `broker/`, `agent/risk/`, `agent/execution/`, `live/`, `paper/`, `shadow/`, `trading/`, `dashboard/dashboard.py`, `.claude/**`, `.github/workflows/**`, `tests/regression/**`.
- No flag changes: `step5_implementation_allowed` stays `false`; autonomy-ladder Level 6 stays permanently disabled.
- No canonical_roadmap edits.
- No ADR promotion.

## Why this two-step (agent + operator) is the correct minimum

The hook layer is doing exactly the job ADR-015 §Doctrine 2 asks of
it: top-level human-facing docs (`CLAUDE.md`, `AGENTS.md`) cannot be
edited by an autonomous agent. The right response to the hook denial
is **not** to add the path to an agent's `allowed_roots` (that would
require a `governance-bootstrap` PR all by itself, plus weakening the
default-deny posture), but to author the patch as a small, scoped,
human-authored governance-bootstrap PR that the operator merges
directly. This is the smallest safe sequence.

A single follow-up PR covering all three root files is the minimum
operator workload. The patches above are short enough to apply by
hand in under 10 minutes.

## What this PR does **not** do

- **No** edit to `CLAUDE.md`, `AGENTS.md`, `INSTALLATIEGIDS.md` (correctly blocked by the hook layer).
- **No** edit to `.claude/**`.
- **No** edit to canonical_roadmap (`docs/roadmap/autonomous_development.txt`, `docs/roadmap/Roadmap v6.md`).
- **No** ADR promotion (ADR-017 stays in `_drafts/`).
- **No** Step 5 implementation, no flag flipping, no QRE behavior change.
- **No** start of v3.15.17 / v3.15.16 / Intelligent Routing.
- **No** research artifact mutation.
- **No** test weakening.
- **No** CI workflow change.
- **No** branch-protection change.
- **No** security-policy change.

## End of handoff
