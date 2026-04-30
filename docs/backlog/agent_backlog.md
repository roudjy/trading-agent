# Agent Backlog

The Product Owner agent maintains this file. Items here are recommendations
extracted from the agent audit ledger and run summaries — the operator
decides what gets done.

| id | created_utc | priority | category | title | status | source_session |
|---|---|---|---|---|---|---|
| AB-0001 | 2026-04-30 | P2 | governance | Verify regression-fast `-k` filter actually selects all current pin tests; document filter semantics in `tests/regression/README.md` | open | bootstrap |
| AB-0002 | 2026-04-30 | P3 | governance | Decide whether `actions/attest-build-provenance` (GHCR-attached attestation) should be added next to artifact upload | open | bootstrap |
| AB-0003 | 2026-04-30 | P3 | governance | Confirm `docs/adr/_drafts/` subdirectory convention (no drafts exist yet) | open | bootstrap |
| AB-0004 | 2026-04-30 | P3 | observability | Decide whether monthly SHA-pin review runs as a recurring scheduled task or remains manual | open | bootstrap |
| AB-0005 | 2026-04-30 | P3 | governance | Approve agent run summary minimum-content template (current placeholder in `docs/governance/agent_run_summaries/_template.md`) | open | bootstrap |
| AB-0006 | 2026-04-30 | P2 | ci | Verify SHA-pinned action versions are correct against published release SHAs (first SHA-pin review) | open | bootstrap |
| AB-0007 | 2026-04-30 | P2 | observability | Add a smoke test that exercises `reporting.agent_audit.append_event` end-to-end on Windows + POSIX (verifies the locked-handle fix from .3) | open | bootstrap |
| AB-0008 | 2026-04-30 | P3 | governance | CLAUDE.md restructuring into per-layer files (deferred; see Revision 4 plan §17) | open | bootstrap |
| AB-0009 | 2026-04-30 | P2 | governance | Activate branch protection on `main` per `docs/governance/branch_protection_checklist.md` (human task, scheduled morning after this PR exists) | open | bootstrap |
| AB-0010 | 2026-04-30 | P3 | governance | Expand `mypy` scope from the v3.15.15.12.2 narrow set to additional modules; track each expansion as its own PR | open | bootstrap |

---

## Conventions

- **Append-only by item.** A row, once added, may have its `status` updated
  (`open` → `in-progress` → `resolved`/`spilled`/`rejected`) but never deleted.
  Spilled items move to `docs/spillovers/agent_spillovers.md` with a
  back-reference.
- **One PR per session.** The Product Owner agent batches all changes into a
  single PR per agent session. Per-event PRs would shred attention.
- **`source_session`** is the agent session id (or `bootstrap` for the
  initial seed). Linked to `docs/governance/agent_run_summaries/<id>.md`.
- **No secrets**, ever. Items reference paths, ledger event ids, and PR
  numbers — never credentials.

## Status semantics

| Status | Meaning |
|---|---|
| `open` | Recommended; waiting for an agent or human to pick up. |
| `in-progress` | Active session is working on it (set by the planner). |
| `resolved` | Merged PR closes the item. The PR number is appended to the row. |
| `spilled` | Deferred; row continues to exist but a corresponding entry is added to `agent_spillovers.md`. |
| `rejected` | Operator decided no action is needed. Row stays for audit. |
