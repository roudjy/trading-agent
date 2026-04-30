#!/usr/bin/env python3
"""PreToolUse Write — create-deny for live broker / connector files.

This hook blocks the *creation* of a new file whose path or content
suggests it implements a live trading connector. It is intentionally
conservative; an operator can introduce live connectors via a
``governance-bootstrap`` PR (CODEOWNERS-reviewed) — the hook is for
agents only.

Path-side denylist
------------------

Any new file under these globs is blocked:

- ``execution/live/**``
- ``automation/live/**``
- ``agent/execution/live/**``
- ``**/live_*broker*.py``
- ``**/*live_executor*.py``
- ``**/live_*.py`` (when not in tests/)
- ``**/*_live.py``

Content-side denylist
---------------------

Any new file whose content imports/uses live-signing surfaces is blocked:

- ``eth_account.Account.sign_*``
- ``web3.eth.send_raw_transaction``
- ``py_clob_client.client.ClobClient`` combined with ``private_key``
- ``ccxt.<exchange>().create_order`` without a paper-mode flag

Edits to existing live files are already covered by ``deny_no_touch``.
"""

from __future__ import annotations

import fnmatch
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _hook_runtime import run_pre_hook  # noqa: E402

PATH_DENY_GLOBS: tuple[str, ...] = (
    "execution/live/*",
    "execution/live/**",
    "automation/live/*",
    "automation/live/**",
    "agent/execution/live/*",
    "agent/execution/live/**",
    "**/live_*broker*.py",
    "**/*live*broker*.py",
    "**/*live_executor*.py",
    "**/*live*executor*.py",
    "**/*_live.py",
)

# More cautious: live_*.py outside tests/ and outside the existing
# automation/live_gate.py (which exists; deny_no_touch handles it).
_LIVE_STAR_PATTERN = re.compile(r"(^|/)live_[A-Za-z0-9_]+\.py$")
_TEST_PATH_PREFIXES: tuple[str, ...] = ("tests/", "tests_tmp/")


CONTENT_DENY_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"from\s+eth_account\b"), "import_eth_account"),
    (re.compile(r"\beth_account\.Account\.sign_"), "eth_account_sign"),
    (re.compile(r"\bweb3\.eth\.send_raw_transaction\b"), "web3_send_raw"),
    (re.compile(r"from\s+py_clob_client\.client\s+import\s+ClobClient"), "py_clob_client_import"),
    (re.compile(r"\bClobClient\s*\([^)]*private_key"), "clob_with_private_key"),
    (re.compile(r"\bccxt\.\w+\([^)]*\)\.create_order\("), "ccxt_create_order_live"),
    (re.compile(r"\bccxt\.\w+\.\w+\.create_order\("), "ccxt_create_order_live"),
)


def _normalize(p: str) -> str:
    """Forward slashes only; strip literal leading ``./``."""
    p = p.replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    return p


def _is_test_path(p: str) -> bool:
    """Match any path whose components include ``tests`` or ``tests_tmp``.

    Tolerant of absolute paths (e.g. ``C:/Users/.../tests/unit/...``) and
    relative paths (e.g. ``tests/unit/...``). The hook payload may contain
    either form depending on the caller.
    """
    n = _normalize(p)
    parts = set(n.split("/"))
    return "tests" in parts or "tests_tmp" in parts


def _path_matches(rel_path: str) -> str | None:
    n = _normalize(rel_path)
    for pat in PATH_DENY_GLOBS:
        if fnmatch.fnmatchcase(n, pat):
            return pat
    if _LIVE_STAR_PATTERN.search(n) and not _is_test_path(n):
        # Allow the existing live_gate.py path to slip through here; it is
        # already covered by deny_no_touch and we don't want a double-message.
        if not n.endswith("automation/live_gate.py"):
            return "live_<name>.py"
    return None


def _content_matches(content: str) -> str | None:
    for pat, label in CONTENT_DENY_PATTERNS:
        if pat.search(content):
            return label
    return None


def _new_content(payload: dict[str, Any]) -> str:
    ti = payload.get("tool_input") or {}
    tool = payload.get("tool_name")
    if tool == "Write":
        return ti.get("content", "") or ""
    if tool == "Edit":
        return ti.get("new_string", "") or ""
    if tool == "MultiEdit":
        edits = ti.get("edits") or []
        return "\n".join(e.get("new_string", "") for e in edits if isinstance(e, dict))
    if tool == "NotebookEdit":
        return ti.get("new_source", "") or ""
    return ""


def _is_python_target(target: str) -> bool:
    n = _normalize(target).lower()
    return n.endswith(".py")


def check(payload: dict[str, Any]) -> tuple[bool, str | None]:
    tool = payload.get("tool_name")
    if tool not in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
        return (True, None)

    ti = payload.get("tool_input") or {}
    target = ti.get("file_path") or ti.get("path") or ti.get("notebook_path")
    if not isinstance(target, str) or not target.strip():
        return (True, None)

    # Skip files already in test directories — tests for the protocol are
    # allowed.
    if _is_test_path(target):
        return (True, None)

    pat = _path_matches(target)
    if pat is not None:
        return (
            False,
            f"live_connector_create denied: path '{target}' matches '{pat}'. "
            "Live connectors are introduced via a CODEOWNERS-reviewed governance-bootstrap PR, "
            "not by autonomous agents.",
        )

    # Content scan applies only to Python source files; otherwise governance
    # docs that *describe* these patterns would trip the hook.
    if not _is_python_target(target):
        return (True, None)

    content = _new_content(payload)
    if content:
        label = _content_matches(content)
        if label is not None:
            return (
                False,
                f"live_connector_create denied: content matches '{label}' in '{target}'. "
                "Live signing surfaces require human-authored implementation.",
            )

    return (True, None)


if __name__ == "__main__":
    sys.exit(
        run_pre_hook(
            name="deny_live_connector",
            event_phase="PreToolUse",
            check=check,
        )
    )
