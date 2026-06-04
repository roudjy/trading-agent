from __future__ import annotations

import json

from reporting import qre_controlled_validation_research_action_queue_gate as gate


_READY_LEARNING = {
    "report_kind": "qre_controlled_validation_learning_proposal",
    "selection_profile_name": "equities_exploratory_v1",
    "learning_status": "learning_ready_for_operator_review",
    "final_recommendation": "controlled_validation_learning_proposal_ready_for_operator_review",
    "learning_proposal": {
        "available": True,
        "outcome": "pass",
        "hypothesis_action": "continue_validation",
        "next_research_action": "consider_bounded_followup_validation",
        "primary_failure_class": None,
        "evidence_refs": ["research/history/run-a/screening_evidence.v1.json"],
    },
}


def test_queue_gate_blocks_when_learning_not_ready() -> None:
    snapshot = gate.collect_snapshot(
        profile_name="equities_exploratory_v1",
        generated_at_utc="2026-06-03T20:00:00Z",
    )

    assert snapshot["report_kind"] == "qre_controlled_validation_research_action_queue_gate"
    assert snapshot["safe_to_execute"] is False
    assert snapshot["read_only"] is True
    assert snapshot["queue_status"] == "queue_blocked_learning_not_ready"
    assert snapshot["queue_mutation_authorized"] is False
    assert snapshot["writes_research_action_queue"] is False
    assert snapshot["candidate_queue_item"] is None


def test_queue_gate_blocks_when_write_not_requested() -> None:
    snapshot = gate.collect_snapshot(
        learning_snapshot=_READY_LEARNING,
        generated_at_utc="2026-06-03T20:00:00Z",
    )

    assert snapshot["queue_status"] == "queue_blocked_write_not_requested"
    assert snapshot["queue_mutation_authorized"] is False
    assert snapshot["learning_summary"]["proposal_available"] is True


def test_queue_gate_blocks_missing_operator_go() -> None:
    snapshot = gate.collect_snapshot(
        learning_snapshot=_READY_LEARNING,
        write_research_action_queue=True,
        generated_at_utc="2026-06-03T20:00:00Z",
    )

    assert snapshot["queue_status"] == "queue_blocked_operator_go_missing"
    assert snapshot["queue_mutation_authorized"] is False
    assert snapshot["operator_authorization"]["provided"] is False


def test_queue_gate_blocks_wrong_operator_go() -> None:
    snapshot = gate.collect_snapshot(
        learning_snapshot=_READY_LEARNING,
        write_research_action_queue=True,
        operator_go="wrong",
        generated_at_utc="2026-06-03T20:00:00Z",
    )

    assert snapshot["queue_status"] == "queue_blocked_operator_go_mismatch"
    assert snapshot["queue_mutation_authorized"] is False
    assert snapshot["operator_authorization"]["provided"] is True
    assert snapshot["operator_authorization"]["matched"] is False


def test_exact_operator_go_authorizes_but_writer_is_not_connected() -> None:
    snapshot = gate.collect_snapshot(
        learning_snapshot=_READY_LEARNING,
        write_research_action_queue=True,
        operator_go=gate.REQUIRED_QUEUE_GO_PHRASE,
        generated_at_utc="2026-06-03T20:00:00Z",
    )

    assert snapshot["queue_status"] == "queue_authorized_writer_not_connected"
    assert snapshot["queue_mutation_authorized"] is True
    assert snapshot["queue_writer_adapter_status"] == "not_connected"
    assert snapshot["writes_research_action_queue"] is False
    assert snapshot["candidate_queue_item"]["next_research_action"] == (
        "consider_bounded_followup_validation"
    )
    assert snapshot["candidate_queue_item"]["requires_operator_review"] is True


def test_cli_no_write_does_not_create_artifact(tmp_path, monkeypatch, capsys) -> None:
    artifact_path = tmp_path / "latest.json"
    monkeypatch.setattr(gate, "ARTIFACT_LATEST", artifact_path)

    rc = gate.main(
        [
            "--profile",
            "equities_exploratory_v1",
            "--no-write",
            "--frozen-utc",
            "2026-06-03T20:00:00Z",
        ]
    )

    assert rc == 0
    assert not artifact_path.exists()
    payload = json.loads(capsys.readouterr().out)
    assert payload["queue_status"] == "queue_blocked_learning_not_ready"


def test_cli_writes_only_own_artifact(tmp_path, monkeypatch) -> None:
    artifact_dir = tmp_path / "qre_controlled_validation_research_action_queue_gate"
    artifact_path = artifact_dir / "latest.json"
    monkeypatch.setattr(gate, "ARTIFACT_DIR", artifact_dir)
    monkeypatch.setattr(gate, "ARTIFACT_LATEST", artifact_path)

    rc = gate.main(
        [
            "--profile",
            "equities_exploratory_v1",
            "--frozen-utc",
            "2026-06-03T20:00:00Z",
        ]
    )

    assert rc == 0
    assert artifact_path.exists()
    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert payload["queue_status"] == "queue_blocked_learning_not_ready"
    assert payload["read_only"] is True
