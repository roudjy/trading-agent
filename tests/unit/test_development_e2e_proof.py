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
