"""Tests for .claude/hooks/deny_no_touch.py.

Verifies path-pattern matching, the doc/hook sync invariant, and a
representative sample of every category in NO_TOUCH_GLOBS.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
HOOKS_DIR = REPO_ROOT / ".claude" / "hooks"


def _import_no_touch():
    sys.path.insert(0, str(HOOKS_DIR))
    if "deny_no_touch" in sys.modules:
        del sys.modules["deny_no_touch"]
    return importlib.import_module("deny_no_touch")


@pytest.fixture
def hook():
    return _import_no_touch()


# ---------------------------------------------------------------------------
# Pattern matching — by category
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "automation/live_gate.py",
        "config/config.yaml",
        "research/authority_views.py",
        "research/authority_trace.py",
        "research/candidate_lifecycle.py",
        "research/promotion.py",
        "research/strategy_hypothesis_catalog.py",
        "research/campaign_funnel_policy.py",
        "research/campaign_evidence_ledger.py",
        "research/paper_ledger.py",
        "orchestration/orchestrator.py",
        "agent/backtesting/engine.py",
        "agent/backtesting/fitted_features.py",
        "docker-compose.prod.yml",
        "scripts/deploy.sh",
        "ops/systemd/foo.service",
        "ops/nginx/nginx.conf",
        "research/candidate_registry_latest.v1.json",
        "research/campaign_evidence_ledger_latest.v1.jsonl",
        "docs/adr/ADR-014-truth-authority-settlement.md",
        "tests/regression/test_v3_15_pin_alpha.py",
        "tests/regression/test_v3_15_artifacts_deterministic.py",
        "tests/regression/test_authority_invariants.py",
        ".claude/settings.json",
        ".claude/hooks/deny_no_touch.py",
        ".claude/agents/planner.md",
        ".github/CODEOWNERS",
        "VERSION",
        "docs/governance/agent_governance.md",
        "docs/governance/no_touch_paths.md",
        "docs/governance/release_gate.md",
        # R5.2: backend non-core directories
        "agent/brain/agent.py",
        "agent/brain/signal_aggregator.py",
        "agent/execution/order_executor.py",
        "agent/learning/reporter.py",
        "agent/learning/self_improver.py",
        "agent/agents/rsi_agent.py",
        "agent/risk/manager.py",
        "agent/monitoring/health.py",
        "dashboard/dashboard.py",
        # R5.2: full directory expansions
        "automation/some_new_file.py",
        "execution/protocols.py",
        "research/some_new_module.py",
        "strategies/momentum.py",
        "Dockerfile",
    ],
)
def test_no_touch_paths_match(hook, path):
    assert hook._match_no_touch(path) is not None, f"expected deny for {path}"


@pytest.mark.parametrize(
    "path",
    [
        "tests/unit/test_x.py",
        "tests/smoke/test_y.py",
        "frontend/src/Foo.tsx",
        "dashboard/api_campaigns.py",
        "docs/backlog/agent_backlog.md",
        "docs/spillovers/agent_spillovers.md",
        "docs/governance/agent_run_summaries/abc.md",
        "reporting/agent_audit.py",
    ],
)
def test_allowed_paths_pass(hook, path):
    assert hook._match_no_touch(path) is None, f"expected allow for {path}"


# ---------------------------------------------------------------------------
# check() entrypoint
# ---------------------------------------------------------------------------


def test_check_passes_for_unrelated_tool(hook):
    payload = {"tool_name": "Bash", "tool_input": {"command": "ls"}}
    allow, reason = hook.check(payload)
    assert allow
    assert reason is None


def test_check_blocks_edit_to_live_gate(hook):
    payload = {
        "tool_name": "Edit",
        "tool_input": {"file_path": "automation/live_gate.py"},
    }
    allow, reason = hook.check(payload)
    assert not allow
    assert "live_gate" in reason


def test_check_handles_backslash_paths(hook):
    """Windows-style paths are normalized to forward slashes."""
    payload = {
        "tool_name": "Write",
        "tool_input": {"file_path": "automation\\live_gate.py"},
    }
    allow, _ = hook.check(payload)
    assert not allow


# ---------------------------------------------------------------------------
# Doc / hook synchronization invariant
# ---------------------------------------------------------------------------


def test_no_touch_globs_appear_in_doc(hook):
    doc = (REPO_ROOT / "docs" / "governance" / "no_touch_paths.md").read_text(encoding="utf-8")
    # Every glob in the hook should appear (verbatim, possibly inside backticks)
    # somewhere in the doc. We accept either the bare glob or a backticked
    # variant, because the doc renders pretty.
    missing = []
    # A small allowlist of patterns that are described conceptually but not
    # listed verbatim (e.g. duplicate **/* variants for fnmatch coverage).
    conceptual_only = {
        "automation/*.secret",
        "ops/systemd/*",
        "ops/nginx/*",
        "**/*_latest.v1.json",
        "**/*_latest.v1.jsonl",
        ".claude/hooks/*",
        ".claude/agents/*",
    }
    for glob in hook.NO_TOUCH_GLOBS:
        if glob in conceptual_only:
            continue
        if glob in doc:
            continue
        # Accept "without the trailing /*" form, e.g. ops/systemd/** vs ops/systemd/*
        if glob.replace("/*", "/").rstrip("/") in doc:
            continue
        missing.append(glob)
    assert not missing, (
        f"NO_TOUCH_GLOBS entries missing from docs/governance/no_touch_paths.md: {missing}"
    )
