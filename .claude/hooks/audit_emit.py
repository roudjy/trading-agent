#!/usr/bin/env python3
"""PostToolUse / Stop — append a redacted event to the agent audit ledger.

This is a best-effort hook: failures emit to stderr but never block (the
tool call has already completed). The fail-closed timeout policy still
applies so a hung audit-emit cannot stall the session.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

# Make ``reporting`` importable.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Time budget in seconds — aligned with hooks_runtime_policy.md.
_BUDGET = 1.0


def _summarize_diff(payload: dict[str, Any]) -> dict[str, Any] | None:
    ti = payload.get("tool_input") or {}
    tool = payload.get("tool_name")
    if tool == "Write":
        content = ti.get("content", "") or ""
        return {
            "lines_added": content.count("\n"),
            "lines_removed": 0,
            "content_sha256": _sha256(content),
        }
    if tool == "Edit":
        old = ti.get("old_string", "") or ""
        new = ti.get("new_string", "") or ""
        return {
            "lines_added": new.count("\n"),
            "lines_removed": old.count("\n"),
            "content_sha256": _sha256(new),
        }
    if tool == "MultiEdit":
        edits = ti.get("edits") or []
        new_total = "\n".join(e.get("new_string", "") for e in edits if isinstance(e, dict))
        old_total = "\n".join(e.get("old_string", "") for e in edits if isinstance(e, dict))
        return {
            "lines_added": new_total.count("\n"),
            "lines_removed": old_total.count("\n"),
            "content_sha256": _sha256(new_total),
        }
    return None


def _sha256(s: str) -> str:
    import hashlib

    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _safe_target(payload: dict[str, Any]) -> str | None:
    ti = payload.get("tool_input") or {}
    for key in ("file_path", "path", "notebook_path"):
        v = ti.get(key)
        if isinstance(v, str):
            return v
    return None


def _safe_command_summary(payload: dict[str, Any]) -> str | None:
    ti = payload.get("tool_input") or {}
    cmd = ti.get("command")
    if isinstance(cmd, str):
        return cmd[:80]
    return None


def main() -> int:
    t0 = time.monotonic()
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except Exception as e:
        sys.stderr.write(f"[audit_emit] malformed stdin: {e!r}\n")
        return 0  # do not block

    # Lazy import — keep audit logging best-effort.
    try:
        from reporting import agent_audit
    except Exception as e:
        sys.stderr.write(f"[audit_emit] reporting.agent_audit unavailable: {e!r}\n")
        return 0

    event_phase = payload.get("hook_event_name") or "PostToolUse"
    base: dict[str, Any] = {
        "actor": "claude:audit_emit",
        "event": "tool_result" if event_phase != "Stop" else "stop",
        "tool": payload.get("tool_name"),
        "target_path": _safe_target(payload),
        "diff_summary": _summarize_diff(payload),
        "command_summary": _safe_command_summary(payload),
        "outcome": "ok",
        "session_id": payload.get("session_id"),
    }

    # Budget enforcement.
    if (time.monotonic() - t0) > _BUDGET:
        sys.stderr.write("[audit_emit] over budget; emitting error event\n")
        try:
            agent_audit.append_event(
                {
                    **base,
                    "outcome": "error",
                    "block_reason": "audit_emit_over_budget",
                }
            )
        except Exception:
            pass
        return 0

    try:
        agent_audit.append_event(base)
    except Exception as e:
        sys.stderr.write(f"[audit_emit] append failed: {e!r}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
