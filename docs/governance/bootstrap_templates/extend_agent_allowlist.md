# Bootstrap template — extend an agent allowlist

> Template shape used by `reporting.governance_bootstrap`
> (v3.15.16.9) when a roadmap item's `affected_files` includes a
> path that is not in any `.claude/agents/*.md` `allowed_roots`
> union (so the `deny_outside_agent_allowlist` hook blocks all
> writes to it).

## When this template fires

- A future v3.15.16.4 ships `ops/systemd/*` files; `ops/systemd/*`
  is in no agent's `allowed_roots`, so the agent cannot write
  them. The bootstrap is operator-authored.
- A future release introduces a new top-level package
  (e.g., a hypothetical `engine/` directory) that needs to be
  added to one or more agent allowlists.

## Synthesized fields

```
branch_name:    governance-bootstrap/<event_id>
commit_message: governance-bootstrap: extend allowlist for <path>
file_diff:      delta to .claude/agents/<agent>.md frontmatter
                adding the path under allowed_roots
pr_title:       governance-bootstrap: extend allowlist for <path>
pr_body:        operator-facing markdown explaining the carveout
```

## Why the operator merges this manually

`.claude/agents/*.md` is on the no-touch list. Allowlist
extensions establish new authority surface and require explicit
operator review. The bootstrap PR keeps the change small (one
file, additive) so review is fast.

## Validation checklist (operator)

- [ ] The added path is genuinely needed by an in-flight roadmap
      item (cross-reference the source `human_needed` event).
- [ ] The added path is the narrowest possible scope (no
      wildcards beyond the directory needed).
- [ ] No additional `allowed_roots` entries beyond the one being
      added in this PR.
- [ ] `python scripts/governance_lint.py` passes.
- [ ] CI green on every required check.

## After merge

The agent gains write authority to the new path on its next
session. The operator should subsequently approve the
implementation PR that uses the newly-allowed path.
