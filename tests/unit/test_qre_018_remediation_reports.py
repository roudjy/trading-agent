from __future__ import annotations

import json
from pathlib import Path

from reporting import qre_ade018_remediation_closeout as closeout
from reporting import qre_campaign_portfolio_reconstruction as portfolio
from reporting import qre_evidence_reason_record_completion as completion
from reporting import qre_rejected_thesis_replacement_plan as replacement
from reporting import qre_validation_repro_operator_completion as validation


def _write(path: Path, payload: dict | list) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def test_remediation_reports_are_deterministic_and_fail_closed(tmp_path: Path) -> None:
    registry = {
        "rows": [
            {
                "thesis_id": "qbt_rej",
                "source_hypothesis_id": "trend_pullback_v1",
                "behavior_family": "pullback_continuation",
                "mechanism": "pullback resumes trend",
                "status": "research_ready",
                "null_controls": ["shuffle_returns"],
                "provenance_refs": ["registry:rejected"],
            },
            {
                "thesis_id": "qbt_vol",
                "source_hypothesis_id": "volatility_compression_breakout_v0",
                "behavior_family": "volatility_compression_breakout",
                "mechanism": "compressed volatility expands",
                "status": "research_ready",
                "null_controls": ["shuffle_returns"],
                "provenance_refs": ["registry:vol"],
            },
        ]
    }
    evidence = {
        "rows": [
            {
                "thesis_id": "qbt_rej",
                "supporting_evidence_count": 3,
                "contradicting_evidence_count": 1,
                "unresolved_evidence_count": 1,
                "provenance_refs": ["evidence:rejected"],
            },
            {
                "thesis_id": "qbt_vol",
                "supporting_evidence_count": 1,
                "contradicting_evidence_count": 0,
                "unresolved_evidence_count": 1,
                "provenance_refs": ["evidence:vol"],
            },
        ]
    }
    operator = {
        "rows": [
            {
                "source_hypothesis_id": "trend_pullback_v1",
                "final_decision": "REJECTED",
                "primary_reasons": ["No positive OOS trades."],
                "next_action": "reject_hypothesis",
                "funnel_result": {"status": "all_windows_no_oos_trades", "campaign_outcome": "rejected"},
                "provenance_refs": ["operator:rejected"],
            },
            {
                "source_hypothesis_id": "volatility_compression_breakout_v0",
                "final_decision": "BLOCKED",
                "primary_reasons": ["Missing campaign lineage."],
                "next_action": "establish_campaign_lineage_for_thesis",
                "funnel_result": {"status": ""},
                "provenance_refs": ["operator:vol"],
            },
        ]
    }
    why = {"rows": [{"source_hypothesis_id": "trend_pullback_v1", "provenance_refs": ["why:rejected"]}]}
    lineage = {
        "rows": [
            {
                "thesis_id": "qbt_rej",
                "source_hypothesis_id": "trend_pullback_v1",
                "lineage_complete": True,
                "missing_lineage_fields": [],
                "provenance_refs": ["lineage:rejected"],
            },
            {
                "thesis_id": "qbt_vol",
                "source_hypothesis_id": "volatility_compression_breakout_v0",
                "lineage_complete": False,
                "missing_lineage_fields": ["campaign_identity"],
                "provenance_refs": ["lineage:vol"],
            },
        ]
    }
    decay = {
        "rows": [
            {
                "thesis_id": "qbt_rej",
                "decay_blocks_readiness": True,
                "blocking_reasons": ["stale_or_superseded_artifacts_visible", "contradicting_evidence_visible"],
                "dimension_statuses": {"source_freshness": "stale", "reproducibility": "campaign_visible_but_validation_missing"},
            },
            {
                "thesis_id": "qbt_vol",
                "decay_blocks_readiness": True,
                "blocking_reasons": ["missing_campaign_identity", "reproducibility_unverifiable"],
                "dimension_statuses": {"source_freshness": "missing", "reproducibility": "reproducibility_unverifiable_without_campaign"},
            },
        ]
    }
    reason_maturity = {"summary": {"record_count": 2}}
    reason_audit = {"summary": {"reason_records_manifest_total": 0, "missing_ref_class_counts": {"evidence_refs_missing": 2}}}
    independent = {
        "rows": [
            {
                "source_hypothesis_id": "trend_pullback_v1",
                "consumed_oos_windows": [{"window_sequence": 1}, {"window_sequence": 2}],
                "consumed_window_count": 2,
                "independent_oos_status": "BLOCKED_REJECTED_NO_ACCEPTED_OOS",
                "provenance_refs": ["independent:rejected"],
            }
        ]
    }
    catalog = {
        "hypotheses": [
            {"hypothesis_id": "trend_pullback_v1", "status": "active_discovery"},
            {"hypothesis_id": "volatility_compression_breakout_v0", "status": "active_discovery"},
        ]
    }
    old_portfolio = {
        "rows": [
            {
                "cell_id": "cell-rejected",
                "source_hypothesis_id": "trend_pullback_v1",
                "preset_name": "trend_pullback_equities_4h",
                "proposed_timeframe": "4h",
                "provenance_refs": ["portfolio:rejected"],
            },
            {
                "cell_id": "cell-vol",
                "source_hypothesis_id": "volatility_compression_breakout_v0",
                "preset_name": "vol_compression_breakout_crypto_4h",
                "proposed_timeframe": "4h",
                "provenance_refs": ["portfolio:vol"],
            },
        ]
    }

    _write(tmp_path / "logs/qre_behavior_thesis_registry/latest.json", registry)
    _write(tmp_path / "logs/qre_behavior_thesis_evidence/latest.json", evidence)
    _write(tmp_path / "logs/qre_operator_decision_report/latest.json", operator)
    _write(tmp_path / "logs/qre_why_surfaces/latest.json", why)
    _write(tmp_path / "logs/qre_contradiction_hypothesis_lineage/latest.json", lineage)
    _write(tmp_path / "logs/qre_evidence_decay/latest.json", decay)
    _write(tmp_path / "logs/qre_reason_record_maturity/latest.json", reason_maturity)
    _write(tmp_path / "logs/qre_reason_record_audit/latest.json", reason_audit)
    _write(tmp_path / "logs/qre_repeated_independent_oos/latest.json", independent)
    _write(tmp_path / "research/strategy_hypothesis_catalog_latest.v1.json", catalog)
    _write(tmp_path / "logs/qre_campaign_portfolio_plan/latest.json", old_portfolio)
    _write(tmp_path / "logs/qre_source_identity_authority_normalization/latest.json", {"rows": []})
    _write(tmp_path / "logs/qre_data_cache_manifest/latest.json", {"coverage": []})
    _write(tmp_path / "research/strategy_campaign_metadata_latest.v1.json", {"hypotheses": {"volatility_compression_breakout_v0": {"eligible_campaign_types": ["daily_primary"]}}})
    _write(tmp_path / "research/campaign_templates_latest.v1.json", {"templates": []})
    (tmp_path / "research").mkdir(parents=True, exist_ok=True)
    (tmp_path / "research/presets.py").write_text("", encoding="utf-8")
    _write(tmp_path / "logs/qre_synthesis_readiness_review/latest.json", {"summary": {"failed_mandatory_gates": ["reason_record_completeness", "identity_readiness", "null_control_completeness"]}, "synthesis_readiness_identity": "qrsr_test"})

    completion_snapshot = completion.collect_snapshot(repo_root=tmp_path)
    completion_rows = {row["source_hypothesis_id"]: row for row in completion_snapshot["rows"]}
    assert completion_rows["trend_pullback_v1"]["evidence_state"] == "PRESENT_STALE"
    assert completion_rows["volatility_compression_breakout_v0"]["evidence_state"] == "BLOCKED"

    validation_snapshot = validation.collect_snapshot(repo_root=tmp_path)
    validation_rows = {row["source_hypothesis_id"]: row for row in validation_snapshot["rows"]}
    assert validation_rows["trend_pullback_v1"]["validation_state"] == "CONTEXT_ONLY"
    assert validation_rows["volatility_compression_breakout_v0"]["operator_report_completeness_state"] == "BLOCKED"

    replacement_snapshot = replacement.collect_snapshot(repo_root=tmp_path)
    assert replacement_snapshot["archive"]["archive_state"] == "ARCHIVED_REJECTED"
    assert replacement_snapshot["replacement"]["replacement_hypothesis_id"] == "volatility_compression_breakout_v0"
    assert replacement_snapshot["replacement"]["proposal_state"] == "PROPOSAL_ONLY"

    portfolio_snapshot = portfolio.collect_snapshot(repo_root=tmp_path)
    statuses = {row["source_hypothesis_id"]: row["inclusion_status"] for row in portfolio_snapshot["rows"]}
    assert statuses["trend_pullback_v1"] == "EXCLUDED_REJECTED"
    assert statuses["volatility_compression_breakout_v0"] == "BLOCKED"
    assert portfolio_snapshot["preregistration_preparation"]["manifest_materialized"] is False

    closeout_snapshot = closeout.collect_snapshot(repo_root=tmp_path)
    assert closeout_snapshot["summary"]["final_outcome"] == "PARTIALLY_REMEDIATED"
    assert closeout_snapshot["summary"]["final_recommendation"] == "COMPLETE_REMAINING_LINEAGE_AND_CONTROL_GAPS"

    repeat = closeout.collect_snapshot(repo_root=tmp_path)
    assert repeat["remediation_closeout_identity"] == closeout_snapshot["remediation_closeout_identity"]
