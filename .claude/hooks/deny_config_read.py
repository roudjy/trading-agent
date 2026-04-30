#!/usr/bin/env python3
"""PreToolUse Read|Grep|Glob|Bash — deny reads of config/secrets.

Even though ``deny_dangerous_bash`` blocks ``cat config/config.yaml`` etc.
at the shell level, this hook is the second layer that catches any tool
that takes a path and would expose credential content.

Read-deny targets:

- ``config/config.yaml`` (the live credential file)
- ``state/*.secret``
- ``.env`` and ``.env.*``
- ``automation/*.secret`` (defense in depth)
"""

from __future__ import annotations

import fnmatch
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _hook_runtime import run_pre_hook  # noqa: E402

READ_DENY_GLOBS: tuple[str, ...] = (
    "config/config.yaml",
    "state/*.secret",
    "automation/*.secret",
    ".env",
    ".env.*",
)


def _normalize(p: str) -> str:
    """Forward slashes only; strip literal leading ``./``."""
    p = p.replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    return p


def _matches(rel_path: str) -> str | None:
    n = _normalize(rel_path)
    for pat in READ_DENY_GLOBS:
        if fnmatch.fnmatchcase(n, pat):
            return pat
    return None


# Bash-side deny patterns that the dangerous-bash hook also covers but we
# repeat here for defense in depth.
_BASH_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?:cat|head|tail|less|more|nl|bat|view)\s+[^|;]*config/config\.yaml"),
    re.compile(r"(?:cat|head|tail|less|more|nl|bat|view)\s+[^|;]*state/[^/\s]*\.secret"),
    re.compile(r"(?:cat|head|tail|less|more|nl|bat|view)\s+[^|;]*\.env(?:\.\S+)?"),
    re.compile(r"python\S*\s+.*open\s*\(\s*[\"']config/config\.yaml"),
    re.compile(r"python\S*\s+.*Path\s*\([\"']config/config\.yaml"),
    re.compile(r"\bgrep\b[^|;]*\sconfig/config\.yaml"),
    re.compile(r"\brg\b[^|;]*\sconfig/config\.yaml"),
)


def check(payload: dict[str, Any]) -> tuple[bool, str | None]:
    tool = payload.get("tool_name")
    ti = payload.get("tool_input") or {}

    if tool == "Read":
        path = ti.get("file_path")
        if isinstance(path, str):
            pat = _matches(path)
            if pat is not None:
                return (
                    False,
                    f"config_read denied: '{path}' matches '{pat}'. "
                    "See docs/governance/no_touch_paths.md (read-deny list).",
                )

    elif tool == "Grep":
        path = ti.get("path")
        if isinstance(path, str):
            pat = _matches(path)
            if pat is not None:
                return (False, f"config_read denied via Grep on '{path}'.")
        glob = ti.get("glob")
        if isinstance(glob, str) and any(s in glob for s in ("config.yaml", ".env", ".secret")):
            return (False, f"config_read denied via Grep glob '{glob}'.")

    elif tool == "Glob":
        pattern = ti.get("pattern")
        if isinstance(pattern, str) and any(
            s in pattern for s in ("config.yaml", ".env", ".secret")
        ):
            return (False, f"config_read denied via Glob pattern '{pattern}'.")

    elif tool == "Bash":
        cmd = ti.get("command")
        if isinstance(cmd, str):
            for pat in _BASH_PATTERNS:
                if pat.search(cmd):
                    return (
                        False,
                        "config_read denied: command would expose secrets file content.",
                    )

    return (True, None)


if __name__ == "__main__":
    sys.exit(
        run_pre_hook(
            name="deny_config_read",
            event_phase="PreToolUse",
            check=check,
        )
    )
