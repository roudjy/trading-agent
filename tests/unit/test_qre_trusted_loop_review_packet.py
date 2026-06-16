from __future__ import annotations

import json
from pathlib import Path

import pytest

from research import qre_trusted_loop_review_packet as packet_module


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _seed_repo_files(tmp_path: Path) -> None:
    _write_json(tmp_path / "research" / "research_latest.json", {"report_kind": "seed"})
    (tmp_path / "research" / "strategy_matrix.csv").write_text("seed\n", encoding="utf-8")


def _ready_snapshots() -> dict[str, dict]:
    return {
        "readiness": {
            "readiness_state": "operator_trusted",
            "operator_report_available": True,
            "contradiction_visibility": {"status": "visible"},
            "source_lineage": {"status": "complete"},
            "repeatability_status": "operator_approved_repeatability_evidence_present",
            "blockers": [],
            "final_recommendation": "trusted_loop_ready_for_operator_use",
        },
        "reason_records": {
            "meta": {"record_count": 3},
        },
        "failure_action": {
            "summary": {"actionable_count": 3, "non_actionable_count": 0},
        },
        "basket_closure": {
            "summary": {"evidence_complete_count": 1},
        },
        "routing": {
            "summary": {"final_recommendation": "routing_calibration_evidence_ready"},
        },
        "sampling": {
            "summary": {"final_recommendation": "sampling_calibration_evidence_ready"},
        },
        "research_memory": {
            "summary": {"final_recommendation": "research_memory_current_artifacts_ready"},
        },
    }


