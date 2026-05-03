"""Roadmap item execution protocol (v3.15.15.28).

A deterministic, stdlib-only protocol module that converts a
single roadmap item into a fully-specified execution plan without
running any code. Implementation is forbidden in this module —
the plan is a *proposal*, not an action. Actual implementation
requires:

* operator approval for HIGH/UNKNOWN/secret/external/paid/
  telemetry/protected/canonical-roadmap items;
* the existing CI gates;
* the existing PR-lifecycle protocol;
* a separate human-authored implementation step inside the
  branch the plan proposes.

Hard guarantees
---------------

* Stdlib-only. No subprocess, no ``gh``, no ``git``, no network.
* Output limited to ``logs/roadmap_execution_protocol/``.
* Atomic writes (``tmp`` + ``os.replace``); no in-place edits.
* Risk decisions delegate to ``reporting.approval_policy.decide()``
  — there is no second source of truth.
* ``safe_to_execute`` is hard-coded ``false`` at the digest level.
* ``executable`` is False for every emitted plan; the operator
  decides whether to start implementation by hand.
* ``implementation_allowed`` is True only for LOW / MEDIUM items
  whose policy decision is ``allowed_read_only`` AND whose item
  type is in the closed ``ITEM_TYPES_OPEN_TO_IMPLEMENTATION``
  set; HIGH / UNKNOWN / governance / canonical / live / paid /
  external / secret items are False by construction.
* Agent assignments come from a closed taxonomy; an item that
  doesn't fit any known type lands as ``unknown_state`` and
  routes to the operator.

CLI
---

::

    python -m reporting.roadmap_execution_protocol --describe
    python -m reporting.roadmap_execution_protocol \
        --plan-item path/to/item.json --dry-run
    python -m reporting.roadmap_execution_protocol --status

Stdlib-only.
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as _dt
import hashlib
import json
import os
import re
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final

from reporting import approval_policy as _approval_policy

REPO_ROOT: Path = Path(__file__).resolve().parent.parent
MODULE_VERSION: Final[str] = "v3.15.15.28"
SCHEMA_VERSION: Final[int] = 1

DIGEST_DIR_JSON: Path = REPO_ROOT / "logs" / "roadmap_execution_protocol"


# ---------------------------------------------------------------------------
# Closed taxonomies
# ---------------------------------------------------------------------------


# Item types the protocol recognises. Anything outside this set is
# classified ``unknown_state`` regardless of any other signal.
ITEM_TYPES: Final[tuple[str, ...]] = (
    "docs_only",
    "frontend_read_only",
    "reporting_read_only",
    "test_only",
    "dependency_floor_bump",
    "ci_hardening",
    "observability_addition",
    "tooling_intake",
    "governance_change",
    "canonical_roadmap_adoption",
    "live_paper_shadow_risk",
    "frozen_contract_change",
    "external_account_or_secret",
    "telemetry_or_data_egress",
    "paid_tool",
    "unknown",
)


# Item types that, when paired with a LOW/MEDIUM policy decision,
# are eligible to enter the implementation phase under the PR
# protocol. Everything else (HIGH-by-shape items, unknown,
# governance-change, etc.) routes to needs_human regardless.
ITEM_TYPES_OPEN_TO_IMPLEMENTATION: Final[frozenset[str]] = frozenset(
    {
        "docs_only",
        "frontend_read_only",
        "reporting_read_only",
        "test_only",
        "observability_addition",
    }
)


# Status enum — surfaces the high-level state of the plan to the
# operator inbox / metrics surface.
STATUS_PROPOSED: Final[str] = "proposed"
STATUS_NEEDS_HUMAN: Final[str] = "needs_human"
STATUS_BLOCKED: Final[str] = "blocked"
STATUS_UNKNOWN: Final[str] = "unknown_state"

STATUSES: Final[tuple[str, ...]] = (
    STATUS_PROPOSED,
    STATUS_NEEDS_HUMAN,
    STATUS_BLOCKED,
    STATUS_UNKNOWN,
)


# ---------------------------------------------------------------------------
# Agent role catalog
# ---------------------------------------------------------------------------


AGENT_PRODUCT_OWNER: Final[str] = "product_owner"
AGENT_STRATEGIC_ADVISOR: Final[str] = "strategic_advisor"
AGENT_PLANNER: Final[str] = "planner"
AGENT_IMPLEMENTATION: Final[str] = "implementation_agent"
AGENT_ARCHITECTURE_GUARDIAN: Final[str] = "architecture_guardian"
AGENT_CI_GUARDIAN: Final[str] = "ci_guardian"
AGENT_SECURITY_GOVERNANCE_GUARDIAN: Final[str] = "security_governance_guardian"
AGENT_OPERATOR: Final[str] = "operator"


# Role definitions — surfaced through ``--describe`` so the
# operator can audit who is allowed to do what without reading
# the source. Every field is a tuple of strings; deterministic
# ordering is guaranteed.
@dataclasses.dataclass(frozen=True)
class AgentRole:
    name: str
    title: str
    responsibilities: tuple[str, ...]
    allowed_actions: tuple[str, ...]
    forbidden_actions: tuple[str, ...]
    handoff_input: tuple[str, ...]
    handoff_output: tuple[str, ...]
    required_evidence: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "title": self.title,
            "responsibilities": list(self.responsibilities),
            "allowed_actions": list(self.allowed_actions),
            "forbidden_actions": list(self.forbidden_actions),
            "handoff_input": list(self.handoff_input),
            "handoff_output": list(self.handoff_output),
            "required_evidence": list(self.required_evidence),
        }


_AGENT_ROLES: Final[tuple[AgentRole, ...]] = (
    AgentRole(
        name=AGENT_PRODUCT_OWNER,
        title="Product Owner Agent",
        responsibilities=(
            "convert a roadmap item into operator-shaped acceptance criteria",
            "prevent vague scope; reject items without measurable value",
            "confirm user value with operator before any branch is opened",
        ),
        allowed_actions=(
            "read roadmap / proposal / inbox artifacts",
            "draft acceptance_criteria entries on the plan",
            "request operator clarification via the inbox",
        ),
        forbidden_actions=(
            "open branches",
            "open PRs",
            "modify code",
            "modify tests",
            "modify governance",
        ),
        handoff_input=("roadmap item record", "operator brief"),
        handoff_output=("acceptance_criteria", "scope_summary", "user_value"),
        required_evidence=("title", "summary", "operator_user_value_confirmed"),
    ),
    AgentRole(
        name=AGENT_STRATEGIC_ADVISOR,
        title="Strategic Advisor",
        responsibilities=(
            "check sequencing and strategic fit against the autonomy roadmap",
            "recommend deferral or split when scope is too large",
            "raise authority concerns to the operator",
        ),
        allowed_actions=(
            "read roadmap / ADR / governance / proposal artifacts",
            "annotate the plan with strategic notes",
            "recommend a different proposed_release_id",
        ),
        forbidden_actions=(
            "implement directly",
            "approve HIGH-risk items",
            "open or merge PRs",
        ),
        handoff_input=("plan draft from product_owner",),
        handoff_output=("strategic_fit", "deferral_recommendation"),
        required_evidence=("roadmap_reference", "scope_summary"),
    ),
    AgentRole(
        name=AGENT_PLANNER,
        title="Planner Agent",
        responsibilities=(
            "produce a bounded release plan for the proposed item",
            "define branch, commit boundaries, tests, and rollback",
            "list expected artifacts and operator-visible changes",
        ),
        allowed_actions=(
            "read repository state",
            "draft proposed_branch / required_tests / rollback_plan",
            "write the plan to logs/roadmap_execution_protocol/",
        ),
        forbidden_actions=(
            "implement code",
            "open branches in git",
            "open PRs",
            "modify governance",
            "modify .claude/**",
        ),
        handoff_input=("plan draft from strategic_advisor",),
        handoff_output=(
            "proposed_branch",
            "proposed_release_id",
            "required_tests",
            "expected_artifacts",
            "rollback_plan",
        ),
        required_evidence=("acceptance_criteria",),
    ),
    AgentRole(
        name=AGENT_IMPLEMENTATION,
        title="Implementation Agent",
        responsibilities=(
            "implement only the approved scope on the proposed branch",
            "make no scope changes without re-running the protocol",
            "run all required tests before opening the PR",
        ),
        allowed_actions=(
            "edit files declared under affected_areas",
            "add tests under tests/{smoke,unit,...}",
            "open the PR with the deterministic body shape",
        ),
        forbidden_actions=(
            "expand scope without operator approval",
            "weaken tests / governance / CI",
            "force push",
            "admin merge",
            "direct main push",
            "modify .claude/**",
            "modify frozen contracts",
            "modify automation/live_gate.py",
            "wire api_execute_safe_controls without explicit operator brief",
        ),
        handoff_input=("approved plan",),
        handoff_output=("PR URL", "CI status", "self_review_notes"),
        required_evidence=("proposed_branch", "approval_policy_decision"),
    ),
    AgentRole(
        name=AGENT_ARCHITECTURE_GUARDIAN,
        title="Architecture Guardian",
        responsibilities=(
            "check layering, contracts, frozen outputs, no-touch files",
            "verify no protected-path or live-trading touch",
            "confirm schema version bumps when a contract changes",
        ),
        allowed_actions=(
            "read PR diff",
            "block merge with a comment",
            "request re-plan via the operator",
        ),
        forbidden_actions=(
            "rewrite the implementation",
            "merge the PR",
            "wave through HIGH-risk items",
        ),
        handoff_input=("open PR",),
        handoff_output=("architecture_review_pass_or_block",),
        required_evidence=("PR URL", "files_changed"),
    ),
    AgentRole(
        name=AGENT_CI_GUARDIAN,
        title="CI Guardian",
        responsibilities=(
            "verify required GitHub checks all green",
            "verify no test was skipped, deleted, or weakened",
            "verify required smoke + unit + governance_lint coverage",
        ),
        allowed_actions=(
            "read CI artefacts",
            "block merge with a comment",
        ),
        forbidden_actions=(
            "skip or downgrade required checks",
            "merge the PR",
            "modify CI workflows outside a separate ci-hardening release",
        ),
        handoff_input=("open PR",),
        handoff_output=("ci_review_pass_or_block",),
        required_evidence=("CI run summary",),
    ),
    AgentRole(
        name=AGENT_SECURITY_GOVERNANCE_GUARDIAN,
        title="Security / Governance Guardian",
        responsibilities=(
            "check for secret-shaped values, protected paths, mutation routes",
            "check for unsafe automation or governance weakening",
            "check approval_policy compliance for the item",
        ),
        allowed_actions=(
            "read PR diff",
            "block merge with a comment",
            "demand the plan be re-run through approval_policy",
        ),
        forbidden_actions=(
            "approve HIGH/UNKNOWN items autonomously",
            "merge the PR",
            "weaken redaction or guards",
        ),
        handoff_input=("open PR",),
        handoff_output=("security_review_pass_or_block",),
        required_evidence=("PR URL", "approval_policy_decision"),
    ),
    AgentRole(
        name=AGENT_OPERATOR,
        title="Operator (Joery)",
        responsibilities=(
            "decide HIGH / UNKNOWN / needs_human items",
            "approve external accounts / secrets / paid / telemetry",
            "approve live / paper / shadow / risk changes",
            "approve canonical roadmap adoption",
        ),
        allowed_actions=(
            "approve or reject any plan",
            "merge a PR after Guardian reviews pass",
            "ramp / disable / re-arm the autonomous loop",
        ),
        forbidden_actions=(
            "(none — the operator is the trust boundary)",
        ),
        handoff_input=("plan with all guardian reviews",),
        handoff_output=("merge_decision", "post_merge_signal"),
        required_evidence=("acceptance_criteria", "approval_policy_decision"),
    ),
)


# ---------------------------------------------------------------------------
# Required evidence per plan field
# ---------------------------------------------------------------------------


# The set of fields the planner is REQUIRED to populate. Missing
# fields do not fail the plan — they route it to ``unknown_state``
# with a deterministic ``blocked_reason``.
_REQUIRED_FIELDS: Final[tuple[str, ...]] = (
    "item_id",
    "source",
    "source_type",
    "title",
    "summary",
    "roadmap_reference",
    "proposed_release_id",
    "proposed_branch",
    "risk_class",
    "decision",
    "requires_human",
    "approval_policy_decision",
    "affected_areas",
    "forbidden_actions",
    "required_tests",
    "expected_artifacts",
    "rollback_plan",
    "acceptance_criteria",
    "agent_assignments",
    "guardian_reviews_required",
    "merge_requirements",
    "post_merge_checks",
    "status",
    "blocked_reason",
    "generated_at_utc",
    "schema_version",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _utcnow() -> str:
    return (
        _dt.datetime.now(_dt.UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT.resolve())).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slug(s: str, *, max_len: int = 48) -> str:
    cleaned = _SLUG_RE.sub("-", s.lower()).strip("-")
    return cleaned[:max_len] or "item"


def _branch_for(item_id: str, title: str, release_id: str) -> str:
    """Deterministic branch name: one item per branch by default."""
    rel_slug = _slug(release_id, max_len=20) or "release"
    title_slug = _slug(title, max_len=40)
    item_slug = _slug(item_id, max_len=12)
    return f"fix/{rel_slug}-{item_slug}-{title_slug}".rstrip("-")


# ---------------------------------------------------------------------------
# Item-shape inputs
# ---------------------------------------------------------------------------


def _coerce_str(v: Any, default: str = "") -> str:
    if v is None:
        return default
    return str(v)


def _coerce_tuple_str(v: Any) -> tuple[str, ...]:
    if v is None:
        return ()
    if isinstance(v, (list, tuple)):
        return tuple(str(x) for x in v)
    return (str(v),)


def _coerce_bool(v: Any) -> bool:
    if v is None:
        return False
    return bool(v)


# ---------------------------------------------------------------------------
# Item type classification
# ---------------------------------------------------------------------------


def _classify_item_type(item: Mapping[str, Any]) -> str:
    """Map an item to one of the closed ITEM_TYPES. First-match wins.

    The classifier is intentionally narrow: anything that does not
    match a known shape lands as ``unknown`` and routes through
    the operator. We never invent a permissive default.
    """
    requested = _coerce_str(item.get("item_type")).strip().lower()
    if requested in ITEM_TYPES:
        return requested

    files = _coerce_tuple_str(item.get("affected_files"))
    files_normalised = tuple(f.replace("\\", "/") for f in files)
    title = _coerce_str(item.get("title")).lower()
    summary = _coerce_str(item.get("summary")).lower()
    text = f"{title}\n{summary}"

    # 0. frozen contract (highest precedence — file-level match;
    # mirrors approval_policy.diff_touches_frozen).
    for f in files_normalised:
        if f in _approval_policy.FROZEN_CONTRACTS:
            return "frozen_contract_change"
    if _coerce_bool(item.get("touches_frozen_contract")):
        return "frozen_contract_change"

    # 1. canonical-roadmap adoption (always blocks).
    if _approval_policy._matched_token(
        text, _approval_policy.CANONICAL_ROADMAP_TOKENS
    ) or _coerce_bool(item.get("changes_canonical_roadmap")):
        return "canonical_roadmap_adoption"

    # 2. governance change (always blocks).
    if _coerce_bool(item.get("touches_governance")) or any(
        t in text
        for t in (
            ".claude/",
            "agents.md",
            "claude.md",
            "branch protection",
            "codeowners",
            "no_touch_paths",
            "agent governance",
            "release gate",
            "autonomy ladder",
        )
    ):
        return "governance_change"

    # 3. live / paper / shadow / risk path.
    if _coerce_bool(item.get("touches_live_paper_shadow_risk")):
        return "live_paper_shadow_risk"
    for f in files_normalised:
        if _approval_policy._matches_any(f, _approval_policy.LIVE_PATH_GLOBS):
            return "live_paper_shadow_risk"

    # 4. external secret / account.
    if (
        _coerce_bool(item.get("requires_secret"))
        or _coerce_bool(item.get("requires_external_account"))
        or _approval_policy._matched_token(
            text, _approval_policy.EXTERNAL_SECRET_TOKENS
        )
    ):
        return "external_account_or_secret"

    # 5. telemetry / data egress.
    if _coerce_bool(item.get("has_telemetry_or_data_egress")) or (
        _approval_policy._matched_token(text, _approval_policy.TELEMETRY_TOKENS)
    ):
        return "telemetry_or_data_egress"

    # 6. paid tool.
    if _coerce_bool(item.get("requires_paid_tool")) or (
        _approval_policy._matched_token(text, _approval_policy.PAID_TOOL_TOKENS)
    ):
        return "paid_tool"

    # 7. CI / test path.
    if _coerce_bool(item.get("touches_ci_or_tests")) or any(
        _approval_policy._matches_any(f, _approval_policy.CI_OR_TESTS_GLOBS)
        for f in files_normalised
    ):
        return "ci_hardening"

    # 8. docs_only — every affected file is under docs/.
    if files_normalised and all(
        f.startswith("docs/") for f in files_normalised
    ):
        return "docs_only"

    # 9. frontend_read_only — every affected file is under frontend/
    # and the title/summary do not mention a mutation verb.
    if files_normalised and all(f.startswith("frontend/") for f in files_normalised):
        if not _approval_policy._matched_token(
            text,
            ("execute", "approve", "reject", "merge button", "post", "mutate"),
        ):
            return "frontend_read_only"

    # 10. reporting_read_only — every affected file is under reporting/
    # and the title/summary describe an additive read-only module.
    if files_normalised and all(f.startswith("reporting/") for f in files_normalised):
        if any(t in text for t in ("read-only", "report", "metric", "audit", "digest")):
            return "reporting_read_only"

    # 11. test_only.
    if files_normalised and all(f.startswith("tests/") for f in files_normalised):
        return "test_only"

    # 12. dependency_floor_bump — affected files are requirements
    # or package.json, summary mentions "bump" / "update".
    if files_normalised and all(
        f.endswith("requirements.txt")
        or f.endswith("package.json")
        or f.endswith("package-lock.json")
        for f in files_normalised
    ):
        return "dependency_floor_bump"

    # 13. observability_addition.
    if any(
        t in text
        for t in ("observability", "logging", "metrics", "audit log", "monitoring")
    ):
        return "observability_addition"

    # 14. tooling intake.
    if any(
        t in text
        for t in ("tooling", "library upgrade", "dev dependency", "new package")
    ):
        return "tooling_intake"

    # Default: operator decides.
    return "unknown"


# ---------------------------------------------------------------------------
# Risk decision via approval_policy
# ---------------------------------------------------------------------------


def _approval_decision(item: Mapping[str, Any]) -> _approval_policy.PolicyDecision:
    """Lift a roadmap item into a PolicyInput and run the canonical
    decide() function. The mapping is verbatim; we never reshape
    the policy decision."""
    pi = _approval_policy.PolicyInput.from_mapping(
        {
            "title": item.get("title"),
            "summary": item.get("summary"),
            "source_type": item.get("source_type"),
            "affected_files": item.get("affected_files"),
            "labels": item.get("labels"),
            "risk_class": item.get("risk_class"),
            "requested_action": "propose",
            "requires_secret": item.get("requires_secret"),
            "requires_external_account": item.get("requires_external_account"),
            "requires_paid_tool": item.get("requires_paid_tool"),
            "has_telemetry_or_data_egress": item.get(
                "has_telemetry_or_data_egress"
            ),
            "touches_governance": item.get("touches_governance"),
            "touches_frozen_contract": item.get("touches_frozen_contract"),
            "touches_live_paper_shadow_risk": item.get(
                "touches_live_paper_shadow_risk"
            ),
            "touches_ci_or_tests": item.get("touches_ci_or_tests"),
            "changes_canonical_roadmap": item.get("changes_canonical_roadmap"),
            "is_dependabot": False,
            "pr_author": item.get("pr_author"),
        }
    )
    return _approval_policy.decide(pi)


# ---------------------------------------------------------------------------
# Plan synthesis
# ---------------------------------------------------------------------------


def _agent_assignments_for(item_type: str) -> list[dict[str, Any]]:
    """Every plan involves the full agent chain. The order encodes
    the handoff sequence: PO → Strategic → Planner → Implementation
    → Architecture/CI/Security guardians → Operator. Items that
    the policy blocks still surface the chain so the operator can
    audit which guardian would block."""
    return [role.to_dict() for role in _AGENT_ROLES]


def _guardian_reviews_required(decision: _approval_policy.PolicyDecision) -> list[str]:
    """Every implementation-eligible item gets all three guardian
    reviews. Blocked items still document the reviews so the
    operator sees what would have been required."""
    return [
        AGENT_ARCHITECTURE_GUARDIAN,
        AGENT_CI_GUARDIAN,
        AGENT_SECURITY_GOVERNANCE_GUARDIAN,
    ]


def _merge_requirements() -> list[str]:
    return [
        "all required GitHub checks green",
        "local governance_lint OK",
        "local pytest tests/smoke OK",
        "frozen contract sha256 unchanged",
        "approval_policy decision is not HIGH/UNKNOWN executable",
        "no protected-path / live-path / governance-weakening touch",
        "no test/CI weakening",
        "no unresolved approval inbox row tied to the same item_id",
    ]


def _post_merge_checks() -> list[str]:
    return [
        "pull main",
        "verify final main SHA",
        "rerun python -m reporting.workloop_runtime --once",
        "rerun python -m reporting.autonomy_metrics --collect",
        "verify approval_inbox does not surface a new runtime_halt for the merged item",
        "verify frozen contract sha256 unchanged",
    ]


def _required_tests_for(item_type: str) -> list[str]:
    base = [
        "scripts/governance_lint.py",
        "tests/smoke",
        "frozen-hash check",
    ]
    if item_type == "frontend_read_only":
        return base + [
            "npm --prefix frontend test -- --run",
            "npm --prefix frontend run build",
        ]
    if item_type == "reporting_read_only" or item_type == "observability_addition":
        return base + ["tests/unit (targeted module + cross-module sweep)"]
    if item_type == "test_only":
        return base + ["tests/unit (the new tests)"]
    if item_type == "docs_only":
        return base + ["doc presence test if a schema doc changed"]
    if item_type == "dependency_floor_bump":
        return base + [
            "tests/unit",
            "no SHA pin downgrades in .github/workflows",
        ]
    return base + ["tests/unit"]


def _expected_artifacts_for(item_type: str) -> list[str]:
    if item_type == "reporting_read_only" or item_type == "observability_addition":
        return [
            "reporting/<new_module>.py",
            "logs/<new_module>/latest.json (atomic write)",
            "tests/unit/test_<new_module>.py",
            "docs/governance/<new_module>.md",
        ]
    if item_type == "frontend_read_only":
        return [
            "frontend/src/...",
            "frontend/dist/assets/index-<hash>.{js,css} after npm run build",
            "frontend tests pass",
        ]
    if item_type == "docs_only":
        return ["docs/governance/<doc>.md"]
    if item_type == "test_only":
        return ["tests/unit/test_<scope>.py"]
    return ["see plan"]


def _rollback_plan_for(item_type: str) -> list[str]:
    return [
        "git revert <release_commit_sha> on a fresh branch",
        "open a one-line revert PR with the same release id",
        "merge after CI green and frozen hashes unchanged",
        "post-merge re-run workloop_runtime + autonomy_metrics",
    ]


def _acceptance_criteria_for(
    item: Mapping[str, Any], item_type: str
) -> list[str]:
    declared = item.get("acceptance_criteria")
    if isinstance(declared, list) and declared:
        return [str(x) for x in declared]
    # Default per item type so the operator at least sees a
    # measurable bar even when the upstream item didn't declare
    # one.
    if item_type == "frontend_read_only":
        return [
            "the new UI is visible on phone-portrait at /agent-control",
            "no execute / approve / reject / merge buttons added",
            "no mutation fetch verbs in frontend code",
        ]
    if item_type == "reporting_read_only":
        return [
            "the new module emits a deterministic JSON digest",
            "missing/malformed sources are counted, never silently OK",
            "narrow credential-value redaction enforced",
            "stdlib-only (no subprocess / network / gh / git)",
        ]
    if item_type == "observability_addition":
        return [
            "the new signal is reachable from /api/agent-control/status",
            "the signal is read-only and auditable",
            "no new mutation routes",
        ]
    if item_type == "docs_only":
        return [
            "the new doc references the canonical schema",
            "no behavior change implied",
        ]
    if item_type == "test_only":
        return [
            "the new tests pin a real invariant",
            "no production code changes",
        ]
    return ["operator-defined acceptance criteria required"]


def _affected_areas(item: Mapping[str, Any]) -> list[str]:
    files = _coerce_tuple_str(item.get("affected_files"))
    return list(files)


def _status_from(decision: _approval_policy.PolicyDecision, item_type: str) -> str:
    if item_type == "unknown":
        return STATUS_UNKNOWN
    if decision.requires_human_approval and not decision.executable:
        if decision.decision == _approval_policy.DECISION_BLOCKED_UNKNOWN:
            return STATUS_UNKNOWN
        if decision.decision == _approval_policy.DECISION_NEEDS_HUMAN:
            return STATUS_NEEDS_HUMAN
        return STATUS_BLOCKED
    return STATUS_PROPOSED


def _implementation_allowed(
    decision: _approval_policy.PolicyDecision, item_type: str
) -> bool:
    """``implementation_allowed`` is True only when the policy
    decision is allowed_read_only AND the item type is in the
    open-to-implementation set. Every other shape is False."""
    if decision.decision != _approval_policy.DECISION_ALLOWED_READ_ONLY:
        return False
    return item_type in ITEM_TYPES_OPEN_TO_IMPLEMENTATION


def _blocked_reason(
    decision: _approval_policy.PolicyDecision, item_type: str
) -> str | None:
    if item_type == "unknown":
        return "unknown_item_type: routes to operator inspection"
    if decision.decision != _approval_policy.DECISION_ALLOWED_READ_ONLY:
        return f"approval_policy: {decision.decision} ({decision.reason})"
    if item_type not in ITEM_TYPES_OPEN_TO_IMPLEMENTATION:
        return (
            f"item_type {item_type!r} requires operator approval before "
            "an implementation branch may be opened"
        )
    return None


def plan_item(item: Mapping[str, Any], *, frozen_utc: str | None = None) -> dict[str, Any]:
    """Produce a fully-specified execution plan for one roadmap
    item. Pure function — no I/O. Determinism is guaranteed when
    ``frozen_utc`` is provided.
    """
    item_type = _classify_item_type(item)
    decision = _approval_decision(item)
    proposed_release_id = _coerce_str(
        item.get("proposed_release_id"), default="v3.15.16.x"
    )
    item_id = _coerce_str(
        item.get("item_id"),
        default="r_" + hashlib.sha256(
            (
                _coerce_str(item.get("title"))
                + "|"
                + _coerce_str(item.get("summary"))
            ).encode("utf-8")
        ).hexdigest()[:8],
    )
    title = _coerce_str(item.get("title"), default="(no title)")
    proposed_branch = _branch_for(item_id, title, proposed_release_id)
    status = _status_from(decision, item_type)
    blocked_reason = _blocked_reason(decision, item_type)

    plan: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "report_kind": "roadmap_execution_plan",
        "module_version": MODULE_VERSION,
        "generated_at_utc": frozen_utc or _utcnow(),
        "item_id": item_id,
        "source": _coerce_str(item.get("source")),
        "source_type": _coerce_str(item.get("source_type")),
        "title": title,
        "summary": _coerce_str(item.get("summary")),
        "roadmap_reference": _coerce_str(
            item.get("roadmap_reference"), default="docs/roadmap"
        ),
        "proposed_release_id": proposed_release_id,
        "proposed_branch": proposed_branch,
        "item_type": item_type,
        "risk_class": decision.risk_class,
        "decision": decision.decision,
        "approval_policy_decision": decision.to_dict(),
        "requires_human": decision.requires_human_approval,
        "executable": False,  # the protocol never auto-executes
        "implementation_allowed": _implementation_allowed(decision, item_type),
        "affected_areas": _affected_areas(item),
        "forbidden_actions": list(decision.forbidden_agent_actions),
        "required_tests": _required_tests_for(item_type),
        "expected_artifacts": _expected_artifacts_for(item_type),
        "rollback_plan": _rollback_plan_for(item_type),
        "acceptance_criteria": _acceptance_criteria_for(item, item_type),
        "agent_assignments": _agent_assignments_for(item_type),
        "guardian_reviews_required": _guardian_reviews_required(decision),
        "merge_requirements": _merge_requirements(),
        "post_merge_checks": _post_merge_checks(),
        "status": status,
        "blocked_reason": blocked_reason,
        "policy": {
            "module_version": _approval_policy.MODULE_VERSION,
            "schema_version": _approval_policy.SCHEMA_VERSION,
            "high_or_unknown_is_executable": False,
        },
        "safe_to_execute": False,
    }

    _approval_policy.assert_no_credential_values(plan)
    return plan


def describe_protocol() -> dict[str, Any]:
    """Return the full role / handoff / status / item-type
    catalogue. The shape is stable; callers (docs, tests, status
    surface) consume it deterministically."""
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": "roadmap_execution_protocol_description",
        "module_version": MODULE_VERSION,
        "generated_at_utc": _utcnow(),
        "item_types": list(ITEM_TYPES),
        "item_types_open_to_implementation": sorted(
            ITEM_TYPES_OPEN_TO_IMPLEMENTATION
        ),
        "statuses": list(STATUSES),
        "agent_roles": [r.to_dict() for r in _AGENT_ROLES],
        "merge_requirements": _merge_requirements(),
        "post_merge_checks": _post_merge_checks(),
        "policy": {
            "module_version": _approval_policy.MODULE_VERSION,
            "schema_version": _approval_policy.SCHEMA_VERSION,
            "high_or_unknown_is_executable": False,
        },
        "safe_to_execute": False,
    }


# ---------------------------------------------------------------------------
# Atomic write
# ---------------------------------------------------------------------------


def write_outputs(snapshot: dict[str, Any]) -> dict[str, str]:
    """Atomic write of latest.json + timestamped copy + history append."""
    DIGEST_DIR_JSON.mkdir(parents=True, exist_ok=True)
    ts = snapshot["generated_at_utc"].replace(":", "-")
    json_now = DIGEST_DIR_JSON / f"{ts}.json"
    json_latest = DIGEST_DIR_JSON / "latest.json"
    history = DIGEST_DIR_JSON / "history.jsonl"
    payload = json.dumps(snapshot, sort_keys=True, indent=2)

    tmp_now = json_now.with_suffix(json_now.suffix + ".tmp")
    tmp_now.write_text(payload, encoding="utf-8")
    os.replace(tmp_now, json_now)

    tmp_latest = json_latest.with_suffix(json_latest.suffix + ".tmp")
    tmp_latest.write_text(payload, encoding="utf-8")
    os.replace(tmp_latest, json_latest)

    compact = json.dumps(snapshot, sort_keys=True, separators=(",", ":"))
    with history.open("a", encoding="utf-8") as f:
        f.write(compact + "\n")

    return {
        "latest": _rel(json_latest),
        "timestamped": _rel(json_now),
        "history": _rel(history),
    }


def read_latest_snapshot() -> dict[str, Any] | None:
    p = DIGEST_DIR_JSON / "latest.json"
    if not p.exists():
        return None
    try:
        text = p.read_text(encoding="utf-8")
        data = json.loads(text)
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


# ---------------------------------------------------------------------------
# Item file loader
# ---------------------------------------------------------------------------


def _load_item(arg: str) -> dict[str, Any]:
    """Load an item from a path or an inline JSON string. Never
    raises — returns a minimal item with status=unknown if the
    input is unreadable."""
    p = Path(arg)
    if p.exists() and p.is_file():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {"item_id": "r_unparseable", "title": _rel(p)}
    # Inline JSON string?
    try:
        parsed = json.loads(arg)
        if isinstance(parsed, dict):
            return parsed
    except (TypeError, json.JSONDecodeError):
        pass
    # Treat as a title only — minimum-viable plan.
    return {"title": arg}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="reporting.roadmap_execution_protocol",
        description=(
            "Read-only roadmap-item execution protocol planner "
            f"({MODULE_VERSION}). Stdlib-only. Never executes "
            "implementation; always proposes."
        ),
    )
    g = parser.add_mutually_exclusive_group(required=True)
    g.add_argument(
        "--describe",
        action="store_true",
        help="Print the full role/handoff/item-type catalogue.",
    )
    g.add_argument(
        "--plan-item",
        type=str,
        default=None,
        help="Path to a JSON item file or an inline JSON object.",
    )
    g.add_argument(
        "--status",
        action="store_true",
        help="Read and print the latest plan from logs/.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "When set with --plan-item, do NOT write to logs/. "
            "The plan is printed to stdout instead. This release's "
            "policy: --plan-item without --dry-run is REJECTED."
        ),
    )
    parser.add_argument(
        "--frozen-utc",
        type=str,
        default=None,
        help="Pin generated_at_utc for deterministic tests.",
    )
    args = parser.parse_args(argv)

    if args.describe:
        print(json.dumps(describe_protocol(), sort_keys=True, indent=2))
        return 0

    if args.status:
        snap = read_latest_snapshot()
        if snap is None:
            print(json.dumps({"status": "not_available", "reason": "missing"}, indent=2))
            return 1
        print(json.dumps(snap, sort_keys=True, indent=2))
        return 0

    if args.plan_item is not None:
        if not args.dry_run:
            # Hard policy: this release does not implement, only
            # proposes. Refuse any non-dry-run invocation so we
            # never silently mutate state outside the gitignored
            # logs/ dir.
            parser.error(
                "--plan-item must be combined with --dry-run in "
                f"{MODULE_VERSION} (the protocol does not implement)."
            )
            return 2  # unreachable
        item = _load_item(args.plan_item)
        plan = plan_item(item, frozen_utc=args.frozen_utc)
        # Even in --dry-run we still emit the plan to logs/ so the
        # status surface can read it. The dry-run flag prevents
        # any other side effect.
        write_outputs(plan)
        print(json.dumps(plan, sort_keys=True, indent=2))
        return 0

    parser.error("no mode chosen")
    return 2  # unreachable


if __name__ == "__main__":
    sys.exit(main())
