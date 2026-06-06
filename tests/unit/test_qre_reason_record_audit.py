from __future__ import annotations

import json
from pathlib import Path

from research import qre_reason_record_audit as audit


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _seed_common_repo(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "logs" / "qre_data_cache_manifest" / "latest.json",
        {"coverage": [{"instrument": "AAPL", "timeframe": "1d", "ready": True}]},
    )
    _write_json(
        tmp_path / "logs" / "qre_data_source_quality_readiness" / "latest.json",
        {
            "rows": [
                {
                    "instrument": "AAPL",
                    "timeframe": "1d",
                    "quality_status": "ready",
                    "operator_explanation": "AAPL ready",
                    "path": "data/cache/market/yfinance__AAPL__1d.parquet",
                }
            ]
        },
    )
    _write_json(
        tmp_path / "research" / "screening_evidence_latest.v1.json",
        {
            "candidates": [
                {
                    "asset": "AAPL",
                    "hypothesis_id": "trend_pullback_behavior_v1",
                    "stage_result": "screening_pass",
                    "validation_evidence": {
                        "status": "sufficient_oos_evidence",
                        "oos_trade_count": 12,
                    },
                }
            ]
        },
    )
    _write_json(
        tmp_path / "research" / "campaign_registry_latest.v1.json",
        {
            "campaigns": {
                "cmp-1": {
                    "preset_name": "trend_pullback_continuation_daily_v1",
                    "hypothesis_id": "trend_pullback_behavior_v1",
                    "state": "completed",
                }
            }
        },
    )
    _write_json(
        tmp_path / "research" / "candidate_registry_latest.v1.json",
        {"candidates": [{"asset": "AAPL", "status": "candidate"}]},
    )
    _write_json(
        tmp_path / "logs" / "failure_action_mapping_minimal" / "latest.json",
        {
            "items": [
                {
                    "subject_id": "screening:no_oos",
                    "reason_record": {
                        "reason_codes": ["taxonomy_match"],
                        "reason_text": "Collect more evidence.",
                        "evidence_refs": ["failure_input.subject_id"],
                    },
                }
            ]
        },
    )
    _write_json(
        tmp_path / "logs" / "reason_records" / "manifest.v1.json",
        {
            "total_records": 0,
        },
    )
    _write_json(
        tmp_path / "research" / "paper_readiness_latest.v1.json",
        {
            "entries": [
                {
                    "candidate_id": "cand-1",
                    "blocking_reasons": ["missing_execution_events"],
                    "warnings": ["negative_paper_sharpe"],
                    "evidence": {
                        "source_artifacts": [
                            "research/paper_ledger_latest.v1.json",
                            "research/paper_divergence_latest.v1.json",
                        ]
                    },
                }
            ]
        },
    )


def test_build_reason_record_audit_flags_missing_basket_reason_refs(tmp_path: Path) -> None:
    _seed_common_repo(tmp_path)

    report = audit.build_reason_record_audit(repo_root=tmp_path, max_candidates=2)

    rows = {row["producer_id"]: row for row in report["producer_rows"]}
    basket = rows["real_basket_diagnosis"]
    assert basket["expected_subject_count"] == 2
    assert basket["subjects_with_reason_codes"] >= 1
    assert basket["subjects_with_evidence_refs"] == 0
    assert basket["status"] == "coverage_missing"
    assert basket["missing_ref_classes"]["evidence_refs_missing"] == 2


def test_build_reason_record_audit_counts_failure_action_and_source_quality_refs(
    tmp_path: Path,
) -> None:
    _seed_common_repo(tmp_path)

    report = audit.build_reason_record_audit(repo_root=tmp_path, max_candidates=1)
    rows = {row["producer_id"]: row for row in report["producer_rows"]}

    source_quality = rows["source_quality_readiness"]
    assert source_quality["subjects_with_evidence_refs"] == 1
    assert source_quality["subjects_with_reason_text"] == 1
    assert source_quality["status"] == "coverage_complete"

    failure_action = rows["failure_action_mapping"]
    assert failure_action["subjects_with_reason_codes"] == 1
    assert failure_action["subjects_with_reason_text"] == 1
    assert failure_action["subjects_with_evidence_refs"] == 1
    assert failure_action["status"] == "coverage_complete"


def test_build_reason_record_audit_surfaces_empty_manifest_and_partial_paper_blockers(
    tmp_path: Path,
) -> None:
    _seed_common_repo(tmp_path)

    report = audit.build_reason_record_audit(repo_root=tmp_path, max_candidates=1)

    assert report["summary"]["reason_records_manifest_total"] == 0
    assert report["summary"]["final_recommendation"] == "reason_record_audit_no_records_present"
    rows = {row["producer_id"]: row for row in report["producer_rows"]}
    paper = rows["paper_readiness_blockers"]
    assert paper["subjects_with_reason_codes"] == 1
    assert paper["subjects_with_evidence_refs"] == 1
    assert paper["subjects_with_reason_text"] == 1


def test_render_operator_summary_and_write_outputs(tmp_path: Path) -> None:
    _seed_common_repo(tmp_path)

    report = audit.build_reason_record_audit(repo_root=tmp_path, max_candidates=1)
    markdown = audit.render_operator_summary(report)
    paths = audit.write_outputs(report, repo_root=tmp_path)

    assert "# QRE Reason Record Audit" in markdown
    assert "## 3. Producer audit" in markdown
    assert paths["latest"] == "logs/qre_reason_record_audit/latest.json"
    assert paths["operator_summary"] == "logs/qre_reason_record_audit/operator_summary.md"
