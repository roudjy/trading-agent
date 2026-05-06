"""v3.15.16.10 Phase B — exhaustive test matrix for the
``reporting.execution_authority`` classifier.

Pinned by the canonical policy doc
``docs/governance/execution_authority.md``. Every cell of the
policy matrix is asserted; the tests are organised in seven
tiers matching the doc's "Test matrix expectations" section.

The test cardinality target from the doc is 70-90 individual
test functions, runtime under 1 second.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

from reporting import approval_policy as ap
from reporting import execution_authority as ea

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


# ---------------------------------------------------------------------------
# Tier 1 — vocabulary integrity
# ---------------------------------------------------------------------------


def test_action_types_pinned() -> None:
    """The 24-value enum must match the doc verbatim."""
    expected = {
        # Read
        "file_read",
        "test_run",
        "governance_lint_run",
        "protocol_dry_run",
        "artifact_regenerate",
        # Modify
        "file_edit",
        "file_create",
        "file_delete",
        # Git
        "branch_create",
        "commit_create",
        "branch_push",
        "pr_open",
        "pr_squash_merge",
        # Always-deny git
        "pr_force_push",
        "main_direct_push",
        "branch_protection_bypass",
        # Always-deny remote
        "remote_ssh",
        "remote_curl",
        # Always-deny live
        "live_broker_call",
        "live_capital_move",
        # Always-deny test
        "test_weaken",
        # Always-deny frozen
        "frozen_contract_mutate",
        # Operator-only
        "approval_inbox_decide",
        "agent_allowlist_widen",
    }
    assert set(ea.ACTION_TYPES) == expected
    assert len(ea.ACTION_TYPES) == 24
    # No duplicates.
    assert len(set(ea.ACTION_TYPES)) == len(ea.ACTION_TYPES)


def test_target_path_categories_pinned() -> None:
    expected = {
        "claude_governance_hook",
        "dashboard_wiring",
        "frozen_contract",
        "live_path",
        "branch_protection_config",
        "deploy_script",
        "canonical_policy_doc",
        "canonical_roadmap",
        "ci_workflow",
        "reporting_module",
        "dashboard_api",
        "frontend",
        "test",
        "doc_non_policy",
        "other",
    }
    assert set(ea.TARGET_PATH_CATEGORIES) == expected
    assert len(ea.TARGET_PATH_CATEGORIES) == 15
    assert len(set(ea.TARGET_PATH_CATEGORIES)) == len(ea.TARGET_PATH_CATEGORIES)


def test_decisions_pinned() -> None:
    assert set(ea.DECISIONS) == {
        "AUTO_ALLOWED",
        "NEEDS_HUMAN",
        "PERMANENTLY_DENIED",
    }


def test_reasons_pinned() -> None:
    expected = {
        # AUTO_ALLOWED
        "low_risk_read_only_projection",
        "low_risk_frontend_read_only",
        "low_risk_test_addition",
        "low_risk_docs_non_policy",
        "pure_read_no_side_effect",
        # NEEDS_HUMAN
        "high_risk_governance_change",
        "high_risk_canonical_policy_change",
        "high_risk_canonical_roadmap_change",
        "agent_allowlist_widening",
        "deploy_script_modification",
        "ci_workflow_modification",
        "dashboard_wiring_modification",
        "claude_governance_hook_modification",
        "approval_inbox_decision",
        "unknown_risk_or_target_fail_safe",
        # PERMANENTLY_DENIED
        "denied_frozen_contract_mutation",
        "denied_live_path_modification",
        "denied_branch_protection_bypass",
        "denied_main_direct_push",
        "denied_pr_force_push",
        "denied_remote_ssh",
        "denied_remote_curl",
        "denied_live_broker_call",
        "denied_live_capital_move",
        "denied_test_weakening",
    }
    assert set(ea.REASONS) == expected


def test_risk_classes_match_approval_policy() -> None:
    assert ea.RISK_CLASSES == ap.RISK_CLASSES
    assert ea.RISK_LOW == ap.RISK_LOW
    assert ea.RISK_MEDIUM == ap.RISK_MEDIUM
    assert ea.RISK_HIGH == ap.RISK_HIGH
    assert ea.RISK_UNKNOWN == ap.RISK_UNKNOWN


# ---------------------------------------------------------------------------
# Tier 2 — path categorization (one assert per row of the doc table)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path,expected",
    [
        (".claude/hooks/foo.py", "claude_governance_hook"),
        (".claude/agents/foo.md", "claude_governance_hook"),
        ("dashboard/dashboard.py", "dashboard_wiring"),
        ("dashboard/api_agent_control.py", "dashboard_api"),
        ("research/research_latest.json", "frozen_contract"),
        ("research/strategy_matrix.csv", "frozen_contract"),
        ("automation/live_gate.py", "live_path"),
        ("broker/whatever.py", "live_path"),
        ("agent/risk/policy.py", "live_path"),
        ("agent/execution/runner.py", "live_path"),
        ("scripts/deploy_vps_dashboard.sh", "deploy_script"),
        ("scripts/deploy.sh", "deploy_script"),
        ("docs/governance/execution_authority.md", "canonical_policy_doc"),
        ("docs/governance/no_touch_paths.md", "canonical_policy_doc"),
        (
            "docs/governance/observability_security_hardening.md",
            "canonical_policy_doc",
        ),
        ("docs/roadmap/qre_roadmap_v6_1.md", "canonical_roadmap"),
        (".github/workflows/tests.yml", "ci_workflow"),
        ("reporting/proposal_queue.py", "reporting_module"),
        ("tests/unit/foo.py", "test"),
        ("tests/smoke/bar.py", "test"),
        ("tests/integration/baz.py", "test"),
        ("tests/resilience/qux.py", "test"),
        ("tests/functional/quux.py", "test"),
        ("tests/regression/foo.py", "other"),
        ("docs/operator/getting_started.md", "doc_non_policy"),
        ("frontend/src/App.tsx", "frontend"),
        ("random/path.py", "other"),
    ],
)
def test_categorize_path_table(path: str, expected: str) -> None:
    assert ea._categorize_path(path) == expected


def test_categorize_empty_path_returns_other() -> None:
    assert ea._categorize_path("") == "other"


def test_categorize_branch_protection_config() -> None:
    """Pinned even though no exact such file ships today; the rule
    must be ready for a future repo-config addition."""
    assert (
        ea._categorize_path(".github/branch_protection_main.yml")
        == "branch_protection_config"
    )


def test_categorize_dashboard_wiring_exact_only() -> None:
    """``dashboard/dashboard.py`` (exact) is wiring; siblings under
    ``dashboard/`` that start with ``api_`` are ``dashboard_api``."""
    assert ea._categorize_path("dashboard/dashboard.py") == "dashboard_wiring"
    assert ea._categorize_path("dashboard/api_anything.py") == "dashboard_api"


def test_categorize_handles_windows_separators() -> None:
    """Backslashes are normalized to forward slashes."""
    assert (
        ea._categorize_path("dashboard\\dashboard.py") == "dashboard_wiring"
    )


# ---------------------------------------------------------------------------
# Tier 3 — permanent-deny pinning
# ---------------------------------------------------------------------------


_ALL_RISK_CLASSES = ("LOW", "MEDIUM", "HIGH", "UNKNOWN")
_ALL_CATEGORY_REPRESENTATIVES: dict[str, str] = {
    "claude_governance_hook": ".claude/hooks/foo.py",
    "dashboard_wiring": "dashboard/dashboard.py",
    "frozen_contract": "research/research_latest.json",
    "live_path": "automation/live_gate.py",
    "branch_protection_config": ".github/branch_protection_main.yml",
    "deploy_script": "scripts/deploy_vps_dashboard.sh",
    "canonical_policy_doc": "docs/governance/execution_authority.md",
    "canonical_roadmap": "docs/roadmap/qre_roadmap_v6_1.md",
    "ci_workflow": ".github/workflows/tests.yml",
    "reporting_module": "reporting/foo.py",
    "dashboard_api": "dashboard/api_x.py",
    "frontend": "frontend/src/App.tsx",
    "test": "tests/unit/foo.py",
    "doc_non_policy": "docs/operator/note.md",
    "other": "random/path.py",
}


@pytest.mark.parametrize(
    "action_type,expected_reason",
    [
        ("pr_force_push", "denied_pr_force_push"),
        ("main_direct_push", "denied_main_direct_push"),
        ("branch_protection_bypass", "denied_branch_protection_bypass"),
        ("remote_ssh", "denied_remote_ssh"),
        ("remote_curl", "denied_remote_curl"),
        ("live_broker_call", "denied_live_broker_call"),
        ("live_capital_move", "denied_live_capital_move"),
        ("test_weaken", "denied_test_weakening"),
        ("frozen_contract_mutate", "denied_frozen_contract_mutation"),
    ],
)
def test_action_level_permanent_deny(
    action_type: str, expected_reason: str
) -> None:
    """Each action-level deny applies regardless of category and risk.
    Exhaustively cover every (category, risk_class) combination."""
    for category, sample_path in _ALL_CATEGORY_REPRESENTATIVES.items():
        for risk in _ALL_RISK_CLASSES:
            d = ea.classify(
                action_type=action_type,
                target_path=sample_path,
                risk_class=risk,
            )
            assert d.decision == "PERMANENTLY_DENIED", (
                action_type,
                category,
                risk,
                d,
            )
            assert d.reason == expected_reason, (
                action_type,
                category,
                risk,
                d,
            )


@pytest.mark.parametrize(
    "category,expected_reason",
    [
        ("frozen_contract", "denied_frozen_contract_mutation"),
        ("live_path", "denied_live_path_modification"),
        ("branch_protection_config", "denied_branch_protection_bypass"),
    ],
)
@pytest.mark.parametrize("modify_action", ["file_edit", "file_create", "file_delete"])
def test_modify_protected_category_permanent_deny(
    category: str, expected_reason: str, modify_action: str
) -> None:
    sample = _ALL_CATEGORY_REPRESENTATIVES[category]
    for risk in _ALL_RISK_CLASSES:
        d = ea.classify(
            action_type=modify_action,
            target_path=sample,
            risk_class=risk,
        )
        assert d.decision == "PERMANENTLY_DENIED", (modify_action, risk, d)
        assert d.reason == expected_reason, (modify_action, risk, d)


def test_file_read_on_protected_category_is_not_denied() -> None:
    """The category-level deny applies only to modify actions. Read
    is allowed against frozen / live / branch-protection paths."""
    for category in ("frozen_contract", "live_path", "branch_protection_config"):
        sample = _ALL_CATEGORY_REPRESENTATIVES[category]
        d = ea.classify(action_type="file_read", target_path=sample)
        assert d.decision == "AUTO_ALLOWED", (category, d)
        assert d.reason == "pure_read_no_side_effect"


# ---------------------------------------------------------------------------
# Tier 4 — needs-human pinning (one row per doc table line)
# ---------------------------------------------------------------------------


def test_modify_claude_governance_hook_needs_human() -> None:
    d = ea.classify(
        action_type="file_edit",
        target_path=".claude/hooks/deny_no_touch.py",
        risk_class="LOW",
    )
    assert d.decision == "NEEDS_HUMAN"
    assert d.reason == "claude_governance_hook_modification"


def test_modify_dashboard_wiring_needs_human() -> None:
    d = ea.classify(
        action_type="file_edit",
        target_path="dashboard/dashboard.py",
        risk_class="LOW",
    )
    assert d.decision == "NEEDS_HUMAN"
    assert d.reason == "dashboard_wiring_modification"


def test_modify_canonical_policy_doc_needs_human() -> None:
    d = ea.classify(
        action_type="file_edit",
        target_path="docs/governance/execution_authority.md",
        risk_class="LOW",
    )
    assert d.decision == "NEEDS_HUMAN"
    assert d.reason == "high_risk_canonical_policy_change"


def test_modify_canonical_roadmap_needs_human() -> None:
    d = ea.classify(
        action_type="file_edit",
        target_path="docs/roadmap/qre_roadmap_v6_1.md",
        risk_class="LOW",
    )
    assert d.decision == "NEEDS_HUMAN"
    assert d.reason == "high_risk_canonical_roadmap_change"


def test_modify_deploy_script_needs_human() -> None:
    d = ea.classify(
        action_type="file_edit",
        target_path="scripts/deploy_vps_dashboard.sh",
        risk_class="LOW",
    )
    assert d.decision == "NEEDS_HUMAN"
    assert d.reason == "deploy_script_modification"


def test_modify_ci_workflow_needs_human() -> None:
    d = ea.classify(
        action_type="file_edit",
        target_path=".github/workflows/tests.yml",
        risk_class="LOW",
    )
    assert d.decision == "NEEDS_HUMAN"
    assert d.reason == "ci_workflow_modification"


def test_agent_allowlist_widen_needs_human() -> None:
    d = ea.classify(action_type="agent_allowlist_widen", target_path=None)
    assert d.decision == "NEEDS_HUMAN"
    assert d.reason == "agent_allowlist_widening"


def test_approval_inbox_decide_needs_human() -> None:
    d = ea.classify(action_type="approval_inbox_decide", target_path=None)
    assert d.decision == "NEEDS_HUMAN"
    assert d.reason == "approval_inbox_decision"


def test_high_risk_on_otherwise_auto_category_needs_human() -> None:
    d = ea.classify(
        action_type="file_edit",
        target_path="reporting/foo.py",
        risk_class="HIGH",
    )
    assert d.decision == "NEEDS_HUMAN"
    assert d.reason == "high_risk_governance_change"


def test_unknown_risk_modify_always_needs_human() -> None:
    d = ea.classify(
        action_type="file_edit",
        target_path="reporting/foo.py",
        risk_class="UNKNOWN",
    )
    assert d.decision == "NEEDS_HUMAN"
    assert d.reason == "unknown_risk_or_target_fail_safe"


def test_other_target_category_modify_needs_human() -> None:
    d = ea.classify(
        action_type="file_edit",
        target_path="random/path.py",
        risk_class="LOW",
    )
    assert d.decision == "NEEDS_HUMAN"
    assert d.reason == "unknown_risk_or_target_fail_safe"


# ---------------------------------------------------------------------------
# Tier 5 — auto-allowed pinning (one row per doc table line)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "action_type",
    [
        "file_read",
        "test_run",
        "governance_lint_run",
        "protocol_dry_run",
        "artifact_regenerate",
    ],
)
def test_pure_reads_always_auto_allowed(action_type: str) -> None:
    """Pure reads bypass risk-class escalation. Every category and
    every risk_class yields AUTO_ALLOWED."""
    for category, sample in _ALL_CATEGORY_REPRESENTATIVES.items():
        for risk in _ALL_RISK_CLASSES:
            d = ea.classify(
                action_type=action_type,
                target_path=sample,
                risk_class=risk,
            )
            assert d.decision == "AUTO_ALLOWED", (action_type, category, risk, d)
            assert d.reason == "pure_read_no_side_effect"


def test_low_risk_reporting_module_edit_auto_allowed() -> None:
    d = ea.classify(
        action_type="file_edit",
        target_path="reporting/foo.py",
        risk_class="LOW",
    )
    assert d.decision == "AUTO_ALLOWED"
    assert d.reason == "low_risk_read_only_projection"


def test_low_risk_dashboard_api_edit_auto_allowed() -> None:
    d = ea.classify(
        action_type="file_edit",
        target_path="dashboard/api_x.py",
        risk_class="LOW",
    )
    assert d.decision == "AUTO_ALLOWED"
    assert d.reason == "low_risk_read_only_projection"


def test_low_risk_frontend_edit_auto_allowed() -> None:
    d = ea.classify(
        action_type="file_edit",
        target_path="frontend/src/App.tsx",
        risk_class="LOW",
    )
    assert d.decision == "AUTO_ALLOWED"
    assert d.reason == "low_risk_frontend_read_only"


def test_low_risk_test_edit_auto_allowed() -> None:
    d = ea.classify(
        action_type="file_create",
        target_path="tests/unit/test_foo.py",
        risk_class="LOW",
    )
    assert d.decision == "AUTO_ALLOWED"
    assert d.reason == "low_risk_test_addition"


def test_low_risk_doc_non_policy_edit_auto_allowed() -> None:
    d = ea.classify(
        action_type="file_edit",
        target_path="docs/operator/note.md",
        risk_class="LOW",
    )
    assert d.decision == "AUTO_ALLOWED"
    assert d.reason == "low_risk_docs_non_policy"


@pytest.mark.parametrize(
    "git_action",
    ["branch_create", "commit_create", "branch_push", "pr_open", "pr_squash_merge"],
)
def test_low_risk_composite_git_actions_auto_allowed_on_auto_category(
    git_action: str,
) -> None:
    d = ea.classify(
        action_type=git_action,
        target_path="reporting/foo.py",
        risk_class="LOW",
    )
    assert d.decision == "AUTO_ALLOWED"
    assert d.reason == "low_risk_read_only_projection"


@pytest.mark.parametrize(
    "git_action",
    ["branch_create", "commit_create", "branch_push", "pr_open", "pr_squash_merge"],
)
def test_low_risk_composite_git_actions_auto_allowed_with_no_target(
    git_action: str,
) -> None:
    """For aggregated calls (caller has already verified every touched
    path is auto-allowed), passing ``target_path=None`` is the
    canonical aggregate signal. Returns AUTO_ALLOWED."""
    d = ea.classify(action_type=git_action, target_path=None, risk_class="LOW")
    assert d.decision == "AUTO_ALLOWED"
    assert d.reason == "low_risk_read_only_projection"


# ---------------------------------------------------------------------------
# Tier 6 — precedence pinning
# ---------------------------------------------------------------------------


def test_permanent_deny_overrides_risk_class() -> None:
    """``pr_force_push`` with risk LOW is still PERMANENTLY_DENIED."""
    d = ea.classify(
        action_type="pr_force_push", target_path=None, risk_class="LOW"
    )
    assert d.decision == "PERMANENTLY_DENIED"
    assert d.reason == "denied_pr_force_push"


def test_protected_path_overrides_low_risk_auto_allow() -> None:
    """``file_edit`` on ``live_path`` with risk LOW is PERMANENTLY_DENIED."""
    d = ea.classify(
        action_type="file_edit",
        target_path="automation/live_gate.py",
        risk_class="LOW",
    )
    assert d.decision == "PERMANENTLY_DENIED"
    assert d.reason == "denied_live_path_modification"


def test_high_risk_overrides_low_risk_auto_categories() -> None:
    """HIGH risk on ``reporting_module`` is NEEDS_HUMAN, not AUTO."""
    d = ea.classify(
        action_type="file_edit",
        target_path="reporting/foo.py",
        risk_class="HIGH",
    )
    assert d.decision == "NEEDS_HUMAN"
    assert d.reason == "high_risk_governance_change"


def test_unknown_risk_always_needs_human_on_modify() -> None:
    """UNKNOWN risk on any auto category is NEEDS_HUMAN."""
    for category in ("reporting_module", "dashboard_api", "frontend", "test", "doc_non_policy"):
        sample = _ALL_CATEGORY_REPRESENTATIVES[category]
        d = ea.classify(
            action_type="file_edit", target_path=sample, risk_class="UNKNOWN"
        )
        assert d.decision == "NEEDS_HUMAN", (category, d)
        assert d.reason == "unknown_risk_or_target_fail_safe"


def test_default_fallback_is_needs_human_not_auto_allowed() -> None:
    """Unknown action_type → NEEDS_HUMAN with the fail-safe reason."""
    d = ea.classify(
        action_type="some_future_unknown_action",
        target_path="reporting/foo.py",
        risk_class="LOW",
    )
    assert d.decision == "NEEDS_HUMAN"
    assert d.reason == "unknown_risk_or_target_fail_safe"


def test_file_read_on_protected_path_still_auto_allowed() -> None:
    for category in (
        "claude_governance_hook",
        "dashboard_wiring",
        "frozen_contract",
        "live_path",
        "branch_protection_config",
    ):
        sample = _ALL_CATEGORY_REPRESENTATIVES[category]
        d = ea.classify(action_type="file_read", target_path=sample)
        assert d.decision == "AUTO_ALLOWED", (category, d)
        assert d.reason == "pure_read_no_side_effect"


def test_protected_category_modify_overrides_high_risk() -> None:
    """A modify on ``frozen_contract`` is PERMANENTLY_DENIED even when
    the caller passes risk_class=HIGH (which would otherwise route to
    NEEDS_HUMAN). Permanent-deny precedes risk."""
    d = ea.classify(
        action_type="file_edit",
        target_path="research/research_latest.json",
        risk_class="HIGH",
    )
    assert d.decision == "PERMANENTLY_DENIED"
    assert d.reason == "denied_frozen_contract_mutation"


def test_modify_canonical_policy_doc_high_risk_still_canonical_policy_reason() -> None:
    """Category-level NEEDS_HUMAN beats the generic HIGH-risk reason
    because category-level rules run first in the precedence order."""
    d = ea.classify(
        action_type="file_edit",
        target_path="docs/governance/execution_authority.md",
        risk_class="HIGH",
    )
    assert d.decision == "NEEDS_HUMAN"
    assert d.reason == "high_risk_canonical_policy_change"


# ---------------------------------------------------------------------------
# Tier 7 — module invariants
# ---------------------------------------------------------------------------


def test_classify_is_deterministic() -> None:
    """10 calls with identical input return identical output."""
    args = dict(
        action_type="file_edit",
        target_path="reporting/foo.py",
        risk_class="LOW",
    )
    first = ea.classify(**args)
    for _ in range(10):
        d = ea.classify(**args)
        assert d == first


def _module_source() -> str:
    return (REPO_ROOT / "reporting" / "execution_authority.py").read_text(
        encoding="utf-8"
    )


def _strip_strings_and_comments(src: str) -> str:
    """Return source with all string literals and ``#`` comments
    blanked out so token-level scans only see executable code.

    Mirrors the helper used in the v3.15.16.9 ``test_governance_bootstrap``
    source-text invariants — without it, a token matched in our own
    docstring's "do not import" prose would falsely fail the test."""
    import io
    import tokenize

    out: list[str] = []
    try:
        tokens = tokenize.generate_tokens(io.StringIO(src).readline)
        for tok in tokens:
            if tok.type in (tokenize.STRING, tokenize.COMMENT):
                # Replace string/comment payloads with whitespace
                # placeholder to preserve line/column positions.
                placeholder = " " * (len(tok.string) or 1)
                out.append(placeholder)
            else:
                out.append(tok.string)
    except tokenize.TokenizeError:
        return src
    return "".join(out)


