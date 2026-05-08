"""Unit tests for N1 — ADE Notification Event Taxonomy.

The module under test is pure data + one pure routing function. It
emits no notifications, mints no tokens, and grants no authority.

Hard guarantees (pinned here):

* Closed vocabularies (`EVENT_KINDS`, `EVENT_SEVERITIES`,
  `DECISION_STATES`) are byte-exact.
* The default-severity routing table covers every event_kind.
* Unknown event kinds fail closed to ``push_action_required`` —
  never to ``silent`` or ``digest``.
* Importing the module performs zero side-effects and does not flip
  any Step 5 invariant.
* The module imports nothing from dashboard / frontend / research /
  automation / broker / agent.risk / agent.execution /
  reporting.intelligent_routing.
* No subprocess / network / gh / git references in the module.
* The companion governance doc mentions Level 6 only with the
  ``permanently disabled`` qualifier and contains the load-bearing
  rule "no approval from notification click alone".
"""

from __future__ import annotations

import importlib
from pathlib import Path

from reporting import notification_event as ne


REPO_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# Closed vocabularies
# ---------------------------------------------------------------------------


def test_event_kinds_pinned_exactly() -> None:
    assert ne.EVENT_KINDS == (
        "queue_item_proposed",
        "queue_item_blocked",
        "queue_item_human_needed",
        "delegation_emitted",
        "delegation_blocked",
        "bugfix_candidate_proposed",
        "bugfix_candidate_blocked",
        "intake_candidate_proposed",
        "intake_candidate_eligible",
        "intake_candidate_blocked",
        "step5_cycle_planned",
        "step5_cycle_halted",
        "step5_cycle_needs_human",
        "release_gate_pass",
        "release_gate_fail",
        "release_gate_needs_human",
        "operational_digest_emitted",
        "e2e_proof_pass",
        "e2e_proof_fail",
        "pr_lifecycle_event",
        "pr_merge_approval_required",
        "pr_merge_approved",
        "pr_merge_rejected",
        "pr_merge_executed",
        "deploy_approval_required",
        "deploy_approved",
        "deploy_rejected",
        "deploy_executed",
        "governance_violation_detected",
        "secret_or_pii_redaction_event",
        "audit_chain_anomaly",
        "unknown_state",
    )


def test_event_severities_pinned_exactly_and_ordered() -> None:
    assert ne.EVENT_SEVERITIES == (
        "silent",
        "digest",
        "push_info",
        "push_action_required",
        "approval_required",
        "critical",
    )


def test_decision_states_pinned_exactly() -> None:
    assert ne.DECISION_STATES == (
        "pending",
        "acknowledged",
        "approved",
        "rejected",
        "expired",
        "superseded",
    )


def test_event_kinds_are_unique() -> None:
    assert len(set(ne.EVENT_KINDS)) == len(ne.EVENT_KINDS)


def test_event_severities_are_unique() -> None:
    assert len(set(ne.EVENT_SEVERITIES)) == len(ne.EVENT_SEVERITIES)


def test_decision_states_are_unique() -> None:
    assert len(set(ne.DECISION_STATES)) == len(ne.DECISION_STATES)


# ---------------------------------------------------------------------------
# Routing table — pinned shape and coverage
# ---------------------------------------------------------------------------


def test_routing_table_covers_all_event_kinds() -> None:
    """Every event_kind in EVENT_KINDS must have a default severity.
    No silent omissions allowed."""
    missing = set(ne.EVENT_KINDS) - set(ne.EVENT_KIND_DEFAULT_SEVERITY)
    extra = set(ne.EVENT_KIND_DEFAULT_SEVERITY) - set(ne.EVENT_KINDS)
    assert missing == set(), f"event_kinds without a default: {missing}"
    assert extra == set(), f"routing-table keys not in EVENT_KINDS: {extra}"


def test_routing_table_severities_are_valid() -> None:
    for kind, sev in ne.EVENT_KIND_DEFAULT_SEVERITY.items():
        assert sev in ne.EVENT_SEVERITIES, (kind, sev)


