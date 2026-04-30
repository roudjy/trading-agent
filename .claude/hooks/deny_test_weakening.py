#!/usr/bin/env python3
"""PreToolUse Edit|Write — deny test weakening patterns.

Refuses to add ``@pytest.mark.skip``, ``@pytest.mark.xfail``, or inline
``pytest.skip(...)`` to anything under ``tests/``. Also refuses to
delete an entire test file (deletes go through ``ask`` flow with
operator review).

The check is heuristic and runs on the new content of an Edit/Write.
False positives (e.g. a test that intentionally documents that something
is not yet supported) are handled via an explicit ``ask`` exception in
``settings.json`` — currently no such exception exists.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _hook_runtime import run_pre_hook  # noqa: E402

# Patterns that introduce skipped or excused failing tests.
WEAKENING_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"@pytest\.mark\.skip\b"), "pytest.mark.skip"),
    (re.compile(r"@pytest\.mark\.skipif\b"), "pytest.mark.skipif"),
    (re.compile(r"@pytest\.mark\.xfail\b"), "pytest.mark.xfail"),
    (re.compile(r"\bpytest\.skip\s*\("), "pytest.skip(...)"),
    (re.compile(r"\bpytest\.xfail\s*\("), "pytest.xfail(...)"),
    (re.compile(r"\bpytest\.importorskip\s*\("), "pytest.importorskip(...)"),
)

# Comment markers that look like the agent is muting a known failure.
SUSPICIOUS_COMMENT_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"#\s*TODO:?\s*re-enable"), "todo_reenable_comment"),
    (re.compile(r"#\s*flaky"), "flaky_comment"),
)


def _is_test_target(path: str) -> bool:
    """True if ``path`` lives under a ``tests`` or ``tests_tmp`` directory.

    Tolerant of absolute paths and trailing components.
    """
    p = path.replace("\\", "/")
    parts = set(p.split("/"))
    return "tests" in parts or "tests_tmp" in parts


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


def check(payload: dict[str, Any]) -> tuple[bool, str | None]:
    tool = payload.get("tool_name")
    if tool not in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
        return (True, None)
    ti = payload.get("tool_input") or {}
    target = ti.get("file_path") or ti.get("path") or ti.get("notebook_path")
    if not isinstance(target, str) or not _is_test_target(target):
        return (True, None)

    new = _new_content(payload)
    if not new:
        return (True, None)

    for pat, label in WEAKENING_PATTERNS:
        if pat.search(new):
            return (
                False,
                f"test_weakening: introduces '{label}' in {target}. "
                "Per docs/governance/no_test_weakening.md, skipping/xfail/relaxing "
                "tests requires a human-authored PR with operator approval.",
            )

    # Suspicious comments alone don't deny, but if combined with the above
    # patterns they would already have triggered.
    return (True, None)


if __name__ == "__main__":
    sys.exit(
        run_pre_hook(
            name="deny_test_weakening",
            event_phase="PreToolUse",
            check=check,
        )
    )