def test_no_subprocess_in_module() -> None:
    src = _strip_strings_and_comments(_module_source())
    assert "import subprocess" not in src
    assert "from subprocess" not in src


def test_no_network_in_module() -> None:
    src = _strip_strings_and_comments(_module_source())
    forbidden = (
        "import socket",
        "from socket",
        "import http.client",
        "from http.client",
        "import urllib",
        "from urllib",
        "import requests",
        "from requests",
    )
    for token in forbidden:
        assert token not in src, f"forbidden network import: {token!r}"


def test_no_dashboard_py_import() -> None:
    src = _strip_strings_and_comments(_module_source())
    assert "import dashboard" not in src
    assert "from dashboard" not in src


def test_no_live_path_import() -> None:
    src = _strip_strings_and_comments(_module_source())
    forbidden = (
        "automation.live_gate",
        "from automation",
        "import broker",
        "from broker",
        "agent.risk",
        "from agent.risk",
        "agent.execution",
        "from agent.execution",
    )
    for token in forbidden:
        assert token not in src, f"forbidden live-path import: {token!r}"


def test_no_gh_or_git_invocation_in_module() -> None:
    src = _strip_strings_and_comments(_module_source())
    forbidden = ("Popen", "os.system")
    for token in forbidden:
        assert token not in src, f"forbidden token: {token!r}"


