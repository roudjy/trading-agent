# `.claude/hooks/` — SELF-PROTECTED

> These files implement the v3.15.15.12 Claude Agent Governance & Safety Layer.
>
> **They cannot be modified by an agent.** `deny_no_touch.py` lists
> `.claude/hooks/**` and `.claude/settings.json` in its denylist. Any agent
> attempt to write here will be blocked at the hook layer.
>
> Modifications happen exclusively via a human-authored, CODEOWNERS-reviewed
> Pull Request labeled `governance-bootstrap`. See
> [`docs/governance/permission_model.md`](../../docs/governance/permission_model.md).

## Hook layout

| File | Trigger | Purpose | Fail-closed timeout |
|---|---|---|---|
| `_hook_runtime.py` | (library) | Shared timeout + fail-closed wrapper. Imported by every deny hook. | n/a |
| `deny_no_touch.py` | PreToolUse Edit/Write/MultiEdit/NotebookEdit | Blocks writes to no-touch globs (live gate, secrets, authority surface, frozen schemas, hooks/agents themselves, VERSION, …). | 2 s |
| `deny_dangerous_bash.py` | PreToolUse Bash | Blocks destructive Git, deploy commands, SSH-to-VPS, secret reads via shell, non-localhost curl/wget, edits to `settings.local.json`. | 2 s |
| `deny_test_weakening.py` | PreToolUse Edit/Write | Blocks new `pytest.mark.skip` / `xfail` / `pytest.skip(...)` etc. inside `tests/`. | 2 s |
| `deny_config_read.py` | PreToolUse Read/Grep/Glob/Bash | Read-deny for `config/config.yaml`, `state/*.secret`, `.env*`. | 2 s |
| `deny_live_connector.py` | PreToolUse Write/Edit/MultiEdit | Create-deny for new broker/live connector files (path + content patterns). | 2 s |
| `audit_emit.py` | PostToolUse Edit/Write/Bash + Stop | Best-effort append of a redacted event to `logs/agent_audit.<UTC date>.jsonl` via `reporting.agent_audit`. | 1 s |
| `precompact_preserve.py` | PreCompact | Re-injects no-touch list + autonomy ladder + pin-test names so post-compaction context is still guarded. | 5 s |

## Fail-closed semantics

For every PreToolUse-style deny hook, **any** of the following ⇒ DENY (exit 2):

- the user-supplied check raised an exception
- the wall-clock budget was exceeded
- stdin was malformed JSON
- a required field was missing
- an `ImportError` occurred (e.g. `reporting.agent_audit` is missing)

`audit_emit.py` is the one exception: it is best-effort (never blocks the
already-completed action) but its budget still applies, and a budget-violation
emits an `error` event to the ledger.

## Adding or changing a hook

1. Open a PR titled `governance-bootstrap: ...`.
2. Update [`docs/governance/no_touch_paths.md`](../../docs/governance/no_touch_paths.md) and (if relevant) [`docs/governance/hooks_runtime_policy.md`](../../docs/governance/hooks_runtime_policy.md).
3. Add or update a unit test under `tests/unit/test_hooks_*.py` so the
   `hook-tests` job covers the new behaviour.
4. CODEOWNERS review.
5. Merge.

## Verifying the audit chain

```sh
python -m reporting.agent_audit verify logs/agent_audit.<YYYY-MM-DD>.jsonl
```
