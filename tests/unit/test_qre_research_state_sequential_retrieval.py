from __future__ import annotations

import json
from pathlib import Path

from research import qre_research_state_sequential_retrieval as sequential


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _seed_repo(tmp_path: Path) -> None:
    run_id = "20260619T100000000000Z"
    prior_run_id = "20260618T100000000000Z"
    _write_json(
        tmp_path / "research" / "run_manifest_latest.v1.json",
        {
            "run_id": run_id,
            "status": "failed",
            "git_revision": "abc123",
            "config_hash": "cfg-1",
            "feature_version": "1.0",
            "evaluation_version": "1.0",
            "lifecycle_mode": "resume",
            "resumed_from_run_id": prior_run_id,
            "retry_failed_batches": True,
            "continuation_summary": {
                "fresh_batch_count": 1,
                "reused_terminal_batch_count": 1,
                "resumed_pending_batch_count": 0,
                "resumed_stale_batch_count": 0,
                "retried_failed_batch_count": 1,
            },
            "recovery_policy": {"batch_recovery_unit": "batch"},
        },
    )
    _write_json(
        tmp_path / "research" / "run_state.v1.json",
        {
            "run_id": run_id,
            "status": "failed",
            "status_reason": "research_run_failed:screening",
            "error": {"error_type": "DegenerateResearchRunError", "error_message": "failed"},
        },
    )
    _write_json(
        tmp_path / "research" / "run_progress_latest.v1.json",
        {"run_id": run_id, "status": "failed", "total_items": 5, "completed_items": 2, "failed_items": 1},
    )
    _write_json(
        tmp_path / "research" / "run_batches_latest.v1.json",
        {
            "batches": [
                {"batch_id": "batch-1", "status": "completed", "last_attempt_reason": "fresh_run"},
                {"batch_id": "batch-2", "status": "failed", "last_attempt_reason": "retry_failed_batch"},
            ]
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
    history_dir = tmp_path / "research" / "history" / prior_run_id
    _write_json(
        history_dir / "run_manifest.v1.json",
        {
            "run_id": prior_run_id,
            "status": "completed",
            "git_revision": "def456",
            "config_hash": "cfg-0",
            "lifecycle_mode": "fresh",
            "continuation_summary": {"fresh_batch_count": 2},
        },
    )
    _write_json(history_dir / "run_state.v1.json", {"run_id": prior_run_id, "status": "completed"})
    _write_json(
        history_dir / "run_progress.v1.json",
        {"run_id": prior_run_id, "status": "completed", "total_items": 2, "completed_items": 2, "failed_items": 0},
    )
    _write_json(
        tmp_path / "research" / "history" / run_id / "run_manifest.v1.json",
        json.loads((tmp_path / "research" / "run_manifest_latest.v1.json").read_text(encoding="utf-8")),
    )
    _write_json(
        tmp_path / "research" / "history" / run_id / "run_state.v1.json",
        json.loads((tmp_path / "research" / "run_state.v1.json").read_text(encoding="utf-8")),
    )
    _write_json(
        tmp_path / "research" / "history" / run_id / "run_progress.v1.json",
        json.loads((tmp_path / "research" / "run_progress_latest.v1.json").read_text(encoding="utf-8")),
    )
    _write_json(
        tmp_path / "research" / "history" / run_id / "batches" / "batch-2" / "candidate_resume" / "resume.v1.json",
        {"version": "v1"},
    )


def test_build_research_state_sequential_retrieval_surfaces_sequence_and_recovery(tmp_path: Path) -> None:
    _seed_repo(tmp_path)

    report = sequential.build_research_state_sequential_retrieval(repo_root=tmp_path)

    assert report["summary"]["research_state_sequential_retrieval_ready"] is True
    assert report["summary"]["current_run_id"] == "20260619T100000000000Z"
    assert report["summary"]["history_run_count"] == 2
    assert report["summary"]["visible_sequence_row_count"] == 3
    assert report["summary"]["resumable"] is True
    assert report["summary"]["exact_next_action"] == "resume_from_existing_run_history"
    assert report["summary"]["current_hypothesis_state"] == "needs_more_diagnostic_evidence"
    assert report["recovery_context"]["retry_failed_batches"] is True
    assert report["recovery_context"]["same_input_history_count"] == 1
    assert report["sequence_rows"][-1]["source"] == "current_latest"
    assert report["sequence_rows"][-1]["next_best_test"] == "inspect_gate_diagnostics"
    assert report["sequence_rows"][-1]["batch_attempt_reason_counts"]["retry_failed_batch"] == 1


def test_build_research_state_sequential_retrieval_fails_closed_when_current_artifacts_missing(tmp_path: Path) -> None:
    report = sequential.build_research_state_sequential_retrieval(repo_root=tmp_path)

    assert report["summary"]["research_state_sequential_retrieval_ready"] is False
    assert report["summary"]["blocked_count"] >= 4
    blocker_codes = {row["blocker_code"] for row in report["blockers"]}
    assert "missing_run_manifest" in blocker_codes
    assert "missing_research_state" in blocker_codes
    assert report["summary"]["exact_next_action"] == "restore_current_run_artifacts"


def test_write_outputs_stays_in_allowlist(tmp_path: Path) -> None:
    _seed_repo(tmp_path)

    report = sequential.build_research_state_sequential_retrieval(repo_root=tmp_path)
    paths = sequential.write_outputs(report, repo_root=tmp_path)

    assert paths["latest"] == "logs/qre_research_state_sequential_retrieval/latest.json"
    assert paths["operator_summary"] == "logs/qre_research_state_sequential_retrieval/operator_summary.md"
    assert (tmp_path / paths["latest"]).exists()
    assert (tmp_path / paths["operator_summary"]).exists()
