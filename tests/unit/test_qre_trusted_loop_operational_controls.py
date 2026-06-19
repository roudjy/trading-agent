from __future__ import annotations

import json
from pathlib import Path

import pytest

from research import qre_trusted_loop_operational_controls as controls


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _seed_terminal_run(tmp_path: Path, *, run_id: str = "20260605T160110658896Z") -> None:
    _write_json(
        tmp_path / "research" / "run_manifest_latest.v1.json",
        {
            "version": "v1",
            "run_id": run_id,
            "status": "failed",
            "git_revision": "abc123",
            "config_hash": "cfg-1",
            "feature_version": "1.0",
            "evaluation_version": "1.0",
            "lifecycle_mode": "fresh",
            "continuation_summary": {"resumed_pending_batch_count": 1},
            "recovery_policy": {"batch_recovery_unit": "batch"},
        },
    )
    _write_json(
        tmp_path / "research" / "run_state.v1.json",
        {
            "version": "v1",
            "run_id": run_id,
            "status": "failed",
            "pid": None,
            "status_reason": "research_run_failed:screening",
            "error": {
                "error_type": "DegenerateResearchRunError",
                "error_message": "screening failed",
            },
        },
    )
    _write_json(
        tmp_path / "research" / "run_progress_latest.v1.json",
        {
            "version": "v1",
            "run_id": run_id,
            "status": "failed",
            "total_items": 5,
            "completed_items": 2,
            "failed_items": 1,
        },
    )
    _write_json(
        tmp_path / "research" / "research_state_latest.v1.json",
        {
            "hypothesis_state": "needs_more_diagnostic_evidence",
            "policy_state": "blocked_no_candidates",
            "synthesis_gate": "blocked_insufficient_attribution",
            "next_best_test": "inspect_gate_diagnostics",
        },
    )
    _write_json(
        tmp_path / "logs" / "qre_trusted_loop_review" / "latest.json",
        {"summary": {"trust_verdict": "operator_review_required"}},
    )
    history_dir = tmp_path / "research" / "history" / run_id
    _write_json(history_dir / "run_manifest.v1.json", json.loads((tmp_path / "research" / "run_manifest_latest.v1.json").read_text(encoding="utf-8")))
    _write_json(history_dir / "run_state.v1.json", json.loads((tmp_path / "research" / "run_state.v1.json").read_text(encoding="utf-8")))
    _write_json(history_dir / "run_progress.v1.json", json.loads((tmp_path / "research" / "run_progress_latest.v1.json").read_text(encoding="utf-8")))
    _write_json(
        history_dir / "batches" / "batch-1" / "candidate_resume" / "abc.v1.json",
        {"kind": "screening_candidate_resume", "version": "v1"},
    )


def test_build_trusted_loop_operational_controls_marks_failed_run_resumable(tmp_path: Path) -> None:
    _seed_terminal_run(tmp_path)

    report = controls.build_trusted_loop_operational_controls(repo_root=tmp_path)

    assert report["summary"]["status"] == "failed_resumable"
    assert report["summary"]["exact_next_safe_action"] == "resume_from_existing_run_history"
    assert report["resumability"]["resumable"] is True
    assert report["resumability"]["resume_sidecar_count"] == 1
    assert report["state_reconciliation"]["status"] == "reconciled"
    assert report["artifact_freshness"]["status"] == "fresh"
    assert report["failure_retry_reason_records"]["status_reason"] == "research_run_failed:screening"


def test_build_trusted_loop_operational_controls_detects_active_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _seed_terminal_run(tmp_path, run_id="20260610T100000000000Z")
    _write_json(
        tmp_path / "research" / "run_state.v1.json",
        {
            "version": "v1",
            "run_id": "20260610T100000000000Z",
            "status": "running",
            "pid": 4321,
            "status_reason": "research_run_started",
            "error": None,
        },
    )
    _write_json(
        tmp_path / "research" / "run_progress_latest.v1.json",
        {
            "version": "v1",
            "run_id": "20260610T100000000000Z",
            "status": "running",
            "total_items": 5,
            "completed_items": 1,
            "failed_items": 0,
        },
    )
    monkeypatch.setattr(controls, "_pid_is_live", lambda pid: True)

    report = controls.build_trusted_loop_operational_controls(repo_root=tmp_path)

    assert report["summary"]["status"] == "running_active"
    assert report["summary"]["exact_next_safe_action"] == "wait_for_active_run_completion"
    assert report["current_run"]["pid_live"] is True
    assert report["summary"]["trusted_loop_operational_controls_ready"] is False


def test_build_trusted_loop_operational_controls_detects_superseded_latest_artifacts(tmp_path: Path) -> None:
    _seed_terminal_run(tmp_path, run_id="20260601T100000000000Z")
    later_history = tmp_path / "research" / "history" / "20260602T100000000000Z"
    _write_json(later_history / "run_manifest.v1.json", {"run_id": "20260602T100000000000Z", "status": "completed"})
    _write_json(later_history / "run_state.v1.json", {"run_id": "20260602T100000000000Z", "status": "completed"})
    _write_json(later_history / "run_progress.v1.json", {"run_id": "20260602T100000000000Z", "status": "completed"})

    report = controls.build_trusted_loop_operational_controls(repo_root=tmp_path)

    assert report["state_reconciliation"]["superseded_artifacts_detected"] is True
    assert report["artifact_freshness"]["status"] == "stale_or_missing"
    assert report["summary"]["exact_next_safe_action"] == "reconcile_stale_or_mismatched_run_artifacts"


def test_write_outputs_respects_allowlist(tmp_path: Path) -> None:
    _seed_terminal_run(tmp_path)
    report = controls.build_trusted_loop_operational_controls(repo_root=tmp_path)

    paths = controls.write_outputs(report, repo_root=tmp_path)

    assert paths["latest"] == "logs/qre_trusted_loop_operational_controls/latest.json"
    assert paths["operator_summary"] == "logs/qre_trusted_loop_operational_controls/operator_summary.md"
    assert (tmp_path / paths["latest"]).exists()
    assert (tmp_path / paths["operator_summary"]).exists()
