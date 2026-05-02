---
status: operator-applied governance-bootstrap proposal
applies_to: .claude/hooks/audit_emit.py
related_adr: ADR-015 §Doctrine 7 (self-protected), §Doctrine 12 (no bypass)
proposed_in_release: v3.15.15.15
---

# ADR-016 (proposal) — Subagent attribution at the writer

> **Status: operator-applied governance-bootstrap proposal.**
> No agent applies this. The operator opens a separate PR titled
> `governance-bootstrap: subagent attribution writer (ADR-016)` that
> touches `.claude/hooks/audit_emit.py` and is CODEOWNERS-reviewed
> before merge. Until then, [`reporting.subagent_attribution`](../../../reporting/subagent_attribution.py)
> is the convenience-only inferred view (see
> [`agent_audit_inspection.md` §Inferred attribution`](../agent_audit_inspection.md)).

## Why

`reporting.agent_audit` records `actor` for each ledger event, but
`audit_emit.py` hard-codes the actor to `claude:audit_emit` for every
PostToolUse event. The hook payload from Claude Code already carries
fields that identify the active subagent
(`subagent_name`, `subagent_id` — confirm in the runtime payload at
patch time; treat as best-effort if missing). We are not capturing
those fields, so the operator cannot answer *"which subagent ran which
tool"* from the ledger directly. The post-hoc reconstruction in
v3.15.15.15 is convenience-only.

This proposal is the writer-level fix.

## Scope (additive only — no policy weakening)

This patch:

- Adds the `subagent_name` / `subagent_id` fields from the hook
  payload (when present) into the audit event.
- Sets `actor` to `claude:<subagent_name>` when the payload provides
  one; otherwise keeps the existing `claude:audit_emit` literal.
- Updates `_hook_runtime._enrich` to honour an explicit `actor` key
  in the event dict before falling back to the default.
- Updates the audit-chain schema documentation to list the new
  optional fields.

This patch does **not**:

- Change any allow / deny / ask permission rule.
- Loosen any hook (`deny_no_touch`, `deny_test_weakening`,
  `deny_dangerous_bash`, `deny_config_read`, `deny_live_connector`,
  `deny_outside_agent_allowlist` are untouched).
- Add or remove any CODEOWNERS line.
- Mutate any no-touch marker, dry-run flag, or session toggle.
- Bypass the fail-closed timeout policy.
- Weaken any existing test.

## Patch (apply by hand from the operator's shell)

### 1. `.claude/hooks/audit_emit.py` — capture from payload

```diff
@@ def main() -> int:
     event_phase = payload.get("hook_event_name") or "PostToolUse"
+    subagent_name = payload.get("subagent_name")
+    subagent_id = payload.get("subagent_id")
     base: dict[str, Any] = {
-        "actor": "claude:audit_emit",
+        "actor": (
+            f"claude:{subagent_name}"
+            if isinstance(subagent_name, str) and subagent_name
+            else "claude:audit_emit"
+        ),
         "event": "tool_result" if event_phase != "Stop" else "stop",
         "tool": payload.get("tool_name"),
         "target_path": _safe_target(payload),
         "diff_summary": _summarize_diff(payload),
         "command_summary": _safe_command_summary(payload),
         "outcome": "ok",
         "session_id": payload.get("session_id"),
+        "subagent_name": subagent_name if isinstance(subagent_name, str) else None,
+        "subagent_id": subagent_id if isinstance(subagent_id, str) else None,
     }
```

### 2. `.claude/hooks/_hook_runtime.py:_enrich` — honour explicit actor

```diff
 def _enrich(event: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
     enriched = dict(event)
     enriched.setdefault("session_id", payload.get("session_id"))
     enriched.setdefault("branch", _git_branch())
     enriched.setdefault("head_sha", _git_head_sha())
-    enriched.setdefault("actor", "claude:hook")
+    payload_subagent = payload.get("subagent_name")
+    if isinstance(payload_subagent, str) and payload_subagent:
+        enriched.setdefault("actor", f"claude:{payload_subagent}")
+    else:
+        enriched.setdefault("actor", "claude:hook")
     return enriched
```

### 3. `docs/governance/audit_chain.md` — schema additive update

Add two rows to the event schema table (after `session_id`):

```
| `subagent_name` | string\|null | Claude Code subagent identifier when the active session is a sub-agent invocation. |
| `subagent_id` | string\|null | Per-invocation id. |
```

Schema_version stays at 1 (additive change, no field removed or
renamed).

### 4. `tests/unit/test_hooks_audit_emit.py` — add the attribution case

Add one test that feeds a payload containing `subagent_name`,
`subagent_id`, and `tool_input`, and asserts the resulting event has
`actor == "claude:<name>"` and that the two new fields round-trip.
Keep all existing assertions intact (no test weakening).

### 5. Run all gates

```sh
pytest tests/unit/test_hooks_audit_emit.py tests/unit/test_hook_runtime.py tests/unit/test_agent_audit*.py tests/unit/test_subagent_attribution.py -q
pytest tests/smoke -q
pytest tests/regression -q --ignore=tests/regression/test_v3_15_8_canonical_dump_and_digest.py
python scripts/governance_lint.py
python -m reporting.agent_audit verify logs/agent_audit.$(date -u +%F).jsonl
sha256sum research/research_latest.json research/strategy_matrix.csv
```

## Attestation

By opening the corresponding `governance-bootstrap` PR, the operator
attests that this change:

- [ ] does not weaken any allow/deny/ask permission rule;
- [ ] does not modify hook fail-closed semantics or timeout budgets;
- [ ] does not introduce any environment variable / CLI flag /
      session toggle that re-enables hook bypass (Doctrine 12);
- [ ] does not touch any frozen contract;
- [ ] does not enable live / paper / shadow / trading code paths;
- [ ] does not regenerate any pin or determinism digest;
- [ ] does not skip / xfail / relax any existing test.

## Once merged

`reporting.subagent_attribution` continues to function (it reads
the same ledger). New events will carry `subagent_name` directly, so
the inferred view's confidence will rise to `high` for the recently-
written window without any post-hoc inference. The
[`agent_audit_inspection.md` §Inferred attribution`](../agent_audit_inspection.md)
section's caveat ("convenience-only, not source-of-truth") remains in
place for older events written before this patch.

## Reverting

If a regression is found post-merge: revert this single PR. The
rollback restores the pre-ADR-016 actor-hardcoding without affecting
the chain (existing events have no `subagent_name` field; absence is
schema-valid).
