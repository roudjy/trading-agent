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
        "operational_controls": {
            "summary": {
                "trusted_loop_operational_controls_ready": True,
                "exact_next_safe_action": "preserve_terminal_run_and_compare_before_rerun",
            }
        },
        "shadow_readiness": {
            "summary": {
                "readiness_status": "shadow_readiness_deferred",
                "exact_next_action": "produce_accepted_oos_and_evidence_complete_scope",
            }
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
        packet_module.artifact_continuity,
        "build_read_only_artifact_continuity",
        lambda **_: {
            "summary": {
                "artifact_continuity_ready": True,
                "exact_next_action": "preserve_current_read_only_artifacts",
            }
        },
    )
    monkeypatch.setattr(
        packet_module.contradiction_staleness,
        "build_contradiction_staleness_intelligence",
        lambda **_: {
            "summary": {
                "contradiction_staleness_ready": True,
                "contradiction_count": 0,
                "stale_or_superseded_count": 0,
                "exact_next_action": "preserve_contradiction_and_staleness_visibility",
            }
        },
    )
    monkeypatch.setattr(
        packet_module.lineage_graph,
        "build_qre_lineage_graph_v1",
        lambda **_: {
            "summary": {
                "graph_status": "partial",
                "candidate_count": 2,
                "reason_record_count": 3,
            }
        },
    )
    monkeypatch.setattr(
        packet_module.throughput_bottlenecks,
        "build_campaign_throughput_bottleneck_intelligence",
        lambda **_: {
            "summary": {
                "campaign_throughput_bottleneck_intelligence_ready": True,
                "bottleneck_count": 0,
                "exact_next_action": "preserve_campaign_throughput_context",
            }
        },
    )
    monkeypatch.setattr(
        packet_module.novelty_enforcement,
        "build_experiment_dedup_novelty_enforcement",
        lambda **_: {
            "summary": {
                "experiment_dedup_novelty_enforcement_ready": True,
                "duplicate_pressure_count": 0,
                "exact_next_action": "route_only_to_eligible_novel_directions",
            }
        },
    )
    monkeypatch.setattr(
        packet_module.sequential_retrieval,
        "build_research_state_sequential_retrieval",
        lambda **_: {
            "summary": {
                "research_state_sequential_retrieval_ready": True,
                "visible_sequence_row_count": 4,
                "exact_next_action": "preserve_research_state_sequence_visibility",
            }
        },
    )
    monkeypatch.setattr(
        packet_module.reason_record_normalization,
        "build_reason_record_normalization",
        lambda **_: {
            "summary": {
                "reason_record_normalization_ready": True,
                "normalized_record_count": 7,
                "invalid_record_count": 2,
                "exact_next_action": "normalize_reason_record_contract_gaps_before_authority_upgrade",
            }
        },
    )
    monkeypatch.setattr(
        packet_module.remediation_planning,
        "build_incomplete_artifact_remediation_planning",
        lambda **_: {
            "summary": {
                "remediation_planning_ready": True,
                "remediation_count": 2,
                "exact_next_action": "preserve_current_read_only_artifact_visibility",
            }
        },
    )
    monkeypatch.setattr(
        packet_module.operational_controls,
        "build_trusted_loop_operational_controls",
        lambda **_: snapshots["operational_controls"],
    )
    monkeypatch.setattr(
        packet_module.shadow_readiness_gates,
        "build_shadow_readiness_gates",
        lambda **_: snapshots["shadow_readiness"],
    )
    monkeypatch.setattr(
        packet_module.basket_action_plan,
        "build_basket_operator_action_plan",
        lambda **_: {
            "summary": {
                "final_recommendation": "basket_operator_action_plan_ready",
                "first_batch_candidate_symbols": ["AAPL", "NVDA"],
                "generation_command_discovery_result": "qre_bounded_aapl_nvda_current_basket_generation_discovery",
                "generation_command_discovery_safe_command_found": False,
                "generation_command_discovery_final_recommendation": "NO_SAFE_BOUNDED_GENERATION_COMMAND_FOUND",
            }
        },
    )
    monkeypatch.setattr(
        packet_module.first_batch_readiness,
        "build_first_batch_evidence_recovery_readiness",
        lambda **_: {"report_kind": "qre_first_batch_evidence_recovery_readiness"},
    )
    monkeypatch.setattr(
        packet_module.first_batch_cascade,
        "build_first_batch_evidence_recovery_cascade",
        lambda **_: {
            "report_kind": "qre_first_batch_evidence_recovery_cascade",
            "overall_result": "PRESET_TIMEFRAME_ALIAS_BLOCKED",
            "first_batch_summary": {"current_top_blocker": "preset_timeframe_alias_unproven"},
        },
    )
    monkeypatch.setattr(
        packet_module,
        "_guarded_alias_bounded_generation_snapshot",
        lambda *_: {
            "report_kind": "qre_guarded_alias_bounded_generation_cascade",
            "overall_result": "ALIAS_POLICY_CONTEXT_ONLY_BOUNDED_GENERATION_READY",
            "summary": {"current_top_blocker": "operator_approval_required_for_bounded_generation"},
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
    assert packet["summary"]["artifact_continuity_ready"] is True
    assert packet["summary"]["artifact_continuity_exact_next_action"] == "preserve_current_read_only_artifacts"
    assert packet["summary"]["contradiction_staleness_ready"] is True
    assert packet["summary"]["lineage_graph_status"] == "partial"
    assert packet["summary"]["visible_lineage_candidate_count"] == 2
    assert packet["summary"]["visible_lineage_reason_record_count"] == 3
    assert packet["summary"]["visible_contradiction_count"] == 0
    assert packet["summary"]["visible_stale_or_superseded_count"] == 0
    assert packet["summary"]["campaign_throughput_bottleneck_intelligence_ready"] is True
    assert packet["summary"]["visible_campaign_throughput_bottleneck_count"] == 0
    assert packet["summary"]["experiment_dedup_novelty_enforcement_ready"] is True
    assert packet["summary"]["visible_experiment_duplicate_pressure_count"] == 0
    assert packet["summary"]["research_state_sequential_retrieval_ready"] is True
    assert packet["summary"]["visible_research_state_sequence_count"] == 4
    assert packet["summary"]["research_state_sequential_exact_next_action"] == "preserve_research_state_sequence_visibility"
    assert packet["summary"]["reason_record_normalization_ready"] is True
    assert packet["summary"]["visible_reason_record_normalized_count"] == 7
    assert packet["summary"]["visible_reason_record_invalid_count"] == 2
    assert packet["summary"]["reason_record_normalization_exact_next_action"] == "normalize_reason_record_contract_gaps_before_authority_upgrade"
    assert packet["summary"]["incomplete_artifact_remediation_planning_ready"] is True
    assert packet["summary"]["visible_incomplete_artifact_remediation_count"] == 2
    assert packet["summary"]["incomplete_artifact_remediation_exact_next_action"] == "preserve_current_read_only_artifact_visibility"
    assert packet["summary"]["trusted_loop_operational_controls_ready"] is True
    assert packet["summary"]["trusted_loop_operational_exact_next_action"] == "preserve_terminal_run_and_compare_before_rerun"
    assert packet["summary"]["shadow_readiness_status"] == "shadow_readiness_deferred"
    assert packet["summary"]["shadow_readiness_next_action"] == "produce_accepted_oos_and_evidence_complete_scope"
    assert packet["summary"]["basket_operator_action_plan_ready"] is True
    assert packet["summary"]["basket_operator_action_plan_first_batch"] == ["AAPL", "NVDA"]
    assert packet["summary"]["generation_command_discovery_safe_command_found"] is False
    assert packet["summary"]["generation_command_discovery_final_recommendation"] == "NO_SAFE_BOUNDED_GENERATION_COMMAND_FOUND"
    assert packet["summary"]["first_batch_readiness_available"] is True
    assert packet["summary"]["first_batch_recovery_cascade_available"] is True
    assert packet["summary"]["first_batch_recovery_cascade_result"] == "PRESET_TIMEFRAME_ALIAS_BLOCKED"
    assert packet["summary"]["guarded_alias_bounded_generation_cascade_result"] == "ALIAS_POLICY_CONTEXT_ONLY_BOUNDED_GENERATION_READY"
    assert packet["summary"]["guarded_alias_bounded_generation_top_blocker"] == "operator_approval_required_for_bounded_generation"
    assert packet["summary"]["structured_lineage_artifact_status"] == "request_invalid_fails_closed"
    assert packet["summary"]["structured_lineage_artifact_count"] == 0
    assert packet["summary"]["structured_oos_artifact_status"] == "request_invalid_fails_closed"
    assert packet["summary"]["structured_oos_artifact_count"] == 0
    assert packet["summary"]["trust_blocker_count"] == 0
    assert packet["protected_artifacts"][0]["exists"] is True
    assert packet["protected_artifacts"][1]["exists"] is True
    assert packet["evidence_inputs"]["trusted_loop_readiness"]["readiness_state"] == "operator_trusted"
    assert packet["evidence_inputs"]["structured_lineage_artifacts"]["summary"]["final_recommendation"] == "request_invalid_fails_closed"
    assert packet["evidence_inputs"]["structured_oos_artifacts"]["summary"]["final_recommendation"] == "request_invalid_fails_closed"
    assert packet["evidence_inputs"]["lineage_graph"]["summary"]["candidate_count"] == 2
    assert packet["evidence_inputs"]["reason_record_normalization"]["summary"]["normalized_record_count"] == 7


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
    monkeypatch.setattr(
        packet_module.artifact_continuity,
        "build_read_only_artifact_continuity",
        lambda **_: {
            "summary": {
                "artifact_continuity_ready": False,
                "exact_next_action": "materialize_read_only_qre_artifacts",
            }
        },
    )
    monkeypatch.setattr(
        packet_module.contradiction_staleness,
        "build_contradiction_staleness_intelligence",
        lambda **_: {
            "summary": {
                "contradiction_staleness_ready": False,
                "contradiction_count": 2,
                "stale_or_superseded_count": 1,
                "exact_next_action": "reconcile_stale_or_superseded_artifacts",
            }
        },
    )
    monkeypatch.setattr(
        packet_module.throughput_bottlenecks,
        "build_campaign_throughput_bottleneck_intelligence",
        lambda **_: {
            "summary": {
                "campaign_throughput_bottleneck_intelligence_ready": False,
                "bottleneck_count": 2,
                "exact_next_action": "reconcile_campaign_queue_from_registry",
            }
        },
    )
    monkeypatch.setattr(
        packet_module.novelty_enforcement,
        "build_experiment_dedup_novelty_enforcement",
        lambda **_: {
            "summary": {
                "experiment_dedup_novelty_enforcement_ready": False,
                "duplicate_pressure_count": 2,
                "exact_next_action": "deduplicate_active_campaign_scope",
            }
        },
    )
    monkeypatch.setattr(
        packet_module.sequential_retrieval,
        "build_research_state_sequential_retrieval",
        lambda **_: {
            "summary": {
                "research_state_sequential_retrieval_ready": False,
                "visible_sequence_row_count": 0,
                "exact_next_action": "restore_current_run_artifacts",
            }
        },
    )
    monkeypatch.setattr(
        packet_module.remediation_planning,
        "build_incomplete_artifact_remediation_planning",
        lambda **_: {
            "summary": {
                "remediation_planning_ready": False,
                "remediation_count": 5,
                "exact_next_action": "restore_inputs",
            }
        },
    )
    monkeypatch.setattr(
        packet_module.operational_controls,
        "build_trusted_loop_operational_controls",
        lambda **_: {
            "summary": {
                "trusted_loop_operational_controls_ready": False,
                "exact_next_safe_action": "resume_from_existing_run_history",
            }
        },
    )
    monkeypatch.setattr(
        packet_module.shadow_readiness_gates,
        "build_shadow_readiness_gates",
        lambda **_: {
            "summary": {
                "readiness_status": "shadow_readiness_deferred",
                "exact_next_action": "satisfy_candidate_quality_prerequisites",
            }
        },
    )
    monkeypatch.setattr(
        packet_module.basket_action_plan,
        "build_basket_operator_action_plan",
        lambda **_: {
            "summary": {
                "final_recommendation": "basket_operator_action_plan_ready",
                "first_batch_candidate_symbols": [],
                "generation_command_discovery_result": "qre_bounded_aapl_nvda_current_basket_generation_discovery",
                "generation_command_discovery_safe_command_found": False,
                "generation_command_discovery_final_recommendation": "NO_SAFE_BOUNDED_GENERATION_COMMAND_FOUND",
            }
        },
    )
    monkeypatch.setattr(
        packet_module.first_batch_readiness,
        "build_first_batch_evidence_recovery_readiness",
        lambda **_: {"report_kind": "qre_first_batch_evidence_recovery_readiness"},
    )
    monkeypatch.setattr(
        packet_module.first_batch_cascade,
        "build_first_batch_evidence_recovery_cascade",
        lambda **_: {
            "report_kind": "qre_first_batch_evidence_recovery_cascade",
            "overall_result": "PRESET_TIMEFRAME_ALIAS_BLOCKED",
            "first_batch_summary": {"current_top_blocker": "preset_timeframe_alias_unproven"},
        },
    )
    monkeypatch.setattr(
        packet_module,
        "_guarded_alias_bounded_generation_snapshot",
        lambda *_: {
            "report_kind": "qre_guarded_alias_bounded_generation_cascade",
            "overall_result": "ALIAS_POLICY_CONTEXT_ONLY_BOUNDED_GENERATION_READY",
            "summary": {"current_top_blocker": "operator_approval_required_for_bounded_generation"},
        },
    )

    packet = packet_module.build_trusted_loop_review_packet(repo_root=tmp_path)

    assert packet["summary"]["trusted_loop_review_ready"] is False
    assert packet["summary"]["trust_level"] == "1"
    assert packet["summary"]["trust_verdict"] == "read_only_context_fail_closed"
    assert packet["summary"]["exact_next_action"] == "restore_trusted_loop_readiness_evidence"
    assert "readiness_state:working_capability" in packet["summary"]["trust_blockers"]
    assert "reason_records_missing" in packet["summary"]["trust_blockers"]
    assert "operational_controls_not_ready" in packet["summary"]["trust_blockers"]
    assert packet["summary"]["final_recommendation"] == "trusted_loop_operator_review_required"
    assert packet["summary"]["structured_lineage_artifact_status"] == "request_invalid_fails_closed"
    assert packet["summary"]["structured_oos_artifact_status"] == "request_invalid_fails_closed"


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
    monkeypatch.setattr(
        packet_module.artifact_continuity,
        "build_read_only_artifact_continuity",
        lambda **_: {
            "summary": {
                "artifact_continuity_ready": True,
                "exact_next_action": "preserve_current_read_only_artifacts",
            }
        },
    )
    monkeypatch.setattr(
        packet_module.contradiction_staleness,
        "build_contradiction_staleness_intelligence",
        lambda **_: {
            "summary": {
                "contradiction_staleness_ready": True,
                "contradiction_count": 0,
                "stale_or_superseded_count": 0,
                "exact_next_action": "preserve_contradiction_and_staleness_visibility",
            }
        },
    )
    monkeypatch.setattr(
        packet_module.throughput_bottlenecks,
        "build_campaign_throughput_bottleneck_intelligence",
        lambda **_: {
            "summary": {
                "campaign_throughput_bottleneck_intelligence_ready": True,
                "bottleneck_count": 0,
                "exact_next_action": "preserve_campaign_throughput_context",
            }
        },
    )
    monkeypatch.setattr(
        packet_module.novelty_enforcement,
        "build_experiment_dedup_novelty_enforcement",
        lambda **_: {
            "summary": {
                "experiment_dedup_novelty_enforcement_ready": True,
                "duplicate_pressure_count": 0,
                "exact_next_action": "route_only_to_eligible_novel_directions",
            }
        },
    )
    monkeypatch.setattr(
        packet_module.sequential_retrieval,
        "build_research_state_sequential_retrieval",
        lambda **_: {
            "summary": {
                "research_state_sequential_retrieval_ready": True,
                "visible_sequence_row_count": 4,
                "exact_next_action": "preserve_research_state_sequence_visibility",
            }
        },
    )
    monkeypatch.setattr(
        packet_module.remediation_planning,
        "build_incomplete_artifact_remediation_planning",
        lambda **_: {
            "summary": {
                "remediation_planning_ready": True,
                "remediation_count": 2,
                "exact_next_action": "preserve_current_read_only_artifact_visibility",
            }
        },
    )
    monkeypatch.setattr(
        packet_module.operational_controls,
        "build_trusted_loop_operational_controls",
        lambda **_: snapshots["operational_controls"],
    )
    monkeypatch.setattr(
        packet_module.shadow_readiness_gates,
        "build_shadow_readiness_gates",
        lambda **_: snapshots["shadow_readiness"],
    )
    monkeypatch.setattr(
        packet_module.basket_action_plan,
        "build_basket_operator_action_plan",
        lambda **_: {
            "summary": {
                "final_recommendation": "basket_operator_action_plan_ready",
                "first_batch_candidate_symbols": ["AAPL"],
                "generation_command_discovery_result": "qre_bounded_aapl_nvda_current_basket_generation_discovery",
                "generation_command_discovery_safe_command_found": False,
                "generation_command_discovery_final_recommendation": "NO_SAFE_BOUNDED_GENERATION_COMMAND_FOUND",
            }
        },
    )
    monkeypatch.setattr(
        packet_module.first_batch_readiness,
        "build_first_batch_evidence_recovery_readiness",
        lambda **_: {"report_kind": "qre_first_batch_evidence_recovery_readiness"},
    )
    monkeypatch.setattr(
        packet_module.first_batch_cascade,
        "build_first_batch_evidence_recovery_cascade",
        lambda **_: {
            "report_kind": "qre_first_batch_evidence_recovery_cascade",
            "overall_result": "PRESET_TIMEFRAME_ALIAS_BLOCKED",
            "first_batch_summary": {"current_top_blocker": "preset_timeframe_alias_unproven"},
        },
    )
    monkeypatch.setattr(
        packet_module,
        "_guarded_alias_bounded_generation_snapshot",
        lambda *_: {
            "report_kind": "qre_guarded_alias_bounded_generation_cascade",
            "overall_result": "ALIAS_POLICY_CONTEXT_ONLY_BOUNDED_GENERATION_READY",
            "summary": {"current_top_blocker": "operator_approval_required_for_bounded_generation"},
        },
    )

    packet = packet_module.build_trusted_loop_review_packet(repo_root=tmp_path)
    text = packet_module.render_operator_summary(packet)

    assert "# QRE Trusted Loop Review Packet" in text
    assert "trust_level: 3" in text
    assert "maintain_operator_trusted_read_only_mode" in text
    assert "structured_lineage_artifact_status:" in text
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
    monkeypatch.setattr(
        packet_module.artifact_continuity,
        "build_read_only_artifact_continuity",
        lambda **_: {
            "summary": {
                "artifact_continuity_ready": True,
                "exact_next_action": "preserve_current_read_only_artifacts",
            }
        },
    )
    monkeypatch.setattr(
        packet_module.contradiction_staleness,
        "build_contradiction_staleness_intelligence",
        lambda **_: {
            "summary": {
                "contradiction_staleness_ready": True,
                "contradiction_count": 0,
                "stale_or_superseded_count": 0,
                "exact_next_action": "preserve_contradiction_and_staleness_visibility",
            }
        },
    )
    monkeypatch.setattr(
        packet_module.throughput_bottlenecks,
        "build_campaign_throughput_bottleneck_intelligence",
        lambda **_: {
            "summary": {
                "campaign_throughput_bottleneck_intelligence_ready": True,
                "bottleneck_count": 0,
                "exact_next_action": "preserve_campaign_throughput_context",
            }
        },
    )
    monkeypatch.setattr(
        packet_module.novelty_enforcement,
        "build_experiment_dedup_novelty_enforcement",
        lambda **_: {
            "summary": {
                "experiment_dedup_novelty_enforcement_ready": True,
                "duplicate_pressure_count": 0,
                "exact_next_action": "route_only_to_eligible_novel_directions",
            }
        },
    )
    monkeypatch.setattr(
        packet_module.sequential_retrieval,
        "build_research_state_sequential_retrieval",
        lambda **_: {
            "summary": {
                "research_state_sequential_retrieval_ready": True,
                "visible_sequence_row_count": 4,
                "exact_next_action": "preserve_research_state_sequence_visibility",
            }
        },
    )
    monkeypatch.setattr(
        packet_module.remediation_planning,
        "build_incomplete_artifact_remediation_planning",
        lambda **_: {
            "summary": {
                "remediation_planning_ready": True,
                "remediation_count": 2,
                "exact_next_action": "preserve_current_read_only_artifact_visibility",
            }
        },
    )
    monkeypatch.setattr(
        packet_module.operational_controls,
        "build_trusted_loop_operational_controls",
        lambda **_: snapshots["operational_controls"],
    )
    monkeypatch.setattr(
        packet_module.shadow_readiness_gates,
        "build_shadow_readiness_gates",
        lambda **_: snapshots["shadow_readiness"],
    )
    monkeypatch.setattr(
        packet_module.first_batch_readiness,
        "build_first_batch_evidence_recovery_readiness",
        lambda **_: {"report_kind": "qre_first_batch_evidence_recovery_readiness"},
    )
    monkeypatch.setattr(
        packet_module.first_batch_cascade,
        "build_first_batch_evidence_recovery_cascade",
        lambda **_: {
            "report_kind": "qre_first_batch_evidence_recovery_cascade",
            "overall_result": "PRESET_TIMEFRAME_ALIAS_BLOCKED",
            "first_batch_summary": {"current_top_blocker": "preset_timeframe_alias_unproven"},
        },
    )
    monkeypatch.setattr(
        packet_module,
        "_guarded_alias_bounded_generation_snapshot",
        lambda *_: {
            "report_kind": "qre_guarded_alias_bounded_generation_cascade",
            "overall_result": "ALIAS_POLICY_CONTEXT_ONLY_BOUNDED_GENERATION_READY",
            "summary": {"current_top_blocker": "operator_approval_required_for_bounded_generation"},
        },
    )

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
    monkeypatch.setattr(
        packet_module,
        "_guarded_alias_bounded_generation_snapshot",
        lambda *_: {
            "report_kind": "qre_guarded_alias_bounded_generation_cascade",
            "overall_result": "ALIAS_POLICY_CONTEXT_ONLY_BOUNDED_GENERATION_READY",
            "summary": {"current_top_blocker": "operator_approval_required_for_bounded_generation"},
        },
    )
    monkeypatch.setattr(packet_module, "DEFAULT_OUTPUT_DIR", Path("bad"))
    packet = packet_module.build_trusted_loop_review_packet(repo_root=tmp_path)

    with pytest.raises(ValueError):
        packet_module.write_outputs(packet, repo_root=tmp_path)
