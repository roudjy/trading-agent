"""Shared runtime for Claude Code governance hooks.

All deny-style hooks (``deny_no_touch``, ``deny_dangerous_bash``,
``deny_test_weakening``, ``deny_config_read``, ``deny_live_connector``)
import :func:`run_pre_hook` from this module so that they share a single
fail-closed timeout and audit emission policy.

Fail-closed contract
--------------------

Any of the following conditions causes the hook to **DENY**:

- :class:`Exception` raised by the user-supplied check function
- timeout exceeded (per-event budget)
- malformed stdin (non-JSON)
- missing required field in payload
- :exc:`ImportError` / missing dependency

In every case the hook writes a best-effort audit event with
``outcome=blocked_by_hook`` and ``block_reason=hook_runtime_<class>`` and
exits with code 2 (which Claude Code interprets as "block this tool
call").

Per-event timeout budgets:

    PreToolUse  : 2 seconds
    PostToolUse : 2 seconds
    Stop        : 5 seconds
    PreCompact  : 5 seconds
    audit_emit  : 1 second

The runtime is stdlib-only.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import traceback
from pathlib import Path
from typing import Any, Callable, Optional

# Make ``reporting`` importable regardless of where the hook script lives.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Lazy import — failure is fail-closed for deny hooks but best-effort for
# audit_emit (see _try_emit).
try:
    from reporting import agent_audit as _audit  # noqa: E402
except Exception:  # pragma: no cover - fallback
    _audit = None  # type: ignore[assignment]


# Per-event timeouts (seconds). Aligned with docs/governance/hooks_runtime_policy.md.
TIMEOUTS: dict[str, int] = {
    "PreToolUse": 2,
    "PostToolUse": 2,
    "Stop": 5,
    "PreCompact": 5,
    "audit_emit": 1,
}


# ---------------------------------------------------------------------------
# Audit helpers (best-effort — never raise)
# ---------------------------------------------------------------------------


def _git_head_sha() -> Optional[str]:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            check=False,
            text=True,
            timeout=1,
        )
        if out.returncode == 0:
            return out.stdout.strip() or None
    except Exception:
        return None
    return None


def _git_branch() -> Optional[str]:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            check=False,
            text=True,
            timeout=1,
        )
        if out.returncode == 0:
            return out.stdout.strip() or None
    except Exception:
        return None
    return None


def _try_emit(event: dict[str, Any]) -> None:
    """Best-effort audit event append. Never raises."""
    if _audit is None:
        return
    try:
        _audit.append_event(event)
    except Exception:
        # Last resort: write to stderr so the operator notices.
        sys.stderr.write(
            "[hook_runtime] audit emit failed: "
            + traceback.format_exc(limit=2)
            + "\n"
        )


def _enrich(event: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    enriched = dict(event)
    enriched.setdefault("session_id", payload.get("session_id"))
    enriched.setdefault("branch", _git_branch())
    enriched.setdefault("head_sha", _git_head_sha())
    enriched.setdefault("actor", "claude:hook")
    return enriched


# ---------------------------------------------------------------------------
# Timeout helper (cross-platform)
# ---------------------------------------------------------------------------


class _TimeoutError(Exception):
    pass


def _run_with_timeout(fn: Callable[[], Any], seconds: int) -> Any:
    """Run ``fn()`` with a wall-clock timeout. Raises ``_TimeoutError``."""
    if os.name != "nt" and hasattr(signal, "SIGALRM"):
        def _handler(signum, frame):  # noqa: ANN001
            raise _TimeoutError(f"hook exceeded {seconds}s budget")

        prev = signal.signal(signal.SIGALRM, _handler)
        signal.alarm(seconds)
        try:
            return fn()
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, prev)
    else:
        # Windows: no SIGALRM. Run in a thread with join timeout.
        import threading

        result: dict[str, Any] = {}

        def _runner() -> None:
            try:
                result["value"] = fn()
            except BaseException as e:  # pragma: no cover
                result["error"] = e

        t = threading.Thread(target=_runner, daemon=True)
        t.start()
        t.join(seconds)
        if t.is_alive():
            raise _TimeoutError(f"hook exceeded {seconds}s budget")
        if "error" in result:
            raise result["error"]
        return result.get("value")


# ---------------------------------------------------------------------------
# Public entrypoints
# ---------------------------------------------------------------------------


def _read_payload() -> dict[str, Any]:
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    return json.loads(raw)


def run_pre_hook(
    *,
    name: str,
    event_phase: str,
    check: Callable[[dict[str, Any]], tuple[bool, Optional[str]]],
) -> int:
    """Run a PreToolUse/PostToolUse/Stop/PreCompact deny-style hook.

    ``check(payload) -> (allow, reason)``:
        ``allow=True``  → exit 0 (allow)
        ``allow=False`` → exit 2 with reason on stderr (block)

    Any exception, timeout, or malformed input → exit 2 (fail-closed).
    """
    timeout = TIMEOUTS.get(event_phase, 2)
    payload: dict[str, Any] = {}

    try:
        payload = _read_payload()
    except Exception as e:
        msg = f"[{name}] malformed stdin: {e!r}"
        sys.stderr.write(msg + "\n")
        _try_emit(
            _enrich(
                {
                    "event": "blocked",
                    "tool": "_hook_runtime",
                    "outcome": "blocked_by_hook",
                    "block_reason": f"hook_runtime_malformed_stdin",
                    "command_summary": msg[:80],
                },
                {},
            )
        )
        return 2

    try:
        allow, reason = _run_with_timeout(lambda: check(payload), timeout)
    except _TimeoutError as e:
        msg = f"[{name}] timeout: {e}"
        sys.stderr.write(msg + "\n")
        _try_emit(
            _enrich(
                {
                    "event": "blocked",
                    "tool": payload.get("tool_name"),
                    "outcome": "blocked_by_hook",
                    "block_reason": "hook_timeout",
                    "command_summary": msg[:80],
                },
                payload,
            )
        )
        return 2
    except Exception as e:
        msg = f"[{name}] runtime error: {e!r}"
        sys.stderr.write(msg + "\n")
        sys.stderr.write(traceback.format_exc(limit=3) + "\n")
        _try_emit(
            _enrich(
                {
                    "event": "blocked",
                    "tool": payload.get("tool_name"),
                    "outcome": "blocked_by_hook",
                    "block_reason": f"hook_runtime_error_{type(e).__name__}",
                    "command_summary": msg[:80],
                },
                payload,
            )
        )
        return 2

    if allow:
        # Allow path: do not emit per-call event from deny-hooks; the
        # PostToolUse audit_emit hook captures the canonical record. This
        # avoids double-emission.
        return 0

    # Block path: emit explicit deny event.
    msg = f"[{name}] denied: {reason or 'no reason provided'}"
    sys.stderr.write(msg + "\n")
    _try_emit(
        _enrich(
            {
                "event": "blocked",
                "tool": payload.get("tool_name"),
                "target_path": _safe_path(payload),
                "outcome": "blocked_by_hook",
                "block_reason": reason or "denied",
                "command_summary": _safe_command_summary(payload),
            },
            payload,
        )
    )
    return 2


def _safe_path(payload: dict[str, Any]) -> Optional[str]:
    ti = payload.get("tool_input") or {}
    for key in ("file_path", "path", "notebook_path"):
        val = ti.get(key)
        if isinstance(val, str):
            return val
    return None


def _safe_command_summary(payload: dict[str, Any]) -> Optional[str]:
    ti = payload.get("tool_input") or {}
    cmd = ti.get("command")
    if isinstance(cmd, str):
        return cmd[:80]
    return None
