"""Tests for .claude/hooks/precompact_preserve.py.

PreCompact hook injects governance reminders into compaction context.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
HOOKS_DIR = REPO_ROOT / ".claude" / "hooks"
PRECOMPACT = HOOKS_DIR / "precompact_preserve.py"


def _run(payload):
    raw = json.dumps(payload) if payload is not None else ""
    return subprocess.run(
        [sys.executable, str(PRECOMPACT)],
        input=raw,
        capture_output=True,
        text=True,
        timeout=10,
    )


def test_returns_zero():
    r = _run({"session_id": "s1", "hook_event_name": "PreCompact"})
    assert r.returncode == 0


def test_emits_well_formed_json_on_stdout():
    r = _run({"session_id": "s2", "hook_event_name": "PreCompact"})
    assert r.returncode == 0
    out = r.stdout.strip()
    assert out, "expected JSON on stdout"
    obj = json.loads(out)
    assert "hookSpecificOutput" in obj
    hso = obj["hookSpecificOutput"]
    assert hso.get("hookEventName") == "PreCompact"
    ctx = hso.get("additionalContext", "")
    assert "no-touch" in ctx.lower() or "governance" in ctx.lower()
    assert "level 6" in ctx.lower()
    assert "fail-closed" in ctx.lower()


def test_handles_empty_stdin():
    r = _run(None)
    assert r.returncode == 0


def test_handles_garbage_stdin():
    r = subprocess.run(
        [sys.executable, str(PRECOMPACT)],
        input="not json {",
        capture_output=True,
        text=True,
        timeout=10,
    )
    # Should still exit 0 (best-effort).
    assert r.returncode == 0
