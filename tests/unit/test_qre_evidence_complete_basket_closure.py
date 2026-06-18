from __future__ import annotations

import json
from pathlib import Path

from research import qre_evidence_complete_basket_closure as closure


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _accepted_verifier_report(*, candidate_id: str = "c1", preset_id: str = "trend_pullback_continuation_daily_v1", timeframe: str = "1d") -> dict:
    return {
        "report_kind": "qre_bounded_generation_artifact_acceptance_verifier",
        "summary": {
            "accepted_lineage_candidate_count": 1,
            "accepted_oos_candidate_count": 1,
        },
        "rows": [
            {
                "relative_path": "logs/qre_controlled_validation_adapter_results/latest.json",
                "classification": "accepted_for_campaign_lineage",
                "accepted_for_campaign_lineage": True,
                "accepted_for_oos_evidence": True,
                "accepted_lineage_count": 1,
                "accepted_oos_count": 1,
                "accepted_lineage_records": [
                    {
                        "request_ref": "req-001",
                        "candidate_id": candidate_id,
                        "campaign_id": "camp-001",
                        "generation_id": "gen-001",
                        "preset_id": preset_id,
                        "timeframe": timeframe,
                        "source_ref": "artifacts/qre_controlled_validation/source-001.json",
                        "reason_record_refs": ["rr-lineage-001"],
                        "verifier_ref": "logs/qre_bounded_generation_artifact_acceptance_verifier/latest.json#lineage",
                    }
                ],
                "accepted_oos_records": [
                    {
                        "request_ref": "req-001",
                        "candidate_id": candidate_id,
                        "preset_id": preset_id,
                        "timeframe": timeframe,
                        "source_ref": "artifacts/qre_controlled_validation/source-001.json",
                        "oos_window": {"start": "2025-01-01", "end": "2025-06-30"},
                        "oos_metric_fields": {"oos_trade_count": 12, "oos_return_pct": 2.1},
                        "cost_slippage_assumption_refs": ["cost-001"],
                        "reason_record_refs": ["rr-oos-001"],
                        "verifier_ref": "logs/qre_bounded_generation_artifact_acceptance_verifier/latest.json#oos",
                    }
                ],
            }
        ],
    }


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


def test_closure_marks_complete_basket_without_blockers(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        closure,
        "_guarded_alias_bounded_generation_snapshot",
        lambda *_: {"overall_result": "ALIAS_POLICY_CONTEXT_ONLY_BOUNDED_GENERATION_READY"},
    )
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

    report = closure.build_evidence_complete_basket_closure(repo_root=tmp_path)
    row = report["rows"][0]
    assert row["closure_status"] == "evidence_complete"
    assert row["exact_blockers"] == []
    assert row["reason_record_count"] == 1
    assert row["closure_criteria"]["reason_records_present"] is True
    assert report["summary"]["evidence_complete_count"] == 1
    assert report["summary"]["all_complete_baskets_have_reason_records"] is True
    assert report["summary"]["final_recommendation"] == "evidence_complete_reason_records_ready"
    assert report["summary"]["guarded_alias_bounded_generation_cascade_result"] == "ALIAS_POLICY_CONTEXT_ONLY_BOUNDED_GENERATION_READY"
    assert report["summary"]["structured_lineage_artifact_status"] == "request_invalid_fails_closed"
    assert report["summary"]["structured_lineage_artifact_count"] == 0
    assert report["summary"]["structured_oos_artifact_status"] == "request_invalid_fails_closed"
    assert report["summary"]["structured_oos_artifact_count"] == 0


