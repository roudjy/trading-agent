# Hooks Runtime Policy

This document specifies the runtime behavior shared by every governance hook
in `.claude/hooks/`. The shared behavior is implemented in
[`_hook_runtime.py`](../../.claude/hooks/_hook_runtime.py); each specific
hook contributes only its check function.

---

## Fail-closed contract

For every PreToolUse-style deny hook, **any** of the following ⇒ **DENY**
(exit code 2 + reason on stderr + best-effort audit event):

- the user-supplied check function raised an exception
- the wall-clock budget was exceeded
- stdin was malformed JSON
- a required field was missing in the payload
- an `ImportError` occurred (e.g. `reporting.agent_audit` is absent)

There is no "warn-only" mode. There is no `--dry-run` flag. The first time
the hooks fail to import, the agent loses its ability to write — and that
is the intended fail-mode.

The one exception is `audit_emit.py`, which runs PostToolUse and on Stop.
Because the action it observes has *already* completed, blocking would have
no effect. `audit_emit` is therefore best-effort: failures emit a stderr
warning, write an `outcome=error, block_reason=audit_emit_*` event when
possible, and exit 0. Its time budget still applies.

---

## Timeout budgets

| Phase | Budget | Failure mode |
|---|---|---|
| `PreToolUse` | **2 s** | DENY |
| `PostToolUse` | **2 s** | best-effort warn |
| `Stop` | **5 s** | best-effort warn |
| `PreCompact` | **5 s** | best-effort warn (and context loses the reminder) |
| `audit_emit` (any phase) | **1 s** | warn + over-budget event |

The budget is enforced via `signal.alarm` on POSIX and a join-with-timeout
thread on Windows.

---

## Stdin & stdout protocol

Each hook receives a single JSON object on stdin:

```json
{
  "session_id": "...",
  "transcript_path": "...",
  "hook_event_name": "PreToolUse",
  "tool_name": "Edit",
  "tool_input": {
    "file_path": "...",
    "old_string": "...",
    "new_string": "..."
  }
}
```

A deny hook signals:

- **Allow**: exit 0, empty stdout.
- **Deny**: exit 2, reason on stderr.

`precompact_preserve.py` writes JSON to stdout to inject context per the
Claude Code hook protocol:

```json
{
  "hookSpecificOutput": {
    "hookEventName": "PreCompact",
    "additionalContext": "..."
  }
}
```

---

## Hook dry-run mode

> **Hook dry-run mode is NOT permitted once `.3` is active.**
>
> Specifically: there is no environment variable, command-line flag, or
> session toggle that converts a deny into a warn. Anyone who introduces one
> in a future PR is violating ADR-015 §dry-run-mode-only-pre-`.3` doctrine.

This was a deliberate choice during Revision 4 of the implementation plan:
soft-fail modes always end up enabled in production, then forgotten, then
exploited.

---

## Self-protection

The hook scripts and `.claude/settings.json` are themselves on the no-touch
list (see [`no_touch_paths.md`](no_touch_paths.md)). Modifications to either
require a human-authored, CODEOWNERS-reviewed PR labeled
`governance-bootstrap`. The hook layer cannot loosen its own constraints
at runtime.

---

## Audit emission

On allow, deny hooks do **not** emit per-call events; the canonical record
comes from the PostToolUse `audit_emit` hook to avoid double-emission. On
deny, the deny hook emits an `event=blocked` record with the responsible
`block_reason`.

The audit ledger lives at `logs/agent_audit.<UTC date>.jsonl` and is
append-only with a SHA-256 hash chain (see
[`audit_chain.md`](audit_chain.md)). Hooks call
`reporting.agent_audit.append_event` which handles redaction, sequence
numbering, and chain linkage.

If `reporting.agent_audit` is unavailable (import error), deny hooks still
DENY but the audit emission silently fails to stderr. This is intentional:
a missing audit module must not become a way to bypass deny.

---

## Adding a new hook

1. Open a `governance-bootstrap` PR.
2. Create the new hook in `.claude/hooks/<name>.py`. Import and use
   `run_pre_hook` from `_hook_runtime`.
3. Wire it into `.claude/settings.json` under the appropriate
   `PreToolUse` / `PostToolUse` / etc. matcher.
4. Update [`no_touch_paths.md`](no_touch_paths.md) if the hook protects new
   paths.
5. Add a unit test in `tests/unit/test_hooks_<name>.py` that exercises both
   allow and deny paths plus at least one failure mode (timeout, malformed
   input, missing field).
6. Confirm the `hook-tests` CI job passes.
7. CODEOWNERS review.
