# Audit Chain Specification

Append-only, hash-chained agent audit ledger. Implemented in
[`reporting/agent_audit.py`](../../reporting/agent_audit.py); written
by the [`audit_emit.py`](../../.claude/hooks/audit_emit.py) hook;
verified by the `evidence-verifier` agent and the
`/release-gate` command.

---

## File layout

- One file per UTC day:
  `logs/agent_audit.YYYY-MM-DD.jsonl`
- One JSON object per line; UTF-8; trailing newline.
- File is gitignored. The committed bridge to Git history is
  `docs/governance/agent_run_summaries/<session_id>.md` (redacted).

## Event schema (v1)

| field | type | notes |
|---|---|---|
| `schema_version` | int | always `1` |
| `sequence_id` | int | monotonic per file, starting at `0` |
| `timestamp_utc` | string | ISO-8601 `Z` |
| `session_id` | string\|null | Claude Code session uuid |
| `actor` | string | e.g. `claude:audit_emit`, `claude:planner`, `claude:hook` |
| `model` | string\|null | e.g. `claude-sonnet-4-6` |
| `event` | enum | `tool_use` \| `tool_result` \| `stop` \| `subagent_invoke` \| `blocked` |
| `tool` | string\|null | e.g. `Edit`, `Write`, `Bash` |
| `target_path` | string\|null | for Edit/Write/Read |
| `diff_summary` | object\|null | `{lines_added, lines_removed, content_sha256}` |
| `command_summary` | string\|null | first 80 chars, redacted |
| `outcome` | enum | `ok` \| `blocked_by_hook` \| `denied` \| `error` |
| `block_reason` | string\|null | rule id when `outcome != ok` |
| `branch` | string\|null | git branch at event time |
| `head_sha` | string\|null | git HEAD at event time |
| `redacted` | bool | true when the redaction layer modified the record |
| `autonomy_level_claimed` | int\|null | 0–3 |
| `prev_event_sha256` | string\|null | sha256 of previous event canonical bytes |
| `event_sha256` | string | sha256 of THIS event canonical bytes (excluding `event_sha256` itself) |

`canonical_bytes` =
`json.dumps(record_minus_event_sha256, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")`.

## Hash chain invariants

For event N > 0:

```
record_N["prev_event_sha256"] = canonical(record_{N-1})
record_N["event_sha256"]      = canonical(record_N excluding event_sha256)
```

For N == 0 (first event in a fresh file):

```
record_0["prev_event_sha256"] = null
record_0["event_sha256"]      = canonical(record_0 excluding event_sha256)
```

Any deletion, insertion, or rewrite of past events breaks the chain.
`verify_chain(path)` returns `(True, None)` if intact, otherwise
`(False, <first_corrupt_index>)`.

## Concurrency

- Single-process append.
- File-level exclusive lock via `fcntl.flock` on POSIX or
  `msvcrt.locking` on Windows. The lock spans both the read of the
  last event and the write.
- The `_read_last_event_from_handle()` helper reuses the locked file
  handle to avoid a second-handle `PermissionError` on Windows.

## Redaction

The writer applies a regex-based redaction pass before sealing the
hash:

- Anthropic key prefix `sk-ant-`
- GitHub PAT prefixes `ghp_` / `gho_` / `github_pat_`
- AWS access key id pattern `AKIA[0-9A-Z]{16}`
- Generic long hex (≥40 chars) and base64 (≥40 chars) substrings

`diff_summary` is restricted to `{lines_added, lines_removed,
content_sha256}` — any other key is dropped before write.

## Verification

- CLI: `python -m reporting.agent_audit verify <path>`
- Programmatic: `from reporting.agent_audit import verify_chain`

The `evidence-verifier` agent runs verification as part of every
release-gate report.

## Rotation

Daily by UTC date. The previous day's file is read-only by convention;
new events go into today's file with `prev_event_sha256` reset to
`null`.

This means the chain is **per-day**, not per-repo. Cross-day continuity
is not enforced — the per-day chain detects intra-day tampering, which
is the realistic threat model. A cross-day chain would couple the
ledger to the previous day's file in a way that breaks the rotation
invariant.

## Out of scope (intentional)

- Token/cost telemetry — out of scope for v3.15.15.12 (Joery's call).
- Off-host export — local-only for now; a future version may add a
  push to a private bucket.
