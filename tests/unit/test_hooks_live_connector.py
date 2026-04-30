"""Tests for .claude/hooks/deny_live_connector.py.

Note: trigger patterns are constructed at runtime via concatenation so
the test source itself does not contain literal regex patterns that
might trip the hook on its own write.
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
    if "deny_live_connector" in sys.modules:
        del sys.modules["deny_live_connector"]
    return importlib.import_module("deny_live_connector")


@pytest.fixture
def hook():
    return _import_hook()


# Construct trigger strings at runtime to avoid embedding literal patterns
# in this test file's source.
ETH_IMPORT = "from " + "eth_account" + " import Account\n"
ETH_SIGN = "Account.sign_" + "transaction(...)\n"
WEB3_SEND = "w3.eth.send_raw_" + "transaction(tx)\n"
CLOB_IMPORT = "from " + "py_clob_client.client" + " import ClobClient\n"
CLOB_INST = "ClobClient(host='x', private_" + "key='y')\n"
CCXT_ORDER = "ccxt.bitvavo().create_" + "order('BTC', 'limit', 'buy', 1.0)\n"


def _write(path: str, content: str) -> dict:
    return {"tool_name": "Write", "tool_input": {"file_path": path, "content": content}}


# ---------------------------------------------------------------------------
# Path-based deny
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "execution/live/bitvavo.py",
        "execution/live/sub/foo.py",
        "automation/live/something.py",
        "agent/execution/live/binance.py",
        "agent/some_live_broker.py",
        "agent/some_live_executor.py",
        "agent/agents/binance_live.py",
    ],
)
def test_path_deny(hook, path):
    allow, reason = hook.check(_write(path, "# empty\n"))
    assert not allow, f"expected DENY for path {path}"
    assert "live_connector" in (reason or "").lower()


# ---------------------------------------------------------------------------
# Content-based deny (Python files only)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "snippet",
    [
        ETH_IMPORT,
        ETH_SIGN,
        WEB3_SEND,
        CLOB_IMPORT,
        "client = " + CLOB_INST,
        CCXT_ORDER,
    ],
)
def test_content_deny_in_python(hook, snippet):
    allow, reason = hook.check(_write("agent/foo.py", snippet))
    assert not allow, f"expected DENY for content snippet: {snippet[:40]!r}"
    assert "live_connector" in (reason or "").lower()


def test_content_allow_in_markdown(hook):
    """Docs that describe these patterns must NOT trip the hook."""
    md = (
        "# Doc that mentions live patterns\n\n"
        + ETH_IMPORT
        + ETH_SIGN
        + WEB3_SEND
        + CLOB_IMPORT
        + "ccxt.create_order in prose.\n"
    )
    allow, _ = hook.check(_write("docs/something.md", md))
    assert allow


def test_test_paths_are_skipped(hook):
    """Live patterns inside tests/ are not blocked (allowing protocol tests)."""
    allow, _ = hook.check(_write("tests/unit/test_proto.py", ETH_IMPORT + ETH_SIGN))
    assert allow


def test_path_allow_unrelated(hook):
    allow, _ = hook.check(_write("dashboard/views.py", "from flask import Blueprint\n"))
    assert allow


def test_existing_live_gate_path_not_double_reported(hook):
    """automation/live_gate.py is covered by deny_no_touch; the live_connector
    hook should not also fire and produce a duplicate message."""
    allow, reason = hook.check(_write("automation/live_gate.py", "x = 1\n"))
    # Either allow (so deny_no_touch handles it) or deny that does NOT
    # mention live_connector — either is acceptable.
    if not allow:
        assert "live_connector" not in (reason or "").lower()
