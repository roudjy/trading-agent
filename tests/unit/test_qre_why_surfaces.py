from __future__ import annotations

import json
from pathlib import Path

import pytest

from reporting import qre_why_surfaces as report


def test_blocked_surface_explains_missing_lineage_and_next_action() -> None:
    out = report.build_why_surfaces(
        operator_report={
            "rows": [
                {
                    "thesis_id": "qbt_blocked",
                    "source_hypothesis_id": "blocked_hypothesis",
                    "title": "Blocked Thesis",
                    "mechanism": "Visible mechanism",
                    "final_decision": "BLOCKED",
                    "next_action": "establish_campaign_lineage_for_thesis",
                    "primary_reasons": [
                        "Required lineage field is missing: campaign identity.",
                        "Required lineage field is missing: source identity.",
                    ],
                    "contradictions": {
                        "supporting_evidence_count": 2,
                        "unresolved_evidence_refs": ["state:oos_plan:blocked"],
                    },
                    "evidence_completeness": {"decay_blocks_readiness": True},
                    "funnel_result": {"status": "no_campaign_closure_visible", "campaign_ids": []},
                    "provenance_refs": ["logs/qre_operator_decision_report/latest.json"],
                }
            ]
        },
        lineage_report={
            "rows": [
                {
                    "thesis_id": "qbt_blocked",
                    "missing_lineage_fields": ["campaign_identity", "source_identity"],
                    "supporting_evidence_refs": ["registry:blocked_hypothesis"],
                    "graph_nodes": {"campaign": []},
                    "provenance_refs": ["logs/qre_contradiction_hypothesis_lineage/latest.json"],
                }
            ]
        },
        decay_report={
            "rows": [
                {
                    "thesis_id": "qbt_blocked",
                    "blocking_reasons": ["missing_campaign_identity", "missing_source_identity"],
                    "provenance_refs": ["logs/qre_evidence_decay/latest.json"],
                }
            ]
        },
    )

    row = out["rows"][0]
    assert row["why_explored"]["status"] == "evidence_linked"
    assert row["why_blocked"]["status"] == "blocked_explained"
    assert "missing lineage fields" in row["why_blocked"]["explanation"]
    assert row["why_no_candidate_emerged"]["status"] == "blocked_before_candidate_stage"
    assert row["why_next_action_selected"]["status"] == "next_action_evidence_linked"
    assert "missing_lineage:campaign_identity" in row["missing_evidence_states"]


def test_rejected_surface_explains_failure_and_candidate_outcome() -> None:
    out = report.build_why_surfaces(
        operator_report={
            "rows": [
                {
                    "thesis_id": "qbt_rejected",
                    "source_hypothesis_id": "trend_pullback_v1",
                    "title": "Rejected Thesis",
                    "mechanism": "Visible mechanism",
                    "final_decision": "REJECTED",
                    "next_action": "reject_hypothesis",
                    "primary_reasons": ["The preregistered campaign completed with no positive OOS trades."],
                    "contradictions": {
                        "supporting_evidence_count": 4,
                        "unresolved_evidence_refs": [],
                    },
                    "evidence_completeness": {"decay_blocks_readiness": True},
                    "funnel_result": {
                        "status": "all_windows_no_oos_trades",
                        "campaign_outcome": "all_windows_non_positive_trade_count",
                        "campaign_ids": ["campaign-1"],
                    },
                    "oos": {"closure_status": "all_windows_no_oos_trades", "accepted_oos_count": 0},
                    "null_controls": {"status": "controls_incomplete"},
                    "provenance_refs": ["logs/qre_operator_decision_report/latest.json"],
                }
            ]
        },
        lineage_report={
            "rows": [
                {
                    "thesis_id": "qbt_rejected",
                    "supporting_evidence_refs": ["registry:trend_pullback_v1"],
                    "graph_nodes": {"campaign": ["campaign-1"]},
                    "provenance_refs": ["logs/qre_contradiction_hypothesis_lineage/latest.json"],
                }
            ]
        },
        decay_report={
            "rows": [
                {
                    "thesis_id": "qbt_rejected",
                    "blocking_reasons": ["campaign_closure:all_windows_no_oos_trades"],
                    "provenance_refs": ["logs/qre_evidence_decay/latest.json"],
                }
            ]
        },
    )

    row = out["rows"][0]
    assert row["why_failed"]["status"] == "failure_explained"
    assert "accepted OOS count `0`" in row["why_failed"]["explanation"]
    assert row["why_no_candidate_emerged"]["status"] == "candidate_outcome_visible"
    assert row["why_blocked"]["status"] == "not_blocked"


def test_insufficient_evidence_surface_preserves_missing_states() -> None:
    out = report.build_why_surfaces(
        operator_report={
            "rows": [
                {
                    "thesis_id": "qbt_insufficient",
                    "source_hypothesis_id": "insufficient_hypothesis",
                    "title": "Insufficient Thesis",
                    "mechanism": "",
                    "final_decision": "INSUFFICIENT_EVIDENCE",
                    "next_action": "collect_missing_evidence",
                    "primary_reasons": ["Stale or superseded artifacts remain attached to the thesis."],
                    "contradictions": {
                        "supporting_evidence_count": 0,
                        "unresolved_evidence_refs": ["state:missing_validation_result"],
                    },
                    "evidence_completeness": {"decay_blocks_readiness": True},
                    "funnel_result": {"status": "campaign_visible_without_closure_status", "campaign_ids": ["campaign-2"]},
                    "provenance_refs": ["logs/qre_operator_decision_report/latest.json"],
                }
            ]
        },
        lineage_report={
            "rows": [
                {
                    "thesis_id": "qbt_insufficient",
                    "missing_lineage_fields": [],
                    "supporting_evidence_refs": [],
                    "graph_nodes": {"campaign": ["campaign-2"]},
                    "provenance_refs": ["logs/qre_contradiction_hypothesis_lineage/latest.json"],
                }
            ]
        },
        decay_report={
            "rows": [
                {
                    "thesis_id": "qbt_insufficient",
                    "blocking_reasons": [
                        "stale_or_superseded_artifacts_visible",
                        "validation_result_missing",
                    ],
                    "provenance_refs": ["logs/qre_evidence_decay/latest.json"],
                }
            ]
        },
    )

    row = out["rows"][0]
    assert row["why_explored"]["status"] == "record_present_without_supporting_evidence"
    assert row["why_evidence_insufficient"]["status"] == "insufficiency_explained"
    assert "validation_result_missing" in row["why_evidence_insufficient"]["missing_evidence"]
    assert row["why_failed"]["status"] == "not_rejected"
    assert row["why_no_candidate_emerged"]["status"] == "candidate_outcome_visible"


def test_write_outputs_refuses_outside_allowlist(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="outside allowlist"):
        report._validate_write_target(tmp_path / "outside" / "latest.json")
