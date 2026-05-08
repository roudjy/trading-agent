"""Unit tests for A13 — Autonomous Development End-to-End Proof Harness.

Synthetic deterministic fixtures only. The proof harness exercises
the full ADE lifecycle on synthetic no-op fixtures and emits a
proof artifact. Tests assert the harness:

* mutates nothing real,
* uses no subprocess/network/gh/git,
* does not import QRE internals,
* produces the eight closed lifecycle steps in order,
* surfaces protected-path violations honestly,
* never authorises Step 5 implementation autonomously,
* runs end-to-end on synthetic fixtures and yields
  ``proof_status="passed"`` and
  ``autonomous_development_possible=True``.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

import pytest

from reporting import development_e2e_proof as e2e
from reporting import execution_authority as ea


# ---------------------------------------------------------------------------
# Vocabulary / shape
# ---------------------------------------------------------------------------


def test_flow_steps_vocabulary_is_closed_and_ordered() -> None:
    assert e2e.FLOW_STEPS == (
        "roadmap_pickup",
        "agent_refinement",
        "prioritisation",
        "execution_readiness",
        "bounded_execution_or_simulation",
        "validation",
        "release_gate",
        "digest_report_out",
    )
    assert len(e2e.FLOW_STEPS) == 8


def test_step_statuses_vocabulary_is_closed() -> None:
    assert e2e.STEP_STATUSES == ("passed", "failed", "blocked", "not_evaluated")


def test_proof_statuses_vocabulary_is_closed() -> None:
    assert e2e.PROOF_STATUSES == ("passed", "failed", "blocked")


def test_blocker_reasons_vocabulary_is_closed() -> None:
    assert "none" in e2e.BLOCKER_REASONS
    assert "no_delegation_entry_parsed" in e2e.BLOCKER_REASONS
    assert "release_gate_no_go" in e2e.BLOCKER_REASONS
    assert "qre_coupling_detected" in e2e.BLOCKER_REASONS
    assert "protected_path_violation" in e2e.BLOCKER_REASONS


def test_artifact_path_is_under_logs() -> None:
    assert e2e.ARTIFACT_RELATIVE_PATH.startswith("logs/")
    assert "research/" not in e2e.ARTIFACT_RELATIVE_PATH


def test_atomic_write_refuses_non_logs_path(tmp_path: Path) -> None:
    bad = tmp_path / "evil_dir" / "latest.json"
    with pytest.raises(ValueError):
        e2e._atomic_write_json(bad, {"x": 1})


# ---------------------------------------------------------------------------
# End-to-end proof — happy path
# ---------------------------------------------------------------------------


def test_e2e_proof_passes_on_synthetic_fixtures(tmp_path: Path) -> None:
    """The full lifecycle must run end-to-end on a synthetic fixture
    and reach proof_status='passed' with
    autonomous_development_possible=True."""
    snap = e2e.collect_snapshot(
        scratch_dir=tmp_path / "scratch",
        generated_at_utc="2026-05-08T00:00:00Z",
    )
    assert snap["proof_status"] == "passed", snap
    assert snap["autonomous_development_possible"] is True
    assert snap["protected_path_violations"] == []
    assert snap["qre_coupling_violations"] == []
    assert snap["missing_capabilities"] == []
    assert snap["step5_design_planning_allowed"] is True
    # Step 5 implementation is NEVER auto-authorised by the harness.
    assert snap["step5_implementation_allowed"] is False


def test_e2e_proof_emits_all_eight_lifecycle_steps(tmp_path: Path) -> None:
    snap = e2e.collect_snapshot(scratch_dir=tmp_path / "scratch")
    step_names = [s["step"] for s in snap["flow_steps"]]
    assert step_names == list(e2e.FLOW_STEPS)
    for s in snap["flow_steps"]:
        assert s["status"] in e2e.STEP_STATUSES
        assert s["blocker_reason"] in e2e.BLOCKER_REASONS


def test_e2e_proof_each_step_passed_in_happy_path(tmp_path: Path) -> None:
    snap = e2e.collect_snapshot(scratch_dir=tmp_path / "scratch")
    for s in snap["flow_steps"]:
        assert s["status"] == "passed", (s["step"], s)


def test_e2e_proof_simulation_is_dry_run_only(tmp_path: Path) -> None:
    """The bounded execution step must record that it would modify
    a target without actually doing so. Pinned by the
    ``actual_modification: False`` flag and by absence of the file
    on disk."""
    snap = e2e.collect_snapshot(scratch_dir=tmp_path / "scratch")
    sim = next(
        s for s in snap["flow_steps"] if s["step"] == "bounded_execution_or_simulation"
    )
    assert sim["status"] == "passed"
    assert sim["evidence"]["actual_modification"] is False
    assert sim["evidence"]["simulation_kind"] == "no_op_dry_run"
    # The synthetic target file must NOT exist on disk after the proof.
    assert not (tmp_path / "scratch" / e2e.SIMULATION_TARGET_PATH).exists()


def test_e2e_proof_top_level_keys(tmp_path: Path) -> None:
    snap = e2e.collect_snapshot(
        scratch_dir=tmp_path / "scratch",
        generated_at_utc="2026-05-08T00:00:00Z",
    )
    expected = {
        "schema_version",
        "module_version",
        "report_kind",
        "generated_at_utc",
        "proof_id",
        "proof_status",
        "autonomous_development_possible",
        "step5_design_planning_allowed",
        "step5_implementation_allowed",
        "flow_steps",
        "missing_capabilities",
        "protected_path_violations",
        "qre_coupling_violations",
        "human_needed_items",
        "vocabularies",
        "scratch_dir",
        "discipline_invariants",
        "final_operator_summary",
    }
    assert set(snap.keys()) == expected
    assert snap["report_kind"] == "development_e2e_proof"


def test_proof_id_is_deterministic_for_same_run(tmp_path: Path) -> None:
    snap_a = e2e.collect_snapshot(
        scratch_dir=tmp_path / "scratch_a",
        generated_at_utc="2026-05-08T00:00:00Z",
    )
    snap_b = e2e.collect_snapshot(
        scratch_dir=tmp_path / "scratch_b",
        generated_at_utc="2026-05-08T00:00:00Z",
    )
    # proof_id encodes timestamp + step results; identical inputs
    # → identical id.
    assert snap_a["proof_id"] == snap_b["proof_id"]
    assert snap_a["proof_id"].startswith("e2e_")


# ---------------------------------------------------------------------------
# Discipline invariants
# ---------------------------------------------------------------------------


def test_discipline_invariants_block_pinned(tmp_path: Path) -> None:
    snap = e2e.collect_snapshot(scratch_dir=tmp_path / "scratch")
    inv = snap["discipline_invariants"]
    assert inv["actually_modifies_target"] is False
    assert inv["creates_real_branches"] is False
    assert inv["opens_real_prs"] is False
    assert inv["mutates_production_artifacts"] is False
    assert inv["uses_subprocess_or_network"] is False
    assert inv["operator_step5_authorisation_required"] is True


def test_proof_does_not_mutate_real_repo_artifacts(tmp_path: Path) -> None:
    """Running the proof against a tmp scratch dir must NOT touch
    any file under the real repo's logs/ or docs/. Verified by
    snapshotting the real artifact paths before and after."""
    real_targets = (
        e2e.REPO_ROOT / "logs" / "development_work_queue" / "latest.json",
        e2e.REPO_ROOT / "logs" / "development_release_gate" / "latest.json",
        e2e.REPO_ROOT / "logs" / "development_bugfix_loop" / "latest.json",
        e2e.REPO_ROOT / "logs" / "development_delegation" / "latest.json",
        e2e.REPO_ROOT / "docs" / "roadmap" / "autonomous_development.txt",
        e2e.REPO_ROOT / "docs" / "development_work_queue" / "seed.jsonl",
        e2e.REPO_ROOT / "docs" / "development_work_queue" / "delegation_seed.jsonl",
    )
    before = {
        p: p.read_bytes() if p.is_file() else None for p in real_targets
    }
    e2e.collect_snapshot(scratch_dir=tmp_path / "scratch")
    after = {
        p: p.read_bytes() if p.is_file() else None for p in real_targets
    }
    for p in real_targets:
        assert before[p] == after[p], f"production artifact mutated: {p}"


# ---------------------------------------------------------------------------
# Source-text scans (no subprocess / no network / no forbidden imports)
# ---------------------------------------------------------------------------


def _module_source() -> str:
    return Path(e2e.__file__).read_text(encoding="utf-8")


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
    ):
        assert forbidden not in src
    assert "from socket" not in src
    assert "from urllib" not in src
    assert "from http" not in src


def test_no_dashboard_or_live_path_or_qre_imports() -> None:
    forbidden_prefixes = (
        "dashboard",
        "automation",
        "broker",
        "agent.risk",
        "agent.execution",
        "research",
        "reporting.intelligent_routing",
    )
    for module in _imported_module_names():
        for prefix in forbidden_prefixes:
            assert not (module == prefix or module.startswith(prefix + ".")), (
                f"forbidden import: {module}"
            )


def test_no_gh_or_git_subprocess_references() -> None:
    src = _module_source()
    for forbidden in (
        "subprocess.run",
        "subprocess.Popen",
        "os.system",
        "os.popen",
    ):
        assert forbidden not in src, forbidden


def test_module_imports_cleanly() -> None:
    importlib.reload(e2e)
    assert callable(e2e.collect_snapshot)


# ---------------------------------------------------------------------------
# Schema-version + module-version surfaces
# ---------------------------------------------------------------------------


def test_schema_and_module_version_strings() -> None:
    assert isinstance(e2e.SCHEMA_VERSION, str) and e2e.SCHEMA_VERSION
    assert isinstance(e2e.MODULE_VERSION, str) and e2e.MODULE_VERSION
    assert "A13" in e2e.MODULE_VERSION


# ---------------------------------------------------------------------------
# Final operator summary
# ---------------------------------------------------------------------------


def test_final_operator_summary_describes_passed_run(tmp_path: Path) -> None:
    snap = e2e.collect_snapshot(scratch_dir=tmp_path / "scratch")
    summary: str = snap["final_operator_summary"]
    assert "Step 5 design planning is allowed" in summary
    assert "Step 5 implementation requires separate operator" in summary


# ---------------------------------------------------------------------------
# Failure-mode coverage (post-A13 hardening)
#
# These tests exercise the closed failure / blocked branches inside
# ``reporting.development_e2e_proof._run_lifecycle`` that the
# happy-path tests above do not reach. Each test injects exactly one
# fault by monkeypatching a public seam (``_build_synthetic_*`` fixture
# helper, the imported peer module's ``MODULE_VERSION`` global, or the
# ``SIMULATION_TARGET_PATH`` constant) and asserts that the proof
# snapshot reports the expected blocked / failed state with the
# documented closed-vocabulary reason.
#
# No production code is modified by any of these tests.
# ---------------------------------------------------------------------------


def _step_by_name(snap: dict[str, Any], name: str) -> dict[str, Any]:
    """Return the flow-step entry for ``name``. Raises KeyError if
    the harness did not emit that step."""
    for s in snap["flow_steps"]:
        if s["step"] == name:
            return s
    raise KeyError(name)


# ---------------------------------------------------------------------------
# 1. Protected path violation blocks the proof (queue surface route)
# ---------------------------------------------------------------------------


def test_protected_surface_queue_item_blocks_proof(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A queue item that declares ``protected_surface=True`` must
    cause execution_readiness to emit ``status='blocked'`` with
    blocker_reason ``simulation_target_protected``, append to
    ``protected_path_violations``, drive ``proof_status`` to
    ``'blocked'``, and clear ``autonomous_development_possible``."""
    original = e2e._build_synthetic_queue_seed_item

    def with_protected_surface() -> dict[str, Any]:
        item = original()
        item["protected_surface"] = True
        return item

    monkeypatch.setattr(
        e2e, "_build_synthetic_queue_seed_item", with_protected_surface
    )
    snap = e2e.collect_snapshot(
        scratch_dir=tmp_path / "scratch",
        generated_at_utc="2026-05-08T00:00:00Z",
    )

    assert snap["proof_status"] == "blocked"
    assert snap["protected_path_violations"], snap["protected_path_violations"]
    assert snap["autonomous_development_possible"] is False
    assert snap["step5_implementation_allowed"] is False
    assert snap["step5_design_planning_allowed"] is True

    readiness = _step_by_name(snap, "execution_readiness")
    assert readiness["status"] == "blocked"
    assert readiness["blocker_reason"] == "simulation_target_protected"
    # Closed vocabulary integrity is preserved.
    assert readiness["blocker_reason"] in e2e.BLOCKER_REASONS
    assert readiness["status"] in e2e.STEP_STATUSES


