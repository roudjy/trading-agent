from __future__ import annotations

import json
from pathlib import Path

from research.qre_candidate_quality_framework import (
    build_candidate_quality_framework,
    evaluate_candidate_quality,
    write_outputs,
)


def _reason_contract() -> dict[str, object]:
    return {
        "report_kind": "qre_reason_record_contract",
        "contract": {
            "accepted_record_validation": {
                "validation_status": "valid",
            }
        },
    }


def _source_authority_report(*, status: str = "normalized_context_ready") -> dict[str, object]:
    return {
        "report_kind": "qre_source_identity_authority_normalization",
        "rows": [
            {
                "scope_key": "basket-eligible",
                "authority_status": status,
                "authority_reasons": [] if status == "normalized_context_ready" else ["source_quality_not_research_ready"],
            },
            {
                "scope_key": "basket-1",
                "authority_status": status,
                "authority_reasons": [] if status == "normalized_context_ready" else ["source_quality_not_research_ready"],
            },
            {
                "scope_key": "basket-a",
                "authority_status": status,
                "authority_reasons": [] if status == "normalized_context_ready" else ["source_quality_not_research_ready"],
            },
        ],
    }


def test_quality_report_blocks_when_candidates_missing() -> None:
    report = evaluate_candidate_quality(
        candidate_report={"rows": []},
        breadth_report={"coverage_matrix": []},
        closure_report={},
        null_control_report=None,
        source_quality_status={"status": "missing", "research_ready": False},
        reason_record_contract=_reason_contract(),
        source_authority_report=None,
    )

    assert report["summary"]["status"] == "blocked_candidate_missing"
    assert report["summary"]["candidate_count"] == 0


def test_quality_report_blocks_incomplete_evidence() -> None:
    report = evaluate_candidate_quality(
        candidate_report={
            "rows": [
                {
                    "candidate_id": "qre_cand_1",
                    "candidate_version": "qre_v_1",
                    "status": "evidence_incomplete",
                    "source_scope_ref": "coverage_matrix::basket-1",
                    "scope_signature": "sig-1",
                    "accepted_lineage_count": 1,
                    "accepted_oos_count": 0,
                    "blockers": ["accepted_evidence_incomplete"],
                }
            ]
        },
        breadth_report={
            "coverage_matrix": [
                {
                    "dimension": "basket",
                    "scope_key": "basket-1",
                    "accepted_lineage_count": 1,
                    "accepted_oos_count": 0,
                    "reproducibility_status": "working_read_only",
                    "blocker_reasons": ["no_oos_evidence"],
                    "regime_count": 0,
                }
            ]
        },
        closure_report={"closure_status": "evidence_partial", "positive_oos_trade_count_total": 0},
        null_control_report=None,
        source_quality_status={"status": "ready", "research_ready": True},
        reason_record_contract=_reason_contract(),
        source_authority_report=_source_authority_report(),
    )

    row = report["rows"][0]
    assert row["quality_status"] == "blocked_evidence_incomplete"
    assert row["next_lifecycle_status"] == "evidence_incomplete"
    assert row["reason_record"]["contract_validation"]["validation_status"] == "valid"


def test_quality_report_can_become_operator_review_eligible() -> None:
    report = evaluate_candidate_quality(
        candidate_report={
            "rows": [
                {
                    "candidate_id": "qre_cand_eligible",
                    "candidate_version": "qre_v_eligible",
                    "status": "evidence_complete",
                    "source_scope_ref": "coverage_matrix::basket-eligible",
                    "scope_signature": "sig-eligible",
                    "accepted_lineage_count": 2,
                    "accepted_oos_count": 2,
                    "blockers": [],
                }
            ]
        },
        breadth_report={
            "coverage_matrix": [
                {
                    "dimension": "basket",
                    "scope_key": "basket-eligible",
                    "accepted_lineage_count": 2,
                    "accepted_oos_count": 2,
                    "reproducibility_status": "reproducible_authoritative",
                    "blocker_reasons": [],
                    "regime_count": 2,
                }
            ]
        },
        closure_report={"closure_status": "evidence_complete", "positive_oos_trade_count_total": 5},
        null_control_report={
            "report_kind": "qre_null_control_falsification_suite",
            "evaluation": {
                "status": "controls_passed_context_only",
                "control_result_rows": [
                    {
                        "control_id": "cost_free_vs_cost_adjusted",
                        "control_family": "cost_sensitivity",
                        "result_status": "passed",
                        "passed": True,
                    },
                    {
                        "control_id": "turnover_matched_null",
                        "control_family": "turnover_matched_null",
                        "result_status": "passed",
                        "passed": True,
                    },
                ],
            },
        },
        source_quality_status={"status": "ready", "research_ready": True},
        reason_record_contract=_reason_contract(),
        source_authority_report=_source_authority_report(),
    )

    row = report["rows"][0]
    assert row["quality_status"] == "eligible_for_operator_quality_review"
    assert row["next_lifecycle_status"] == "quality_review"
    assert report["summary"]["eligible_candidate_count"] == 1


