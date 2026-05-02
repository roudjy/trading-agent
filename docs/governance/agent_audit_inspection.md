# Agent Audit Inspection — Operator Runbook

Three sources together let you answer the question *"which agent did
what, when, on which branch?"*. This runbook lists each source, the
exact command to inspect it, and the limitations you must keep in
mind.

> The actual gate is `verify_chain()` plus reviewer discipline plus
> CODEOWNERS plus branch protection. The diagnostics below help you
> *see* state quickly; they do not *enforce* state.

## At a glance

| Question | Source | Command |
|---|---|---|
| Is the governance layer present and intact? | live snapshot | `python -m reporting.governance_status` |
| What did agents do today? (operator-friendly) | runtime ledger | `python -m reporting.agent_audit_summary` |
| Tail one event verbatim | runtime ledger | `python -m reporting.agent_audit tail logs/agent_audit.<UTC date>.jsonl` |
| Is today's hash chain intact? | runtime ledger | `python -m reporting.agent_audit verify logs/agent_audit.<UTC date>.jsonl` |
| What did agents do across an entire session? | committed run summary | open `docs/governance/agent_run_summaries/<session_id>.md` |
| Were the release-stage gates met? | release-gate report | open `docs/governance/release_gates/<version>/<UTC>.md` |
| What was deployed? | build provenance | open `artifacts/build_provenance-<version>.json` (gitignored runtime) |

## The runtime ledger — `logs/agent_audit.<UTC date>.jsonl`

* One file per UTC day. Hash-chained. Gitignored. Schema in
  [`docs/governance/audit_chain.md`](audit_chain.md).
* Every Edit / Write / MultiEdit / Bash and every deny-hook decision
  appends one event.
* Sealed by `event_sha256`; tampering produces a chain break that
  `verify_chain()` reports.

### Read it the operator-friendly way

```sh
python -m reporting.agent_audit_summary
```

That command prints two views as JSON:

* **`timeline`** — last 50 events, sorted by `sequence_id`. Each row
  carries `sequence_id`, `timestamp_utc`, `actor`, `event`, `tool`,
  `outcome`, `block_reason`, `branch`, `head_sha`, `session_id`,
  `target_dir`, `redaction_status`. Anything missing in the source is
  surfaced as `"unknown"`.
* **`groups`** — counts by actor, outcome, tool, branch, session, plus
  the earliest and latest timestamps and chain status.
<<<<<<< fix/v3.15.15.15-agent-audit-subagent-attribution
* **`attribution`** *(v3.15.15.15)* — inferred subagent attribution
  per session, derived from committed run summaries. **Convenience-
  only, not source-of-truth.** See "Inferred attribution" below for
  what `confidence: high` means and what is unknown today.
=======
>>>>>>> main

Useful flags:

* `--limit N` — show last N timeline rows (default 50).
<<<<<<< fix/v3.15.15.15-agent-audit-subagent-attribution
* `--view timeline` / `--view groups` / `--view attribution` / `--view both` (default).
=======
* `--view timeline` / `--view groups` / `--view both` (default).
>>>>>>> main
* `--format table` — render the timeline as a fixed-width table.
* `--actor claude:hook` — filter timeline by actor.
* `--outcome blocked_by_hook` — filter timeline by outcome.
* `--date 2026-04-29` — read a different day's file.
* `--path logs/agent_audit.2026-04-29.jsonl` — explicit file path.

The CLI exits 0 even when the chain is broken, the file is missing, or
some lines are malformed. Status is reported as a field; it is not the
exit code. Use `verify` if you need an exit-code gate.

### What the summary does NOT show (by design)

* **`target_path` is collapsed to `target_dir`** — only the parent
  directory is exposed. The full filename can carry information the
  operator did not explicitly ask about.
* **`command_summary` is omitted** — the writer redacts credential
  patterns, but the summary view drops the field entirely.
* **`diff_summary` is omitted** — the writer caps it at `{lines_added,
  lines_removed, content_sha256}`, but the summary view drops it too.
* **No raw payloads, ever.** If a credential-shaped string somehow
  reaches a kept field, it is replaced with `[REDACTED]` at projection
  time and the safety self-check refuses to print it.

### Known limitations of the source

These are limitations of the *writer*, not of the summary view. They
are documented here so operators do not infer guarantees that do not
hold today.

| Field | Where it is set | Where it is NULL |
|---|---|---|
| `actor` | `claude:audit_emit` for PostToolUse, `claude:hook` for deny hooks, `claude:precompact_preserve` for PreCompact | per-subagent identity is **not** captured today (no `claude:planner`, `claude:test-agent` etc. — that requires a writer change in `audit_emit.py`, which is a no-touch path; an ADR amendment + governance-bootstrap PR would be needed). |
| `branch`, `head_sha` | Enriched by `_hook_runtime` on deny-hook events | NULL on PostToolUse events (the writer there does not call git). |
| `session_id` | Set when the hook payload carries it (Claude Code sends it on PostToolUse) | NULL for synthetic / programmatic events. |

If `branch` or `head_sha` is `null`, the timeline row reports
`"unknown"`. The operator is expected to cross-reference with the
session's run summary at
`docs/governance/agent_run_summaries/<session_id>.md`, which does
record branch and start/end SHAs.

