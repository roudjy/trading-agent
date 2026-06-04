from __future__ import annotations

import json

from reporting import qre_controlled_validation_learning_proposal as learning


def test_learning_blocks_when_analysis_not_ready() -> None:
    snapshot = learning.collect_snapshot(
        profile_name="equities_exploratory_v1",
        generated_at_utc="2026-06-03T19:00:00Z",
    )

    assert snapshot["report_kind"] == "qre_controlled_validation_learning_proposal"
    assert snapshot["safe_to_execute"] is False
    assert snapshot["read_only"] is True
    assert snapshot["learning_status"] == "learning_blocked_analysis_not_ready"
    assert snapshot["counts"]["blocked"] == 1
    assert snapshot["learning_proposal"]["available"] is False
    assert snapshot["writes_research_action_queue"] is False


def test_learning_ready_for_pass_result() -> None:
    analysis_snapshot = {
        "report_kind": "qre_controlled_validation_result_analysis",
        "selection_profile_name": "equities_exploratory_v1",
        "analysis_status": "analysis_ready",
        "final_recommendation": "controlled_validation_result_analysis_ready",
        "result_summary": {
            "completed_run_available": True,
            "pass_fail": "pass",
            "trade_count": 12,
            "primary_failure_class": None,
            "evidence_refs": ["research/history/run-a/screening_evidence.v1.json"],
        },
    }

    snapshot = learning.collect_snapshot(
        analysis_snapshot=analysis_snapshot,
        generated_at_utc="2026-06-03T19:00:00Z",
    )

    assert snapshot["learning_status"] == "learning_ready_for_operator_review"
    assert snapshot["counts"]["ready"] == 1
    assert snapshot["learning_proposal"]["available"] is True
    assert snapshot["learning_proposal"]["outcome"] == "pass"
    assert snapshot["learning_proposal"]["hypothesis_action"] == "continue_validation"
    assert snapshot["learning_proposal"]["next_research_action"] == (
        "consider_bounded_followup_validation"
    )
    assert snapshot["writes_research_action_queue"] is False


def test_learning_ready_for_fail_result() -> None:
    analysis_snapshot = {
        "report_kind": "qre_controlled_validation_result_analysis",
        "selection_profile_name": "equities_exploratory_v1",
        "analysis_status": "analysis_ready",
        "final_recommendation": "controlled_validation_result_analysis_ready",
        "result_summary": {
            "completed_run_available": True,
            "pass_fail": "fail",
            "trade_count": 3,
            "primary_failure_class": "insufficient_trades",
            "evidence_refs": ["research/history/run-b/screening_evidence.v1.json"],
        },
    }

    snapshot = learning.collect_snapshot(
        analysis_snapshot=analysis_snapshot,
        generated_at_utc="2026-06-03T19:00:00Z",
    )

    assert snapshot["learning_status"] == "learning_ready_for_operator_review"
    assert snapshot["learning_proposal"]["hypothesis_action"] == "do_not_promote"
    assert snapshot["learning_proposal"]["next_research_action"] == (
        "investigate_failure_class"
    )
    assert snapshot["learning_proposal"]["primary_failure_class"] == "insufficient_trades"


def test_cli_no_write_does_not_create_artifact(tmp_path, monkeypatch, capsys) -> None:
    artifact_path = tmp_path / "latest.json"
    monkeypatch.setattr(learning, "ARTIFACT_LATEST", artifact_path)

    rc = learning.main(
        [
            "--profile",
            "equities_exploratory_v1",
            "--no-write",
            "--frozen-utc",
            "2026-06-03T19:00:00Z",
        ]
    )

    assert rc == 0
    assert not artifact_path.exists()
    payload = json.loads(capsys.readouterr().out)
    assert payload["learning_status"] == "learning_blocked_analysis_not_ready"


def test_cli_writes_only_own_artifact(tmp_path, monkeypatch) -> None:
    artifact_dir = tmp_path / "qre_controlled_validation_learning_proposal"
    artifact_path = artifact_dir / "latest.json"
    monkeypatch.setattr(learning, "ARTIFACT_DIR", artifact_dir)
    monkeypatch.setattr(learning, "ARTIFACT_LATEST", artifact_path)

    rc = learning.main(
        [
            "--profile",
            "equities_exploratory_v1",
            "--frozen-utc",
            "2026-06-03T19:00:00Z",
        ]
    )

    assert rc == 0
    assert artifact_path.exists()
    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert payload["learning_status"] == "learning_blocked_analysis_not_ready"
    assert payload["read_only"] is True
