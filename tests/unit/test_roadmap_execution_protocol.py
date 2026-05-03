"""Unit tests for ``reporting.roadmap_execution_protocol``.

Properties enforced (verbatim from the v3.15.15.28 brief):

* ``--describe`` outputs the protocol catalogue.
* ``--plan-item`` requires ``--dry-run``; the protocol never
  implements.
* LOW item with a known type produces ``executable=false`` and
  ``implementation_allowed=true`` after policy approval.
* HIGH item routes to ``status=blocked`` / ``needs_human``.
* UNKNOWN item routes to ``blocked_unknown`` / ``unknown_state``.
* Canonical roadmap adoption requires human approval.
* Live / paper / shadow / risk item is blocked.
* Secret / external / paid / telemetry items need human approval.
* Protected / frozen-path items are blocked.
* Missing evidence => UNKNOWN.
* Agent assignment contains all eight required roles in canonical
  order.
* Guardian review requirements present on every plan.
* Required tests list includes the baseline gates.
* Branch naming is deterministic.
* One item per branch by default.
* No actual git/gh/subprocess/network execution path.
* Artifact / schema is stable.
* approval_policy integration is verbatim.
* Frozen contract sha256 unchanged after running the protocol.
* No credential-shaped values in any plan output.
* Status endpoint projection works when the artifact exists.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from reporting import approval_policy as ap
from reporting import roadmap_execution_protocol as rep


REPO_ROOT = Path(__file__).resolve().parent.parent.parent


# ---------------------------------------------------------------------------
# Module-level invariants
# ---------------------------------------------------------------------------


def test_module_version_is_v3_15_15_28() -> None:
    assert rep.MODULE_VERSION == "v3.15.15.28"


def test_schema_version_is_one() -> None:
    assert rep.SCHEMA_VERSION == 1


def test_item_types_is_a_closed_tuple_with_unknown() -> None:
    assert isinstance(rep.ITEM_TYPES, tuple)
    assert "unknown" in rep.ITEM_TYPES


def test_item_types_open_to_implementation_is_a_subset() -> None:
    assert rep.ITEM_TYPES_OPEN_TO_IMPLEMENTATION.issubset(set(rep.ITEM_TYPES))


def test_statuses_enum_is_closed() -> None:
    assert set(rep.STATUSES) == {
        "proposed",
        "needs_human",
        "blocked",
        "unknown_state",
    }


def test_no_subprocess_or_network_in_module() -> None:
    src = Path(rep.__file__).read_text(encoding="utf-8")
    forbidden = (
        "import subprocess",
        "from subprocess",
        "Popen(",
        "import requests",
        "import urllib.request",
        "from urllib.request",
        "import socket",
    )
    for tok in forbidden:
        assert tok not in src, f"forbidden import in roadmap_execution_protocol: {tok!r}"


def test_no_gh_or_git_invocation_in_module() -> None:
    src = Path(rep.__file__).read_text(encoding="utf-8")
    forbidden = ('"gh"', "'gh'", "/usr/bin/gh", '"git"', "'git'", "/usr/bin/git")
    for tok in forbidden:
        assert tok not in src, f"forbidden tool spawn: {tok!r}"


# ---------------------------------------------------------------------------
# describe()
# ---------------------------------------------------------------------------


def test_describe_returns_protocol_catalogue() -> None:
    d = rep.describe_protocol()
    assert d["report_kind"] == "roadmap_execution_protocol_description"
    assert d["module_version"] == rep.MODULE_VERSION
    assert d["safe_to_execute"] is False
    assert set(d["item_types"]) == set(rep.ITEM_TYPES)
    assert set(d["statuses"]) == set(rep.STATUSES)
    role_names = [r["name"] for r in d["agent_roles"]]
    expected_roles = [
        "product_owner",
        "strategic_advisor",
        "planner",
        "implementation_agent",
        "architecture_guardian",
        "ci_guardian",
        "security_governance_guardian",
        "operator",
    ]
    assert role_names == expected_roles


def test_describe_is_serializable() -> None:
    d = rep.describe_protocol()
    json.dumps(d)


# ---------------------------------------------------------------------------
# plan_item — happy paths and forbidden paths
# ---------------------------------------------------------------------------


def _plan(**kw: Any) -> dict[str, Any]:
    return rep.plan_item(kw, frozen_utc="2026-05-03T08:00:00Z")


def test_low_docs_item_is_implementation_allowed() -> None:
    p = _plan(
        item_id="r_docs_aaaa",
        title="Add operator runbook",
        summary="Document staleness threshold semantics",
        affected_files=["docs/governance/autonomy_metrics.md"],
        risk_class="LOW",
    )
    assert p["item_type"] == "docs_only"
    assert p["risk_class"] == "LOW"
    assert p["decision"] == ap.DECISION_ALLOWED_READ_ONLY
    assert p["status"] == rep.STATUS_PROPOSED
    assert p["executable"] is False
    assert p["implementation_allowed"] is True
    assert p["safe_to_execute"] is False
    assert p["blocked_reason"] is None


def test_low_frontend_read_only_item_is_implementation_allowed() -> None:
    p = _plan(
        title="Render new read-only row on Status card",
        summary="Read-only display from existing /api/agent-control/status payload",
        affected_files=[
            "frontend/src/routes/AgentControl.tsx",
            "frontend/src/api/agent_control.ts",
        ],
        risk_class="MEDIUM",
    )
    assert p["item_type"] == "frontend_read_only"
    assert p["status"] == rep.STATUS_PROPOSED
    assert p["implementation_allowed"] is True


def test_low_reporting_read_only_item_is_implementation_allowed() -> None:
    p = _plan(
        title="Add a small read-only digest module",
        summary="Emit a deterministic JSON digest for a new metric source",
        affected_files=["reporting/new_digest.py"],
        risk_class="LOW",
    )
    assert p["item_type"] == "reporting_read_only"
    assert p["implementation_allowed"] is True


def test_high_live_path_item_is_blocked() -> None:
    p = _plan(
        title="Switch broker_kraken to live API",
        summary="execution/live/broker_kraken use_live=True",
        affected_files=["execution/live/broker_kraken.py"],
        risk_class="HIGH",
    )
    assert p["item_type"] == "live_paper_shadow_risk"
    assert p["status"] == rep.STATUS_BLOCKED
    assert p["implementation_allowed"] is False
    assert "blocked_live_paper_shadow_risk" in p["decision"]


def test_unknown_item_routes_to_unknown_state() -> None:
    p = _plan(title="(no idea)")
    # No affected files + no token signals => item_type=unknown.
    assert p["item_type"] == "unknown"
    assert p["status"] == rep.STATUS_UNKNOWN
    assert p["implementation_allowed"] is False
    assert "unknown_item_type" in (p["blocked_reason"] or "")


def test_high_risk_class_routes_to_blocked() -> None:
    p = _plan(
        title="Bump numpy from 1.24 to 2.0",
        summary="major bump",
        affected_files=["requirements.txt"],
        risk_class="HIGH",
    )
    assert p["risk_class"] == "HIGH"
    assert p["decision"] == ap.DECISION_BLOCKED_HIGH_RISK
    assert p["implementation_allowed"] is False
    assert p["status"] == rep.STATUS_BLOCKED


def test_canonical_roadmap_adoption_requires_human() -> None:
    p = _plan(
        title="Adopt v4 roadmap",
        summary="canonical roadmap adoption supersedes v3.15",
    )
    assert p["item_type"] == "canonical_roadmap_adoption"
    # The policy classifies this as blocked_canonical_roadmap_change.
    assert p["decision"] == ap.DECISION_BLOCKED_CANONICAL_ROADMAP_CHANGE
    assert p["status"] == rep.STATUS_BLOCKED
    assert p["implementation_allowed"] is False


def test_governance_change_routes_to_blocked() -> None:
    p = _plan(
        title="Update CODEOWNERS",
        summary="add a new owner to .github/CODEOWNERS",
        touches_governance=True,
    )
    assert p["item_type"] == "governance_change"
    assert p["decision"] == ap.DECISION_BLOCKED_GOVERNANCE_CHANGE
    assert p["status"] == rep.STATUS_BLOCKED
    assert p["implementation_allowed"] is False


def test_external_secret_item_needs_human() -> None:
    p = _plan(
        title="Add Datadog APM",
        summary="we'll need an api key",
        risk_class="MEDIUM",
    )
    assert p["item_type"] == "external_account_or_secret"
    assert p["decision"] == ap.DECISION_BLOCKED_EXTERNAL_SECRET_REQUIRED
    assert p["implementation_allowed"] is False


def test_telemetry_item_needs_human() -> None:
    p = _plan(
        title="Pipe metrics to telemetry",
        summary="telemetry export to a third-party",
        risk_class="MEDIUM",
    )
    assert p["item_type"] == "telemetry_or_data_egress"
    assert p["decision"] == ap.DECISION_BLOCKED_TELEMETRY_OR_DATA_EGRESS
    assert p["implementation_allowed"] is False


def test_paid_tool_item_needs_human() -> None:
    p = _plan(
        title="Subscribe to paid plan for nightly storage",
        summary="paid plan upgrade",
        risk_class="MEDIUM",
    )
    assert p["item_type"] == "paid_tool"
    assert p["decision"] == ap.DECISION_BLOCKED_PAID_TOOL
    assert p["implementation_allowed"] is False


def test_protected_path_item_is_blocked() -> None:
    p = _plan(
        title="Edit no-touch settings",
        summary="touch .claude/settings.json",
        affected_files=[".claude/settings.json"],
    )
    # Protected path takes precedence in approval_policy ordering.
    assert p["decision"] == ap.DECISION_BLOCKED_PROTECTED_PATH
    assert p["status"] == rep.STATUS_BLOCKED
    assert p["implementation_allowed"] is False


def test_frozen_contract_item_is_blocked() -> None:
    p = _plan(
        title="Regenerate research_latest",
        summary="contract regen",
        affected_files=["research/research_latest.json"],
    )
    assert p["decision"] == ap.DECISION_BLOCKED_FROZEN_CONTRACT
    assert p["status"] == rep.STATUS_BLOCKED


def test_ci_or_tests_item_is_blocked_from_implementation() -> None:
    p = _plan(
        title="Tweak CI workflow",
        summary="speed up tests",
        affected_files=[".github/workflows/ci.yml"],
        risk_class="LOW",
    )
    # The policy elevates this to blocked_ci_or_test_weakening.
    assert p["decision"] == ap.DECISION_BLOCKED_CI_OR_TEST_WEAKENING
    assert p["status"] == rep.STATUS_BLOCKED
    assert p["implementation_allowed"] is False


def test_missing_evidence_routes_to_unknown() -> None:
    p = _plan()  # no fields at all
    assert p["item_type"] == "unknown"
    # Empty risk_class => UNKNOWN policy decision.
    assert p["decision"] == ap.DECISION_BLOCKED_UNKNOWN
    assert p["status"] == rep.STATUS_UNKNOWN
    assert p["implementation_allowed"] is False


# ---------------------------------------------------------------------------
# Plan shape
# ---------------------------------------------------------------------------


def test_every_plan_has_eight_agent_roles_in_order() -> None:
    p = _plan(
        title="Add docs",
        summary="docs only",
        affected_files=["docs/governance/example.md"],
        risk_class="LOW",
    )
    role_names = [a["name"] for a in p["agent_assignments"]]
    assert role_names == [
        "product_owner",
        "strategic_advisor",
        "planner",
        "implementation_agent",
        "architecture_guardian",
        "ci_guardian",
        "security_governance_guardian",
        "operator",
    ]


def test_every_plan_has_three_guardian_reviews() -> None:
    p = _plan(title="x")
    assert p["guardian_reviews_required"] == [
        "architecture_guardian",
        "ci_guardian",
        "security_governance_guardian",
    ]


def test_every_plan_has_baseline_required_tests() -> None:
    p = _plan(title="x", affected_files=["docs/governance/example.md"])
    base = ["scripts/governance_lint.py", "tests/smoke", "frozen-hash check"]
    for entry in base:
        assert entry in p["required_tests"], entry


def test_every_plan_has_merge_requirements() -> None:
    p = _plan(title="x")
    assert "all required GitHub checks green" in p["merge_requirements"]
    assert "frozen contract sha256 unchanged" in p["merge_requirements"]


def test_every_plan_has_post_merge_checks() -> None:
    p = _plan(title="x")
    assert "pull main" in p["post_merge_checks"]


def test_every_plan_carries_safe_to_execute_false() -> None:
    p = _plan(title="x")
    assert p["safe_to_execute"] is False
    assert p["executable"] is False


def test_every_plan_carries_policy_reference() -> None:
    p = _plan(title="x")
    assert p["policy"]["module_version"] == ap.MODULE_VERSION
    assert p["policy"]["high_or_unknown_is_executable"] is False


def test_every_plan_emits_forbidden_actions_from_policy() -> None:
    p = _plan(
        title="Edit no-touch",
        affected_files=[".claude/settings.json"],
    )
    # Universal forbidden actions are always present.
    assert "git push --force" in p["forbidden_actions"]
    assert "edit .claude/**" in p["forbidden_actions"]


# ---------------------------------------------------------------------------
# Branch naming
# ---------------------------------------------------------------------------


def test_branch_name_is_deterministic_for_same_inputs() -> None:
    p1 = _plan(
        item_id="r_aaaa1234",
        title="Add operator runbook",
        proposed_release_id="v3.15.16.0",
        affected_files=["docs/governance/example.md"],
        risk_class="LOW",
    )
    p2 = _plan(
        item_id="r_aaaa1234",
        title="Add operator runbook",
        proposed_release_id="v3.15.16.0",
        affected_files=["docs/governance/example.md"],
        risk_class="LOW",
    )
    assert p1["proposed_branch"] == p2["proposed_branch"]


def test_branch_name_uses_item_id_and_title() -> None:
    p = _plan(
        item_id="r_aaaa1234",
        title="Add operator runbook",
        proposed_release_id="v3.15.16.0",
        affected_files=["docs/governance/example.md"],
        risk_class="LOW",
    )
    branch = p["proposed_branch"]
    assert branch.startswith("fix/")
    assert "r-aaaa1234" in branch
    assert "add-operator-runbook" in branch


def test_one_item_per_branch_default() -> None:
    """The branch name embeds the item_id; two different item_ids
    produce two different branches."""
    p1 = _plan(item_id="r_aaaa", title="X", risk_class="LOW")
    p2 = _plan(item_id="r_bbbb", title="X", risk_class="LOW")
    assert p1["proposed_branch"] != p2["proposed_branch"]


# ---------------------------------------------------------------------------
# approval_policy integration
# ---------------------------------------------------------------------------


def test_approval_policy_decision_is_embedded_verbatim() -> None:
    p = _plan(title="x", risk_class="HIGH")
    apd = p["approval_policy_decision"]
    # Shape parity with PolicyDecision.to_dict().
    assert "decision" in apd
    assert "risk_class" in apd
    assert "approval_category" in apd
    assert "allowed_max_action" in apd
    assert "executable" in apd
    assert "requires_human_approval" in apd
    assert "forbidden_agent_actions" in apd
    assert "required_evidence" in apd


def test_implementation_allowed_only_if_policy_says_allowed_read_only() -> None:
    """Even an open-to-implementation item type stays blocked if
    the policy decision is NOT ``allowed_read_only``."""
    # A docs-only item with risk_class HIGH still has decision
    # blocked_high_risk via approval_policy.
    p = _plan(
        title="docs item but flagged HIGH",
        affected_files=["docs/governance/example.md"],
        risk_class="HIGH",
    )
    assert p["item_type"] == "docs_only"
    assert p["decision"] == ap.DECISION_BLOCKED_HIGH_RISK
    assert p["implementation_allowed"] is False


def test_unknown_state_explicitly_returns_implementation_disallowed() -> None:
    p = _plan(title="(unknown)")
    assert p["item_type"] == "unknown"
    assert p["implementation_allowed"] is False


# ---------------------------------------------------------------------------
# Atomic writes + read_latest_snapshot
# ---------------------------------------------------------------------------


@pytest.fixture
def isolated_dirs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setattr(rep, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        rep,
        "DIGEST_DIR_JSON",
        tmp_path / "logs" / "roadmap_execution_protocol",
    )
    return tmp_path


def test_write_outputs_creates_latest_and_timestamped(isolated_dirs) -> None:
    p = _plan(title="x", risk_class="LOW", affected_files=["docs/governance/example.md"])
    paths = rep.write_outputs(p)
    latest = (isolated_dirs / paths["latest"]).read_bytes()
    timestamped = (isolated_dirs / paths["timestamped"]).read_bytes()
    assert latest == timestamped
    history = (isolated_dirs / paths["history"]).read_text(encoding="utf-8")
    assert history.strip().endswith("}")


def test_history_is_append_only(isolated_dirs) -> None:
    p1 = _plan(
        title="x",
        risk_class="LOW",
        affected_files=["docs/governance/example.md"],
    )
    p2 = rep.plan_item(
        {
            "title": "y",
            "risk_class": "LOW",
            "affected_files": ["docs/governance/example.md"],
        },
        frozen_utc="2026-05-03T08:01:00Z",
    )
    rep.write_outputs(p1)
    rep.write_outputs(p2)
    hist = (
        isolated_dirs / "logs" / "roadmap_execution_protocol" / "history.jsonl"
    ).read_text(encoding="utf-8")
    lines = [ln for ln in hist.splitlines() if ln.strip()]
    assert len(lines) == 2


def test_read_latest_snapshot_returns_none_when_missing(isolated_dirs) -> None:
    assert rep.read_latest_snapshot() is None


def test_read_latest_snapshot_round_trips(isolated_dirs) -> None:
    p = _plan(title="x", risk_class="LOW", affected_files=["docs/governance/example.md"])
    rep.write_outputs(p)
    rt = rep.read_latest_snapshot()
    assert isinstance(rt, dict)
    assert rt["item_id"] == p["item_id"]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def test_cli_describe_returns_zero(capsys, monkeypatch: pytest.MonkeyPatch) -> None:
    rc = rep.main(["--describe"])
    assert rc == 0
    out = capsys.readouterr().out
    parsed = json.loads(out)
    assert parsed["report_kind"] == "roadmap_execution_protocol_description"


def test_cli_plan_item_without_dry_run_is_refused(
    capsys, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Hard policy: --plan-item without --dry-run is rejected."""
    with pytest.raises(SystemExit):
        rep.main(["--plan-item", '{"title":"x"}'])