def test_trusted_loop_review_packet_reports_operator_trusted_when_evidence_chain_is_complete(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_repo_files(tmp_path)
    snapshots = _ready_snapshots()
    monkeypatch.setattr(packet_module.trusted_readiness, "collect_snapshot", lambda **_: snapshots["readiness"])
    monkeypatch.setattr(
        packet_module.reason_records,
        "build_reason_records_snapshot",
        lambda **_: snapshots["reason_records"],
    )
    monkeypatch.setattr(
        packet_module.failure_action,
        "build_failure_action_from_basket",
        lambda **_: snapshots["failure_action"],
    )
    monkeypatch.setattr(
        packet_module.basket_closure,
        "build_evidence_complete_basket_closure",
        lambda **_: snapshots["basket_closure"],
    )
    monkeypatch.setattr(
        packet_module.routing_calibration,
        "build_routing_calibration_report",
        lambda **_: snapshots["routing"],
    )
    monkeypatch.setattr(
        packet_module.sampling_calibration,
        "build_sampling_calibration_report",
        lambda **_: snapshots["sampling"],
    )
    monkeypatch.setattr(
        packet_module.research_memory,
        "build_research_memory_current_artifacts",
        lambda **_: snapshots["research_memory"],
    )
    monkeypatch.setattr(
        packet_module.basket_action_plan,
        "build_basket_operator_action_plan",
        lambda **_: {
            "summary": {
                "final_recommendation": "basket_operator_action_plan_ready",
                "first_batch_candidate_symbols": ["AAPL", "NVDA"],
            }
        },
    )

    packet = packet_module.build_trusted_loop_review_packet(repo_root=tmp_path)

    assert packet["summary"]["trusted_loop_review_ready"] is True
    assert packet["summary"]["trust_level"] == "3"
    assert packet["summary"]["trust_verdict"] == "operator_trusted"
    assert packet["summary"]["exact_next_action"] == "maintain_operator_trusted_read_only_mode"
    assert packet["summary"]["final_recommendation"] == "trusted_loop_operator_trusted"
    assert packet["summary"]["reason_record_count"] == 3
    assert packet["summary"]["evidence_complete_basket_count"] == 1
    assert packet["summary"]["routing_evidence_ready"] is True
    assert packet["summary"]["sampling_evidence_ready"] is True
    assert packet["summary"]["research_memory_ready"] is True
    assert packet["summary"]["basket_operator_action_plan_ready"] is True
    assert packet["summary"]["basket_operator_action_plan_first_batch"] == ["AAPL", "NVDA"]
    assert packet["summary"]["trust_blocker_count"] == 0
    assert packet["protected_artifacts"][0]["exists"] is True
    assert packet["protected_artifacts"][1]["exists"] is True
    assert packet["evidence_inputs"]["trusted_loop_readiness"]["readiness_state"] == "operator_trusted"


def test_trusted_loop_review_packet_fails_closed_when_evidence_chain_is_incomplete(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_repo_files(tmp_path)
    monkeypatch.setattr(
        packet_module.trusted_readiness,
        "collect_snapshot",
        lambda **_: {
            "readiness_state": "working_capability",
            "operator_report_available": True,
            "contradiction_visibility": {"status": "visible"},
            "source_lineage": {"status": "complete"},
            "repeatability_status": "no_repeatability_evidence",
            "blockers": ["validation_results_or_evidence_updates_absent"],
            "final_recommendation": "operator_review_required_before_trusted_loop_use",
        },
    )
    monkeypatch.setattr(packet_module.reason_records, "build_reason_records_snapshot", lambda **_: {"meta": {"record_count": 0}})
    monkeypatch.setattr(packet_module.failure_action, "build_failure_action_from_basket", lambda **_: {"summary": {"actionable_count": 0, "non_actionable_count": 1}})
    monkeypatch.setattr(packet_module.basket_closure, "build_evidence_complete_basket_closure", lambda **_: {"summary": {"evidence_complete_count": 0}})
    monkeypatch.setattr(packet_module.routing_calibration, "build_routing_calibration_report", lambda **_: {"summary": {"final_recommendation": "routing_calibration_scaffold_ready"}})
    monkeypatch.setattr(packet_module.sampling_calibration, "build_sampling_calibration_report", lambda **_: {"summary": {"final_recommendation": "sampling_calibration_scaffold_ready"}})
    monkeypatch.setattr(packet_module.research_memory, "build_research_memory_current_artifacts", lambda **_: {"summary": {"final_recommendation": "research_memory_current_artifacts_partial"}})
    monkeypatch.setattr(packet_module.basket_action_plan, "build_basket_operator_action_plan", lambda **_: {"summary": {"final_recommendation": "basket_operator_action_plan_ready", "first_batch_candidate_symbols": []}})

    packet = packet_module.build_trusted_loop_review_packet(repo_root=tmp_path)

    assert packet["summary"]["trusted_loop_review_ready"] is False
    assert packet["summary"]["trust_level"] == "1"
    assert packet["summary"]["trust_verdict"] == "read_only_context_fail_closed"
    assert packet["summary"]["exact_next_action"] == "restore_trusted_loop_readiness_evidence"
    assert "readiness_state:working_capability" in packet["summary"]["trust_blockers"]
    assert "reason_records_missing" in packet["summary"]["trust_blockers"]
    assert packet["summary"]["final_recommendation"] == "trusted_loop_operator_review_required"


def test_trusted_loop_review_packet_operator_summary_renders(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_repo_files(tmp_path)
    snapshots = _ready_snapshots()
    monkeypatch.setattr(packet_module.trusted_readiness, "collect_snapshot", lambda **_: snapshots["readiness"])
    monkeypatch.setattr(packet_module.reason_records, "build_reason_records_snapshot", lambda **_: snapshots["reason_records"])
    monkeypatch.setattr(packet_module.failure_action, "build_failure_action_from_basket", lambda **_: snapshots["failure_action"])
    monkeypatch.setattr(packet_module.basket_closure, "build_evidence_complete_basket_closure", lambda **_: snapshots["basket_closure"])
    monkeypatch.setattr(packet_module.routing_calibration, "build_routing_calibration_report", lambda **_: snapshots["routing"])
    monkeypatch.setattr(packet_module.sampling_calibration, "build_sampling_calibration_report", lambda **_: snapshots["sampling"])
    monkeypatch.setattr(packet_module.research_memory, "build_research_memory_current_artifacts", lambda **_: snapshots["research_memory"])
    monkeypatch.setattr(packet_module.basket_action_plan, "build_basket_operator_action_plan", lambda **_: {"summary": {"final_recommendation": "basket_operator_action_plan_ready", "first_batch_candidate_symbols": ["AAPL"]}})

    packet = packet_module.build_trusted_loop_review_packet(repo_root=tmp_path)
    text = packet_module.render_operator_summary(packet)

    assert "# QRE Trusted Loop Review Packet" in text
    assert "trust_level: 3" in text
    assert "maintain_operator_trusted_read_only_mode" in text
    assert "Authority Boundary" in text


def test_trusted_loop_review_packet_write_outputs_stays_in_allowlist(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_repo_files(tmp_path)
    snapshots = _ready_snapshots()
    monkeypatch.setattr(packet_module.trusted_readiness, "collect_snapshot", lambda **_: snapshots["readiness"])
    monkeypatch.setattr(packet_module.reason_records, "build_reason_records_snapshot", lambda **_: snapshots["reason_records"])
    monkeypatch.setattr(packet_module.failure_action, "build_failure_action_from_basket", lambda **_: snapshots["failure_action"])
    monkeypatch.setattr(packet_module.basket_closure, "build_evidence_complete_basket_closure", lambda **_: snapshots["basket_closure"])
    monkeypatch.setattr(packet_module.routing_calibration, "build_routing_calibration_report", lambda **_: snapshots["routing"])
    monkeypatch.setattr(packet_module.sampling_calibration, "build_sampling_calibration_report", lambda **_: snapshots["sampling"])
    monkeypatch.setattr(packet_module.research_memory, "build_research_memory_current_artifacts", lambda **_: snapshots["research_memory"])

    packet = packet_module.build_trusted_loop_review_packet(repo_root=tmp_path)
    paths = packet_module.write_outputs(packet, repo_root=tmp_path)

    assert paths["latest"] == "logs/qre_trusted_loop_review/latest.json"
    assert paths["operator_summary"] == "logs/qre_trusted_loop_review/operator_summary.md"
    assert (tmp_path / paths["latest"]).exists()
    assert (tmp_path / paths["operator_summary"]).exists()


def test_trusted_loop_review_packet_write_rejects_non_allowlisted_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(packet_module, "DEFAULT_OUTPUT_DIR", Path("bad"))
    packet = packet_module.build_trusted_loop_review_packet(repo_root=tmp_path)

    with pytest.raises(ValueError):
        packet_module.write_outputs(packet, repo_root=tmp_path)