def test_closure_requires_exact_blockers_without_unknowns(monkeypatch) -> None:
    monkeypatch.setattr(
        closure,
        "_guarded_alias_bounded_generation_snapshot",
        lambda *_: {"overall_result": "ALIAS_POLICY_CONTEXT_ONLY_BOUNDED_GENERATION_READY"},
    )
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
        closure,
        "_guarded_alias_bounded_generation_snapshot",
        lambda *_: {"overall_result": "ALIAS_POLICY_CONTEXT_ONLY_BOUNDED_GENERATION_READY"},
    )
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
        closure,
        "_guarded_alias_bounded_generation_snapshot",
        lambda *_: {"overall_result": "ALIAS_POLICY_CONTEXT_ONLY_BOUNDED_GENERATION_READY"},
    )
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
    monkeypatch.setattr(
        closure,
        "_guarded_alias_bounded_generation_snapshot",
        lambda *_: {"overall_result": "ALIAS_POLICY_CONTEXT_ONLY_BOUNDED_GENERATION_READY"},
    )
    report = closure.build_evidence_complete_basket_closure(repo_root=tmp_path)
    paths = closure.write_outputs(report, repo_root=tmp_path)
    markdown = (tmp_path / paths["operator_summary"]).read_text(encoding="utf-8")
    assert paths["latest"] == "logs/qre_evidence_complete_basket_closure/latest.json"
    assert "# QRE Evidence Complete Basket Closure" in markdown


