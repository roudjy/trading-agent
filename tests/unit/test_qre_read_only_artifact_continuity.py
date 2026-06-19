from __future__ import annotations

import json
from pathlib import Path

from research import qre_read_only_artifact_continuity as continuity


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def test_continuity_report_detects_materializable_missing_artifacts(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _write_json(
        tmp_path / "research" / "operator_approvals" / "qre_preregistered_multiwindow_validation_approval.v1.json",
        {"approval_id": "approval-001"},
    )
    monkeypatch.setattr(
        continuity.disposition_memory,
        "read_hypothesis_disposition_memory_status",
        lambda **_: {"status": "missing_hypothesis_disposition_memory"},
    )
    monkeypatch.setattr(
        continuity.disposition_memory,
        "build_hypothesis_disposition_memory",
        lambda **_: {"schema_version": "1.0", "report_kind": "qre_hypothesis_disposition_memory", "status": "ready", "deterministic_hash": "sha256:disp"},
    )
    monkeypatch.setattr(
        continuity.cycle_router,
        "read_research_cycle_router_status",
        lambda **_: {"status": "missing_research_cycle_router"},
    )
    monkeypatch.setattr(
        continuity.cycle_router,
        "_build_research_cycle_router_from_payloads",
        lambda **_: {"schema_version": "1.0", "report_kind": "qre_research_cycle_router", "status": "ready", "deterministic_hash": "sha256:router"},
    )
    monkeypatch.setattr(
        continuity.null_suite,
        "read_null_control_suite_status",
        lambda **_: {"status": "missing_null_control_suite"},
    )
    monkeypatch.setattr(
        continuity.multiwindow_run,
        "build_sampling_plan_for_multiwindow_approval",
        lambda **_: {"sampling_plan_id": "plan-001", "hash": "plan-hash", "status": "sampling_plan_ready_context_only", "null_control_definitions": [{"control_id": "buy_and_hold_baseline"}]},
    )
    monkeypatch.setattr(
        continuity.multiwindow_run,
        "build_campaign_for_multiwindow_approval",
        lambda **_: {"campaign_id": "campaign-001"},
    )
    monkeypatch.setattr(
        continuity.null_suite,
        "build_preregistered_null_control_suite",
        lambda **_: {"schema_version": "1.0", "report_kind": "qre_null_control_falsification_suite", "status": "suite_ready_preregistered_context", "hash": "suite-hash"},
    )
    monkeypatch.setattr(
        continuity.null_suite,
        "evaluate_null_control_suite",
        lambda report, **_: {**report, "evaluation": {"status": "controls_incomplete", "recommended_next_action": "materialize_missing_preregistered_controls"}},
    )

    report = continuity.build_read_only_artifact_continuity(repo_root=tmp_path)

    assert report["summary"]["artifact_continuity_ready"] is True
    assert report["summary"]["materializable_target_count"] == 3
    assert report["summary"]["blocked_target_count"] == 0
    assert report["summary"]["exact_next_action"] == "materialize_read_only_qre_artifacts"


def test_continuity_write_outputs_materializes_nested_artifacts(
    tmp_path: Path,
    monkeypatch,
) -> None:
    calls: list[str] = []
    _write_json(
        tmp_path / "research" / "operator_approvals" / "qre_preregistered_multiwindow_validation_approval.v1.json",
        {"approval_id": "approval-001"},
    )
    monkeypatch.setattr(
        continuity.disposition_memory,
        "build_hypothesis_disposition_memory",
        lambda **_: {"schema_version": "1.0", "report_kind": "qre_hypothesis_disposition_memory", "status": "ready", "deterministic_hash": "sha256:disp"},
    )
    monkeypatch.setattr(
        continuity.disposition_memory,
        "write_outputs",
        lambda report, **_: calls.append("disposition") or {"latest": "logs/qre_hypothesis_disposition_memory/latest.json"},
    )
    monkeypatch.setattr(
        continuity.cycle_router,
        "_build_research_cycle_router_from_payloads",
        lambda **_: {"schema_version": "1.0", "report_kind": "qre_research_cycle_router", "status": "ready", "deterministic_hash": "sha256:router"},
    )
    monkeypatch.setattr(
        continuity.cycle_router,
        "write_outputs",
        lambda report, **_: calls.append("router") or {"latest": "logs/qre_research_cycle_router/latest.json"},
    )
    monkeypatch.setattr(
        continuity.multiwindow_run,
        "build_sampling_plan_for_multiwindow_approval",
        lambda **_: {"sampling_plan_id": "plan-001", "hash": "plan-hash", "status": "sampling_plan_ready_context_only", "null_control_definitions": [{"control_id": "buy_and_hold_baseline"}]},
    )
    monkeypatch.setattr(
        continuity.multiwindow_run,
        "build_campaign_for_multiwindow_approval",
        lambda **_: {"campaign_id": "campaign-001"},
    )
    monkeypatch.setattr(
        continuity.null_suite,
        "build_preregistered_null_control_suite",
        lambda **_: {"schema_version": "1.0", "report_kind": "qre_null_control_falsification_suite", "status": "suite_ready_preregistered_context", "hash": "suite-hash"},
    )
    monkeypatch.setattr(
        continuity.null_suite,
        "evaluate_null_control_suite",
        lambda report, **_: {**report, "evaluation": {"status": "controls_incomplete", "recommended_next_action": "materialize_missing_preregistered_controls"}},
    )
    monkeypatch.setattr(
        continuity.null_suite,
        "write_outputs",
        lambda report, **_: calls.append("null_suite") or {"latest": "logs/qre_null_control_falsification_suite/latest.json"},
    )
    monkeypatch.setattr(
        continuity,
        "build_read_only_artifact_continuity",
        lambda **_: {
            "schema_version": "1.0",
            "report_kind": "qre_read_only_artifact_continuity",
            "summary": {"artifact_continuity_ready": True, "exact_next_action": "preserve_current_read_only_artifacts"},
            "targets": [],
            "current_status": {},
            "projected_reports": {},
            "authority_boundary": {},
            "deterministic_hash": "sha256:continuity",
        },
    )

    report = {
        "schema_version": "1.0",
        "report_kind": "qre_read_only_artifact_continuity",
        "summary": {"artifact_continuity_ready": True},
        "targets": [],
    }
    paths = continuity.write_outputs(report, repo_root=tmp_path)

    assert calls == ["disposition", "router", "null_suite"]
    assert paths["latest"] == "logs/qre_read_only_artifact_continuity/latest.json"
    assert (tmp_path / paths["latest"]).exists()
    assert (tmp_path / paths["operator_summary"]).exists()
