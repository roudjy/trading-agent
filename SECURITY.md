# Security Policy

This file is part of the v3.15.15.12 Claude Agent Governance & Safety Layer.
It documents disclosure handling, secret-rotation runbooks, and the trust model
that keeps live trading code, credentials, and production posture out of agent
reach.

> Rotation timing decision (v3.15.15.12.0): external credential rotation is
> **deferred** because live trading is currently disabled. The repository-side
> containment (config/config.yaml removed from the Git index, `.gitignore`
> + `.dockerignore` updated, image-grep verification in place) closes the
> ongoing leak and is sufficient until the live-trading window opens.
> When live trading is re-enabled, the rotation runbook below becomes
> mandatory before any live order is placed.

---

## Reporting a vulnerability

This is a single-author project. Disclosure goes to the repository owner.
Please do **not** open a public issue for security-sensitive findings.
Send a private message via GitHub or email and allow up to 7 days for a first
response.

---

## Trust boundaries

- The only barrier between paper and live trading is
  [`automation/live_gate.py`](automation/live_gate.py). Treat this file as
  sacred — it is no-touch for agents and changes only via a human-authored
  CODEOWNERS-reviewed PR.
- Credentials live in `config/config.yaml`, which is **not** tracked in Git
  (see `.gitignore`) and **not** present in the Docker build context (see
  `.dockerignore`). Verify both invariants after any change to those files.
- The Polymarket private key controls a wallet. Rotation involves moving funds
  first; see runbook below.

---

## Pre-rotation image suspect notice

GHCR image tags pushed before the v3.15.15.12 containment may have included
`config/config.yaml` in their build context (the project did not have a
`.dockerignore` before this version). Treat the following as **suspect until
manually inspected and re-pushed**:

- `ghcr.io/roudjy/trading-agent-agent:*` (all pre-v3.15.15.12 tags)
- `ghcr.io/roudjy/trading-agent-dashboard:*` (all pre-v3.15.15.12 tags)

Cleanup is a manual GHCR step performed by the repo owner. Do not delete tags
that are referenced by `docs/governance/release_digests.md` until a digest-pinned
rollback path exists for that release.

---

## Credential inventory & rotation order

When rotation becomes necessary (e.g. before live trading is enabled, or after a
suspected leak), rotate **in this order**:

1. **Anthropic API key** — low-blast-radius. Replace and verify with a `models`
   list call.
2. **Bitvavo API key + secret** — paper trading continues to work; rotation is
   safe to perform any time the agent is in paper mode.
3. **Alchemy RPC URL** (Polygon) — the URL itself contains the API key. Rotate
   the key, update the URL, restart any process that holds it.
4. **Polymarket private key** — this controls wallet `0xc9F8323e5124cd09B907abd744Df455482F7807B`.
   Before rotation:
   - Confirm the wallet contains zero funds, **or**
   - Move all funds to a fresh wallet (manual MetaMask transaction; not via
     Claude).
   Only after the wallet is empty (or funds have been moved) should the old key
   be considered compromised and rotated.
   Per current decision (v3.15.15.12.0): wallet has no funds, so no fund-move
   step is required. Rotate when live trading approaches.
5. **IBKR account credentials** — verify scope (read-only vs trading). Rotate if
   the credentials grant trade-placement scope.

Each rotation is logged in [`docs/governance/key_rotation_log.md`](docs/governance/key_rotation_log.md)
with timestamp + service + version-id only — **never the credential value**.

---

## History rewrite (deferred runbook)

The Git history still contains pre-containment commits with credentials inside
`config/config.yaml`. A history rewrite is **deferred** under current decision
(no live trading, no funds at risk). When it becomes appropriate (e.g. before
making the repo public, or after a confirmed leak), the procedure is:

1. Coordinate a window with all collaborators (currently single-author — low
   blast radius).
2. Run on a fresh clone:
   ```bash
   git filter-repo --path config/config.yaml --invert-paths
   ```
3. Force-push to a **new branch** (never directly to `main`). Verify the
   rewrite by inspecting the new history with `git log --diff-filter=D --
   config/config.yaml` (should be empty).
4. After review and approval, replace the remote `main` reference. This is a
   destructive operation and requires explicit operator confirmation.
5. Rotate every credential that was in the rewritten file (the keys that were
   exposed in history must still be considered compromised even after rewrite).
6. Trigger a fresh clone on the production VPS and verify the daemon starts
   under the rotated credentials.

This runbook is **never** executed by an agent. Auto-mode hooks deny
`git filter-*`, `git push --force*`, and any equivalent destructive history
operation.

---

## Secret-handling rules

- Agents must never read, print, summarize, grep, or include in diffs:
  `config/config.yaml`, `state/*.secret`, `.env`, `.env.*`. The
  [`deny_config_read`](.claude/hooks/deny_config_read.py) hook enforces this.
- The audit ledger ([`reporting/agent_audit.py`](reporting/agent_audit.py))
  records paths and content hashes only, never file contents.
- Agent run summaries committed under
  [`docs/governance/agent_run_summaries/`](docs/governance/agent_run_summaries/)
  are redacted by template — only decisions, paths, counts, and gate outcomes.

---

## See also

- [`docs/governance/manual_blockers.md`](docs/governance/manual_blockers.md) — items that must be done outside Claude.
- [`docs/governance/key_rotation_log.md`](docs/governance/key_rotation_log.md) — append-only rotation log.
- [`docs/governance/branch_protection_checklist.md`](docs/governance/branch_protection_checklist.md) — GitHub UI settings for `main`.
- [`docs/adr/ADR-015-claude-agent-governance.md`](docs/adr/ADR-015-claude-agent-governance.md) — formal authority chain.
