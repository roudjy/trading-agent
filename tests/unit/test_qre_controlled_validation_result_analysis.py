from __future__ import annotations

import json

from reporting import qre_controlled_validation_execution as execution
from reporting import qre_controlled_validation_result_analysis as analysis


def test_analysis_blocks_when_execution_not_authorized() -> None:
    snapshot = analysis.collect_snapshot(
        profile_name="equities_exploratory_v1",
        generated_at_utc="2026-06-03T18:00:00Z",
    )

    assert snapshot["report_kind"] == "qre_controlled_validation_result_analysis"
    assert snapshot["safe_to_execute"] is False
    assert snapshot["read_only"] is True
    assert snapshot["analysis_status"] == "analysis_blocked_execution_not_authorized"
    assert snapshot["counts"]["blocked"] == 1
    assert snapshot["result_summary"]["completed_run_available"] is False
    assert snapshot["writes_research_action_queue"] is False


def test_analysis_blocks_when_runner_not_connected_even_if_authorized() -> None:
    execution_snapshot = execution.collect_snapshot(
        profile_name="equities_exploratory_v1",
        execute_controlled_validation=True,
        operator_go=execution.REQUIRED_OPERATOR_GO_PHRASE,
        generated_at_utc="2026-06-03T17:00:00Z",
    )

    snapshot = analysis.collect_snapshot(
        profile_name="equities_exploratory_v1",
        execution_snapshot=execution_snapshot,
        generated_at_utc="2026-06-03T18:00:00Z",
    )

    assert snapshot["analysis_status"] == "analysis_blocked_runner_not_connected"
    assert snapshot["execution_summary"]["controlled_validation_authorized"] is True
    assert snapshot["execution_summary"]["runner_adapter_status"] == "not_connected"
    assert snapshot["result_summary"]["completed_run_available"] is False
    assert snapshot["next_required_step"] == (
        "connect controlled validation runner before result analysis"
    )


def test_analysis_blocks_when_connected_runner_has_no_completed_run() -> None:
    execution_snapshot = {
        "report_kind": "qre_controlled_validation_execution",
        "selection_profile_name": "equities_exploratory_v1",
        "execution_status": "execution_authorized_runner_connected",
        "controlled_validation_authorized": True,
        "runner_adapter_status": "connected",
        "executed_anything": False,
        "final_recommendation": "controlled_validation_execution_ready",
    }

    snapshot = analysis.collect_snapshot(
        execution_snapshot=execution_snapshot,
        generated_at_utc="2026-06-03T18:00:00Z",
    )

    assert snapshot["analysis_status"] == "analysis_blocked_no_completed_run"
    assert snapshot["execution_summary"]["runner_adapter_status"] == "connected"
    assert snapshot["execution_summary"]["executed_anything"] is False


def test_analysis_ready_when_execution_completed() -> None:
    execution_snapshot = {
        "report_kind": "qre_controlled_validation_execution",
        "selection_profile_name": "equities_exploratory_v1",
        "execution_status": "execution_completed",
        "controlled_validation_authorized": True,
        "runner_adapter_status": "connected",
        "executed_anything": True,
        "final_recommendation": "controlled_validation_execution_completed",
    }

    snapshot = analysis.collect_snapshot(
        execution_snapshot=execution_snapshot,
        generated_at_utc="2026-06-03T18:00:00Z",
    )

    assert snapshot["analysis_status"] == "analysis_ready"
    assert snapshot["counts"]["ready"] == 1
    assert snapshot["result_summary"]["completed_run_available"] is True
    assert snapshot["final_recommendation"] == "controlled_validation_result_analysis_ready"


def test_cli_no_write_does_not_create_artifact(tmp_path, monkeypatch, capsys) -> None:
    artifact_path = tmp_path / "latest.json"
    monkeypatch.setattr(analysis, "ARTIFACT_LATEST", artifact_path)

    rc = analysis.main(
        [
            "--profile",
            "equities_exploratory_v1",
            "--no-write",
            "--frozen-utc",
            "2026-06-03T18:00:00Z",
        ]
    )

    assert rc == 0
    assert not artifact_path.exists()
    payload = json.loads(capsys.readouterr().out)
    assert payload["analysis_status"] == "analysis_blocked_execution_not_authorized"


def test_cli_writes_only_own_artifact(tmp_path, monkeypatch) -> None:
    artifact_dir = tmp_path / "qre_controlled_validation_result_analysis"
    artifact_path = artifact_dir / "latest.json"
    monkeypatch.setattr(analysis, "ARTIFACT_DIR", artifact_dir)
    monkeypatch.setattr(analysis, "ARTIFACT_LATEST", artifact_path)

    rc = analysis.main(
        [
            "--profile",
            "equities_exploratory_v1",
            "--frozen-utc",
            "2026-06-03T18:00:00Z",
        ]
    )

    assert rc == 0
    assert artifact_path.exists()
    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert payload["analysis_status"] == "analysis_blocked_execution_not_authorized"
    assert payload["read_only"] is True
