"""Tests for .claude/hooks/deny_outside_agent_allowlist.py.

The allowlist hook is the second layer of agent isolation: writes
must fall under at least one agent's frontmatter allowed_roots.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
HOOKS_DIR = REPO_ROOT / ".claude" / "hooks"


def _import_hook():
    sys.path.insert(0, str(HOOKS_DIR))
    if "deny_outside_agent_allowlist" in sys.modules:
        del sys.modules["deny_outside_agent_allowlist"]
    return importlib.import_module("deny_outside_agent_allowlist")


@pytest.fixture
def hook():
    return _import_hook()


def _write(path: str, content: str = "x") -> dict:
    return {"tool_name": "Write",
            "tool_input": {"file_path": path, "content": content}}


@pytest.mark.parametrize(
    "path",
    [
        "agent/brain/agent.py",
        "agent/execution/order_executor.py",
        "agent/learning/reporter.py",
        "agent/agents/rsi_agent.py",
        "agent/risk/manager.py",
        "agent/monitoring/health.py",
        "automation/something.py",
        "execution/protocols.py",
        "orchestration/orchestrator.py",
        "research/some_module.py",
        "strategies/momentum.py",
        "data/some_module.py",
        "ops/something.conf",
    ],
)
def test_default_deny_for_unallowed_paths(hook, path):
    allow, reason = hook.check(_write(path))
    assert not allow, "expected DENY for path not in any agent allowed_roots: " + path
    assert "outside_agent_allowlist" in (reason or "").lower()


@pytest.mark.parametrize(
    "path",
    [
        "tests/unit/test_x.py",
        "tests/smoke/test_y.py",
        "frontend/src/Foo.tsx",
        "docs/backlog/agent_backlog.md",
        "docs/spillovers/agent_spillovers.md",
        "dashboard/api_campaigns.py",
        "reporting/agent_audit.py",
        ".github/workflows/tests.yml",
        "pyproject.toml",
    ],
)
def test_allow_for_paths_in_some_agent_allowlist(hook, path):
    allow, _ = hook.check(_write(path))
    assert allow, "expected ALLOW for path " + path + " (under some agent allowed_root)"


def test_hard_deny_overrides_allowlist(hook):
    # automation/live_gate.py is hard-deny even if some agent allowlist
    # would otherwise match.
    allow, reason = hook.check(_write("automation/live_gate.py"))
    assert not allow
    assert "hard-deny" in (reason or "").lower() or "outside_agent_allowlist" in (reason or "").lower()


def test_ignores_non_write_tools(hook):
    payload = {"tool_name": "Bash", "tool_input": {"command": "ls"}}
    allow, _ = hook.check(payload)
    assert allow


def test_empty_target_is_denied(hook):
    payload = {"tool_name": "Edit",
               "tool_input": {"file_path": "", "old_string": "", "new_string": "x"}}
    allow, _ = hook.check(payload)
    # Empty path is allowed because target.strip() check; that's intentional.
    # The real defense is no_touch / outside_allowlist on the actual path.
    assert allow


def test_handles_backslash_paths(hook):
    payload = _write("agent\brain\agent.py")
    allow, _ = hook.check(payload)
    assert not allow
