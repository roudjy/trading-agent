"""Tests for .claude/hooks/deny_config_read.py."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
HOOKS_DIR = REPO_ROOT / ".claude" / "hooks"


def _import_hook():
    sys.path.insert(0, str(HOOKS_DIR))
    if "deny_config_read" in sys.modules:
        del sys.modules["deny_config_read"]
    return importlib.import_module("deny_config_read")


@pytest.fixture
def hook():
    return _import_hook()


@pytest.mark.parametrize(
    "path",
    [
        "config/config.yaml",
        ".env",
        ".env.production",
        "state/dashboard_session.secret",
        "state/live_gate.secret",
        "automation/live_gate.secret",
    ],
)
def test_read_deny(hook, path):
    payload = {"tool_name": "Read", "tool_input": {"file_path": path}}
    allow, reason = hook.check(payload)
    assert not allow
    assert "config_read" in (reason or "").lower()


@pytest.mark.parametrize(
    "path",
    [
        "config/config.template.yaml",  # template is allowed
        "tests/unit/test_x.py",
        "frontend/package.json",
        "reporting/agent_audit.py",
    ],
)
def test_read_allow(hook, path):
    payload = {"tool_name": "Read", "tool_input": {"file_path": path}}
    allow, _ = hook.check(payload)
    assert allow


def test_grep_path_deny(hook):
    payload = {
        "tool_name": "Grep",
        "tool_input": {"pattern": "x", "path": "config/config.yaml"},
    }
    allow, _ = hook.check(payload)
    assert not allow


def test_grep_glob_deny(hook):
    payload = {
        "tool_name": "Grep",
        "tool_input": {"pattern": "x", "glob": "**/.env"},
    }
    allow, _ = hook.check(payload)
    assert not allow


def test_glob_pattern_deny(hook):
    payload = {"tool_name": "Glob", "tool_input": {"pattern": "config/config.yaml"}}
    allow, _ = hook.check(payload)
    assert not allow


def test_bash_cat_config_deny(hook):
    payload = {
        "tool_name": "Bash",
        "tool_input": {"command": "cat config/config.yaml | head"},
    }
    allow, _ = hook.check(payload)
    assert not allow


def test_bash_python_open_config_deny(hook):
    payload = {
        "tool_name": "Bash",
        "tool_input": {"command": "python -c \"print(open('config/config.yaml').read())\""},
    }
    allow, _ = hook.check(payload)
    assert not allow