def test_evidence_dict_contains_only_bounded_scalars() -> None:
    """Evidence is a flat scalar dict — no list / dict / tuple body
    payloads, only strings (and primitives)."""
    d = ea.classify(
        action_type="file_edit",
        target_path="reporting/foo.py",
        risk_class="LOW",
    )
    expected_keys = {
        "action_type",
        "target_path",
        "target_path_category",
        "risk_class",
    }
    assert set(d.evidence.keys()) == expected_keys
    for k, v in d.evidence.items():
        assert isinstance(v, str), f"non-string evidence value at {k}: {type(v)}"


def test_evidence_never_carries_pr_body_proposed_patch_file_diff() -> None:
    """Defensive: a synthetic call must not produce any forbidden
    token in the evidence payload."""
    d = ea.classify(
        action_type="pr_open",
        target_path="reporting/foo.py",
        risk_class="LOW",
    )
    text = json.dumps(d.evidence)
    forbidden = (
        "proposed_patch",
        "pr_body",
        "file_diff",
        "commit_message",
        "patch",
        "diff",
        "body",
    )
    for tok in forbidden:
        assert tok not in text, f"evidence leaks token: {tok!r}"


def test_execution_decision_is_frozen_dataclass() -> None:
    d = ea.classify(action_type="file_read", target_path="reporting/foo.py")
    with pytest.raises(dataclasses.FrozenInstanceError):
        d.decision = "MUTATED"  # type: ignore[misc]


def test_module_version_pinned() -> None:
    assert ea.MODULE_VERSION == "v3.15.16.10"
    assert ea.SCHEMA_VERSION == 1