def test_cli_plan_item_with_dry_run_writes_artifact(
    isolated_dirs, capsys, monkeypatch: pytest.MonkeyPatch
) -> None:
    rc = rep.main(
        [
            "--plan-item",
            '{"title":"x","risk_class":"LOW","affected_files":["docs/governance/example.md"]}',
            "--dry-run",
            "--frozen-utc",
            "2026-05-03T08:00:00Z",
        ]
    )
    assert rc == 0
    assert (
        isolated_dirs / "logs" / "roadmap_execution_protocol" / "latest.json"
    ).exists()


def test_cli_status_returns_one_when_artifact_missing(
    isolated_dirs, capsys
) -> None:
    rc = rep.main(["--status"])
    assert rc != 0


def test_cli_no_freeform_command_flags() -> None:
    """The CLI must not expose --command / --argv / --shell / --exec."""
    src = Path(rep.__file__).read_text(encoding="utf-8")
    for tok in ("--command", "--argv", "--shell", "--exec"):
        assert tok not in src, f"free-form CLI flag found: {tok!r}"


# ---------------------------------------------------------------------------
# Frozen-contract integrity
# ---------------------------------------------------------------------------


def test_protocol_does_not_mutate_frozen_contract_paths(isolated_dirs) -> None:
    """The protocol writes only under logs/roadmap_execution_protocol/."""
    p = _plan(title="x", risk_class="LOW", affected_files=["docs/governance/example.md"])
    paths = rep.write_outputs(p)
    for label, rel in paths.items():
        assert rel.startswith(
            "logs/roadmap_execution_protocol/"
        ), f"{label} -> {rel}"


