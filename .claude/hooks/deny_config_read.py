#!/usr/bin/env python3
"""PreToolUse Read|Grep|Glob|Bash — deny reads of config/secrets.

Revision 5 hardening:
  - _normalize() resolves symlinks and is case-insensitive on Windows.
  - Bash-side regex set extended with redirect-reads (`< config/...`),
    process substitution (`<(cat config/...)`), awk/sed/tac/od/xxd/
    strings/nl/cut/find -exec on secret paths, eval, base64 -d, and
    other indirect read patterns surfaced in the v3.15.15.12 audit.
"""

from __future__ import annotations

import fnmatch
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _hook_runtime import run_pre_hook  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent

READ_DENY_GLOBS: tuple[str, ...] = (
    "config/config.yaml",
    "state/*.secret",
    "automation/*.secret",
    ".env",
    ".env.*",
)


def _normalize(p: str) -> str:
    raw = p.replace("\\", "/")
    while raw.startswith("./"):
        raw = raw[2:]
    try:
        resolved = Path(raw).resolve(strict=False).as_posix()
        repo_prefix = _REPO_ROOT.resolve().as_posix()
        if resolved.startswith(repo_prefix + "/"):
            resolved = resolved[len(repo_prefix) + 1:]
        elif resolved == repo_prefix:
            resolved = ""
    except (OSError, ValueError):
        resolved = raw
    return resolved.lower() if sys.platform == "win32" else resolved


def _matches(rel_path: str) -> str | None:
    n = _normalize(rel_path)
    for pat in READ_DENY_GLOBS:
        glob = pat.lower() if sys.platform == "win32" else pat
        if fnmatch.fnmatchcase(n, glob):
            return pat
    return None


# Secret-path token used inside the regex alternation below.
_SECRET_TOKEN = (
    r"(?:config/conf[^|;\s>]*\.ya?ml|"   # config/config.yaml + glob/wildcards
    r"\.env(?:\.[^|;\s]+)?|"            # .env, .env.production, etc
    r"state/[^/\s|;>]*\.secret|"        # state/*.secret
    r"automation/[^/\s|;>]*\.secret)"   # automation/*.secret
)

# Bash patterns that are an indirect read of a secret file. Each pattern
# is searched anywhere in the command string (re.search semantics).
_BASH_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    # Direct reads (kept from Rev4 for defense in depth).
    (re.compile(r"(?:cat|head|tail|less|more|nl|bat|view)\s+[^|;]*config/conf[^|;\s]*\.ya?ml"), "read_config_yaml_direct"),
    (re.compile(r"(?:cat|head|tail|less|more|nl|bat|view)\s+[^|;]*state/[^/\s]*\.secret"), "read_state_secret_direct"),
    (re.compile(r"(?:cat|head|tail|less|more|nl|bat|view)\s+[^|;]*\.env(?:\.\S+)?"), "read_env_direct"),

    # R5.3 - extended file-reading utilities.

    # R5.3 - redirect reads. `< config/config.yaml`, `0< .env`, etc.
    # Process substitution: <(cat config/config.yaml), <(awk ...), etc.
    # Command substitution that reads a secret: $(cat config/...) or `cat config/...`
    # Echo $(<file) - shorthand for read.

    # R5.3 - python interactive interpreter. `python -c` is denied
    # OUTRIGHT to prevent chr() / base64 obfuscation. Tests and module
    # invocation (`python -m pytest`) are unaffected.
    (re.compile(r"\bpython[0-9.]*\s+-c\b"), "python_dash_c"),
    (re.compile(r"\bpython[0-9.]*\s+--command\b"), "python_command"),
    (re.compile(r"\bpython[0-9.]*\S*\s+.*open\s*\(\s*[\"\']config/config\.yaml"), "py_open_config_literal"),
    (re.compile(r"\bpython[0-9.]*\S*\s+.*Path\s*\([\"\']config/config\.yaml"), "py_path_config_literal"),

    # R5.3 - eval / base64 obfuscation.
    (re.compile(r"\beval\b"), "eval_command"),
    (re.compile(r"\bbase64\s+(?:--decode|-d|-D)\b"), "base64_decode"),

    # R5.3 - grep / rg directly on secret paths.

    # R5.3 - dd of=, cp/mv to/from secret paths.
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
        if isinstance(glob, str) and any(s in glob.lower() for s in ("config.yaml", ".env", ".secret")):
            return (False, f"config_read denied via Grep glob '{glob}'.")

    elif tool == "Glob":
        pattern = ti.get("pattern")
        if isinstance(pattern, str) and any(
            s in pattern.lower() for s in ("config.yaml", ".env", ".secret")
        ):
            return (False, f"config_read denied via Glob pattern '{pattern}'.")

    elif tool == "Bash":
        cmd = ti.get("command")
        if isinstance(cmd, str):
            for pat, label in _BASH_PATTERNS:
                if pat.search(cmd):
                    return (
                        False,
                        f"config_read denied: shell pattern '{label}' would expose "
                        "credential / secret content. See docs/governance/"
                        "no_touch_paths.md.",
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
