"""v3.15.16.10 Phase B — Agent Execution Authority Classifier.

Deterministic, stdlib-only projection of
``docs/governance/execution_authority.md``. Tells the caller, for a
given (action_type, target_path, risk_class) tuple, whether the
action is:

* ``AUTO_ALLOWED`` — Claude may take it without operator approval;
* ``NEEDS_HUMAN`` — operator approval required through the PWA
  approval inbox before proceeding; or
* ``PERMANENTLY_DENIED`` — absolute bar; no approval path exists in
  this release.

Hard guarantees (pinned by tests):

* Stdlib-only. No subprocess, no network, no ``gh``, no ``git``.
* No imports from ``dashboard``, ``automation``, ``broker``,
  ``agent.risk``, ``agent.execution``.
* Pure function. No I/O. The classifier never reads the file at
  ``target_path``; it uses the path string only.
* Deterministic. Same input always returns the same output.
* The ``evidence`` dict on the returned ``ExecutionDecision``
  carries bounded scalars only — never PR body text, file diffs,
  proposed patches, commit messages, or template payload.

The canonical source of truth is
``docs/governance/execution_authority.md``. Any change to the
classifier output requires a matching change to that document
(operator approval, since the doc is a ``canonical_policy_doc``).
"""

from __future__ import annotations

import dataclasses
from typing import Any, Final

from reporting.approval_policy import RISK_CLASSES as APPROVAL_POLICY_RISK_CLASSES

MODULE_VERSION: Final[str] = "v3.15.16.10"
SCHEMA_VERSION: Final[int] = 1


# ---------------------------------------------------------------------------
# Closed vocabularies (mirrored from docs/governance/execution_authority.md)
# ---------------------------------------------------------------------------

# action_type — 24 values, closed.
ACTION_TYPES: Final[tuple[str, ...]] = (
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
)

_MODIFY_ACTIONS: Final[frozenset[str]] = frozenset(
    {"file_edit", "file_create", "file_delete"}
)

_PURE_READ_ACTIONS: Final[frozenset[str]] = frozenset(
    {
        "file_read",
        "test_run",
        "governance_lint_run",
        "protocol_dry_run",
        "artifact_regenerate",
    }
)

_PR_COMPOSITE_ACTIONS: Final[frozenset[str]] = frozenset(
    {
        "branch_create",
        "commit_create",
        "branch_push",
        "pr_open",
        "pr_squash_merge",
    }
)

# target_path_category — 15 values, closed.
TARGET_PATH_CATEGORIES: Final[tuple[str, ...]] = (
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
)

# risk_class — reused from reporting.approval_policy. The classifier
# MUST NOT redefine these; this re-export pins the dependency for the
# vocabulary integrity test.
RISK_CLASSES: Final[tuple[str, ...]] = APPROVAL_POLICY_RISK_CLASSES
RISK_LOW: Final[str] = "LOW"
RISK_MEDIUM: Final[str] = "MEDIUM"
RISK_HIGH: Final[str] = "HIGH"
RISK_UNKNOWN: Final[str] = "UNKNOWN"

# decision — 3 values, closed.
DECISION_AUTO_ALLOWED: Final[str] = "AUTO_ALLOWED"
DECISION_NEEDS_HUMAN: Final[str] = "NEEDS_HUMAN"
DECISION_PERMANENTLY_DENIED: Final[str] = "PERMANENTLY_DENIED"
DECISIONS: Final[tuple[str, ...]] = (
    DECISION_AUTO_ALLOWED,
    DECISION_NEEDS_HUMAN,
    DECISION_PERMANENTLY_DENIED,
)

# reason — closed vocabulary, mirrored verbatim from the doc.
REASONS: Final[tuple[str, ...]] = (
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
)


# ---------------------------------------------------------------------------
# Output dataclass
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class ExecutionDecision:
    """Pure output of ``classify(...)``.

    Invariants:

    * ``decision`` is in :data:`DECISIONS`.
    * ``reason`` is in :data:`REASONS`.
    * ``target_path_category`` is in :data:`TARGET_PATH_CATEGORIES`.
    * ``evidence`` carries bounded scalars only — no list / dict
      body content; no PR text; no diffs; no template payload.
    """

    decision: str
    reason: str
    target_path_category: str
    evidence: dict[str, Any]


# ---------------------------------------------------------------------------
# Action-type-level permanent denies (apply regardless of target & risk)
# ---------------------------------------------------------------------------