# ---------------------------------------------------------------------------
# 2. Protected simulation target (PERMANENTLY_DENIED) blocks the proof
# ---------------------------------------------------------------------------


def test_permanently_denied_simulation_target_blocks_proof(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """If the bounded-execution target classifies as
    PERMANENTLY_DENIED via ``execution_authority.classify`` (e.g. a
    ``live_path``), the bounded-execution step must record
    ``status='blocked'`` with the closed
    ``simulation_target_protected`` blocker_reason, append to
    ``protected_path_violations``, and drive ``proof_status`` to
    ``'blocked'``."""
    monkeypatch.setattr(
        e2e, "SIMULATION_TARGET_PATH", "automation/live_gate.py"
    )
    snap = e2e.collect_snapshot(
        scratch_dir=tmp_path / "scratch",
        generated_at_utc="2026-05-08T00:00:00Z",
    )

    assert snap["proof_status"] == "blocked"
    assert "automation/live_gate.py" in snap["protected_path_violations"]
    assert snap["autonomous_development_possible"] is False
    # Discipline invariants must remain pinned even under failure.
    assert snap["discipline_invariants"]["actually_modifies_target"] is False
    assert snap["step5_implementation_allowed"] is False

    sim = _step_by_name(snap, "bounded_execution_or_simulation")
    assert sim["status"] == "blocked"
    assert sim["blocker_reason"] == "simulation_target_protected"
    assert sim["evidence"]["authority_decision"] == ea.DECISION_PERMANENTLY_DENIED
    assert sim["evidence"]["would_modify_target_path"] == "automation/live_gate.py"
    # The synthetic target file must NOT exist on disk after the proof.
    assert not (
        tmp_path / "scratch" / "automation/live_gate.py"
    ).exists()


def test_needs_human_simulation_target_blocks_proof(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """If the bounded-execution target classifies as NEEDS_HUMAN
    (e.g. a ``claude_governance_hook`` path), the bounded-execution
    step must block, ``actual_modification`` must remain false, and
    Step 5 implementation must remain disallowed."""
    monkeypatch.setattr(
        e2e, "SIMULATION_TARGET_PATH", ".claude/agents/synthetic_role.md"
    )
    snap = e2e.collect_snapshot(
        scratch_dir=tmp_path / "scratch",
        generated_at_utc="2026-05-08T00:00:00Z",
    )

    assert snap["proof_status"] == "blocked"
    assert any(
        ".claude/agents/synthetic_role.md" in p
        for p in snap["protected_path_violations"]
    )
    assert snap["autonomous_development_possible"] is False
    assert snap["step5_implementation_allowed"] is False
    assert snap["discipline_invariants"]["actually_modifies_target"] is False
    assert (
        snap["discipline_invariants"][
            "operator_step5_authorisation_required"
        ]
        is True
    )

    sim = _step_by_name(snap, "bounded_execution_or_simulation")
    assert sim["status"] == "blocked"
    assert sim["blocker_reason"] == "simulation_target_protected"
    assert sim["evidence"]["authority_decision"] == ea.DECISION_NEEDS_HUMAN


# ---------------------------------------------------------------------------
# 3. QRE coupling violation blocks the proof
# ---------------------------------------------------------------------------


def test_qre_coupling_violation_via_module_version_blocks_proof(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """If any ADE peer snapshot reports a ``module_version`` that
    contains the substring ``intelligent_routing``, the loose-
    coupling self-check inside the harness must populate
    ``qre_coupling_violations``, drive ``proof_status`` to
    ``'blocked'``, and refuse to authorise autonomous development."""
    # Patch the imported peer module's MODULE_VERSION global. The
    # peer's ``collect_snapshot`` reads this at call time, so the
    # patched string flows into the snapshot the harness inspects.
    monkeypatch.setattr(
        e2e.ddl,
        "MODULE_VERSION",
        "v3.15.16.A11+intelligent_routing_marker",
    )
    snap = e2e.collect_snapshot(
        scratch_dir=tmp_path / "scratch",
        generated_at_utc="2026-05-08T00:00:00Z",
    )

    assert snap["proof_status"] == "blocked"
    assert snap["qre_coupling_violations"], snap["qre_coupling_violations"]
    assert any(
        "intelligent_routing" in v for v in snap["qre_coupling_violations"]
    )
    assert snap["autonomous_development_possible"] is False
    assert snap["step5_implementation_allowed"] is False
    assert snap["step5_design_planning_allowed"] is True


# ---------------------------------------------------------------------------
# 4. Human-needed item surfaces the human signal and never authorises Step 5
# ---------------------------------------------------------------------------


def test_human_needed_queue_item_surfaces_human_needed_signal(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A queue item that declares ``human_needed=True`` with a
    closed-vocabulary reason must propagate to
    ``snap['human_needed_items'] > 0``, surface
    ``requiring_human_operator > 0`` in the execution_readiness
    evidence, raise the digest's operator_action_count, and leave
    Step 5 implementation gated."""
    original = e2e._build_synthetic_queue_seed_item

    def with_human_needed() -> dict[str, Any]:
        item = original()
        item["human_needed"] = True
        item["human_needed_reason"] = "architecture_crossroads"
        return item

    monkeypatch.setattr(
        e2e, "_build_synthetic_queue_seed_item", with_human_needed
    )
    snap = e2e.collect_snapshot(
        scratch_dir=tmp_path / "scratch",
        generated_at_utc="2026-05-08T00:00:00Z",
    )

    assert snap["human_needed_items"] > 0
    assert snap["step5_implementation_allowed"] is False
    assert snap["step5_design_planning_allowed"] is True
    # Discipline invariants must remain pinned.
    inv = snap["discipline_invariants"]
    assert inv["operator_step5_authorisation_required"] is True
    assert inv["actually_modifies_target"] is False

    readiness = _step_by_name(snap, "execution_readiness")
    assert readiness["evidence"]["requiring_human_operator"] >= 1
    assert readiness["evidence"]["ready_for_autonomous_action"] == 0

    digest = _step_by_name(snap, "digest_report_out")
    assert digest["evidence"]["operator_action_count"] >= 1


# ---------------------------------------------------------------------------
# 5. Missing lifecycle step (no parsable delegation) fails safely
# ---------------------------------------------------------------------------


def test_missing_delegation_marker_fails_proof(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """If the canonical-roadmap fixture contains no parsable A11
    delegation marker, ``roadmap_pickup`` must fail with the closed
    blocker_reason ``no_delegation_entry_parsed``,
    ``agent_refinement`` must roll forward to ``not_evaluated`` with
    the same blocker, ``missing_capabilities`` must include
    ``roadmap_pickup``, ``proof_status`` becomes ``'failed'``, and
    ``autonomous_development_possible`` is False."""

    def no_marker() -> str:
        # Plain prose only — no <!-- ade_delegation ... --> block.
        return (
            "# Synthetic roadmap with no marker\n"
            "Plain prose. Bullets and headings must not produce "
            "delegation entries.\n"
        )

    monkeypatch.setattr(
        e2e, "_build_synthetic_canonical_roadmap_text", no_marker
    )
    snap = e2e.collect_snapshot(
        scratch_dir=tmp_path / "scratch",
        generated_at_utc="2026-05-08T00:00:00Z",
    )

    assert snap["proof_status"] == "failed"
    assert snap["autonomous_development_possible"] is False
    assert "roadmap_pickup" in snap["missing_capabilities"]
    assert snap["step5_implementation_allowed"] is False

    pickup = _step_by_name(snap, "roadmap_pickup")
    assert pickup["status"] == "failed"
    assert pickup["blocker_reason"] == "no_delegation_entry_parsed"
    assert pickup["blocker_reason"] in e2e.BLOCKER_REASONS

    refinement = _step_by_name(snap, "agent_refinement")
    assert refinement["status"] == "not_evaluated"
    assert refinement["blocker_reason"] == "no_delegation_entry_parsed"
    assert refinement["status"] in e2e.STEP_STATUSES


# ---------------------------------------------------------------------------
# 6. Malformed input (release evidence) degrades safely without raising
# ---------------------------------------------------------------------------


def test_malformed_release_evidence_degrades_safely(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """If the synthetic release-evidence fixture is degraded so the
    A9 release gate cannot emit a ``go``/``go_with_followups``
    verdict, the harness must NOT raise, ``release_gate`` must record
    ``status='failed'`` with closed blocker_reason
    ``release_gate_no_go``, ``missing_capabilities`` must reflect the
    gap, and ``proof_status`` must become ``'failed'`` (not raise,
    not silently pass)."""

    def empty_evidence() -> dict[str, Any]:
        return {"schema_version": "1.0", "evidence": {}}

    monkeypatch.setattr(
        e2e, "_build_synthetic_release_evidence", empty_evidence
    )

    # Must not raise.
    snap = e2e.collect_snapshot(
        scratch_dir=tmp_path / "scratch",
        generated_at_utc="2026-05-08T00:00:00Z",
    )

    assert snap["proof_status"] == "failed"
    assert snap["autonomous_development_possible"] is False
    assert snap["step5_implementation_allowed"] is False

    rg = _step_by_name(snap, "release_gate")
    assert rg["status"] == "failed"
    assert rg["blocker_reason"] in e2e.BLOCKER_REASONS
    assert rg["blocker_reason"] == "release_gate_no_go"
    # ``missing_capabilities`` must surface a release-gate-related entry.
    assert any("release_gate" in c for c in snap["missing_capabilities"])


# ---------------------------------------------------------------------------
# 7. No-op dry-run invariants pinned (full-block assertion, all six flags)
# ---------------------------------------------------------------------------


def test_no_op_dry_run_invariants_fully_pinned_happy_path(
    tmp_path: Path,
) -> None:
    """Pin every discipline invariant on a clean run so a future
    edit to the harness cannot silently flip any of them. Mirrors
    the existing block test but is explicit per-flag and explicitly
    asserts that the bounded-execution step recorded a no-op
    dry-run."""
    snap = e2e.collect_snapshot(scratch_dir=tmp_path / "scratch")
    inv = snap["discipline_invariants"]

    assert inv["actually_modifies_target"] is False
    assert inv["creates_real_branches"] is False
    assert inv["opens_real_prs"] is False
    assert inv["mutates_production_artifacts"] is False
    assert inv["uses_subprocess_or_network"] is False
    assert inv["operator_step5_authorisation_required"] is True

    sim = _step_by_name(snap, "bounded_execution_or_simulation")
    assert sim["evidence"]["actual_modification"] is False
    assert sim["evidence"]["simulation_kind"] == "no_op_dry_run"
    # The synthetic target file must NOT exist on disk after the proof.
    assert not (
        tmp_path / "scratch" / e2e.SIMULATION_TARGET_PATH
    ).exists()


def test_no_op_dry_run_invariants_pinned_under_blocked_proof(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Even when the proof reaches ``proof_status='blocked'`` via a
    protected-path violation, every discipline invariant must remain
    pinned. A blocked proof MUST NOT silently flip any invariant."""
    monkeypatch.setattr(
        e2e, "SIMULATION_TARGET_PATH", "automation/live_gate.py"
    )
    snap = e2e.collect_snapshot(scratch_dir=tmp_path / "scratch")

    assert snap["proof_status"] == "blocked"
    inv = snap["discipline_invariants"]
    assert inv["actually_modifies_target"] is False
    assert inv["creates_real_branches"] is False
    assert inv["opens_real_prs"] is False
    assert inv["mutates_production_artifacts"] is False
    assert inv["uses_subprocess_or_network"] is False
    assert inv["operator_step5_authorisation_required"] is True

    # The protected target must NOT exist on disk after the proof.
    assert not (
        tmp_path / "scratch" / "automation" / "live_gate.py"
    ).exists()


# ---------------------------------------------------------------------------
# 8. Final operator summary never claims real implementation
# ---------------------------------------------------------------------------


def test_final_operator_summary_never_claims_real_implementation_passed(
    tmp_path: Path,
) -> None:
    """On a passing run the final operator summary must explicitly
    name proof-harness mode and the operator-authorisation gate, and
    must NOT contain any claim that real autonomous implementation
    is currently allowed."""
    snap = e2e.collect_snapshot(scratch_dir=tmp_path / "scratch")
    summary: str = snap["final_operator_summary"]

    assert "proof-harness mode" in summary
    assert "Step 5 design planning is allowed" in summary
    assert "Step 5 implementation requires separate operator" in summary

    # Negative assertions — words that would imply real implementation
    # is now authorised must NOT appear.
    forbidden_phrases = (
        "real autonomous implementation is now allowed",
        "Step 5 implementation is now allowed",
        "Step 5 implementation is authorised",
        "Step 5 implementation is authorized",
        "real branches are created",
        "production artifacts are mutated",
    )
    for phrase in forbidden_phrases:
        assert phrase not in summary, phrase


def test_final_operator_summary_on_blocked_proof_signals_block(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """When the proof reaches ``proof_status='blocked'``, the final
    operator summary must signal the block AND must not contain any
    claim of authorised implementation."""
    monkeypatch.setattr(
        e2e, "SIMULATION_TARGET_PATH", "automation/live_gate.py"
    )
    snap = e2e.collect_snapshot(scratch_dir=tmp_path / "scratch")

    assert snap["proof_status"] == "blocked"
    summary: str = snap["final_operator_summary"]
    assert "BLOCKED" in summary
    assert (
        "protected_path_violations" in summary
        or "qre_coupling_violations" in summary
    )

    forbidden_phrases = (
        "Step 5 implementation is allowed",
        "Step 5 implementation is authorised",
        "Step 5 implementation is authorized",
        "real autonomous implementation",
    )
    for phrase in forbidden_phrases:
        assert phrase not in summary, phrase


def test_final_operator_summary_on_failed_proof_signals_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """When the proof reaches ``proof_status='failed'``, the final
    operator summary must signal failure AND must not authorise
    autonomous implementation."""

    def no_marker() -> str:
        return "# No marker here\nPlain prose only.\n"

    monkeypatch.setattr(
        e2e, "_build_synthetic_canonical_roadmap_text", no_marker
    )
    snap = e2e.collect_snapshot(scratch_dir=tmp_path / "scratch")

    assert snap["proof_status"] == "failed"
    summary: str = snap["final_operator_summary"]
    assert "FAILED" in summary

    forbidden_phrases = (
        "Step 5 implementation is allowed",
        "Step 5 implementation is authorised",
        "Step 5 implementation is authorized",
        "real autonomous implementation",
    )
    for phrase in forbidden_phrases:
        assert phrase not in summary, phrase
