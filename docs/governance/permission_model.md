# Permission Model

The agent permission model is **layered**. Every layer can deny; only the
intersection of all layers is allowed. This is intentional — when an agent
becomes confused, the cost of an unwanted action exceeds the cost of an
unnecessary block.

---

## Layers (top to bottom)

```
                  PROJECT POLICY (.claude/settings.json — tracked, SELF-PROTECTED, FAIL-CLOSED)
                                        |
                                        v
                  PERSONAL OVERRIDES (.claude/settings.local.json — gitignored)
                                        |
                                        v
                  PER-AGENT TOOL ALLOWLIST + ALLOWED-ROOTS (frontmatter)
                                        |
                                        v
                  AUTONOMY LEVEL CAP (frontmatter max <= project max)
                                        |
                                        v
                  HOOKS (PreToolUse / PostToolUse / Stop / PreCompact, fail-closed, timeout-bounded)
                                        |
                                        v
                  CODEOWNERS + BRANCH PROTECTION (final backstop; "Require review from Code Owners")
                                        |
                                        v
                  ADR-015 (architectural authority — humans-only for merge/deploy)
```

**Deny wins, always.** Policy denies override personal allows; per-agent
allowlists override policy allows but cannot override policy denies; hooks
override everything that came before them.

---

## Layer details

### 1. Project policy — `.claude/settings.json`

- **Tracked in Git.** Every change shows up in CI and requires CODEOWNERS
  review.
- **Self-protected.** `deny_no_touch.py` lists `.claude/settings.json` in its
  denylist; the file cannot be edited by an agent.
- Changes happen exclusively via a human-authored `governance-bootstrap` PR.
- The strictest layer. Any `deny` here cannot be loosened by lower layers.

### 2. Personal overrides — `.claude/settings.local.json`

- **Gitignored.** Personal allowlist for the operator's local convenience
  (e.g. `Bash(ssh root@vps)` for *human* SSH sessions).
- Personal allows do **not** override project denies. Hooks evaluate the
  union of project deny + personal allow, but the deny wins.
- The hook layer additionally blocks `Edit`/`Write` to this file from agent
  context.

### 3. Per-agent allowlist + allowed roots

- Each agent under `.claude/agents/` declares in YAML frontmatter:
  - `tools` — the subset of Claude Code tools it may use.
  - `allowed_roots` — directories it may write into (allowlist-only, never
    "everything except").
  - `max_autonomy_level` — see ladder below.
- An agent cannot use a tool that is not in its frontmatter, even if the
  project allows it. Trying to do so produces a hook deny.

### 4. Autonomy level cap

The autonomy ladder ([`autonomy_ladder.md`](autonomy_ladder.md)) describes
six numbered levels of agent capability. Every agent declares a maximum
level; a session running that agent cannot perform actions above its cap,
even if the project policy and frontmatter would otherwise allow them.

| Level | Capability | Status in this project |
|---|---|---|
| 0 | Plan / read only | Always available |
| 1 | Docs + tests + frontend writes | After v3.15.15.12.3 active |
| 2 | Observability + CI writes (with approval per change) | After .4 |
| 3 | Backend non-core writes (allowlist-only) | Not enabled in this version |
| 4 | Merge recommendation | >= 30 days L1-3 stable + ADR-15 amend |
| 5 | Deploy recommendation | >= 60 days L1-4 stable + ADR-15 amend |
| 6 | Autonomous merge / deploy | **Permanently disabled** |

### 5. Hooks

- Implemented in `.claude/hooks/`. Each is stdlib-only Python.
- Fail-closed: any error/timeout/parse-failure on a deny hook ⇒ DENY +
  audit event. See [`hooks_runtime_policy.md`](hooks_runtime_policy.md).
- The hooks are themselves self-protected — they live on the no-touch list.

### 6. CODEOWNERS + branch protection

- `.github/CODEOWNERS` annotates every protected path with `@roudjy`.
- Branch protection on `main` — manually configured in GitHub UI per
  [`branch_protection_checklist.md`](branch_protection_checklist.md) — enforces
  required reviews, required status checks, and prevents force-push.
- Without branch protection, CODEOWNERS is advisory. The checklist activation
  is a human-only step.

### 7. ADR-015

- The architectural-authority capstone. Documents the doctrine the layers
  above implement.
- Humans hold merge and deploy authority indefinitely. Level 6 is permanently
  disabled. Amendments to level 4/5 unlocking require a new ADR.

---

## Decision flow for a single tool call

```
[Claude attempts a tool call]
        |
        v
  project-policy `deny`?  -- yes -->  BLOCK
        | no
        v
  agent frontmatter forbids tool / outside allowed_roots?  -- yes --> BLOCK
        | no
        v
  autonomy level cap exceeded?  -- yes --> BLOCK
        | no
        v
  hook deny (PreToolUse)?  -- yes --> BLOCK + audit
        | no
        v
  project policy `ask`?  -- yes --> prompt operator
        | confirmed
        v
  ALLOW + audit (PostToolUse)
```

A `BLOCK` at any step emits an `outcome=blocked_by_hook` event in
`logs/agent_audit.jsonl` with the responsible `block_reason`.

---

## How to legitimately change a no-touch path

1. Open a PR titled `governance-bootstrap: <subject>`.
2. Update the relevant doc (e.g. `no_touch_paths.md`) and the matching hook
   constant in lockstep.
3. Add or update a unit test under `tests/unit/test_hooks_*.py`.
4. Reference the relevant section of [`ADR-015`](../adr/ADR-015-claude-agent-governance.md)
   or propose an amendment.
5. CODEOWNERS review.
6. Merge.

The hook layer cannot self-loosen at runtime. There is no `--bypass` flag,
no environment variable, no "for this session only" mode after seed.
