#!/usr/bin/env python3
"""PreToolUse Edit|Write — deny writes to no-touch paths.

Single source of patterns is ``docs/governance/no_touch_paths.md``.
This module reads the patterns from a sibling Python list (kept in sync
with the doc and verified by ``tests/unit/test_hooks_no_touch.py``) so
the hook runs without parsing markdown.

Revision 5 hardening:
  - NO_TOUCH expanded to cover agent/{brain,execution,learning,agents,
    risk,monitoring}/**, dashboard/dashboard.py, plus full automation/,
    execution/, orchestration/, research/, strategies/ directories.
  - _normalize() now resolves symlinks (so a symlink to a no-touch path
    is detected) and is case-insensitive on Windows.
"""

from __future__ import annotations

import fnmatch
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _hook_runtime import run_pre_hook  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# ---------------------------------------------------------------------------
# No-touch glob patterns. Each pattern is matched with ``fnmatch.fnmatchcase``
# against the *normalized* relative path (forward slashes, lowercased on
# Windows). Add new entries here AND in docs/governance/no_touch_paths.md
# (the test suite checks they stay in sync).
# ---------------------------------------------------------------------------

NO_TOUCH_GLOBS: tuple[str, ...] = (
    # Live trading / capital
    "automation/live_gate.py",
    "automation/*.secret",
    "state/*.secret",

    # Secrets (also handled separately as read-deny)
    "config/config.yaml",
    ".env",
    ".env.*",

    # Authority surface (ADR-014) — explicit list kept for documentation;
    # the broader research/** pattern below covers all of them too.
    "research/authority_views.py",
    "research/authority_trace.py",
    "research/candidate_lifecycle.py",
    "research/candidate_pipeline.py",
    "research/candidate_registry_v2.py",
    "research/campaign_funnel_policy.py",
    "research/campaign_preset_policy.py",
    "research/campaign_family_policy.py",
    "research/promotion.py",
    "research/strategy_hypothesis_catalog.py",
    "research/campaign_evidence_ledger.py",
    "research/research_evidence_ledger.py",
    "research/paper_ledger.py",
    "research/screening_evidence.py",

    # R5.2 - full backend code surface (no agent should be writing here):
    "agent/brain/*",
    "agent/brain/**",
    "agent/execution/*",
    "agent/execution/**",
    "agent/learning/*",
    "agent/learning/**",
    "agent/agents/*",
    "agent/agents/**",
    "agent/risk/*",
    "agent/risk/**",
    "agent/monitoring/*",
    "agent/monitoring/**",

    # R5.2 - dashboard core (api_observability.py is allowed via
    # observability-guardian; main dashboard.py reads operator secrets).
    "dashboard/dashboard.py",

    # R5.2 - full directories that contain trading logic / authority
    # surface. Specific files are listed above for documentation parity.
    "automation/*",
    "automation/**",
    "execution/*",
    "execution/**",
    "orchestration/*",
    "orchestration/**",
    "research/*",
    "research/**",
    "strategies/*",
    "strategies/**",

    # Orchestration core (ADR-009) and backtest core (kept explicit too)
    "orchestration/orchestrator.py",
    "agent/backtesting/engine.py",
    "agent/backtesting/fitted_features.py",

    # Production posture
    "docker-compose.prod.yml",
    "scripts/deploy.sh",
    "ops/systemd/*",
    "ops/systemd/**",
    "ops/nginx/*",
    "Dockerfile",

    # Frozen v1 schemas (anywhere)
    "*_latest.v1.json",
    "*_latest.v1.jsonl",
    "**/*_latest.v1.json",
    "**/*_latest.v1.jsonl",

    # ADRs (existing - drafts go to docs/adr/_drafts/ via ask)
    "docs/adr/ADR-*.md",

    # Determinism pin tests
    "tests/regression/test_v3_*pin*.py",
    "tests/regression/test_v3_15_artifacts_deterministic.py",
    "tests/regression/test_authority_invariants.py",
    "tests/regression/test_v3_15_8_canonical_dump_and_digest.py",

    # Governance layer - self-protected after seed
    ".claude/settings.json",
    ".claude/hooks/*",
    ".claude/hooks/**",
    ".claude/agents/*",
    ".claude/agents/**",
    ".github/CODEOWNERS",

    # VERSION - bump only via Release Gate-recommended human-approved PR
    "VERSION",

    # Governance core docs (writable only by planner / PO / release-gate-agent)
    "docs/governance/agent_governance.md",
    "docs/governance/autonomy_ladder.md",
    "docs/governance/no_touch_paths.md",
    "docs/governance/permission_model.md",
    "docs/governance/no_test_weakening.md",
    "docs/governance/hooks_runtime_policy.md",
    "docs/governance/provenance.md",
    "docs/governance/audit_chain.md",
    "docs/governance/release_gate.md",
    "docs/governance/release_gate_checklist.md",
    "docs/governance/rollback_drill.md",
    "docs/governance/sha_pin_review.md",
)


def _normalize(p: str) -> str:
    """Normalize a path for pattern matching.

    Revision 5: resolve symlinks (so ``ln -s automation/live_gate.py
    safe.py`` is detected as a no-touch write), strip the repo-root
    prefix from absolute paths, lowercase on Windows for
    case-insensitive matching.
    """
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


def _match_no_touch(rel_path: str) -> str | None:
    n = _normalize(rel_path)
    for pat in NO_TOUCH_GLOBS:
        glob = pat.lower() if sys.platform == "win32" else pat
        if fnmatch.fnmatchcase(n, glob):
            return pat
    return None


def check(payload: dict[str, Any]) -> tuple[bool, str | None]:
    tool = payload.get("tool_name")
    if tool not in ("Edit", "Write", "NotebookEdit", "MultiEdit"):
        return (True, None)
    ti = payload.get("tool_input") or {}
    target = ti.get("file_path") or ti.get("path") or ti.get("notebook_path")
    if not isinstance(target, str) or not target.strip():
        return (True, None)
    pat = _match_no_touch(target)
    if pat is None:
        return (True, None)
    return (
        False,
        f"no_touch_path matched pattern '{pat}' (target: {target}). "
        "See docs/governance/no_touch_paths.md.",
    )


if __name__ == "__main__":
    sys.exit(
        run_pre_hook(
            name="deny_no_touch",
            event_phase="PreToolUse",
            check=check,
        )
    )
