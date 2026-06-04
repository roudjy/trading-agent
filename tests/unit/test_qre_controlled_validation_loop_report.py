from __future__ import annotations

import json

from reporting import qre_controlled_validation_execution as execution
from reporting import qre_controlled_validation_loop_report as loop


def test_loop_report_blocks_before_execution_by_default() -> None:
    snapshot = loop.collect_snapshot(
        profile_name="equities_exploratory_v1",
        generated_at_utc="2026-06-03T21:00:00Z",
    )

    assert snapshot["report_kind"] == "qre_controlled_validation_loop_report"
    assert snapshot["safe_to_execute"] is False
    assert snapshot["read_only"] is True
    assert snapshot["final_recommendation"] == (
        "controlled_validation_loop_blocked_before_execution"
    )
    assert snapshot["counts"]["execution_authorized"] == 0
    assert snapshot["loop_stages"]["execution"]["execution_status"] == (
        "execution_blocked_not_requested"
    )
    assert snapshot["writes_research_action_queue"] is False


def test_loop_report_authorizes_execution_but_stops_at_runner_not_connected() -> None:
    snapshot = loop.collect_snapshot(
        profile_name="equities_exploratory_v1",
        execute_controlled_validation=True,
        execution_operator_go=execution.REQUIRED_OPERATOR_GO_PHRASE,
        generated_at_utc="2026-06-03T21:00:00Z",
    )

    assert snapshot["final_recommendation"] == (
        "controlled_validation_loop_execution_authorized_runner_not_connected"
    )
    assert snapshot["counts"]["execution_authorized"] == 1
    assert snapshot["counts"]["analysis_ready"] == 0
    assert snapshot["loop_stages"]["execution"]["controlled_validation_authorized"] is True
    assert snapshot["loop_stages"]["execution"]["runner_adapter_status"] == "not_connected"
    assert snapshot["loop_stages"]["result_analysis"]["analysis_status"] == (
        "analysis_blocked_runner_not_connected"
    )
    assert snapshot["executed_anything"] is False


def test_loop_report_queue_flags_do_not_bypass_learning_gate() -> None:
    snapshot = loop.collect_snapshot(
        profile_name="equities_exploratory_v1",
        write_research_action_queue=True,
        queue_operator_go="I authorize QRE research action queue mutation",
        generated_at_utc="2026-06-03T21:00:00Z",
    )

    assert snapshot["counts"]["queue_mutation_authorized"] == 0
    assert snapshot["loop_stages"]["research_action_queue_gate"]["queue_status"] == (
        "queue_blocked_learning_not_ready"
    )
    assert snapshot["writes_research_action_queue"] is False


def test_cli_no_write_does_not_create_artifact(tmp_path, monkeypatch, capsys) -> None:
    artifact_path = tmp_path / "latest.json"
    monkeypatch.setattr(loop, "ARTIFACT_LATEST", artifact_path)

    rc = loop.main(
        [
            "--profile",
            "equities_exploratory_v1",
            "--execute-controlled-validation",
            "--execution-operator-go",
            execution.REQUIRED_OPERATOR_GO_PHRASE,
            "--no-write",
            "--frozen-utc",
            "2026-06-03T21:00:00Z",
        ]
    )

    assert rc == 0
    assert not artifact_path.exists()
    payload = json.loads(capsys.readouterr().out)
    assert payload["counts"]["execution_authorized"] == 1


def test_cli_writes_only_own_artifact(tmp_path, monkeypatch) -> None:
    artifact_dir = tmp_path / "qre_controlled_validation_loop_report"
    artifact_path = artifact_dir / "latest.json"
    monkeypatch.setattr(loop, "ARTIFACT_DIR", artifact_dir)
    monkeypatch.setattr(loop, "ARTIFACT_LATEST", artifact_path)

    rc = loop.main(
        [
            "--profile",
            "equities_exploratory_v1",
            "--frozen-utc",
            "2026-06-03T21:00:00Z",
        ]
    )

    assert rc == 0
    assert artifact_path.exists()
    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert payload["final_recommendation"] == (
        "controlled_validation_loop_blocked_before_execution"
    )
    assert payload["read_only"] is True

def test_loop_report_connected_runner_reaches_learning_ready(monkeypatch, tmp_path) -> None:
    def fake_run_controlled_eval(**kwargs: object) -> int:
        report_json = kwargs["report_json"]
        report_md = kwargs["report_md"]
        report_json.write_text(
            json.dumps(
                {
                    "verdict": {
                        "status": "useful_observation",
                        "reason_codes": ["degenerate_no_survivors"],
                    },
                    "campaigns_completed": 1,
                    "recommended_next_action": "inspect_results",
                }
            ),
            encoding="utf-8",
        )
        report_md.write_text("# fake controlled eval", encoding="utf-8")
        out = kwargs["out"]
        out.write("controlled_eval: completed=1 verdict=useful_observation\\n")
        return 0

    class FakeControlledEval:
        @staticmethod
        def run_controlled_eval(**kwargs: object) -> int:
            return fake_run_controlled_eval(**kwargs)

    monkeypatch.setattr(
        execution,
        "_load_controlled_eval_module",
        lambda: FakeControlledEval,
    )
    monkeypatch.setattr(execution, "ARTIFACT_DIR", tmp_path)
    monkeypatch.setattr(
        execution,
        "CONTROLLED_EVAL_REPORT_JSON",
        tmp_path / "controlled_eval_latest.v1.json",
    )
    monkeypatch.setattr(
        execution,
        "CONTROLLED_EVAL_REPORT_MD",
        tmp_path / "controlled_eval_latest.md",
    )

    snapshot = loop.collect_snapshot(
        profile_name="equities_exploratory_v1",
        execute_controlled_validation=True,
        execution_operator_go=execution.REQUIRED_OPERATOR_GO_PHRASE,
        connect_runner_adapter=True,
        timeout_seconds_per_campaign=60,
        generated_at_utc="2026-06-04T00:00:00Z",
    )

    assert snapshot["counts"]["execution_authorized"] == 1
    assert snapshot["counts"]["analysis_ready"] == 1
    assert snapshot["counts"]["learning_ready"] == 1
    assert snapshot["counts"]["queue_mutation_authorized"] == 0
    assert snapshot["loop_stages"]["execution"]["runner_adapter_status"] == "connected"
    assert snapshot["loop_stages"]["result_analysis"]["analysis_status"] == "analysis_ready"
    assert snapshot["loop_stages"]["learning_proposal"]["learning_status"] == (
        "learning_ready_for_operator_review"
    )
    assert snapshot["loop_stages"]["research_action_queue_gate"]["queue_status"] == (
        "queue_blocked_write_not_requested"
    )
    assert snapshot["writes_research_action_queue"] is False

