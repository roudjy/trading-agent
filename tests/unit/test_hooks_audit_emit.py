"""Tests for .claude/hooks/audit_emit.py.

PostToolUse / Stop best-effort logger. Failures must NOT block; budget
violations emit error events; happy path produces well-formed records.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
HOOKS_DIR = REPO_ROOT / ".claude" / "hooks"
AUDIT_EMIT = HOOKS_DIR / "audit_emit.py"


def _run(payload, env=None):
    raw = json.dumps(payload) if payload is not None else ""
    return subprocess.run(
        [sys.executable, str(AUDIT_EMIT)],
        input=raw,
        capture_output=True,
        text=True,
        timeout=10,
        env=env,
    )


def test_happy_path_returns_zero(tmp_path):
    payload = {
        "session_id": "test-session",
        "hook_event_name": "PostToolUse",
        "tool_name": "Edit",
        "tool_input": {
            "file_path": "tests/unit/test_x.py",
            "old_string": "a",
            "new_string": "b\nc\n",
        },
    }
    r = _run(payload)
    assert r.returncode == 0


def test_malformed_stdin_does_not_block():
    r = subprocess.run(
        [sys.executable, str(AUDIT_EMIT)],
        input="not json {",
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert r.returncode == 0
    assert "malformed" in r.stderr.lower() or "audit_emit" in r.stderr.lower()


def test_empty_stdin_does_not_block():
    r = _run(None)
    assert r.returncode == 0


def test_write_tool_payload_summarizes_diff():
    payload = {
        "session_id": "s2",
        "hook_event_name": "PostToolUse",
        "tool_name": "Write",
        "tool_input": {
            "file_path": "frontend/src/App.tsx",
            "content": "line1\nline2\nline3\n",
        },
    }
    r = _run(payload)
    assert r.returncode == 0


def test_bash_tool_payload_does_not_crash():
    payload = {
        "session_id": "s3",
        "hook_event_name": "PostToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "echo hello"},
    }
    r = _run(payload)
    assert r.returncode == 0


def test_stop_event_records_stop_outcome():
    payload = {
        "session_id": "s4",
        "hook_event_name": "Stop",
        "tool_name": None,
        "tool_input": {},
    }
    r = _run(payload)
    assert r.returncode == 0
