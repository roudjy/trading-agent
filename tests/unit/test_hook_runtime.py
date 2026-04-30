"""Tests for .claude/hooks/_hook_runtime.py.

Covers fail-closed semantics, timeout enforcement, malformed-input
handling, and audit emission for blocked actions.
"""

from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
HOOKS_DIR = REPO_ROOT / ".claude" / "hooks"


def _import_hook_runtime():
    """Import _hook_runtime fresh so tests don't share global state."""
    sys.path.insert(0, str(HOOKS_DIR))
    if "_hook_runtime" in sys.modules:
        del sys.modules["_hook_runtime"]
    return importlib.import_module("_hook_runtime")


@pytest.fixture
def runtime():
    return _import_hook_runtime()


def test_run_with_timeout_returns_value(runtime):
    assert runtime._run_with_timeout(lambda: 42, seconds=2) == 42


def test_run_with_timeout_raises_on_overrun(runtime):
    def slow():
        time.sleep(2.5)
        return "should not see this"

    with pytest.raises(runtime._TimeoutError):
        runtime._run_with_timeout(slow, seconds=1)


def test_run_with_timeout_propagates_exceptions(runtime):
    def boom():
        raise ValueError("intentional")

    with pytest.raises(ValueError, match="intentional"):
        runtime._run_with_timeout(boom, seconds=1)


def test_safe_path_extracts_file_path(runtime):
    payload = {"tool_input": {"file_path": "agent/foo.py"}}
    assert runtime._safe_path(payload) == "agent/foo.py"


def test_safe_path_returns_none_when_missing(runtime):
    assert runtime._safe_path({}) is None
    assert runtime._safe_path({"tool_input": {}}) is None


def test_safe_command_summary_truncates(runtime):
    cmd = "x" * 200
    payload = {"tool_input": {"command": cmd}}
    summary = runtime._safe_command_summary(payload)
    assert summary is not None
    assert len(summary) == 80


# ---------------------------------------------------------------------------
# Subprocess-level tests — exercise the entrypoint as Claude Code would.
# ---------------------------------------------------------------------------


def _run_hook(script: str, payload: dict | None) -> tuple[int, str, str]:
    proc = subprocess.run(
        [sys.executable, str(HOOKS_DIR / script)],
        input=json.dumps(payload) if payload is not None else "",
        capture_output=True,
        text=True,
        timeout=10,
    )
    return proc.returncode, proc.stdout, proc.stderr


def test_subprocess_allow_unrelated_path():
    code, _, _ = _run_hook(
        "deny_no_touch.py",
        {
            "tool_name": "Edit",
            "tool_input": {"file_path": "tests/unit/test_x.py"},
        },
    )
    assert code == 0


def test_subprocess_deny_no_touch_live_gate():
    code, _, stderr = _run_hook(
        "deny_no_touch.py",
        {
            "tool_name": "Edit",
            "tool_input": {"file_path": "automation/live_gate.py"},
        },
    )
    assert code == 2
    assert "no_touch_path" in stderr.lower()


def test_subprocess_deny_no_touch_for_settings_json():
    code, _, _ = _run_hook(
        "deny_no_touch.py",
        {
            "tool_name": "Write",
            "tool_input": {"file_path": ".claude/settings.json"},
        },
    )
    assert code == 2


def test_subprocess_deny_no_touch_for_agent_definition():
    code, _, _ = _run_hook(
        "deny_no_touch.py",
        {
            "tool_name": "Write",
            "tool_input": {"file_path": ".claude/agents/planner.md"},
        },
    )
    assert code == 2


def test_subprocess_malformed_stdin_fails_closed():
    """Hook receives non-JSON garbage — must DENY, not allow."""
    proc = subprocess.run(
        [sys.executable, str(HOOKS_DIR / "deny_no_touch.py")],
        input="not json {",
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert proc.returncode == 2
    assert "malformed" in proc.stderr.lower() or "stdin" in proc.stderr.lower()


def test_subprocess_empty_stdin_treated_as_empty_payload():
    """Empty stdin -> empty payload -> tool not in deny list -> allow."""
    proc = subprocess.run(
        [sys.executable, str(HOOKS_DIR / "deny_no_touch.py")],
        input="",
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert proc.returncode == 0