## The committed run summary — per session

The runtime ledger is gitignored. The committed bridge is
`docs/governance/agent_run_summaries/<session_id>.md`, written at the
end of each session that produced a PR. The summary contains:

* `session_id`, `start_utc`, `end_utc`, `branch`, `head_sha_at_start`,
  `head_sha_at_end`;
* subagent invocation counts;
* tool-call counts;
* paths touched (paths only, no content);
* test results;
* hook-event counts;
* ledger event-id range covered (`seq=<lo>..<hi>`);
* release-gate decision (if `/release-gate` was run);
* linked PR.

This is where you go for **per-session** context. The runtime ledger
is for **per-event** context within a single day.

The template lives at
`docs/governance/agent_run_summaries/_template.md`.

## When operator approval is still required

Reading the ledger does not loosen any constraint. Every action that
required operator approval before this view was added still requires
it:

1. Any change to `.claude/{settings.json,hooks/**,agents/**}`,
   `.github/CODEOWNERS`, or `VERSION` — only via human-authored,
   CODEOWNERS-reviewed `governance-bootstrap` PRs.
2. Any merge to `main`, deploy of an image, unlock of Level 4 or 5,
   regeneration of a frozen contract, or addition of a live connector.
3. Any chain-break finding (`chain_status == "broken"`) — investigate
   immediately; do not assume the diagnostic itself is faulty.

## Failure modes

* **`chain_status == "unreadable"`**: the ledger has bytes but no
  valid events parse. The file may be partially overwritten. Run
  `verify` on the previous day's file (it is sealed) and check the
  process that writes the ledger (`audit_emit.py`).
* **`malformed_line_count > 0`**: usually a half-written line at the
  tail because a process was killed. The chain may still be intact;
  the malformed line is skipped by `verify`. Investigate if it
  persists.
* **`by_actor` shows unexpected actors**: today the only legitimate
  actors are `claude:audit_emit`, `claude:hook`, and
  `claude:precompact_preserve`. Anything else is either a future
  writer change (which should arrive via a governance-bootstrap PR)
  or a tampering attempt.
* **`by_branch` shows `main` for events that should have been on a
  feature branch**: cross-reference with `git log --oneline` for that
  range; the writer captures the branch active at event time.

<<<<<<< fix/v3.15.15.15-agent-audit-subagent-attribution
## Inferred attribution (`--view attribution`, v3.15.15.15)

The `attribution` view runs
[`reporting.subagent_attribution`](../../reporting/subagent_attribution.py)
and projects per-event subagent attribution **inferred** from already-
captured signals: the audit ledger plus committed run summaries at
`docs/governance/agent_run_summaries/<session_id>.md`.

This view is **convenience-only, not source-of-truth.** Per-event
subagent attribution at the writer level is gated by ADR-016 (see
[`docs/governance/proposals/ADR-016-subagent-attribution-writer.md`](proposals/ADR-016-subagent-attribution-writer.md));
it requires a writer change to `.claude/hooks/audit_emit.py` that no
agent can apply.

Each row carries four fields. **Never read just the first one** —
always check confidence, source, and warning together:

| field | meaning |
|---|---|
| `inferred_subagent` | `claude:<role>` or `unknown`. |
| `subagent_confidence` | `high` / `low` / `unknown`. Default is `unknown`; promotion is conservative. |
| `attribution_source` | `run_summary` / `transcript_path` / `session_cluster` / `unavailable`. |
| `attribution_warning` | Required when `confidence != high`. Tells the operator why the inference is weak. |

`confidence: high` requires *explicit source evidence* — exactly one
of:

1. The run summary contains an explicit per-event
   timestamp/window/tool/sequence-id mapping AND the tool-count
   matches the ledger event count for the session within ±1.
2. Transcript metadata at `transcript_path` contains an explicit
   subagent identifier keyed to this event's `sequence_id`.
3. The run summary lists exactly **one** subagent for the entire
   session AND there is no competing or conflicting evidence (no
   second name in the summary, no contradiction in the ledger, no
   malformed sections, no orphan tool counts).

Tool-count agreement is *supporting* evidence only. It is never
sufficient on its own.

`confidence: low` is the default for partial / ambiguous evidence:
multiple subagents in the same session without per-event mapping,
pure timing or clustering, solo-subagent contradicted by other
evidence.

`confidence: unknown` is reported when no run summary exists, no
`session_id`, the summary is malformed, evidence conflicts, or the
file cannot be safely read. **Treat unknown as needs-human, never
as `ok`.**

=======
>>>>>>> main
## Where it fits

* **ADR-015 §Doctrine 5 — Audit-chain doctrine**: this runbook is the
  operator-facing companion of `audit_chain.md`. The chain doctrine
  remains canonical; this view just makes it easier to read.
* **Doctrine 13 — Run-summary doctrine**: per-session run summaries
  remain the authoritative bridge between runtime ledger and Git
  history. The summary view is for ad-hoc inspection, not for the
  PR record.
* **v3.15.15.13 governance-status**: `governance_status` reports
  *current* state of the layer; `agent_audit_summary` reports
  *what happened* in a day. Different lenses, same source.