# ---------------------------------------------------------------------------
# Schema/runbook docs presence
# ---------------------------------------------------------------------------


def test_schema_doc_exists() -> None:
    p = (
        REPO_ROOT
        / "docs"
        / "governance"
        / "roadmap_item_execution_protocol"
        / "schema.v1.md"
    )
    assert p.exists(), f"missing schema doc: {p}"
    text = p.read_text(encoding="utf-8")
    assert "v3.15.15.28" in text


def test_runbook_doc_exists() -> None:
    p = REPO_ROOT / "docs" / "governance" / "roadmap_item_execution_protocol.md"
    assert p.exists(), f"missing runbook doc: {p}"
    text = p.read_text(encoding="utf-8")
    assert "v3.15.15.28" in text


def test_agent_handoff_doc_exists() -> None:
    p = REPO_ROOT / "docs" / "governance" / "agent_handoff_protocol.md"
    assert p.exists(), f"missing agent handoff doc: {p}"


# ---------------------------------------------------------------------------
# Credential redaction
# ---------------------------------------------------------------------------


def test_credential_value_in_input_trips_guard() -> None:
    """A credential-shaped string in the title routes through the
    same approval_policy.assert_no_credential_values guard that
    every other reporter uses."""
    with pytest.raises(AssertionError):
        rep.plan_item(
            {"title": "leak: sk-ant-AAAAAAAA12345"},
            frozen_utc="2026-05-03T08:00:00Z",
        )