def test_routing_table_pinned() -> None:
    """The full default-severity table is pinned verbatim. Any
    change requires updating this test together with the module."""
    assert ne.EVENT_KIND_DEFAULT_SEVERITY == {
        "queue_item_proposed": "digest",
        "delegation_emitted": "digest",
        "bugfix_candidate_proposed": "digest",
        "intake_candidate_proposed": "digest",
        "operational_digest_emitted": "digest",
        "intake_candidate_eligible": "push_info",
        "release_gate_pass": "push_info",
        "e2e_proof_pass": "push_info",
        "pr_merge_executed": "push_info",
        "deploy_executed": "push_info",
        "pr_merge_approved": "push_info",
        "pr_merge_rejected": "push_info",
        "deploy_approved": "push_info",
        "deploy_rejected": "push_info",
        "pr_lifecycle_event": "push_info",
        "queue_item_blocked": "push_info",
        "delegation_blocked": "push_info",
        "bugfix_candidate_blocked": "push_info",
        "intake_candidate_blocked": "push_info",
        "queue_item_human_needed": "push_action_required",
        "step5_cycle_halted": "push_action_required",
        "step5_cycle_needs_human": "push_action_required",
        "release_gate_fail": "push_action_required",
        "e2e_proof_fail": "push_action_required",
        "unknown_state": "push_action_required",
        "release_gate_needs_human": "approval_required",
        "pr_merge_approval_required": "approval_required",
        "deploy_approval_required": "approval_required",
        "step5_cycle_planned": "silent",
        "governance_violation_detected": "critical",
        "secret_or_pii_redaction_event": "critical",
        "audit_chain_anomaly": "critical",
    }


def test_unknown_event_kind_fallback_is_push_action_required() -> None:
    assert ne.UNKNOWN_EVENT_KIND_FALLBACK_SEVERITY == "push_action_required"


def test_unknown_event_kind_fallback_is_not_silent_or_digest() -> None:
    """Unknown is never silently OK."""
    assert ne.UNKNOWN_EVENT_KIND_FALLBACK_SEVERITY not in ("silent", "digest")


# ---------------------------------------------------------------------------
# route_for() — known kinds
# ---------------------------------------------------------------------------


def test_route_for_returns_pinned_default_for_each_kind() -> None:
    for kind, expected in ne.EVENT_KIND_DEFAULT_SEVERITY.items():
        assert ne.route_for(kind) == expected


def test_route_for_critical_kind_stays_critical() -> None:
    assert ne.route_for("governance_violation_detected") == "critical"
    assert ne.route_for("secret_or_pii_redaction_event") == "critical"
    assert ne.route_for("audit_chain_anomaly") == "critical"


def test_route_for_silent_kind_default_silent() -> None:
    assert ne.route_for("step5_cycle_planned") == "silent"


# ---------------------------------------------------------------------------
# route_for() — unknown kinds (fail-closed)
# ---------------------------------------------------------------------------


def test_route_for_unknown_kind_routes_to_fallback() -> None:
    assert ne.route_for("not_a_real_kind") == "push_action_required"
    assert ne.route_for("") == "push_action_required"


def test_route_for_unknown_kind_does_not_route_to_silent_or_digest() -> None:
    for bogus in ("does_not_exist", "x", "QUEUE_ITEM_PROPOSED"):
        # Note: "QUEUE_ITEM_PROPOSED" is upper-case and therefore NOT
        # a member of EVENT_KINDS; it must fail closed.
        assert ne.route_for(bogus) not in ("silent", "digest")


# ---------------------------------------------------------------------------
# route_for() — escalations only lift, never lower
# ---------------------------------------------------------------------------


