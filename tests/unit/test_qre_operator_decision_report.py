from __future__ import annotations

import json
from pathlib import Path

import pytest

from reporting import qre_operator_decision_report as report


def _write(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def _base_registry_row(*, thesis_id: str, source_hypothesis_id: str, status: str) -> dict:
    return {
        "thesis_id": thesis_id,
        "source_hypothesis_id": source_hypothesis_id,
        "title": f"Title {source_hypothesis_id}",
        "mechanism": f"Mechanism for {source_hypothesis_id}",
        "status": status,
        "screening_plan": ["screening-step"],
        "validation_plan": ["validation-step"],
        "oos_plan": ["oos-step"],
        "null_controls": ["null-control-step"],
        "minimum_sample": "sample-step",
        "falsification_plan": ["falsification-step"],
        "source_requirements": ["lineage_evidence"],
        "provenance_refs": [f"registry:{source_hypothesis_id}"],
    }


def test_blocked_decision_when_lineage_identity_chain_is_missing() -> None:
    out = report.build_operator_decision_report(
        registry_report={
            "rows": [
                _base_registry_row(
                    thesis_id="qbt_blocked",
                    source_hypothesis_id="blocked_hypothesis",
                    status="draft",
                )
            ]
        },
        evidence_report={
            "rows": [
                {
                    "thesis_id": "qbt_blocked",
                    "summary_status": "support_contradiction_and_unresolved_visible",
                    "supporting_evidence_count": 1,
                    "contradicting_evidence_count": 0,
                    "unresolved_evidence_count": 2,
                    "provenance_refs": ["evidence:blocked"],
                }
            ]
        },
        lineage_report={
            "rows": [
                {
                    "thesis_id": "qbt_blocked",
                    "source_hypothesis_id": "blocked_hypothesis",
                    "lineage_complete": False,
                    "missing_lineage_fields": [
                        "campaign_identity",
                        "source_identity",
                        "data_snapshot_identity",
                    ],
                    "orphan_status": {"is_orphan": True, "reason": "missing_campaign"},
                    "graph_nodes": {
                        "next_action": "establish_campaign_lineage_for_thesis",
                        "policy_decision": "blocked_missing_campaign_lineage",
                    },
                    "contradicting_evidence_refs": [],
                    "unresolved_evidence_refs": ["state:oos_plan:blocked"],
                    "provenance_refs": ["lineage:blocked"],
                }
            ]
        },
        decay_report={
            "rows": [
                {
                    "thesis_id": "qbt_blocked",
                    "decay_blocks_readiness": True,
                    "blocking_reasons": [
                        "missing_source_identity",
                        "missing_data_snapshot_identity",
                        "missing_campaign_identity",
                        "lineage_incomplete",
                    ],
                    "dimension_statuses": {
                        "source_freshness": "missing_source_identity",
                        "source_authority_loss": "authority_unverifiable_missing_source_identity",
                        "data_age": "missing_data_snapshot_identity",
                        "reproducibility": "reproducibility_unverifiable_without_campaign",
                        "contradiction_state": "no_visible_contradiction_or_unresolved_evidence",
                        "missing_oos_renewal": "missing_oos_plan_or_renewal",
                    },
                    "stale_artifact_refs": [],
                }
            ]
        },
    )

    row = out["rows"][0]
    assert row["final_decision"] == "BLOCKED"
    assert row["next_action"] == "establish_campaign_lineage_for_thesis"
    assert len(row["primary_reasons"]) <= 5
    assert row["lineage_completeness"]["lineage_complete"] is False
    assert row["evidence_based_readiness"] == "not_ready_for_review"


def test_rejected_decision_when_closed_preregistered_campaign_fails_closed() -> None:
    out = report.build_operator_decision_report(
        registry_report={
            "rows": [
                _base_registry_row(
                    thesis_id="qbt_rejected",
                    source_hypothesis_id="trend_pullback_v1",
                    status="research_ready",
                )
            ]
        },
        evidence_report={
            "rows": [
                {
                    "thesis_id": "qbt_rejected",
                    "summary_status": "support_contradiction_and_unresolved_visible",
                    "supporting_evidence_count": 4,
                    "contradicting_evidence_count": 1,
                    "unresolved_evidence_count": 2,
                    "provenance_refs": ["evidence:rejected"],
                }
            ]
        },
        lineage_report={
            "rows": [
                {
                    "thesis_id": "qbt_rejected",
                    "source_hypothesis_id": "trend_pullback_v1",
                    "lineage_complete": True,
                    "missing_lineage_fields": [],
                    "orphan_status": {"is_orphan": False, "reason": "none"},
                    "graph_nodes": {
                        "next_action": "reconcile_stale_or_superseded_artifacts",
                        "policy_decision": "context_only_visible_no_execution_authority",
                        "campaign": ["campaign::one"],
                        "funnel_result": ["completed_no_survivor"],
                    },
                    "contradicting_evidence_refs": ["memory:contradiction"],
                    "unresolved_evidence_refs": ["state:missing_validation_result"],
                    "provenance_refs": ["lineage:rejected"],
                }
            ]
        },
        decay_report={
            "rows": [
                {
                    "thesis_id": "qbt_rejected",
                    "decay_blocks_readiness": True,
                    "blocking_reasons": [
                        "validation_result_missing",
                        "contradicting_evidence_visible",
                        "stale_or_superseded_artifacts_visible",
                        "campaign_closure:all_windows_no_oos_trades",
                    ],
                    "dimension_statuses": {
                        "source_freshness": "stale_or_superseded_visible",
                        "source_authority_loss": "authority_loss_or_staleness_visible",
                        "data_age": "age_unverifiable_no_snapshot_timestamp",
                        "reproducibility": "campaign_visible_but_validation_missing",
                        "contradiction_state": "contradicting_evidence_visible",
                        "missing_oos_renewal": "campaign_closure:all_windows_no_oos_trades",
                    },
                    "stale_artifact_refs": ["artifact:stale"],
                }
            ]
        },
        closure_report={
            "campaign_scope": {"hypothesis_id": "trend_pullback_v1", "campaign_id": "campaign-1"},
            "campaign_ref": "qmwv_ref",
            "campaign_outcome": "all_windows_non_positive_trade_count",
            "closure_status": "all_windows_no_oos_trades",
            "hypothesis_disposition": "fail_closed_rejected",
            "recommended_next_action": "reject_hypothesis",
            "rejection_reasons": [
                "non_positive_oos_trade_count",
                "accepted_oos_count_mismatch",
            ],
        },
        run_report={
            "campaign_scope": {"hypothesis_id": "trend_pullback_v1", "campaign_id": "campaign-1"},
            "campaign_id": "qmwv_ref",
            "accepted_lineage_count": 30,
            "accepted_oos_count": 0,
            "accepted_window_count": 0,
            "failed_window_count": 2,
            "positive_oos_trade_count_total": 0,
            "null_control_results": {
                "status": "controls_incomplete",
                "blockers": ["null_controls_incomplete"],
                "missing_control_ids": ["null_preregistered_holdout"],
                "recommended_next_action": "materialize_missing_preregistered_controls",
            },
        },
    )

    row = out["rows"][0]
    assert row["final_decision"] == "REJECTED"
    assert row["next_action"] == "reject_hypothesis"
    assert row["funnel_result"]["campaign_outcome"] == "all_windows_non_positive_trade_count"
    assert row["null_controls"]["status"] == "controls_incomplete"
    assert any("OOS trades" in item or "null controls" in item.lower() for item in row["primary_reasons"])


def test_supported_for_review_when_lineage_and_decay_are_clear() -> None:
    out = report.build_operator_decision_report(
        registry_report={
            "rows": [
                _base_registry_row(
                    thesis_id="qbt_supported",
                    source_hypothesis_id="supported_hypothesis",
                    status="research_ready",
                )
            ]
        },
        evidence_report={
            "rows": [
                {
                    "thesis_id": "qbt_supported",
                    "summary_status": "support_visible",
                    "supporting_evidence_count": 3,
                    "contradicting_evidence_count": 0,
                    "unresolved_evidence_count": 0,
                    "provenance_refs": ["evidence:supported"],
                }
            ]
        },
        lineage_report={
            "rows": [
                {
                    "thesis_id": "qbt_supported",
                    "source_hypothesis_id": "supported_hypothesis",
                    "lineage_complete": True,
                    "missing_lineage_fields": [],
                    "orphan_status": {"is_orphan": False, "reason": "none"},
                    "graph_nodes": {
                        "next_action": "prepare_operator_review",
                        "policy_decision": "context_only_visible_no_execution_authority",
                        "campaign": ["campaign::supported"],
                        "funnel_result": ["supported"],
                    },
                    "contradicting_evidence_refs": [],
                    "unresolved_evidence_refs": [],
                    "provenance_refs": ["lineage:supported"],
                }
            ]
        },
        decay_report={
            "rows": [
                {
                    "thesis_id": "qbt_supported",
                    "decay_blocks_readiness": False,
                    "blocking_reasons": [],
                    "dimension_statuses": {
                        "source_freshness": "fresh",
                        "source_authority_loss": "not_lost",
                        "data_age": "bounded",
                        "reproducibility": "validation_result_present",
                        "contradiction_state": "no_visible_contradiction_or_unresolved_evidence",
                        "missing_oos_renewal": "sufficient_oos_evidence",
                    },
                    "stale_artifact_refs": [],
                }
            ]
        },
    )

    row = out["rows"][0]
    assert row["final_decision"] == "SUPPORTED_FOR_REVIEW"
    assert row["evidence_based_readiness"] == "readiness_supported_for_review"
    assert row["next_action"] == "prepare_operator_review"


def test_write_outputs_writes_inside_allowlist(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    payload = report.build_operator_decision_report(registry_report={"rows": []})
    out = report.write_outputs(payload, repo_root=tmp_path)

    latest = tmp_path / "logs" / "qre_operator_decision_report" / "latest.json"
    latest_md = tmp_path / "logs" / "qre_operator_decision_report" / "latest.md"
    assert latest.exists()
    assert latest_md.exists()
    assert out["latest"] == "logs/qre_operator_decision_report/latest.json"
    with pytest.raises(ValueError):
        report._validate_write_target(tmp_path / "outside.json")


def test_cli_no_write_prints_json_without_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    rc = report.main([])
    parsed = json.loads(capsys.readouterr().out)

    assert rc == 0
    assert parsed["report_kind"] == report.REPORT_KIND
    assert (tmp_path / "logs" / "qre_operator_decision_report" / "latest.json").exists() is False


def test_source_has_no_runtime_mutation_tokens() -> None:
    src = Path(report.__file__).read_text(encoding="utf-8")
    forbidden = (
        "import subprocess",
        "from subprocess",
        "subprocess.",
        "os.system",
        ".post(",
        "approval_token",
        "campaign_queue.append",
        "registry.py",
        "agent/backtesting/strategies.py",
    )
    for token in forbidden:
        assert token not in src, token