def test_quality_report_blocks_scope_mismatch() -> None:
    report = evaluate_candidate_quality(
        candidate_report={
            "rows": [
                {
                    "candidate_id": "qre_cand_mismatch",
                    "candidate_version": "qre_v_mismatch",
                    "status": "evidence_complete",
                    "source_scope_ref": "coverage_matrix::basket-a",
                    "scope_signature": "sig-a",
                    "accepted_lineage_count": 1,
                    "accepted_oos_count": 1,
                    "blockers": [],
                }
            ]
        },
        breadth_report={
            "coverage_matrix": [
                {
                    "dimension": "basket",
                    "scope_key": "basket-a",
                    "accepted_lineage_count": 2,
                    "accepted_oos_count": 1,
                    "reproducibility_status": "reproducible_authoritative",
                    "blocker_reasons": [],
                    "regime_count": 1,
                }
            ]
        },
        closure_report={"closure_status": "evidence_complete", "positive_oos_trade_count_total": 2},
        null_control_report=None,
        source_quality_status={"status": "ready", "research_ready": True},
        reason_record_contract=_reason_contract(),
        source_authority_report=_source_authority_report(),
    )

    assert report["rows"][0]["quality_status"] == "blocked_scope_mismatch"


def test_build_candidate_quality_framework_materializes_missing_lifecycle(tmp_path: Path) -> None:
    logs = tmp_path / "logs"
    (logs / "qre_evidence_breadth_framework").mkdir(parents=True)
    (logs / "qre_hypothesis_disposition_memory").mkdir(parents=True)
    (logs / "qre_multiwindow_evidence_closure").mkdir(parents=True)
    (logs / "qre_reason_record_contract").mkdir(parents=True)

    (logs / "qre_evidence_breadth_framework" / "latest.json").write_text(
        json.dumps(
            {
                "report_kind": "qre_evidence_breadth_framework",
                "coverage_matrix": [
                    {
                        "dimension": "basket",
                        "scope_key": "basket-1",
                        "scope_label": "basket-1",
                        "hypothesis_id": "h1",
                        "behavior_id": "b1",
                        "timeframe": "1d",
                        "accepted_lineage_count": 1,
                        "accepted_oos_count": 0,
                        "reproducibility_status": "working_read_only",
                        "blocker_reasons": ["no_oos_evidence"],
                        "regime_count": 0,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (logs / "qre_hypothesis_disposition_memory" / "latest.json").write_text(
        json.dumps({"record": {}}),
        encoding="utf-8",
    )
    (logs / "qre_multiwindow_evidence_closure" / "latest.json").write_text(
        json.dumps(
            {
                "report_kind": "qre_multiwindow_evidence_closure",
                "closure_status": "all_windows_no_oos_trades",
                "positive_oos_trade_count_total": 0,
                "evidence_complete_count": 0,
            }
        ),
        encoding="utf-8",
    )
    (logs / "qre_reason_record_contract" / "latest.json").write_text(
        json.dumps(_reason_contract()),
        encoding="utf-8",
    )

    report = build_candidate_quality_framework(repo_root=tmp_path)

    assert report["summary"]["candidate_count"] == 1
    assert report["rows"][0]["quality_status"] == "blocked_evidence_incomplete"


def test_write_outputs_uses_allowlisted_location(tmp_path: Path) -> None:
    report = {
        "schema_version": "1.0",
        "report_kind": "qre_candidate_quality_framework",
        "summary": {"status": "blocked_candidate_missing"},
        "rows": [],
    }

    paths = write_outputs(report, repo_root=tmp_path)

    latest = tmp_path / paths["latest"]
    assert latest.is_file()
    assert "qre_candidate_quality_framework" in latest.as_posix()
