#!/usr/bin/env python3
"""PreToolUse Edit|Write|MultiEdit|NotebookEdit — default-deny for paths
outside the union of all agent ``allowed_roots``.

This is the second layer of the allowlist doctrine (Doctrine 1).
``deny_no_touch`` blocks specific protected paths. This hook flips the
default: a write is **denied unless at least one agent in ``.claude/agents/``
declares the path under its ``allowed_roots``**.

Failure modes — all DENY:

- ``.claude/agents/`` is unreadable.
- Frontmatter parsing fails for any agent.
- The target path is not under any ``allowed_roots`` entry.
- The hook itself errors out (handled by ``_hook_runtime``).

Allowlist-by-union semantics
----------------------------

Some agents have narrow ``allowed_roots`` (e.g. release-gate-agent only
writes ``docs/governance/release_gates/``). Some are broad (e.g.
implementation-agent writes ``dashboard/``, ``tests/``, ``frontend/``,
``docs/``). The hook does not distinguish *which* agent is active —
that information is not reliably exposed in the hook payload. Instead
it asks "is there ANY agent that could legitimately be writing here?"

If no agent has the path under its ``allowed_roots``, no agent should
be writing it; the hook denies. This is conservative by design and
matches the user-stated intent of "default: deny als agent/context
onbekend is".

Allowed-root excludes
---------------------

Some agents declare ``allowed_root_excludes`` (carve-outs inside an
otherwise allowed root, e.g. observability core). Those exclusions
must reduce the agent's scope but do not enlarge anyone else's. The
hook treats excludes as the agent's local decision; the union is over
``allowed_roots`` only.

The deny_no_touch hook still runs alongside this one and remains the
ground truth for "this specific file is sacred".
"""

from __future__ import annotations

import fnmatch
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _hook_runtime import run_pre_hook

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_AGENTS_DIR = _REPO_ROOT / ".claude" / "agents"

# Paths that are always denied here too (defense in depth in case the
# agent allowlist somehow omits these). The deny_no_touch hook is
# canonical, but this list ensures the union does not accidentally
# include them via a future careless frontmatter edit.
_HARD_DENY: tuple[str, ...] = (
    "automation/live_gate.py",
    "config/config.yaml",
    "VERSION",
    ".claude/settings.json",
    ".github/CODEOWNERS",
)


def _normalize(p: str) -> str:
    """Forward slashes only; strip literal leading ``./``; lowercase
    on Windows-like environments for case-insensitive match.

    The hook also resolves symlinks via ``Path.resolve(strict=False)``
    so a symlink ``safe.txt -> automation/live_gate.py`` is detected.
    """
    raw = p.replace("\\", "/")
    while raw.startswith("./"):
        raw = raw[2:]
    # Resolve symlinks if the path exists, else keep the literal form.
    try:
        resolved = Path(raw).resolve(strict=False).as_posix()
        # Strip the repo-root prefix if present (so /abs/path/<repo>/x
        # becomes x for matching).
        repo_prefix = _REPO_ROOT.resolve().as_posix()
        if resolved.startswith(repo_prefix + "/"):
            resolved = resolved[len(repo_prefix) + 1:]
        elif resolved == repo_prefix:
            resolved = ""
        return resolved.lower() if sys.platform == "win32" else resolved
    except (OSError, ValueError):
        return raw.lower() if sys.platform == "win32" else raw


_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_ALLOWED_ROOTS_RE = re.compile(
    r"^allowed_roots\s*:\s*\n((?:\s+-\s+\S.*\n?)+)",
    re.MULTILINE,
)


def _read_agents_allowed_roots() -> tuple[str, ...]:
    """Parse all .claude/agents/*.md frontmatters and return the union of
    ``allowed_roots`` entries as fnmatch globs. Stdlib-only.
    """
    if not _AGENTS_DIR.is_dir():
        # No agents = nothing is allowed by union semantics. Fail-closed.
        return ()
    union: set[str] = set()
    for md in sorted(_AGENTS_DIR.glob("*.md")):
        try:
            text = md.read_text(encoding="utf-8")
        except OSError:
            continue
        m = _FRONTMATTER_RE.search(text)
        if not m:
            continue
        block = m.group(1)
        ar_match = _ALLOWED_ROOTS_RE.search(block)
        if not ar_match:
            continue
        items_block = ar_match.group(1)
        for line in items_block.splitlines():
            line = line.strip()
            if not line.startswith("-"):
                continue
            value = line[1:].strip().strip("'\"")
            if not value:
                continue
            # Treat an entry with a trailing slash as "this directory and
            # everything under it" — translate to fnmatch globs.
            entry = value.rstrip("/")
            union.add(entry)
            union.add(entry + "/*")
            union.add(entry + "/**")
            union.add("**/" + entry + "/**")
    return tuple(sorted(union))


def _matches_any(path: str, globs: tuple[str, ...]) -> bool:
    if not globs:
        return False
    n = path
    for g in globs:
        # On Windows, our normalized path is already lowercased; the glob
        # should be too for symmetric matching.
        glob = g.lower() if sys.platform == "win32" else g
        if fnmatch.fnmatchcase(n, glob):
            return True
    return False


def _is_hard_deny(path: str) -> bool:
    for d in _HARD_DENY:
        glob = d.lower() if sys.platform == "win32" else d
        if fnmatch.fnmatchcase(path, glob):
            return True
    return False


def check(payload: dict[str, Any]) -> tuple[bool, str | None]:
    tool = payload.get("tool_name")
    if tool not in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
        return (True, None)
    ti = payload.get("tool_input") or {}
    target = ti.get("file_path") or ti.get("path") or ti.get("notebook_path")
    if not isinstance(target, str) or not target.strip():
        return (True, None)

    n = _normalize(target)
    if not n:
        return (
            False,
            "outside_agent_allowlist: target normalizes to empty path; refusing as fail-closed.",
        )

    # Defense in depth: hard-deny list overrides everything (deny_no_touch
    # also covers these but we duplicate here in case the lists drift).
    if _is_hard_deny(n):
        return (
            False,
            f"outside_agent_allowlist: target '{n}' is on the hard-deny list "
            "(live gate, secrets, VERSION, settings.json, CODEOWNERS).",
        )

    union = _read_agents_allowed_roots()
    if not union:
        return (
            False,
            "outside_agent_allowlist: no .claude/agents/*.md found or no "
            "allowed_roots declared. Default-deny.",
        )

    if _matches_any(n, union):
        return (True, None)

    return (
        False,
        f"outside_agent_allowlist: target '{target}' (normalized: '{n}') is not "
        "under any agent's allowed_roots. If a legitimate agent should be writing "
        "here, add the path to that agent's frontmatter via a "
        "governance-bootstrap PR.",
    )


if __name__ == "__main__":
    sys.exit(
        run_pre_hook(
            name="deny_outside_agent_allowlist",
            event_phase="PreToolUse",
            check=check,
        )
    )
