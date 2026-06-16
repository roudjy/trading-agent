from __future__ import annotations

import json
from pathlib import Path

from research import qre_evidence_complete_basket_closure as closure


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _seed_complete_repo(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "logs" / "qre_data_cache_manifest" / "latest.json",
        {"coverage": [{"instrument": "AAPL", "timeframe": "1d", "ready": True}]},
    )
    _write_json(
        tmp_path / "logs" / "qre_data_source_quality_readiness" / "latest.json",
        {"rows": [{"instrument": "AAPL", "timeframe": "1d", "quality_status": "ready"}]},
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


def test_closure_marks_complete_basket_without_blockers(monkeypatch) -> None:
    monkeypatch.setattr(
        closure.evidence_coverage,
        "build_real_basket_evidence_coverage",
        lambda **_: {
            "rows": [
                {
                    "candidate_id": "c1",
                    "symbol": "AAPL",
                    "preset_id": "trend_pullback_continuation_daily_v1",
                    "diagnosis_class": "diagnosable",
                    "evidence_completeness_score_pct": 100,
                    "evidence_completeness_status": "complete",
                    "missing_evidence_taxonomy": [],
                    "follow_up": "eligible_for_readonly_routing",
                    "evidence_presence": {
                        "source_identity_ready": True,
                        "source_quality_ready": True,
                        "cache_ready": True,
                        "screening_evidence_present": True,
                        "oos_evidence_known": True,
                        "campaign_lineage_present": True,
                        "candidate_lineage_present": True,
                    },
                }
            ]
        },
    )
    monkeypatch.setattr(
        closure.reason_records,
        "build_reason_records_snapshot",
        lambda **_: {
            "records": [
                {
                    "subject_id": "c1",
                    "record_ids": ["qrr_c1_reason_1"],
                    "record_families": ["basket_diagnosis"],
                    "reason_codes": ["screening_evidence_present"],
                    "evidence_refs": ["research/production_discovery_catalog.py"],
                }
            ]
        },
    )
    monkeypatch.setattr(
        closure.failure_action,
        "build_failure_action_from_basket",
        lambda **_: {
            "rows": [
                {
                    "candidate_id": "c1",
                    "recommended_action": "eligible_for_readonly_routing",
                    "actionability": {"is_actionable": True, "status": "actionable"},
                }
            ]
        },
    )

    report = closure.build_evidence_complete_basket_closure()
    row = report["rows"][0]
    assert row["closure_status"] == "evidence_complete"
    assert row["exact_blockers"] == []
    assert row["reason_record_count"] == 1
    assert row["closure_criteria"]["reason_records_present"] is True
    assert report["summary"]["evidence_complete_count"] == 1
    assert report["summary"]["all_complete_baskets_have_reason_records"] is True
    assert report["summary"]["final_recommendation"] == "evidence_complete_reason_records_ready"


def test_closure_requires_exact_blockers_without_unknowns(monkeypatch) -> None:
    monkeypatch.setattr(
        closure.evidence_coverage,
        "build_real_basket_evidence_coverage",
        lambda **_: {
            "rows": [
                {
                    "candidate_id": "c2",
                    "symbol": "ASML",
                    "preset_id": "trend_continuation_daily_v1",
                    "diagnosis_class": "diagnosable",
                    "evidence_completeness_score_pct": 57,
                    "evidence_completeness_status": "partial",
                    "missing_evidence_taxonomy": [
                        "screening_evidence_missing",
                        "oos_evidence_missing",
                        "campaign_lineage_missing",
                    ],
                    "follow_up": "collect_more_evidence",
                    "evidence_presence": {
                        "source_identity_ready": True,
                        "source_quality_ready": True,
                        "cache_ready": True,
                        "screening_evidence_present": False,
                        "oos_evidence_known": False,
                        "campaign_lineage_present": False,
                        "candidate_lineage_present": True,
                    },
                }
            ]
        },
    )
    monkeypatch.setattr(
        closure.reason_records,
        "build_reason_records_snapshot",
        lambda **_: {
            "records": [
                {
                    "subject_id": "c2",
                    "record_ids": ["qrr_c2_reason_1"],
                    "record_families": ["basket_diagnosis"],
                    "reason_codes": ["screening_evidence_missing"],
                    "evidence_refs": ["research/production_discovery_catalog.py"],
                }
            ]
        },
    )
    monkeypatch.setattr(
        closure.failure_action,
        "build_failure_action_from_basket",
        lambda **_: {
            "rows": [
                {
                    "candidate_id": "c2",
                    "recommended_action": "restore_or_run_grid_artifacts",
                    "actionability": {"is_actionable": True, "status": "actionable"},
                }
            ]
        },
    )

    report = closure.build_evidence_complete_basket_closure()
    row = report["rows"][0]
    assert row["closure_status"] == "blocked_not_evidence_complete"
    assert row["exact_next_action"] == "restore_or_run_grid_artifacts"
    assert row["unknown_blocker_count"] == 0
    assert report["summary"]["all_non_complete_baskets_have_exact_blockers"] is True
    assert report["summary"]["all_non_complete_baskets_have_no_unknown_blockers"] is True
    assert report["summary"]["final_recommendation"] == "no_basket_evidence_complete_reason_records_preserved"


def test_closure_treats_explicit_oos_gap_states_as_known_blockers(monkeypatch) -> None:
    monkeypatch.setattr(
        closure.evidence_coverage,
        "build_real_basket_evidence_coverage",
        lambda **_: {
            "rows": [
                {
                    "candidate_id": "c4",
                    "symbol": "NVDA",
                    "preset_id": "trend_pullback_continuation_daily_v1",
                    "diagnosis_class": "diagnosable",
                    "evidence_completeness_score_pct": 42,
                    "evidence_completeness_status": "thin",
                    "missing_evidence_taxonomy": [
                        "oos_evidence_unknown",
                        "no_oos_evidence",
                        "oos_evidence_missing",
                    ],
                    "follow_up": "collect_more_evidence",
                    "evidence_presence": {
                        "source_identity_ready": True,
                        "source_quality_ready": True,
                        "cache_ready": True,
                        "screening_evidence_present": True,
                        "oos_evidence_known": False,
                        "campaign_lineage_present": False,
                        "candidate_lineage_present": False,
                    },
                }
            ]
        },
    )
    monkeypatch.setattr(
        closure.reason_records,
        "build_reason_records_snapshot",
        lambda **_: {
            "records": [
                {
                    "subject_id": "c4",
                    "record_ids": ["qrr_c4_reason_1"],
                    "record_families": ["basket_diagnosis"],
                    "reason_codes": ["oos_evidence_unknown"],
                    "evidence_refs": ["research/screening_evidence_latest.v1.json"],
                }
            ]
        },
    )
    monkeypatch.setattr(
        closure.failure_action,
        "build_failure_action_from_basket",
        lambda **_: {
            "rows": [
                {
                    "candidate_id": "c4",
                    "recommended_action": "collect_oos_evidence",
                    "actionability": {"is_actionable": True, "status": "actionable"},
                }
            ]
        },
    )

    report = closure.build_evidence_complete_basket_closure()
    row = report["rows"][0]
    assert row["closure_status"] == "blocked_not_evidence_complete"
    assert "oos_evidence_unknown" in row["exact_blockers"]
    assert row["unknown_blocker_count"] == 0
    assert row["exact_next_action"] == "collect_oos_evidence"
    assert report["summary"]["unknown_blocker_count"] == 0
    assert report["summary"]["all_non_complete_baskets_have_no_unknown_blockers"] is True


def test_closure_fails_closed_when_reason_records_missing_for_complete_basket(monkeypatch) -> None:
    monkeypatch.setattr(
        closure.evidence_coverage,
        "build_real_basket_evidence_coverage",
        lambda **_: {
            "rows": [
                {
                    "candidate_id": "c3",
                    "symbol": "ADYEN",
                    "preset_id": "trend_continuation_daily_v1",
                    "diagnosis_class": "diagnosable",
                    "evidence_completeness_score_pct": 100,
                    "evidence_completeness_status": "complete",
                    "missing_evidence_taxonomy": [],
                    "follow_up": "eligible_for_readonly_routing",
                    "evidence_presence": {
                        "source_identity_ready": True,
                        "source_quality_ready": True,
                        "cache_ready": True,
                        "screening_evidence_present": True,
                        "oos_evidence_known": True,
                        "campaign_lineage_present": True,
                        "candidate_lineage_present": True,
                    },
                }
            ]
        },
    )
    monkeypatch.setattr(
        closure.reason_records,
        "build_reason_records_snapshot",
        lambda **_: {"records": []},
    )
    monkeypatch.setattr(
        closure.failure_action,
        "build_failure_action_from_basket",
        lambda **_: {
            "rows": [
                {
                    "candidate_id": "c3",
                    "recommended_action": "keep_blocked",
                    "actionability": {"is_actionable": False, "status": "non_actionable"},
                }
            ]
        },
    )

    report = closure.build_evidence_complete_basket_closure()
    row = report["rows"][0]
    assert row["closure_status"] == "blocked_not_evidence_complete"
    assert row["exact_next_action"] == "keep_blocked"
    assert row["closure_criteria"]["reason_records_present"] is False
    assert report["summary"]["all_input_complete_rows_have_reason_records"] is False


def test_closure_writes_outputs(tmp_path: Path, monkeypatch) -> None:
    _seed_complete_repo(tmp_path)
    report = closure.build_evidence_complete_basket_closure(repo_root=tmp_path)
    paths = closure.write_outputs(report, repo_root=tmp_path)
    markdown = (tmp_path / paths["operator_summary"]).read_text(encoding="utf-8")
    assert paths["latest"] == "logs/qre_evidence_complete_basket_closure/latest.json"
    assert "# QRE Evidence Complete Basket Closure" in markdown