def test_route_for_escalations_only_lift_never_lower() -> None:
    """For every (kind, hint) combination, the routed severity must
    be at least as strict as the routing-table default."""
    sev_rank = {s: i for i, s in enumerate(ne.EVENT_SEVERITIES)}
    risk_hints = (None, "LOW", "MEDIUM", "HIGH", "UNKNOWN", "weird_value")
    decision_hints = (
        None,
        "AUTO_ALLOWED",
        "NEEDS_HUMAN",
        "PERMANENTLY_DENIED",
        "weird_value",
    )
    for kind, default in ne.EVENT_KIND_DEFAULT_SEVERITY.items():
        for r in risk_hints:
            for d in decision_hints:
                routed = ne.route_for(
                    kind, risk_class=r, execution_authority_decision=d
                )
                assert sev_rank[routed] >= sev_rank[default], (
                    kind,
                    default,
                    r,
                    d,
                    routed,
                )


def test_route_for_high_risk_floors_at_push_info() -> None:
    # A digest kind escalates to push_info under HIGH risk.
    assert ne.route_for("queue_item_proposed", risk_class="HIGH") == "push_info"
    # A push_info kind stays push_info.
    assert ne.route_for("queue_item_blocked", risk_class="HIGH") == "push_info"
    # A critical kind stays critical.
    assert (
        ne.route_for("governance_violation_detected", risk_class="HIGH")
        == "critical"
    )


def test_route_for_unknown_risk_floors_at_push_action_required() -> None:
    assert (
        ne.route_for("queue_item_proposed", risk_class="UNKNOWN")
        == "push_action_required"
    )
    # silent → push_action_required when risk_class is unknown
    assert (
        ne.route_for("step5_cycle_planned", risk_class="UNKNOWN")
        == "push_action_required"
    )


def test_route_for_needs_human_floors_at_approval_required() -> None:
    assert (
        ne.route_for(
            "queue_item_proposed",
            execution_authority_decision="NEEDS_HUMAN",
        )
        == "approval_required"
    )
    # An already-approval_required kind stays approval_required.
    assert (
        ne.route_for(
            "pr_merge_approval_required",
            execution_authority_decision="NEEDS_HUMAN",
        )
        == "approval_required"
    )


def test_route_for_permanently_denied_floors_at_critical() -> None:
    assert (
        ne.route_for(
            "queue_item_proposed",
            execution_authority_decision="PERMANENTLY_DENIED",
        )
        == "critical"
    )
    assert (
        ne.route_for(
            "step5_cycle_planned",
            execution_authority_decision="PERMANENTLY_DENIED",
        )
        == "critical"
    )


def test_route_for_no_hints_returns_default() -> None:
    for kind, expected in ne.EVENT_KIND_DEFAULT_SEVERITY.items():
        assert (
            ne.route_for(kind, risk_class=None, execution_authority_decision=None)
            == expected
        )


# ---------------------------------------------------------------------------
# Module versioning
# ---------------------------------------------------------------------------


def test_module_and_schema_version_strings() -> None:
    assert isinstance(ne.MODULE_VERSION, str) and ne.MODULE_VERSION
    assert isinstance(ne.SCHEMA_VERSION, str) and ne.SCHEMA_VERSION
    assert "N1" in ne.MODULE_VERSION


# ---------------------------------------------------------------------------
# Side-effect / authority isolation
# ---------------------------------------------------------------------------


def test_module_imports_cleanly_and_is_pure() -> None:
    importlib.reload(ne)
    assert callable(ne.route_for)


def test_importing_module_does_not_flip_step5_invariants() -> None:
    """Re-importing notification_event must not mutate Step 5.0
    invariants on the live development_step5_loop module."""
    from reporting import development_step5_loop as dsl

    importlib.reload(ne)
    assert dsl.step5_implementation_allowed is False
    assert dsl.STEP5_ENABLED_SUBSTAGE == "none"


# ---------------------------------------------------------------------------
# Source-text scans
# ---------------------------------------------------------------------------


def _module_source() -> str:
    return Path(ne.__file__).read_text(encoding="utf-8")


def _imported_module_names() -> set[str]:
    import ast

    src = _module_source()
    tree = ast.parse(src)
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module is not None:
                names.add(node.module)
    return names