_ACTION_LEVEL_PERMANENT_DENY: Final[dict[str, str]] = {
    "pr_force_push": "denied_pr_force_push",
    "main_direct_push": "denied_main_direct_push",
    "branch_protection_bypass": "denied_branch_protection_bypass",
    "remote_ssh": "denied_remote_ssh",
    "remote_curl": "denied_remote_curl",
    "live_broker_call": "denied_live_broker_call",
    "live_capital_move": "denied_live_capital_move",
    "test_weaken": "denied_test_weakening",
    "frozen_contract_mutate": "denied_frozen_contract_mutation",
}

# ---------------------------------------------------------------------------
# Target-category-level permanent denies (modify actions only)
# ---------------------------------------------------------------------------

_CATEGORY_LEVEL_PERMANENT_DENY: Final[dict[str, str]] = {
    "frozen_contract": "denied_frozen_contract_mutation",
    "live_path": "denied_live_path_modification",
    "branch_protection_config": "denied_branch_protection_bypass",
}

# ---------------------------------------------------------------------------
# Target-category-level NEEDS_HUMAN rules (for modify actions)
# ---------------------------------------------------------------------------

_CATEGORY_LEVEL_NEEDS_HUMAN: Final[dict[str, str]] = {
    "claude_governance_hook": "claude_governance_hook_modification",
    "dashboard_wiring": "dashboard_wiring_modification",
    "canonical_policy_doc": "high_risk_canonical_policy_change",
    "canonical_roadmap": "high_risk_canonical_roadmap_change",
    "deploy_script": "deploy_script_modification",
    "ci_workflow": "ci_workflow_modification",
}

# ---------------------------------------------------------------------------
# Target-category-level AUTO_ALLOWED rules (for modify actions, LOW risk)
# ---------------------------------------------------------------------------

_CATEGORY_LEVEL_AUTO_ALLOWED: Final[dict[str, str]] = {
    "reporting_module": "low_risk_read_only_projection",
    "dashboard_api": "low_risk_read_only_projection",
    "frontend": "low_risk_frontend_read_only",
    "test": "low_risk_test_addition",
    "doc_non_policy": "low_risk_docs_non_policy",
}


# ---------------------------------------------------------------------------
# Path categorization (path string → target_path_category)
# ---------------------------------------------------------------------------


def _normalize(target_path: str) -> str:
    """Repo-relative POSIX path. Strips a leading ``./`` and converts
    backslashes to forward slashes; never reads the filesystem."""
    p = target_path.replace("\\", "/").lstrip("./")
    # ``lstrip("./")`` strips ANY mix of '.' and '/' characters from
    # the left. That is what we want here for ``./foo`` and ``foo``,
    # but we also want to leave a literal ``.claude/...`` alone — and
    # ``lstrip`` is set-based, so it would also strip the leading dot
    # of ``.claude/...``. Restore the canonical leading dot for the
    # ``.claude`` and ``.github`` namespaces.
    if not target_path.replace("\\", "/").startswith("./") and target_path.startswith(
        "."
    ):
        # The user supplied an already-leading-dot path (``.claude/..``,
        # ``.github/..``); trust it verbatim.
        return target_path.replace("\\", "/")
    return p


_LIVE_PATH_PREFIXES: Final[tuple[str, ...]] = (
    "automation/live_gate.py",
    "broker/",
    "agent/risk/",
    "agent/execution/",
)

_DEPLOY_SCRIPT_EXACT: Final[frozenset[str]] = frozenset(
    {"scripts/deploy.sh", "scripts/deploy_vps_dashboard.sh"}
)

_FROZEN_CONTRACT_EXACT: Final[frozenset[str]] = frozenset(
    {"research/research_latest.json", "research/strategy_matrix.csv"}
)

_CANONICAL_POLICY_DOC_EXACT: Final[frozenset[str]] = frozenset(
    {
        "docs/governance/execution_authority.md",
        "docs/governance/no_touch_paths.md",
        "docs/governance/observability_security_hardening.md",
    }
)

_CANONICAL_ROADMAP_EXACT: Final[str] = "docs/roadmap/qre_roadmap_v6_1.md"

_DASHBOARD_WIRING_EXACT: Final[str] = "dashboard/dashboard.py"

_TEST_DIR_PREFIXES: Final[tuple[str, ...]] = (
    "tests/smoke/",
    "tests/unit/",
    "tests/integration/",
    "tests/resilience/",
    "tests/functional/",
)


