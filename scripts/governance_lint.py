#!/usr/bin/env python3
"""governance_lint.py - CI lint that enforces ADR-015 invariants.

Run with: python scripts/governance_lint.py

Exits non-zero on any violation. Designed to run in CI as part of the
fast pre-merge gate (governance-lint job).

Invariants checked:
  1. No agent in .claude/agents/*.md declares max_autonomy_level > 3.
  2. No file in repo mentions 'Level 6' without a nearby qualifier
     (disabled/never/auto-block/permanent/etc.) - i.e. Level 6 is
     never represented as 'enabled' or 'available'.
  3. No GitHub Action in .github/workflows/*.yml uses a floating tag
     (must be a 40-char commit SHA).
  4. docs/governance/no_touch_paths.md and the NO_TOUCH_GLOBS constant
     in .claude/hooks/deny_no_touch.py both exist.
  5. Every deny-style hook imports run_pre_hook.

Stdlib-only.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ERRORS: list[str] = []


def _err(msg: str) -> None:
    ERRORS.append(msg)


# 1. Agent autonomy levels --------------------------------------------------

_LEVEL_RE = re.compile(r"^max_autonomy_level\s*:\s*(\d+)\s*$", re.MULTILINE)

agents_dir = ROOT / ".claude" / "agents"
if agents_dir.is_dir():
    for md in sorted(agents_dir.glob("*.md")):
        text = md.read_text(encoding="utf-8")
        m = _LEVEL_RE.search(text)
        if not m:
            _err(f"{md.relative_to(ROOT)}: missing max_autonomy_level")
            continue
        level = int(m.group(1))
        if level > 3:
            _err(
                f"{md.relative_to(ROOT)}: max_autonomy_level={level} exceeds the "
                "current cap of 3 (Levels 4-5 require ADR-015 amendment; "
                "Level 6 is permanently disabled)"
            )

# 2. Level 6 mentions ------------------------------------------------------

_L6_RE = re.compile(r"\bLevel\s*6\b")

_DISABLED_WORDS = (
    "disabled",
    "permanently",
    "never",
    "forbidden",
    "off",
    "locked",
    "auto-block",
    "auto-recommend",
    "stays disabled",
    "stay disabled",
    "not enabled",
    "not a level",
    "open-loop",
    "deliberately overriding",
    "amendment",
    "must explicitly justify",
    "permanent",
    "ever reach",
    "block recommendation",
    "humans-only",
    "never reach",
)

# Canonical docs that DEFINE Level 6 = permanently disabled. They are
# expected to mention Level 6 multiple times in narrative context; skip
# the lint there. The point is to catch rogue mentions in other files.
_CANONICAL_LEVEL6_DOCS = {
    "docs/adr/ADR-015-claude-agent-governance.md",
    "docs/governance/autonomy_ladder.md",
    "docs/governance/no_touch_paths.md",
    "docs/governance/permission_model.md",
    "docs/governance/agent_governance.md",
    "docs/governance/release_gate.md",
    "docs/governance/release_gate_checklist.md",
    "docs/governance/manual_blockers.md",
}

for path in ROOT.rglob("*.md"):
    if any(p in path.parts for p in (".tmp", "node_modules", ".git", ".mypy_cache")):
        continue
    rel_posix = path.relative_to(ROOT).as_posix()
    if rel_posix in _CANONICAL_LEVEL6_DOCS:
        continue
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        continue
    for m in _L6_RE.finditer(text):
        start = max(0, m.start() - 200)
        end = m.start() + 600
        window = text[start:end].lower()
        if not any(word.lower() in window for word in _DISABLED_WORDS):
            _err(
                f"{path.relative_to(ROOT)}: 'Level 6' at offset {m.start()} "
                "appears without a disabled/never/auto-block/permanent qualifier "
                "in the surrounding 800 chars"
            )

# 3. Floating GitHub Actions tags -----------------------------------------

_USES_FLOATING = re.compile(r"^\s*-?\s*uses:\s+[A-Za-z0-9_./-]+@(v[0-9][^\s#]*)")
_USES_SHA = re.compile(r"^\s*-?\s*uses:\s+[A-Za-z0-9_./-]+@([0-9a-f]{40})\b")

wf_dir = ROOT / ".github" / "workflows"
if wf_dir.is_dir():
    for yml in sorted(wf_dir.glob("*.yml")):
        for line_no, line in enumerate(yml.read_text(encoding="utf-8").splitlines(), 1):
            if "uses:" not in line:
                continue
            if _USES_SHA.match(line):
                continue
            m = _USES_FLOATING.match(line)
            if m:
                _err(
                    f"{yml.relative_to(ROOT)}:{line_no}: floating tag '@{m.group(1)}' "
                    "(use 40-char commit SHA per ADR-015 Doctrine 6 / sha_pin_review.md)"
                )

# 4. NO_TOUCH doc/hook existence ------------------------------------------

doc = ROOT / "docs" / "governance" / "no_touch_paths.md"
hook = ROOT / ".claude" / "hooks" / "deny_no_touch.py"
if not doc.is_file():
    _err(f"missing: {doc.relative_to(ROOT)}")
if not hook.is_file():
    _err(f"missing: {hook.relative_to(ROOT)}")
else:
    hook_text = hook.read_text(encoding="utf-8")
    if "NO_TOUCH_GLOBS" not in hook_text:
        _err(f"{hook.relative_to(ROOT)}: NO_TOUCH_GLOBS constant missing")

# 5. Hook scripts use run_pre_hook ----------------------------------------

hooks_dir = ROOT / ".claude" / "hooks"
expected_runtime_users = {
    "deny_no_touch.py",
    "deny_dangerous_bash.py",
    "deny_test_weakening.py",
    "deny_config_read.py",
    "deny_live_connector.py",
    "deny_outside_agent_allowlist.py",
}
for py in sorted(hooks_dir.glob("*.py")):
    if py.name not in expected_runtime_users:
        continue
    text = py.read_text(encoding="utf-8")
    if "run_pre_hook" not in text:
        _err(
            f"{py.relative_to(ROOT)}: does not import run_pre_hook from "
            "_hook_runtime (fail-closed wrapper required for deny hooks)"
        )

# Result -------------------------------------------------------------------

if ERRORS:
    print("Governance lint FAILED:")
    for e in ERRORS:
        print(f"  - {e}")
    sys.exit(1)

n_agents = len(list(agents_dir.glob("*.md"))) if agents_dir.is_dir() else 0
n_workflows = len(list(wf_dir.glob("*.yml"))) if wf_dir.is_dir() else 0
print(f"Governance lint OK ({n_agents} agents, {n_workflows} workflows checked).")