def test_no_subprocess_in_module() -> None:
    src = _module_source()
    assert "import subprocess" not in src
    assert "from subprocess" not in src


def test_no_network_in_module() -> None:
    src = _module_source()
    for forbidden in (
        "import socket",
        "import urllib",
        "import http.client",
        "import requests",
        "import httpx",
        "import aiohttp",
    ):
        assert forbidden not in src, forbidden
    assert "from socket" not in src
    assert "from urllib" not in src
    assert "from http" not in src
    assert "from requests" not in src
    assert "from httpx" not in src
    assert "from aiohttp" not in src


def test_no_gh_or_git_subprocess_references() -> None:
    src = _module_source()
    for forbidden in (
        "subprocess.run",
        "subprocess.Popen",
        "os.system",
        "os.popen",
        "shell=True",
    ):
        assert forbidden not in src, forbidden


def test_no_io_in_module() -> None:
    """N1 is pure — no path open / read / write helpers."""
    src = _module_source()
    for forbidden in (
        "Path(",
        "open(",
        ".read_text(",
        ".write_text(",
        "tempfile",
        "os.replace",
    ):
        assert forbidden not in src, forbidden


def test_no_dashboard_or_live_path_or_qre_imports() -> None:
    forbidden_prefixes = (
        "dashboard",
        "frontend",
        "automation",
        "broker",
        "agent.risk",
        "agent.execution",
        "research",
        "reporting.intelligent_routing",
        "live",
        "paper",
        "shadow",
        "trading",
    )
    for module in _imported_module_names():
        for prefix in forbidden_prefixes:
            assert not (
                module == prefix or module.startswith(prefix + ".")
            ), f"forbidden import: {module}"


def test_module_imports_only_typing() -> None:
    """N1 is pure stdlib + nothing more. The only allowed import is
    ``typing`` (for ``Final``)."""
    names = _imported_module_names()
    # ``__future__`` is allowed (annotations).
    allowed = {"__future__", "typing"}
    extra = names - allowed
    assert extra == set(), f"unexpected imports: {extra}"


# ---------------------------------------------------------------------------
# Companion doc invariants
# ---------------------------------------------------------------------------


def _doc_text() -> str:
    return (REPO_ROOT / "docs" / "governance" / "notification_engine.md").read_text(
        encoding="utf-8"
    )


def test_doc_mentions_level_6_only_as_permanently_disabled() -> None:
    """Every mention of "Level 6" in the companion doc must appear
    near a `permanently disabled` qualifier (mirrors
    governance_lint.py rules)."""
    import re

    text = _doc_text()
    pattern = re.compile(r"\bLevel\s*6\b")
    for m in pattern.finditer(text):
        start = max(0, m.start() - 200)
        end = m.start() + 600
        window = text[start:end].lower()
        assert "permanently disabled" in window, (
            f"'Level 6' at offset {m.start()} lacks "
            f"'permanently disabled' qualifier in surrounding window"
        )


def test_doc_states_no_approval_from_notification_click_alone() -> None:
    text = _doc_text().lower()
    assert "no approval from notification click alone" in text


def test_doc_states_mobile_approval_is_human_approval() -> None:
    text = _doc_text().lower()
    assert "human approval" in text
    assert "autonomous merge" in text or "autonomous merge or deploy" in text


def test_doc_pins_step5_invariants_text() -> None:
    text = _doc_text()
    assert "step5_implementation_allowed" in text
    assert "STEP5_ENABLED_SUBSTAGE" in text


def test_doc_lists_n1_through_n5_tracks() -> None:
    text = _doc_text()
    for marker in ("N1", "N2", "N3", "N4", "N5"):
        assert marker in text, marker


def test_doc_marks_n2_through_n5_as_design_only() -> None:
    text = _doc_text().lower()
    assert "design only" in text or "design-only" in text


def test_doc_states_no_secrets_in_repo() -> None:
    text = _doc_text().lower()
    assert "never in repo" in text or "never in the repo" in text
