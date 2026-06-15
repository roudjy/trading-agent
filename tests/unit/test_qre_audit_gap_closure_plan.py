from __future__ import annotations

import json
from pathlib import Path

import pytest

from research import qre_audit_gap_closure_plan as plan


FROZEN = "2026-06-15T00:00:00Z"


def _built() -> dict:
    return plan.build_audit_gap_closure_plan(generated_at_utc=FROZEN)


def test_plan_contains_all_20_audit_items_and_required_fields() -> None:
    payload = _built()

    assert payload["schema_version"] == "1.0"
    assert payload["generated_at_utc"] == FROZEN
    assert len(payload["audit_items"]) == 20
    assert [row["id"] for row in payload["audit_items"]] == list(range(1, 21))

    required = {
        "id",
        "audit_item",
        "current_maturity",
        "repo_evidence",
        "target_capability",
        "target_maturity",
        "closure_prs",
    }
    for row in payload["audit_items"]:
        assert required <= set(row)
        assert row["repo_evidence"]
        assert row["closure_prs"]


def test_maturity_matrix_counts_are_deterministic() -> None:
    payload_a = _built()
    payload_b = _built()

    assert json.dumps(payload_a, sort_keys=True) == json.dumps(payload_b, sort_keys=True)
    assert payload_a["current_maturity"] == {"SCAFFOLD": 11, "WORKING_CAPABILITY": 9}
    assert payload_a["target_maturity"] == {
        "OPERATOR_TRUSTED": 14,
        "WORKING_CAPABILITY": 6,
    }


def test_pr_sequence_covers_pr0_through_pr18_and_all_audit_items() -> None:
    payload = _built()
    prs = payload["gap_closure_prs"]
    pr_ids = {row["pr"] for row in prs}

    assert pr_ids == set(range(19))
    assert prs[0]["title"] == "Audit gap closure plan and maturity matrix"
    for item in payload["audit_items"]:
        assert set(item["closure_prs"]) <= pr_ids
        assert item["closure_prs"], item["audit_item"]


def test_forbidden_shortcuts_and_safety_flags_stay_fail_closed() -> None:
    payload = _built()

    for shortcut in {
        "source_to_alpha",
        "cache_to_trade",
        "diagnostic_to_trade",
        "retrieval_to_authority",
        "knowledge_graph_to_truth",
        "identity_ambiguity_to_escalation",
        "throughput_bypasses_source_quality",
    }:
        assert shortcut in payload["blocked_shortcuts"]

    for key in (
        "safe_to_strategy_synthesis",
        "safe_to_shadow",
        "safe_to_paper",
        "safe_to_live",
    ):
        assert payload[key] is False

    assert payload["safety_invariants"]["runs_research"] is False
    assert payload["safety_invariants"]["launches_campaigns"] is False
    assert payload["safety_invariants"]["mutates_research_outputs"] is False


def test_source_lifecycle_gates_block_candidate_to_active_jump() -> None:
    payload = _built()
    pr1 = next(row for row in payload["gap_closure_prs"] if row["pr"] == 1)

    assert pr1["depends_on"] == [0]
    assert "tests blocking candidate to active_read_only jumps" in pr1["main_artifacts_tests"]
    assert set(pr1["required_gates"]) == {
        "manifest_completeness",
        "allowed_use_declared",
        "forbidden_use_declared",
        "quality_gates_passed",
        "identity_mapping_present",
        "historical_lineage_present",
    }


def test_identity_ambiguity_blocks_escalation() -> None:
    payload = _built()
    pr3 = next(row for row in payload["gap_closure_prs"] if row["pr"] == 3)
    pr10 = next(row for row in payload["gap_closure_prs"] if row["pr"] == 10)

    assert "ambiguity blocks escalation tests" in pr3["main_artifacts_tests"]
    assert "ambiguity blocks escalation tests" in pr10["main_artifacts_tests"]
    assert "identity_ambiguity_to_escalation" in payload["blocked_shortcuts"]


def test_throughput_depends_on_source_quality_gates() -> None:
    payload = _built()
    pr6 = next(row for row in payload["gap_closure_prs"] if row["pr"] == 6)

    assert set(pr6["required_gates"]) == {"source_quality_ready", "cache_manifest_ready"}
    assert 1 in pr6["depends_on"]
    assert "throughput_bypasses_source_quality" in payload["blocked_shortcuts"]


def test_rendered_markdown_contains_operator_sections() -> None:
    rendered = plan.render_markdown(_built())

    assert "# QRE Audit Gap Closure Plan" in rendered
    assert "## Current-To-Target Matrix" in rendered
    assert "## PR Sequence" in rendered
    assert "## Blocked Shortcuts" in rendered
    assert "PR1" in rendered
    assert "safe_to_live: False" in rendered


def test_write_outputs_are_allowlisted(tmp_path: Path) -> None:
    payload = _built()

    paths = plan.write_outputs(payload, repo_root=tmp_path)

    assert paths == {
        "latest": "logs/qre_audit_gap_closure_plan/latest.json",
        "operator_plan": "docs/roadmap/qre_audit_gap_closure_plan.md",
    }
    assert (tmp_path / paths["latest"]).is_file()
    assert (tmp_path / paths["operator_plan"]).is_file()
    written = json.loads((tmp_path / paths["latest"]).read_text(encoding="utf-8"))
    assert written["summary"]["audit_item_count"] == 20


def test_validate_write_target_refuses_unexpected_path(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        plan._validate_write_target(tmp_path / "research" / "research_latest.json")


def test_cli_no_write_outputs_json_without_writing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(plan, "DEFAULT_OUTPUT_DIR", Path("logs/qre_audit_gap_closure_plan"))
    monkeypatch.chdir(tmp_path)

    rc = plan.main([])

    assert rc == 0
    assert not (tmp_path / "logs/qre_audit_gap_closure_plan/latest.json").exists()
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["summary"]["audit_item_count"] == 20


def test_source_has_no_runtime_launch_or_network_calls() -> None:
    src = Path(plan.__file__).read_text(encoding="utf-8")
    forbidden = (
        "import subprocess",
        "from subprocess",
        "subprocess.",
        "import socket",
        "from socket",
        "import requests",
        "import httpx",
        "import aiohttp",
        "import urllib",
        "from urllib",
        "os.system",
        "os.popen",
        "shell=True",
        "git ",
        "gh ",
        "codex ",
    )
    for token in forbidden:
        assert token not in src, token