def _categorize_path(target_path: str) -> str:
    """Pure deterministic mapping from a repo-relative path string
    to a value in :data:`TARGET_PATH_CATEGORIES`. Returns ``"other"``
    for paths matching no rule. Never reads the filesystem.
    """
    if not target_path:
        return "other"
    p = _normalize(target_path)

    # Exact-match categories first (highest specificity).
    if p == _DASHBOARD_WIRING_EXACT:
        return "dashboard_wiring"
    if p in _FROZEN_CONTRACT_EXACT:
        return "frozen_contract"
    if p in _CANONICAL_POLICY_DOC_EXACT:
        return "canonical_policy_doc"
    if p == _CANONICAL_ROADMAP_EXACT:
        return "canonical_roadmap"
    if p in _DEPLOY_SCRIPT_EXACT:
        return "deploy_script"

    # Prefix / glob categories.
    if p.startswith(".claude/"):
        return "claude_governance_hook"
    for prefix in _LIVE_PATH_PREFIXES:
        if p == prefix or p.startswith(prefix):
            return "live_path"
    if p.startswith(".github/branch_protection_") and p.endswith(".yml"):
        return "branch_protection_config"
    if p.startswith(".github/workflows/") and p.endswith(".yml"):
        return "ci_workflow"
    if p.startswith("dashboard/api_") and p.endswith(".py"):
        return "dashboard_api"
    if p.startswith("reporting/") and p.endswith(".py"):
        return "reporting_module"
    if p.startswith("frontend/src/"):
        return "frontend"
    for prefix in _TEST_DIR_PREFIXES:
        if p.startswith(prefix):
            return "test"
    # docs/** — exclude policy / roadmap (already handled above).
    if p.startswith("docs/"):
        return "doc_non_policy"

    return "other"


# ---------------------------------------------------------------------------
# Classifier
# ---------------------------------------------------------------------------


def _bounded_evidence(
    *,
    action_type: str,
    target_path: str | None,
    target_path_category: str,
    risk_class: str,
) -> dict[str, Any]:
    """Build the evidence dict. Scalars only — no body content, no
    diffs, no PR text. Pinned by tests."""
    return {
        "action_type": action_type,
        "target_path": target_path if isinstance(target_path, str) else "",
        "target_path_category": target_path_category,
        "risk_class": risk_class,
    }