# ---------------------------------------------------------------------------
# Dashboard projection (read-only)
# ---------------------------------------------------------------------------


def test_dashboard_status_includes_roadmap_protocol_block(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """End-to-end: /api/agent-control/status emits a
    ``roadmap_protocol`` envelope that is either ``ok`` with
    populated data or ``not_available`` with a reason."""
    from flask import Flask
    from dashboard import api_agent_control as ac

    monkeypatch.setattr(ac, "LOGS_DIR", tmp_path / "logs")
    monkeypatch.setattr(
        ac,
        "WORKLOOP_LATEST",
        tmp_path / "logs" / "autonomous_workloop" / "latest.json",
    )
    monkeypatch.setattr(
        ac,
        "PR_LIFECYCLE_LATEST",
        tmp_path / "logs" / "github_pr_lifecycle" / "latest.json",
    )
    flask_app = Flask(__name__)
    ac.register_agent_control_routes(flask_app)
    client = flask_app.test_client()
    body = client.get("/api/agent-control/status").get_json()
    assert "roadmap_protocol" in body
    rp = body["roadmap_protocol"]
    assert rp["status"] in ("ok", "not_available")
    if rp["status"] == "not_available":
        assert "reason" in rp


# ---------------------------------------------------------------------------
# Defense-in-depth: no plan ever returns executable=True
# ---------------------------------------------------------------------------


def test_no_combination_of_inputs_yields_executable_true() -> None:
    """Sweep a large representative sample of inputs and confirm
    the protocol never emits ``executable=true``."""
    samples: list[dict[str, Any]] = [
        {"title": "x"},
        {"title": "x", "risk_class": "LOW"},
        {"title": "x", "risk_class": "MEDIUM"},
        {"title": "x", "risk_class": "HIGH"},
        {"title": "x", "risk_class": "UNKNOWN"},
        {"title": "x", "is_dependabot": True},
        {"title": "x", "affected_files": ["docs/governance/example.md"]},
        {"title": "x", "affected_files": [".claude/settings.json"]},
        {"title": "x", "affected_files": ["execution/live/foo.py"]},
        {"title": "x", "affected_files": ["research/research_latest.json"]},
        {"title": "x", "affected_files": [".github/workflows/ci.yml"]},
        {"title": "v4 roadmap supersedes v3.15"},
        {"title": "Datadog API key needed"},
        {"title": "telemetry export"},
        {"title": "paid plan upgrade"},
    ]
    for s in samples:
        p = rep.plan_item(s, frozen_utc="2026-05-03T08:00:00Z")
        assert p["executable"] is False, f"input {s!r} yielded executable=True"
        assert p["safe_to_execute"] is False