def test_accepted_lineage_only_clears_lineage_blocker_but_not_oos(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        closure,
        "_guarded_alias_bounded_generation_snapshot",
        lambda *_: {"overall_result": "ALIAS_POLICY_CONTEXT_ONLY_BOUNDED_GENERATION_READY"},
    )
    monkeypatch.setattr(
        closure.evidence_coverage,
        "build_real_basket_evidence_coverage",
        lambda **_: {
            "rows": [
                {
                    "candidate_id": "c1",
                    "symbol": "AAPL",
                    "preset_id": "trend_pullback_continuation_daily_v1",
                    "timeframes": ["1d"],
                    "diagnosis_class": "diagnosable",
                    "evidence_completeness_score_pct": 57,
                    "evidence_completeness_status": "partial",
                    "missing_evidence_taxonomy": ["campaign_lineage_missing", "no_oos_evidence"],
                    "follow_up": "collect_more_evidence",
                    "evidence_presence": {
                        "source_identity_ready": True,
                        "source_quality_ready": True,
                        "cache_ready": True,
                        "screening_evidence_present": True,
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
        lambda **_: {"records": [{"subject_id": "c1", "record_ids": ["qrr-1"], "record_families": ["basket_diagnosis"], "reason_codes": ["campaign_lineage_missing"], "evidence_refs": ["research/production_discovery_catalog.py"]}]},
    )
    monkeypatch.setattr(
        closure.failure_action,
        "build_failure_action_from_basket",
        lambda **_: {"rows": [{"candidate_id": "c1", "recommended_action": "collect_oos_evidence", "actionability": {"is_actionable": True, "status": "actionable"}}]},
    )
    verifier_report = _accepted_verifier_report()
    verifier_report["rows"][0]["accepted_for_oos_evidence"] = False
    verifier_report["rows"][0]["accepted_oos_count"] = 0
    verifier_report["rows"][0]["accepted_oos_records"] = []
    verifier_report["summary"]["accepted_oos_candidate_count"] = 0
    _write_json(tmp_path / "logs" / "qre_bounded_generation_artifact_acceptance_verifier" / "latest.json", verifier_report)

    report = closure.build_evidence_complete_basket_closure(repo_root=tmp_path)
    row = report["rows"][0]

    assert "campaign_lineage_missing" not in row["exact_blockers"]
    assert "no_oos_evidence" in row["exact_blockers"]
    assert row["closure_status"] == "blocked_not_evidence_complete"
    assert any(item["blocker_code"] == "campaign_lineage_missing" for item in row["clearance_reason_records"])


def test_accepted_oos_only_clears_oos_blocker_but_not_lineage(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        closure,
        "_guarded_alias_bounded_generation_snapshot",
        lambda *_: {"overall_result": "ALIAS_POLICY_CONTEXT_ONLY_BOUNDED_GENERATION_READY"},
    )
    monkeypatch.setattr(
        closure.evidence_coverage,
        "build_real_basket_evidence_coverage",
        lambda **_: {
            "rows": [
                {
                    "candidate_id": "c1",
                    "symbol": "AAPL",
                    "preset_id": "trend_pullback_continuation_daily_v1",
                    "timeframes": ["1d"],
                    "diagnosis_class": "diagnosable",
                    "evidence_completeness_score_pct": 57,
                    "evidence_completeness_status": "partial",
                    "missing_evidence_taxonomy": ["campaign_lineage_missing", "no_oos_evidence"],
                    "follow_up": "collect_more_evidence",
                    "evidence_presence": {
                        "source_identity_ready": True,
                        "source_quality_ready": True,
                        "cache_ready": True,
                        "screening_evidence_present": True,
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
        lambda **_: {"records": [{"subject_id": "c1", "record_ids": ["qrr-1"], "record_families": ["basket_diagnosis"], "reason_codes": ["no_oos_evidence"], "evidence_refs": ["research/screening_evidence_latest.v1.json"]}]},
    )
    monkeypatch.setattr(
        closure.failure_action,
        "build_failure_action_from_basket",
        lambda **_: {"rows": [{"candidate_id": "c1", "recommended_action": "materialize_lineage_from_existing_artifacts", "actionability": {"is_actionable": True, "status": "actionable"}}]},
    )
    verifier_report = _accepted_verifier_report()
    verifier_report["rows"][0]["accepted_for_campaign_lineage"] = False
    verifier_report["rows"][0]["accepted_lineage_count"] = 0
    verifier_report["rows"][0]["accepted_lineage_records"] = []
    verifier_report["summary"]["accepted_lineage_candidate_count"] = 0
    _write_json(tmp_path / "logs" / "qre_bounded_generation_artifact_acceptance_verifier" / "latest.json", verifier_report)

    report = closure.build_evidence_complete_basket_closure(repo_root=tmp_path)
    row = report["rows"][0]

    assert "campaign_lineage_missing" in row["exact_blockers"]
    assert "no_oos_evidence" not in row["exact_blockers"]
    assert row["closure_status"] == "blocked_not_evidence_complete"
    assert any(item["blocker_code"] == "no_oos_evidence" for item in row["clearance_reason_records"])


def test_accepted_lineage_and_oos_for_same_scope_can_complete_basket(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        closure,
        "_guarded_alias_bounded_generation_snapshot",
        lambda *_: {"overall_result": "ALIAS_POLICY_CONTEXT_ONLY_BOUNDED_GENERATION_READY"},
    )
    monkeypatch.setattr(
        closure.evidence_coverage,
        "build_real_basket_evidence_coverage",
        lambda **_: {
            "rows": [
                {
                    "candidate_id": "c1",
                    "symbol": "AAPL",
                    "preset_id": "trend_pullback_continuation_daily_v1",
                    "timeframes": ["1d"],
                    "diagnosis_class": "diagnosable",
                    "evidence_completeness_score_pct": 57,
                    "evidence_completeness_status": "partial",
                    "missing_evidence_taxonomy": ["campaign_lineage_missing", "no_oos_evidence"],
                    "follow_up": "collect_more_evidence",
                    "evidence_presence": {
                        "source_identity_ready": True,
                        "source_quality_ready": True,
                        "cache_ready": True,
                        "screening_evidence_present": True,
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
        lambda **_: {"records": [{"subject_id": "c1", "record_ids": ["qrr-1"], "record_families": ["basket_diagnosis"], "reason_codes": ["campaign_lineage_missing"], "evidence_refs": ["research/production_discovery_catalog.py"]}]},
    )
    monkeypatch.setattr(
        closure.failure_action,
        "build_failure_action_from_basket",
        lambda **_: {"rows": [{"candidate_id": "c1", "recommended_action": "keep_fail_closed", "actionability": {"is_actionable": True, "status": "actionable"}}]},
    )
    _write_json(
        tmp_path / "logs" / "qre_bounded_generation_artifact_acceptance_verifier" / "latest.json",
        _accepted_verifier_report(),
    )

    report = closure.build_evidence_complete_basket_closure(repo_root=tmp_path)
    row = report["rows"][0]

    assert row["closure_status"] == "evidence_complete"
    assert row["exact_blockers"] == []
    assert report["summary"]["evidence_complete_count"] == 1


def test_mismatched_scope_does_not_clear_blockers(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        closure,
        "_guarded_alias_bounded_generation_snapshot",
        lambda *_: {"overall_result": "ALIAS_POLICY_CONTEXT_ONLY_BOUNDED_GENERATION_READY"},
    )
    monkeypatch.setattr(
        closure.evidence_coverage,
        "build_real_basket_evidence_coverage",
        lambda **_: {
            "rows": [
                {
                    "candidate_id": "c1",
                    "symbol": "AAPL",
                    "preset_id": "trend_pullback_continuation_daily_v1",
                    "timeframes": ["1d"],
                    "diagnosis_class": "diagnosable",
                    "evidence_completeness_score_pct": 57,
                    "evidence_completeness_status": "partial",
                    "missing_evidence_taxonomy": ["campaign_lineage_missing", "no_oos_evidence"],
                    "follow_up": "collect_more_evidence",
                    "evidence_presence": {
                        "source_identity_ready": True,
                        "source_quality_ready": True,
                        "cache_ready": True,
                        "screening_evidence_present": True,
                        "oos_evidence_known": False,
                        "campaign_lineage_present": False,
                        "candidate_lineage_present": True,
                    },
                }
            ]
        },
    )
    monkeypatch.setattr(closure.reason_records, "build_reason_records_snapshot", lambda **_: {"records": []})
    monkeypatch.setattr(
        closure.failure_action,
        "build_failure_action_from_basket",
        lambda **_: {"rows": [{"candidate_id": "c1", "recommended_action": "keep_fail_closed", "actionability": {"is_actionable": False, "status": "non_actionable"}}]},
    )
    _write_json(
        tmp_path / "logs" / "qre_bounded_generation_artifact_acceptance_verifier" / "latest.json",
        _accepted_verifier_report(candidate_id="other-candidate"),
    )

    report = closure.build_evidence_complete_basket_closure(repo_root=tmp_path)
    row = report["rows"][0]

    assert "campaign_lineage_missing" in row["exact_blockers"]
    assert "no_oos_evidence" in row["exact_blockers"]
    assert row["clearance_reason_records"] == []


def test_provisional_or_context_only_records_do_not_clear_blockers(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        closure,
        "_guarded_alias_bounded_generation_snapshot",
        lambda *_: {"overall_result": "ALIAS_POLICY_CONTEXT_ONLY_BOUNDED_GENERATION_READY"},
    )
    monkeypatch.setattr(
        closure.evidence_coverage,
        "build_real_basket_evidence_coverage",
        lambda **_: {
            "rows": [
                {
                    "candidate_id": "c1",
                    "symbol": "AAPL",
                    "preset_id": "trend_pullback_continuation_daily_v1",
                    "timeframes": ["1d"],
                    "diagnosis_class": "diagnosable",
                    "evidence_completeness_score_pct": 57,
                    "evidence_completeness_status": "partial",
                    "missing_evidence_taxonomy": ["campaign_lineage_missing", "no_oos_evidence"],
                    "follow_up": "collect_more_evidence",
                    "evidence_presence": {
                        "source_identity_ready": True,
                        "source_quality_ready": True,
                        "cache_ready": True,
                        "screening_evidence_present": True,
                        "oos_evidence_known": False,
                        "campaign_lineage_present": False,
                        "candidate_lineage_present": True,
                    },
                }
            ]
        },
    )
    monkeypatch.setattr(closure.reason_records, "build_reason_records_snapshot", lambda **_: {"records": []})
    monkeypatch.setattr(
        closure.failure_action,
        "build_failure_action_from_basket",
        lambda **_: {"rows": [{"candidate_id": "c1", "recommended_action": "keep_fail_closed", "actionability": {"is_actionable": False, "status": "non_actionable"}}]},
    )
    _write_json(
        tmp_path / "logs" / "qre_bounded_generation_artifact_acceptance_verifier" / "latest.json",
        {
            "report_kind": "qre_bounded_generation_artifact_acceptance_verifier",
            "summary": {"accepted_lineage_candidate_count": 0, "accepted_oos_candidate_count": 0},
            "rows": [
                {
                    "classification": "rejected_materialized_provisional_only",
                    "accepted_for_campaign_lineage": False,
                    "accepted_for_oos_evidence": False,
                }
            ],
        },
    )

    report = closure.build_evidence_complete_basket_closure(repo_root=tmp_path)
    row = report["rows"][0]

    assert "campaign_lineage_missing" in row["exact_blockers"]
    assert "no_oos_evidence" in row["exact_blockers"]
    assert row["clearance_reason_records"] == []
