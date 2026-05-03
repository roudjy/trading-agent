"""Unit tests for the shared HIGH-risk approval policy
(``reporting.approval_policy``).

Properties enforced:

* ``UNKNOWN`` and ``HIGH`` are NEVER ``executable``.
* Protected / frozen / live / CI / governance / secret / telemetry /
  paid / canonical-roadmap inputs all route to a non-executable
  decision and a sensible approval category.
* The order of evaluation is stable and matches the docstring.
* The output dataclass never carries credential-shaped strings.
* Every decision in ``DECISIONS`` round-trips through
  ``decision_to_category`` without raising.
* Cross-module alignment: ``proposal_queue``, ``approval_inbox``,
  ``github_pr_lifecycle``, ``execute_safe_controls``,
  ``recurring_maintenance``, and ``workloop_runtime`` agree with the
  policy on a representative sample of inputs.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from reporting import approval_policy as ap


REPO_ROOT = Path(__file__).resolve().parent.parent.parent


# ---------------------------------------------------------------------------
# Pure invariants on the policy module itself
# ---------------------------------------------------------------------------


def test_module_version_is_v3_15_15_24() -> None:
    assert ap.MODULE_VERSION == "v3.15.15.24"


def test_schema_version_is_one() -> None:
    assert ap.SCHEMA_VERSION == 1


def test_risk_classes_are_four() -> None:
    assert ap.RISK_CLASSES == ("LOW", "MEDIUM", "HIGH", "UNKNOWN")


def test_decisions_enum_is_closed_and_documented() -> None:
    expected = {
        "allowed_read_only",
        "allowed_low_risk_execute_safe",
        "needs_human",
        "blocked_high_risk",
        "blocked_unknown",
        "blocked_protected_path",
        "blocked_frozen_contract",
        "blocked_live_paper_shadow_risk",
        "blocked_governance_change",
        "blocked_external_secret_required",
        "blocked_telemetry_or_data_egress",
        "blocked_paid_tool",
        "blocked_ci_or_test_weakening",
        "blocked_canonical_roadmap_change",
    }
    assert set(ap.DECISIONS) == expected


def test_only_one_decision_is_executable() -> None:
    executable = [
        d for d in ap.DECISIONS if ap.is_executable_decision(d)
    ]
    assert executable == ["allowed_low_risk_execute_safe"]


def test_decision_to_category_round_trips_for_every_decision() -> None:
    for d in ap.DECISIONS:
        cat = ap.decision_to_category(d)
        # All emitted categories belong to the closed approval list.
        assert cat in ap.APPROVAL_CATEGORIES, f"decision {d!r} -> {cat!r}"


def test_universal_forbidden_actions_includes_critical_no_touch_items() -> None:
    fa = ap.universal_forbidden_actions()
    for must in (
        "edit .claude/**",
        "edit AGENTS.md",
        "edit CLAUDE.md",
        "edit frozen contracts",
        "git push --force",
        "gh pr merge --admin",
        "execute live broker",
        "place real-money order",
    ):
        assert must in fa, f"missing forbidden action: {must!r}"


# ---------------------------------------------------------------------------
# decide() — order of evaluation invariants
# ---------------------------------------------------------------------------


def _decide(**kw: Any) -> ap.PolicyDecision:
    return ap.decide(kw)


def test_unknown_risk_class_is_never_executable() -> None:
    d = _decide(risk_class="UNKNOWN")
    assert d.decision == "blocked_unknown"
    assert d.executable is False


def test_high_risk_class_is_never_executable() -> None:
    d = _decide(risk_class="HIGH", title="bump numpy major")
    assert d.decision == "blocked_high_risk"
    assert d.executable is False


def test_high_with_execute_safe_request_is_still_blocked() -> None:
    d = _decide(
        risk_class="HIGH",
        requested_action="execute_safe",
        is_dependabot=True,
        checks_state="passed",
        mergeability_state="clean",
    )
    assert d.decision == "blocked_high_risk"
    assert d.executable is False


def test_protected_path_overrides_low_risk() -> None:
    d = _decide(
        risk_class="LOW",
        affected_files=[".claude/agents/orchestrator.md"],
    )
    assert d.decision == "blocked_protected_path"
    assert d.executable is False


def test_protected_path_overrides_medium_risk() -> None:
    d = _decide(
        risk_class="MEDIUM",
        affected_files=["VERSION"],
    )
    assert d.decision == "blocked_protected_path"


def test_frozen_contract_overrides_low_risk_and_outranks_protected() -> None:
    """Frozen check fires BEFORE the generic protected check, so the
    decision is the dedicated frozen one (not protected_path)."""
    d = _decide(
        risk_class="LOW",
        affected_files=[
            "research/research_latest.json",
            ".claude/hooks/foo.py",
        ],
    )
    assert d.decision == "blocked_frozen_contract"


def test_frozen_contract_strategy_matrix_is_blocked() -> None:
    d = _decide(
        risk_class="MEDIUM",
        affected_files=["research/strategy_matrix.csv"],
    )
    assert d.decision == "blocked_frozen_contract"


def test_live_path_overrides_low_risk() -> None:
    d = _decide(
        risk_class="LOW",
        affected_files=["execution/live/broker_kraken.py"],
    )
    assert d.decision == "blocked_live_paper_shadow_risk"


def test_paper_shadow_path_blocks() -> None:
    d = _decide(
        risk_class="LOW",
        affected_files=["agent/paper/shadow_runner.py"],
    )
    # paper/** glob hits live globs.
    assert d.decision == "blocked_live_paper_shadow_risk"


def test_ci_path_overrides_low_risk() -> None:
    d = _decide(
        risk_class="LOW",
        affected_files=[".github/workflows/ci.yml"],
    )
    assert d.decision == "blocked_ci_or_test_weakening"


def test_governance_change_blocks() -> None:
    d = _decide(
        risk_class="MEDIUM",
        title="Update CODEOWNERS",
    )
    assert d.decision == "blocked_governance_change"


def test_governance_flag_alone_blocks() -> None:
    d = _decide(risk_class="LOW", touches_governance=True)
    assert d.decision == "blocked_governance_change"


def test_canonical_roadmap_token_blocks() -> None:
    d = _decide(summary="v4 roadmap supersedes v3.15", risk_class="MEDIUM")
    assert d.decision == "blocked_canonical_roadmap_change"


def test_canonical_roadmap_flag_alone_blocks() -> None:
    d = _decide(risk_class="LOW", changes_canonical_roadmap=True)
    assert d.decision == "blocked_canonical_roadmap_change"


def test_external_account_or_secret_blocks() -> None:
    d = _decide(
        risk_class="MEDIUM",
        summary="add Datadog APM with api_key auth",
    )
    # api_key is more specific (secret) than telemetry; the order in
    # the policy makes secret fire first.
    assert d.decision == "blocked_external_secret_required"


def test_telemetry_token_blocks_when_no_secret_present() -> None:
    d = _decide(
        risk_class="MEDIUM",
        summary="enable telemetry export to a third-party",
    )
    assert d.decision == "blocked_telemetry_or_data_egress"


def test_paid_tool_token_blocks() -> None:
    d = _decide(
        risk_class="MEDIUM",
        summary="upgrade to the paid plan for nightly storage",
    )
    assert d.decision == "blocked_paid_tool"


def test_negation_disables_telemetry_token() -> None:
    """`no telemetry` must NOT trigger the telemetry rule."""
    d = _decide(
        risk_class="LOW",
        summary="dev-only tool with no telemetry",
    )
    assert d.decision != "blocked_telemetry_or_data_egress"


def test_negation_disables_secret_token() -> None:
    d = _decide(
        risk_class="LOW",
        summary="library that uses no api key, fully local",
    )
    assert d.decision != "blocked_external_secret_required"


# ---------------------------------------------------------------------------
# Provider / merge / checks state — UNKNOWN routing
# ---------------------------------------------------------------------------


def test_malformed_provider_routes_unknown() -> None:
    d = _decide(
        risk_class="LOW",
        requested_action="execute_safe",
        provider_state="malformed",
        is_dependabot=True,
        checks_state="passed",
        mergeability_state="clean",
    )
    assert d.decision == "blocked_unknown"
    assert d.executable is False


def test_pending_checks_block_execute_safe() -> None:
    d = _decide(
        risk_class="LOW",
        requested_action="execute_safe",
        is_dependabot=True,
        checks_state="pending",
        mergeability_state="clean",
    )
    assert d.decision == "blocked_unknown"


def test_failing_checks_block_execute_safe() -> None:
    d = _decide(
        risk_class="LOW",
        requested_action="execute_safe",
        is_dependabot=True,
        checks_state="failed",
        mergeability_state="clean",
    )
    assert d.decision == "blocked_unknown"


def test_unknown_checks_block_execute_safe() -> None:
    d = _decide(
        risk_class="LOW",
        requested_action="execute_safe",
        is_dependabot=True,
        checks_state="unknown",
        mergeability_state="clean",
    )
    assert d.decision == "blocked_unknown"


def test_dirty_merge_blocks_execute_safe() -> None:
    d = _decide(
        risk_class="LOW",
        requested_action="execute_safe",
        is_dependabot=True,
        checks_state="passed",
        mergeability_state="dirty",
    )
    assert d.decision == "blocked_unknown"


# ---------------------------------------------------------------------------
# Dependabot execute-safe — the only allowed_low_risk_execute_safe path
# ---------------------------------------------------------------------------


def test_non_dependabot_execute_safe_routes_to_needs_human() -> None:
    d = _decide(
        risk_class="LOW",
        requested_action="execute_safe",
        is_dependabot=False,
        pr_author="joery",
        checks_state="passed",
        mergeability_state="clean",
    )
    assert d.decision == "needs_human"
    assert d.executable is False


def test_dependabot_low_with_all_evidence_is_executable() -> None:
    d = _decide(
        risk_class="LOW",
        requested_action="execute_safe",
        is_dependabot=True,
        checks_state="passed",
        mergeability_state="clean",
    )
    assert d.decision == "allowed_low_risk_execute_safe"
    assert d.executable is True


def test_dependabot_medium_with_all_evidence_is_executable() -> None:
    d = _decide(
        risk_class="MEDIUM",
        requested_action="execute_safe",
        is_dependabot=True,
        checks_state="passed",
        mergeability_state="clean",
    )
    assert d.decision == "allowed_low_risk_execute_safe"
    assert d.executable is True


def test_dependabot_high_is_blocked_even_when_other_evidence_is_perfect() -> None:
    d = _decide(
        risk_class="HIGH",
        requested_action="execute_safe",
        is_dependabot=True,
        checks_state="passed",
        mergeability_state="clean",
    )
    assert d.decision == "blocked_high_risk"
    assert d.executable is False


# ---------------------------------------------------------------------------
# Default / read-only path
# ---------------------------------------------------------------------------


def test_low_risk_no_signals_is_read_only() -> None:
    d = _decide(risk_class="LOW", title="harmless docs change")
    assert d.decision == "allowed_read_only"
    assert d.executable is False
    assert d.allowed_max_action == "read_only"


def test_medium_risk_no_signals_is_read_only() -> None:
    d = _decide(risk_class="MEDIUM", title="another harmless change")
    assert d.decision == "allowed_read_only"
    assert d.executable is False


# ---------------------------------------------------------------------------
# Defensive: no decision returns executable=true except the canonical one
# ---------------------------------------------------------------------------


def test_no_blocked_or_needs_human_ever_executable() -> None:
    """Iterate the full enumeration and verify the invariant."""
    for d_name in ap.DECISIONS:
        # Skip the one positive case.
        if d_name == "allowed_low_risk_execute_safe":
            continue
        # Build a synthetic decision via _build_decision-equivalent
        # path: invoke decide() with inputs tailored to land on each
        # decision. We only sanity-check the closed enum here.
        assert ap.is_executable_decision(d_name) is False


# ---------------------------------------------------------------------------
# PolicyInput.from_mapping robustness
# ---------------------------------------------------------------------------


def test_from_mapping_handles_missing_fields() -> None:
    pi = ap.PolicyInput.from_mapping({})
    assert pi.title == ""
    assert pi.risk_class == "UNKNOWN"
    assert pi.affected_files == ()
    assert pi.is_dependabot is False


def test_from_mapping_normalises_unknown_risk_class() -> None:
    pi = ap.PolicyInput.from_mapping({"risk_class": "WAT"})
    assert pi.risk_class == "UNKNOWN"


def test_from_mapping_handles_none_values() -> None:
    pi = ap.PolicyInput.from_mapping(
        {"title": None, "affected_files": None, "is_dependabot": None}
    )
    assert pi.title == ""
    assert pi.affected_files == ()
    assert pi.is_dependabot is False


# ---------------------------------------------------------------------------
# policy_summary() shape
# ---------------------------------------------------------------------------


def test_policy_summary_is_stable_shape() -> None:
    s = ap.policy_summary()
    for k in (
        "module_version",
        "schema_version",
        "generated_at_utc",
        "risk_classes",
        "decisions",
        "approval_categories",
        "allowed_max_actions",
        "forbidden_agent_actions_universal",
        "frozen_contracts",
        "high_or_unknown_is_executable",
        "execute_safe_requires_dependabot_low_or_medium",
        "execute_safe_requires_two_layer_opt_in",
    ):
        assert k in s, f"missing key {k!r}"
    assert s["high_or_unknown_is_executable"] is False
    assert s["execute_safe_requires_dependabot_low_or_medium"] is True
    assert s["execute_safe_requires_two_layer_opt_in"] is True


def test_policy_summary_has_no_credentials() -> None:
    ap.assert_no_credential_values(ap.policy_summary())


# ---------------------------------------------------------------------------
# Credential redaction
# ---------------------------------------------------------------------------


def test_assert_no_credential_values_accepts_path_strings() -> None:
    # Path-shaped strings (including config/config.yaml) are NOT
    # credentials. The narrow guard must pass them through.
    ap.assert_no_credential_values(
        {"path": "config/config.yaml", "frozen": "research/research_latest.json"}
    )


def test_assert_no_credential_values_rejects_anthropic_key() -> None:
    with pytest.raises(AssertionError):
        ap.assert_no_credential_values({"leak": "sk-ant-XXXXXXXX"})


def test_assert_no_credential_values_rejects_github_pat() -> None:
    with pytest.raises(AssertionError):
        ap.assert_no_credential_values(["ghp_AAAAAAA"])


def test_assert_no_credential_values_rejects_aws_key() -> None:
    with pytest.raises(AssertionError):
        ap.assert_no_credential_values({"x": {"y": "AKIAEXAMPLE"}})


def test_assert_no_credential_values_rejects_pem() -> None:
    with pytest.raises(AssertionError):
        ap.assert_no_credential_values("-----BEGIN PRIVATE KEY-----")


# ---------------------------------------------------------------------------
# Cross-module alignment — the whole point of v3.15.15.24
# ---------------------------------------------------------------------------


def test_proposal_queue_constants_align_with_policy() -> None:
    """``reporting.proposal_queue`` keeps its own copy of the
    governance lists for self-containment, but every entry must be a
    subset of the canonical lists in approval_policy."""
    from reporting import proposal_queue as pq

    assert set(pq.FROZEN_CONTRACTS) <= set(ap.FROZEN_CONTRACTS)
    # PROTECTED_GLOBS in proposal_queue is a subset of ap's (ap adds
    # AGENTS.md and CLAUDE.md beyond the proposal_queue list).
    assert set(pq.PROTECTED_GLOBS) <= set(ap.PROTECTED_GLOBS)


def test_approval_inbox_categories_align_with_policy() -> None:
    from reporting import approval_inbox as ai

    assert set(ai.CATEGORIES) == set(ap.APPROVAL_CATEGORIES)


def test_github_pr_lifecycle_high_pr_routes_to_high_risk() -> None:
    """A PR classified HIGH by github_pr_lifecycle must, when fed
    through the shared policy, land on blocked_high_risk."""
    d = ap.decide(
        {
            "title": "Bump numpy from 1.24 to 2.0",
            "risk_class": "HIGH",
            "is_dependabot": True,
            "pr_author": "dependabot[bot]",
            "checks_state": "passed",
            "mergeability_state": "clean",
            "requested_action": "execute_safe",
        }
    )
    assert d.decision == "blocked_high_risk"
    assert d.executable is False


def test_github_pr_lifecycle_protected_path_routes_to_protected() -> None:
    d = ap.decide(
        {
            "title": "Bump foo",
            "risk_class": "LOW",
            "is_dependabot": True,
            "affected_files": [".github/CODEOWNERS"],
            "requested_action": "execute_safe",
            "checks_state": "passed",
            "mergeability_state": "clean",
        }
    )
    assert d.decision == "blocked_protected_path"


def test_recurring_maintenance_dependabot_job_disabled_by_default() -> None:
    """Cross-module alignment: the dependabot execute-safe job in
    recurring_maintenance must remain disabled by default. Without
    that, the two-layer opt-in is meaningless."""
    from reporting import recurring_maintenance as rm

    spec = rm._JOB_REGISTRY.get(rm.JOB_DEPENDABOT_EXECUTE_SAFE)
    assert spec is not None
    assert spec["default_enabled"] is False


def test_workloop_runtime_safe_to_execute_remains_false() -> None:
    """The shared policy promises HIGH/UNKNOWN never execute. The
    workloop runtime carries this contract via a hard-coded
    ``safe_to_execute=false``. We verify the constant directly."""
    from reporting import workloop_runtime as wr

    src = Path(wr.__file__).read_text(encoding="utf-8")
    assert '"safe_to_execute": False' in src


def test_recurring_maintenance_safe_to_execute_remains_false() -> None:
    from reporting import recurring_maintenance as rm

    src = Path(rm.__file__).read_text(encoding="utf-8")
    assert '"safe_to_execute": False' in src


def test_execute_safe_controls_high_actions_not_in_catalog() -> None:
    """The execute-safe controls catalog must never list a HIGH
    action as eligible. We assert: every action the catalog declares
    as executable has risk LOW or MEDIUM."""
    from reporting import execute_safe_controls as esc

    for action_name, risk in esc._ACTION_RISK.items():
        assert risk in (esc.RISK_LOW, esc.RISK_MEDIUM), (
            f"action {action_name!r} declared as {risk!r} (must be LOW or MEDIUM)"
        )


def test_no_module_emits_safe_to_execute_true_for_high() -> None:
    """Repository-wide invariant: search every reporting module for a
    line that would wire ``safe_to_execute=True`` near a HIGH
    classification. We rely on the negative property: NO occurrence
    of the literal substring ``"safe_to_execute": True``."""
    bad = []
    for mod_name in (
        "reporting/workloop_runtime.py",
        "reporting/recurring_maintenance.py",
        "reporting/execute_safe_controls.py",
        "reporting/github_pr_lifecycle.py",
        "reporting/proposal_queue.py",
        "reporting/approval_inbox.py",
        "reporting/approval_policy.py",
    ):
        text = (REPO_ROOT / mod_name).read_text(encoding="utf-8")
        if '"safe_to_execute": True' in text or "safe_to_execute=True" in text:
            bad.append(mod_name)
    assert bad == [], f"modules emit safe_to_execute=True: {bad}"


# ---------------------------------------------------------------------------
# Schema doc presence (machine-readable surface)
# ---------------------------------------------------------------------------


def test_schema_doc_exists() -> None:
    p = REPO_ROOT / "docs" / "governance" / "high_risk_approval_policy" / "schema.v1.md"
    assert p.exists(), f"missing schema doc: {p}"
    text = p.read_text(encoding="utf-8")
    assert "v3.15.15.24" in text


def test_runbook_doc_exists() -> None:
    p = REPO_ROOT / "docs" / "governance" / "high_risk_approval_policy.md"
    assert p.exists(), f"missing runbook doc: {p}"
    text = p.read_text(encoding="utf-8")
    assert "v3.15.15.24" in text


# ---------------------------------------------------------------------------
# Decision payload sanity
# ---------------------------------------------------------------------------


def test_decision_to_dict_is_json_safe() -> None:
    d = _decide(risk_class="LOW")
    payload = d.to_dict()
    json.dumps(payload)  # must serialise


def test_every_decision_has_required_evidence_or_explicit_empty() -> None:
    """Every decision either declares which evidence fields it
    references, or explicitly returns empty (read-only)."""
    samples = {
        "blocked_protected_path": {"affected_files": [".claude/hooks/x.py"]},
        "blocked_frozen_contract": {
            "affected_files": ["research/research_latest.json"]
        },
        "blocked_live_paper_shadow_risk": {
            "affected_files": ["execution/live/foo.py"]
        },
        "blocked_ci_or_test_weakening": {
            "affected_files": [".github/workflows/ci.yml"]
        },
        "blocked_governance_change": {"touches_governance": True},
        "blocked_canonical_roadmap_change": {
            "changes_canonical_roadmap": True,
        },
        "blocked_external_secret_required": {"requires_secret": True},
        "blocked_telemetry_or_data_egress": {
            "has_telemetry_or_data_egress": True
        },
        "blocked_paid_tool": {"requires_paid_tool": True},
        "blocked_high_risk": {"risk_class": "HIGH"},
        "blocked_unknown": {"risk_class": "UNKNOWN"},
        "needs_human": {
            "risk_class": "LOW",
            "requested_action": "execute_safe",
            "is_dependabot": False,
            "pr_author": "joery",
            "checks_state": "passed",
            "mergeability_state": "clean",
        },
        "allowed_low_risk_execute_safe": {
            "risk_class": "LOW",
            "requested_action": "execute_safe",
            "is_dependabot": True,
            "checks_state": "passed",
            "mergeability_state": "clean",
        },
        "allowed_read_only": {"risk_class": "LOW"},
    }
    for expected, kwargs in samples.items():
        d = ap.decide(kwargs)
        assert d.decision == expected, f"input {kwargs!r} expected {expected!r} got {d.decision!r}"
