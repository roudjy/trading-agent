# Bootstrap template — add a no-touch carveout

> Template shape used by `reporting.governance_bootstrap`
> (v3.15.16.9) when an in-flight task needs to edit a path that
> is currently under a `.claude/hooks/deny_no_touch.py` glob and
> the operator has explicitly authorised the carveout.

## When this template fires

- A future release needs to edit a file currently covered by a
  no-touch glob (e.g., a one-off legitimate edit to a path that
  was previously declared no-touch).
- A future release needs to relax a hook's `_HARD_DENY` list
  to permit a deliberate operator-approved capability.

This template is **rare** — most blockers route through
`extend_agent_allowlist.md` (allowlist extension) or
`wiring_dashboard_py.md` (dashboard.py wiring) instead.

## Synthesized fields

```
branch_name:    governance-bootstrap/<event_id>
commit_message: governance-bootstrap: add no-touch carveout for <path>
file_diff:      delta to .claude/hooks/deny_no_touch.py
                adding an explicit carveout for the named path
pr_title:       governance-bootstrap: add no-touch carveout for <path>
pr_body:        operator-facing markdown explaining the carveout
                AND including the date the carveout was authorised
                AND including the related roadmap item_id
```

## Why this is the most-restricted template

`.claude/hooks/*` is on the canonical no-touch list. Loosening a
hook directly grants new mutation authority — every carveout
must be:

1. Justified in the PR body with a specific item_id.
2. Authored AND merged by the operator (no agent shortcut).
3. Reverted in a follow-up PR after the one-time edit lands
   (the carveout should NOT be permanent unless explicitly stated).

## Validation checklist (operator)

- [ ] The carveout is the narrowest possible scope (single path,
      not a wildcard).
- [ ] The PR body cross-references the source `human_needed`
      event and the related roadmap `item_id`.
- [ ] `python scripts/governance_lint.py` passes.
- [ ] `pytest tests/unit/test_hooks_no_touch.py -q` passes.
- [ ] A follow-up issue / PR is filed to revert the carveout
      after the one-time edit lands (or the PR body explicitly
      states the carveout is permanent and why).

## After merge

The hook stops blocking writes to the carved-out path. The
operator should immediately follow up with the actual edit PR
and (optionally) a revert PR closing the carveout.
