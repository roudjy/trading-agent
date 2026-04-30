"""Tests for .claude/hooks/deny_test_weakening.py.

The test fixtures contain literal pytest skip/xfail markers because
the hook under test detects exactly those. The file itself was
seeded via scripts/_bootstrap_test_weakening_test.py because the
hook would otherwise block its own test file.
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
    if "deny_test_weakening" in sys.modules:
        del sys.modules["deny_test_weakening"]
    return importlib.import_module("deny_test_weakening")


@pytest.fixture
def hook():
    return _import_hook()


def _edit(path: str, new: str) -> dict:
    return {
        "tool_name": "Edit",
        "tool_input": {"file_path": path, "old_string": "", "new_string": new},
    }


def _write(path: str, content: str) -> dict:
    return {"tool_name": "Write", "tool_input": {"file_path": path, "content": content}}


@pytest.mark.parametrize(
    "marker",
    [
        '@pytest.mark.skip\n',
        "@pytest.mark.skip(reason='wip')\n",
        "@pytest.mark.skipif(True, reason='wip')\n",
        '@pytest.mark.xfail\n',
        '@pytest.mark.xfail(strict=True)\n',
        "    pytest.skip('reason')\n",
        "    pytest.xfail('reason')\n",
        "    pytest.importorskip('foo')\n",
    ],
)
def test_blocks_markers_in_tests(hook, marker):
    new = "def test_a():\n" + marker + "    pass\n"
    allow, reason = hook.check(_write("tests/unit/test_x.py", new))
    assert not allow, f"expected DENY for marker: {marker!r}"
    assert "test_weakening" in (reason or "").lower()


def test_allows_normal_test_addition(hook):
    new = "def test_normal():\n    assert 1 + 1 == 2\n"
    allow, _ = hook.check(_write("tests/unit/test_x.py", new))
    assert allow


def test_ignores_files_outside_tests(hook):
    new = '@pytest.mark.skip\n' + "def test_x(): pass\n"
    allow, _ = hook.check(_write("agent/some_module.py", new))
    assert allow  # not a test path; not the hook's concern


def test_blocks_when_inserted_via_edit(hook):
    allow, _ = hook.check(_edit("tests/unit/test_x.py", '@pytest.mark.skip\n'))
    assert not allow


def test_handles_multiedit(hook):
    payload = {
        "tool_name": "MultiEdit",
        "tool_input": {
            "file_path": "tests/integration/test_y.py",
            "edits": [
                {"old_string": "", "new_string": '@pytest.mark.xfail\n'},
                {"old_string": "", "new_string": "def test(): pass"},
            ],
        },
    }
    allow, _ = hook.check(payload)
    assert not allow
