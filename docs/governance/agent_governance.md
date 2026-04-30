# Agent Governance — Public Overview

This document is the public-facing summary of the Claude Agent
Governance & Safety Layer introduced in v3.15.15.12. New contributors
read this first, then the linked specs.

## What this layer is

A layered set of constraints — policy, hooks, CODEOWNERS, branch
protection, and ADR-015 — that bounds what Claude agents may do in
this repository. The constraints exist because this is a deterministic
Quant Research Engine with frozen v1 schemas, byte-stable replay, and
a single live-trading barrier (`automation/live_gate.py`). A confused
agent must not be able to drift those invariants.

## What it is NOT

- A replacement for code review.
- A blanket allow-list for autonomous merging or deploying — those are
  permanently human-only (see ADR-015 §authority chain).
- A perfect line of defense; it is *one* of several lines.

## Map of the layer

| Layer | Source | Enforced by |
|---|---|---|
| Project policy | [`.claude/settings.json`](../../.claude/settings.json) | Claude Code `permissions.{allow,ask,deny}` |
| Per-agent allowlists | [`.claude/agents/`](../../.claude/agents/) | Frontmatter `allowed_roots`, `tools`, `max_autonomy_level` |
| Hooks (fail-closed) | [`.claude/hooks/`](../../.claude/hooks/) | Python scripts, deny on any exception/timeout |
| Code ownership | [`.github/CODEOWNERS`](../../.github/CODEOWNERS) | Branch protection ("Require review from Code Owners") |
| Branch protection | GitHub UI | Manual operator setup; checklist in [`branch_protection_checklist.md`](branch_protection_checklist.md) |
| Architectural authority | [`docs/adr/ADR-015`](../adr/ADR-015-claude-agent-governance.md) | Reviewer responsibility |

## Autonomy ladder

See [`autonomy_ladder.md`](autonomy_ladder.md). Six levels (0–6); only
0–3 are operationally available in v3.15.15.12. Levels 4–5 require
explicit ADR amendments and stability windows. Level 6 is permanently
disabled.

## Audit, evidence, provenance

- Runtime audit ledger: `logs/agent_audit.<UTC date>.jsonl`
  (gitignored; hash-chained; daily-rotated). See
  [`audit_chain.md`](audit_chain.md).
- Per-PR redacted summary: `docs/governance/agent_run_summaries/<session_id>.md`
  (committed). The bridge between the runtime ledger and Git history.
- Build provenance: `artifacts/build_provenance-<version>.json`
  (gitignored runtime; schema in
  `artifacts/build_provenance.schema.json` is committed). See
  [`provenance.md`](provenance.md).

## Doctrines

The full set lives in ADR-015. The shortest list:

- **Live trading code is human-only.** Always. No agent merges,
  deploys, or creates broker/connector files.
- **Frozen schemas, pins, and digests are read-only for agents.**
  Drift is reported, never fixed.
- **Hooks are self-protected.** They cannot be loosened by an agent
  at runtime — only via human-authored CODEOWNERS-reviewed
  governance-bootstrap PRs.
- **No test weakening.** No `skip`, no `xfail`, no relaxed asserts.
- **No `latest` tag auto-deploy.** Image deploys are pinned by digest.
- **No agent muting another agent's definition.** `.claude/agents/**`
  is on the no-touch list after seed.

## Where to start as a contributor

1. Read this doc and ADR-015.
2. Read [`no_touch_paths.md`](no_touch_paths.md) and
   [`autonomy_ladder.md`](autonomy_ladder.md).
3. Open a PR using the template — it walks you through the governance
   checklist.
4. Touch a no-touch path? Use a `governance-bootstrap` PR with explicit
   ADR alignment.
