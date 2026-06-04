from __future__ import annotations

import json

from reporting import qre_controlled_validation_execution as execution


def test_default_controlled_validation_execution_is_blocked() -> None:
    snapshot = execution.collect_snapshot(
        profile_name="equities_exploratory_v1",
        generated_at_utc="2026-06-03T17:00:00Z",
    )

    assert snapshot["report_kind"] == "qre_controlled_validation_execution"
    assert snapshot["safe_to_execute"] is False
    assert snapshot["read_only"] is True
    assert snapshot["eligible_for_direct_execution"] is False
    assert snapshot["launches_subprocess"] is False
    assert snapshot["executed_anything"] is False
    assert snapshot["controlled_validation_authorized"] is False
    assert snapshot["live_or_paper_execution_authorized"] is False
    assert snapshot["execution_status"] == "execution_blocked_not_requested"
    assert snapshot["final_recommendation"] == "controlled_validation_execution_blocked"
    assert snapshot["preflight"]["selection_route_ready"] is True


def test_execute_flag_without_operator_go_is_blocked() -> None:
    snapshot = execution.collect_snapshot(
        profile_name="equities_exploratory_v1",
        execute_controlled_validation=True,
        generated_at_utc="2026-06-03T17:00:00Z",
    )

    assert snapshot["execution_status"] == "execution_blocked_operator_go_missing"
    assert snapshot["controlled_validation_authorized"] is False
    assert snapshot["operator_authorization"]["provided"] is False
    assert snapshot["operator_authorization"]["matched"] is False


def test_execute_flag_with_wrong_operator_go_is_blocked() -> None:
    snapshot = execution.collect_snapshot(
        profile_name="equities_exploratory_v1",
        execute_controlled_validation=True,
        operator_go="wrong",
        generated_at_utc="2026-06-03T17:00:00Z",
    )

    assert snapshot["execution_status"] == "execution_blocked_operator_go_mismatch"
    assert snapshot["controlled_validation_authorized"] is False
    assert snapshot["operator_authorization"]["provided"] is True
    assert snapshot["operator_authorization"]["matched"] is False


def test_exact_operator_go_authorizes_contract_but_runner_is_not_connected() -> None:
    snapshot = execution.collect_snapshot(
        profile_name="equities_exploratory_v1",
        execute_controlled_validation=True,
        operator_go=execution.REQUIRED_OPERATOR_GO_PHRASE,
        generated_at_utc="2026-06-03T17:00:00Z",
    )

    assert snapshot["execution_status"] == "execution_authorized_runner_not_connected"
    assert snapshot["controlled_validation_authorized"] is True
    assert snapshot["runner_adapter_status"] == "not_connected"
    assert snapshot["planned_runner"]["module"] == "research.controlled_eval"
    assert snapshot["planned_runner"]["connected"] is False
    assert snapshot["launches_subprocess"] is False
    assert snapshot["executed_anything"] is False
    assert snapshot["mutates_campaign_queue"] is False
    assert snapshot["writes_research_action_queue"] is False


def test_preflight_not_ready_blocks_even_with_operator_go() -> None:
    preflight_snapshot = {
        "report_kind": "qre_selection_closed_loop_preflight",
        "final_recommendation": "selection_route_preflight_blocked",
        "selection_route": {"ready": False, "counts": {}},
        "controlled_regeneration_preflight": {"can_be_considered": False},
    }

    snapshot = execution.collect_snapshot(
        profile_name="equities_exploratory_v1",
        execute_controlled_validation=True,
        operator_go=execution.REQUIRED_OPERATOR_GO_PHRASE,
        preflight_snapshot=preflight_snapshot,
        generated_at_utc="2026-06-03T17:00:00Z",
    )

    assert snapshot["execution_status"] == "execution_blocked_preflight_not_ready"
    assert snapshot["controlled_validation_authorized"] is False


def test_cli_no_write_does_not_create_artifact(tmp_path, monkeypatch, capsys) -> None:
    artifact_path = tmp_path / "latest.json"
    monkeypatch.setattr(execution, "ARTIFACT_LATEST", artifact_path)

    rc = execution.main(
        [
            "--profile",
            "equities_exploratory_v1",
            "--execute-controlled-validation",
            "--operator-go",
            execution.REQUIRED_OPERATOR_GO_PHRASE,
            "--no-write",
            "--frozen-utc",
            "2026-06-03T17:00:00Z",
        ]
    )

    assert rc == 0
    assert not artifact_path.exists()
    payload = json.loads(capsys.readouterr().out)
    assert payload["controlled_validation_authorized"] is True


def test_cli_writes_only_own_artifact(tmp_path, monkeypatch) -> None:
    artifact_dir = tmp_path / "qre_controlled_validation_execution"
    artifact_path = artifact_dir / "latest.json"
    monkeypatch.setattr(execution, "ARTIFACT_DIR", artifact_dir)
    monkeypatch.setattr(execution, "ARTIFACT_LATEST", artifact_path)

    rc = execution.main(
        [
            "--profile",
            "equities_exploratory_v1",
            "--frozen-utc",
            "2026-06-03T17:00:00Z",
        ]
    )

    assert rc == 0
    assert artifact_path.exists()
    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert payload["execution_status"] == "execution_blocked_not_requested"
    assert payload["executed_anything"] is False
