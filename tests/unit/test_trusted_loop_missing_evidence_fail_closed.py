from __future__ import annotations

import json
from pathlib import Path

from reporting import trusted_loop_missing_evidence_fail_closed as fail_closed

FROZEN = "2026-05-28T00:00:00Z"


def _missing_materialization_snapshot() -> dict:
    return {
        "reason_record_evidence_density": {
            "final_recommendation": "not_ready_no_reason_records",
            "metrics": {
                "record_count": 0,
                "records_with_evidence_refs": 0,
            },
        },
        "research_quality_kpi_readiness": {
            "kpi_ids": ["TTFPRC", "OOS_DSR"],
            "complete_value_count": 0,
            "fail_closed_count": 2,
            "values": {
                "TTFPRC": {"numeric_value_ready": False},
                "OOS_DSR": {"numeric_value_ready": False},
            },
        },
        "routing_sampling_readiness_density": {
            "values": {
                "routing_ready": {
                    "status": "fail_closed",
                    "ready": False,
                    "artifact_present": False,
                    "final_recommendation": "unknown",
                    "readiness_score": 0.0,
                    "missing_evidence": [
                        "latest_artifact_present",
                        "final_recommendation_ready",
                    ],
                },
                "sampling_ready": {
                    "status": "fail_closed",
                    "ready": False,
                    "artifact_present": False,
                    "final_recommendation": "unknown",
                    "readiness_score": 0.0,
                    "missing_evidence": [
                        "latest_artifact_present",
                        "final_recommendation_ready",
                    ],
                },
            },
        },
    }


def _missing_queue_snapshot() -> dict:
    return {
        "final_recommendation": "operator_review_required_queue_selection_ambiguous",
        "summary": {
            "eligible_ready_items": [],
            "next_eligible_ready_item": None,
            "missing_done_evidence_items": ["ADE-QRE-X"],
            "dependency_gap_items": ["ADE-QRE-Y"],
            "stale_historical_ready_items": [],
            "blocked_items_missing_reason": ["ADE-QRE-Z"],
            "deferred_items_missing_reason": [],
        },
    }


def test_missing_evidence_fails_closed_across_required_surfaces() -> None:
    snapshot = fail_closed.collect_snapshot(
        frozen_utc=FROZEN,
        materialization_snapshot=_missing_materialization_snapshot(),
        diagnostics_status={
            "status": "missing_research_diagnostics_loop",
            "diagnostics_loop_ready": False,
            "path": "logs/qre_research_diagnostics_loop/latest.json",
            "fails_closed": True,
        },
        retrieval_status={
            "status": "missing_retrieval_coverage",
            "retrieval_coverage_ready": False,
            "path": "logs/qre_research_retrieval_coverage/latest.json",
            "fails_closed": True,
        },
        queue_snapshot=_missing_queue_snapshot(),
    )
    rows = {row["surface_id"]: row for row in snapshot["surfaces"]}

    assert snapshot["final_recommendation"] == "not_ready_missing_evidence"
    assert snapshot["summary"]["trusted_loop_ready"] is False
    assert snapshot["summary"]["ready_surface_count"] == 0
    assert snapshot["summary"]["fail_closed_surface_count"] == 7
    assert set(rows) == set(snapshot["summary"]["required_surfaces"])
    assert rows["reason_records"]["fail_closed"] is True
    assert rows["research_quality_kpis"]["fail_closed"] is True
    assert rows["routing_readiness"]["fail_closed"] is True
    assert rows["sampling_readiness"]["fail_closed"] is True
    assert rows["diagnostics_loop"]["fail_closed"] is True
    assert rows["retrieval_coverage"]["fail_closed"] is True
    assert rows["queue_status"]["fail_closed"] is True
    assert "reason_records_present" in rows["reason_records"]["missing_evidence"]
    assert "TTFPRC" in rows["research_quality_kpis"]["missing_evidence"]
    assert "latest_artifact_present" in rows["routing_readiness"]["missing_evidence"]
    assert "diagnostics_loop_ready" in rows["diagnostics_loop"]["missing_evidence"]
    assert "retrieval_coverage_ready" in rows["retrieval_coverage"]["missing_evidence"]
    assert (
        "exactly_one_next_eligible_ready_item"
        in rows["queue_status"]["missing_evidence"]
    )
    assert snapshot["safety_invariants"]["strategy_synthesis_enabled"] is False
    assert snapshot["safety_invariants"]["addendum_runtime_activated"] is False


def test_queue_single_next_item_does_not_override_missing_done_evidence() -> None:
    queue = {
        "final_recommendation": "queue_status_audit_ready_with_warnings",
        "summary": {
            "eligible_ready_items": ["ADE-QRE-016C"],
            "next_eligible_ready_item": "ADE-QRE-016C",
            "missing_done_evidence_items": ["ADE-QRE-007"],
            "dependency_gap_items": [],
            "stale_historical_ready_items": ["ADE-QRE-011"],
            "blocked_items_missing_reason": [],
            "deferred_items_missing_reason": [],
        },
    }

    snapshot = fail_closed.collect_snapshot(
        frozen_utc=FROZEN,
        materialization_snapshot=_missing_materialization_snapshot(),
        diagnostics_status={"status": "ready", "diagnostics_loop_ready": True},
        retrieval_status={"status": "ready", "retrieval_coverage_ready": True},
        queue_snapshot=queue,
    )
    row = {row["surface_id"]: row for row in snapshot["surfaces"]}["queue_status"]

    assert row["status"] == "bounded_selection_ready_with_warnings"
    assert row["ready"] is False
    assert row["fail_closed"] is True
    assert row["evidence"]["bounded_current_selection_ready"] is True
    assert "complete_done_evidence_for_all_done_items" in row["missing_evidence"]
    assert row["notes"] == [
        "A single bounded next item can still be visible while broader "
        "queue-status trust fails closed."
    ]


def test_current_repo_snapshot_is_read_only_and_serializable() -> None:
    snapshot = fail_closed.collect_snapshot(frozen_utc=FROZEN)

    assert snapshot["report_kind"] == fail_closed.REPORT_KIND
    assert snapshot["mode"] == "dry-run"
    assert snapshot["safe_to_execute"] is False
    assert snapshot["safety_invariants"]["read_only"] is True
    assert snapshot["safety_invariants"]["writes_artifacts"] is False
    assert snapshot["safety_invariants"]["mutates_strategy_or_registry"] is False
    assert snapshot["safety_invariants"]["mutates_frozen_contracts"] is False
    assert snapshot["safety_invariants"]["strategy_synthesis_enabled"] is False
    assert json.loads(json.dumps(snapshot))["schema_version"] == (
        fail_closed.SCHEMA_VERSION
    )


def test_module_does_not_import_mutation_or_runtime_surfaces() -> None:
    source = Path(fail_closed.__file__).read_text(encoding="utf-8")

    forbidden_tokens = (
        "from dashboard",
        "import dashboard",
        "from registry",
        "import registry",
        "strategies.py",
        "approval mutation",
    )
    for token in forbidden_tokens:
        assert token not in source
