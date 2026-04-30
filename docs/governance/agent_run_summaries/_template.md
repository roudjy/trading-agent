# Agent Run Summary Template

> Copy this file to `<session_id>.md` in the same directory and fill in
> each section. **Never include file contents, secrets, ledger payloads,
> or anything that does not belong in a public Git history.** Paths,
> counts, decisions, and ledger event ids only.

---

## Session metadata

- **session_id**: `<uuid or short slug>`
- **start_utc**: `YYYY-MM-DDTHH:MM:SSZ`
- **end_utc**: `YYYY-MM-DDTHH:MM:SSZ`
- **branch**: `<git branch>`
- **head_sha_at_start**: `<40-char sha>`
- **head_sha_at_end**: `<40-char sha>`
- **roadmap_item**: `<e.g. v3.15.15.12.7 dry-run docs-only>`
- **autonomy_level_claimed**: `0 | 1 | 2 | 3`

## Subagents invoked

| agent | model | calls |
|---|---|---|
| (e.g.) planner | sonnet | 1 |

## Tools used (counts)

| tool | calls |
|---|---|
| Read | _ |
| Edit | _ |
| Write | _ |
| Bash | _ |
| Grep | _ |
| Glob | _ |

## Files touched

> Paths only. No content snippets.

- `path/to/file1.py`
- `path/to/file2.md`

## Tests executed

| suite | result | notes |
|---|---|---|
| `pytest tests/smoke -q` | pass | — |
| `pytest tests/unit -q` | pass | — |
| `pytest tests/regression -k "pin or deterministic"` | pass | — |
| `npm test --run` (frontend) | pass | — |
| `pytest tests/unit/test_hook_runtime.py tests/unit/test_hooks_*.py tests/unit/test_agent_audit.py -q` | pass | — |

## Hook events

- `outcome=ok` count: _
- `outcome=blocked_by_hook` count: _
  - by reason:
    - (none)

## Determinism / evidence checks

- `pytest tests/regression -k "pin or deterministic or digest or invariant"`: pass / drift
- `python -m reporting.agent_audit verify <today's ledger>`: ok / fail at index _
- Ledger event id range covered by this session: `seq=<lo>..<hi>`

## Release Gate decision (if /release-gate was run)

- commit: recommend yes / no / N/A
- PR: recommend yes / no / N/A
- merge: humans-only — recommend / not-yet
- deploy: humans-only — recommend / not-yet
- Linked report file: `docs/governance/release_gates/<version>/<timestamp>.md`

## Linked PR

- `<owner/repo#NNN>` (or `(none)` if no PR opened in this session)

## Notes

> Free-form narrative. Keep it short. **No secrets, no full diffs.**

---

> **Reminder:** This file is committed to Git and visible in PR history.
> The audit ledger (`logs/agent_audit.<UTC date>.jsonl`) holds the
> machine-readable trail and is not committed. The summary is the bridge
> between the two.