def classify(
    *,
    action_type: str,
    target_path: str | None,
    risk_class: str = RISK_UNKNOWN,
) -> ExecutionDecision:
    """Return the :class:`ExecutionDecision` for one action.

    Deterministic precedence (first-match wins):

    1. ``PERMANENTLY_DENIED`` rules (action-type-level)
    2. ``PERMANENTLY_DENIED`` rules (target-category-level for modify)
    3. ``NEEDS_HUMAN`` rules (target-category-level)
    4. ``NEEDS_HUMAN`` rules (operator-only action types)
    5. ``NEEDS_HUMAN`` rules (risk-class HIGH or UNKNOWN)
    6. ``NEEDS_HUMAN`` rules (``other`` category modify)
    7. ``AUTO_ALLOWED`` rules (pure reads regardless of target)
    8. ``AUTO_ALLOWED`` rules (LOW risk on auto categories)
    9. ``AUTO_ALLOWED`` rules (composite git actions)
    10. Default fallback → ``NEEDS_HUMAN`` /
        ``unknown_risk_or_target_fail_safe``.

    The default fallback is the security keystone: anything not
    explicitly auto-allowed is gated to operator approval.
    """
    # Derive category from the path string. None → empty category
    # signal handled below.
    if target_path is None or target_path == "":
        category = "other"
    else:
        category = _categorize_path(target_path)

    # Normalise risk_class to the closed enum; unknown string → UNKNOWN.
    if risk_class not in RISK_CLASSES:
        risk_class = RISK_UNKNOWN

    is_modify = action_type in _MODIFY_ACTIONS

    def _build(decision: str, reason: str) -> ExecutionDecision:
        return ExecutionDecision(
            decision=decision,
            reason=reason,
            target_path_category=category,
            evidence=_bounded_evidence(
                action_type=action_type,
                target_path=target_path,
                target_path_category=category,
                risk_class=risk_class,
            ),
        )

    # ---- 1. Action-type-level permanent denies ------------------------------
    deny_reason = _ACTION_LEVEL_PERMANENT_DENY.get(action_type)
    if deny_reason is not None:
        return _build(DECISION_PERMANENTLY_DENIED, deny_reason)

    # Reject unknown action_type as fail-safe NEEDS_HUMAN. (We do this
    # AFTER the permanent-deny lookup so the permanent-deny set is
    # authoritative even if someone passes an obviously-malformed
    # action_type that happens to hash-equal one of those strings.)
    if action_type not in ACTION_TYPES:
        return _build(
            DECISION_NEEDS_HUMAN, "unknown_risk_or_target_fail_safe"
        )

    # ---- 2. Target-category permanent denies (modify only) ------------------
    if is_modify:
        deny_reason = _CATEGORY_LEVEL_PERMANENT_DENY.get(category)
        if deny_reason is not None:
            return _build(DECISION_PERMANENTLY_DENIED, deny_reason)

    # ---- 3. Target-category NEEDS_HUMAN (modify only) -----------------------
    if is_modify:
        nh_reason = _CATEGORY_LEVEL_NEEDS_HUMAN.get(category)
        if nh_reason is not None:
            return _build(DECISION_NEEDS_HUMAN, nh_reason)

    # ---- 4. Operator-only action types --------------------------------------
    if action_type == "agent_allowlist_widen":
        return _build(DECISION_NEEDS_HUMAN, "agent_allowlist_widening")
    if action_type == "approval_inbox_decide":
        return _build(DECISION_NEEDS_HUMAN, "approval_inbox_decision")

    # ---- 5. Risk-class escalation -------------------------------------------
    # Pure reads bypass risk-class escalation — reading a file is not
    # a state change. This matches the doc: "Pure reads (any target)
    # → AUTO_ALLOWED" precedes risk gating only for read actions, but
    # the *broader* HIGH/UNKNOWN gate must still cover every modify or
    # git action regardless of category. So we apply the gate here,
    # before the AUTO_ALLOWED rules, only for non-read actions.
    if action_type not in _PURE_READ_ACTIONS:
        if risk_class == RISK_HIGH:
            return _build(DECISION_NEEDS_HUMAN, "high_risk_governance_change")
        if risk_class == RISK_UNKNOWN:
            return _build(
                DECISION_NEEDS_HUMAN, "unknown_risk_or_target_fail_safe"
            )

    # ---- 6. ``other`` category modify ---------------------------------------
    if is_modify and category == "other":
        return _build(
            DECISION_NEEDS_HUMAN, "unknown_risk_or_target_fail_safe"
        )

    # ---- 7. Pure reads (always AUTO_ALLOWED) --------------------------------
    if action_type in _PURE_READ_ACTIONS:
        return _build(DECISION_AUTO_ALLOWED, "pure_read_no_side_effect")

    # ---- 8. LOW risk on auto categories (modify) ----------------------------
    if is_modify and risk_class == RISK_LOW:
        auto_reason = _CATEGORY_LEVEL_AUTO_ALLOWED.get(category)
        if auto_reason is not None:
            return _build(DECISION_AUTO_ALLOWED, auto_reason)

    # ---- 9. Composite git actions on auto categories ------------------------
    # The doc allows pr_open / squash_merge / push / branch_create /
    # commit_create as AUTO_ALLOWED only when every touched path in
    # the PR has an AUTO_ALLOWED file-level decision. This classifier
    # is per-action; the caller is expected to compose this rule by
    # calling classify() per file and aggregating. For a single
    # invocation here we honour the doc by returning AUTO_ALLOWED
    # iff the (single) ``target_path`` resolves to an auto category
    # at LOW risk, OR ``target_path`` is None and risk_class is LOW
    # (caller has already aggregated).
    if action_type in _PR_COMPOSITE_ACTIONS and risk_class == RISK_LOW:
        if target_path is None or category in _CATEGORY_LEVEL_AUTO_ALLOWED:
            return _build(
                DECISION_AUTO_ALLOWED, "low_risk_read_only_projection"
            )

    # ---- 10. Default fallback ------------------------------------------------
    return _build(DECISION_NEEDS_HUMAN, "unknown_risk_or_target_fail_safe")


__all__ = [
    "ACTION_TYPES",
    "DECISIONS",
    "DECISION_AUTO_ALLOWED",
    "DECISION_NEEDS_HUMAN",
    "DECISION_PERMANENTLY_DENIED",
    "ExecutionDecision",
    "MODULE_VERSION",
    "REASONS",
    "RISK_CLASSES",
    "RISK_HIGH",
    "RISK_LOW",
    "RISK_MEDIUM",
    "RISK_UNKNOWN",
    "SCHEMA_VERSION",
    "TARGET_PATH_CATEGORIES",
    "classify",
]
