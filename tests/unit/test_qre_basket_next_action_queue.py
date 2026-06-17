from __future__ import annotations

from pathlib import Path

from research import qre_basket_next_action_queue as queue


def test_build_basket_next_action_queue_prioritizes_first_batch_lineage(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        queue.recovery_plan,
        "build_basket_evidence_recovery_plan",
        lambda **_: {
            "blocker_rows": [
                {
                    "candidate_id": "cand-a",
                    "symbol": "AAPL",
                    "region": "US",
                    "asset_class": "equity",
                    "preset_id": "preset-a",
                    "hypothesis_id": "hyp-a",
                    "blocker_code": "campaign_lineage_missing",
                    "blocker_family": "lineage",
                    "current_status": "partial",
                    "exact_next_action": "materialize_lineage_from_existing_artifacts",
                    "required_artifact": "logs/qre_discovery_basket_grid_evidence_materialization/latest.json",
                    "safe_action_type": "report_only",
                    "blocked_by_identity": False,
                    "blocked_by_source_cache": False,
                    "blocked_by_lineage": True,
                    "blocked_by_screening": False,
                    "blocked_by_oos": True,
                    "potential_clear_refs": ["logs/qre_discovery_basket_grid_evidence_materialization/latest.json"],
                    "reason_record_refs": {"record_ids": ["rr-a"]},
                    "operator_explanation": "AAPL remains blocked by campaign_lineage_missing.",
                },
                {
                    "candidate_id": "cand-n",
                    "symbol": "NVDA",
                    "region": "US",
                    "asset_class": "equity",
                    "preset_id": "preset-n",
                    "hypothesis_id": "hyp-n",
                    "blocker_code": "no_oos_evidence",
                    "blocker_family": "oos",
                    "current_status": "partial",
                    "exact_next_action": "collect_oos_evidence",
                    "required_artifact": "research/screening_evidence_latest.v1.json",
                    "safe_action_type": "report_only",
                    "blocked_by_identity": False,
                    "blocked_by_source_cache": False,
                    "blocked_by_lineage": True,
                    "blocked_by_screening": False,
                    "blocked_by_oos": True,
                    "potential_clear_refs": ["research/screening_evidence_latest.v1.json"],
                    "reason_record_refs": {"record_ids": ["rr-n"]},
                    "operator_explanation": "NVDA remains blocked by no_oos_evidence.",
                },
                {
                    "candidate_id": "cand-s",
                    "symbol": "ASMI",
                    "region": "NL/EU",
                    "asset_class": "equity",
                    "preset_id": "preset-s",
                    "hypothesis_id": "hyp-s",
                    "blocker_code": "source_identity_blocked",
                    "blocker_family": "identity",
                    "current_status": "missing",
                    "exact_next_action": "require_identity_resolution",
                    "required_artifact": "research/production_discovery_catalog.py",
                    "safe_action_type": "report_only",
                    "blocked_by_identity": True,
                    "blocked_by_source_cache": False,
                    "blocked_by_lineage": False,
                    "blocked_by_screening": False,
                    "blocked_by_oos": False,
                    "potential_clear_refs": ["research/production_discovery_catalog.py"],
                    "reason_record_refs": {"record_ids": ["rr-s"]},
                    "operator_explanation": "ASMI remains blocked by source_identity_blocked.",
                },
            ],
            "rows": [
                {"candidate_id": "cand-a", "symbol": "AAPL", "preset_id": "preset-a", "evidence_completeness_score_pct": 86},
                {"candidate_id": "cand-n", "symbol": "NVDA", "preset_id": "preset-n", "evidence_completeness_score_pct": 86},
                {"candidate_id": "cand-s", "symbol": "ASMI", "preset_id": "preset-s", "evidence_completeness_score_pct": 0},
            ],
            "summary": {"evidence_complete_count": 0},
        },
    )
    monkeypatch.setattr(
        queue.lineage_diag,
        "build_basket_lineage_recovery_diagnostics",
        lambda **_: {
            "rows": [
                {"candidate_id": "cand-a", "candidate_lineage_proof_status": "candidate_proven_campaign_missing", "campaign_lineage_proof_status": "gap"},
                {"candidate_id": "cand-n", "candidate_lineage_proof_status": "candidate_proven_campaign_missing", "campaign_lineage_proof_status": "gap"},
                {"candidate_id": "cand-s", "candidate_lineage_proof_status": "lineage_gap", "campaign_lineage_proof_status": "gap"},
            ]
        },
    )
    monkeypatch.setattr(
        queue,
        "_guarded_alias_bounded_generation_snapshot",
        lambda *_: {
            "overall_result": "ALIAS_POLICY_CONTEXT_ONLY_BOUNDED_GENERATION_READY",
        },
    )
    monkeypatch.setattr(
        queue,
        "_generation_command_discovery_snapshot",
        lambda *_: {
            "report_kind": "qre_bounded_aapl_nvda_current_basket_generation_discovery",
            "summary": {
                "safe_bounded_generation_command_found": False,
                "final_recommendation": "NO_SAFE_BOUNDED_GENERATION_COMMAND_FOUND",
            },
        },
    )

    report = queue.build_basket_next_action_queue(repo_root=tmp_path, max_candidates=3)

    assert report["summary"]["top_candidate_symbols"] == ["AAPL", "NVDA"]
    assert report["rows"][0]["priority_bucket"] == "lineage_first"
    assert report["rows"][1]["priority_bucket"] == "lineage_first"
    assert report["rows"][2]["priority_bucket"] == "identity_first"
    assert report["rows"][0]["allowed_to_auto_run"] is False
    assert report["rows"][0]["exact_next_action"] == "investigate_no_safe_bounded_command"
    assert report["rows"][1]["exact_next_action"] == "investigate_no_safe_bounded_command"
    assert report["rows"][0]["allowed_command_template"] == "python -m research.qre_bounded_aapl_nvda_current_basket_generation_discovery --write"
    assert report["summary"]["guarded_alias_bounded_generation_cascade_result"] == "ALIAS_POLICY_CONTEXT_ONLY_BOUNDED_GENERATION_READY"
    assert report["summary"]["generation_command_discovery_safe_command_found"] is False
    assert report["summary"]["generation_command_discovery_final_recommendation"] == "NO_SAFE_BOUNDED_GENERATION_COMMAND_FOUND"
    assert report["summary"]["structured_lineage_artifact_status"] == "request_invalid_fails_closed"
    assert report["summary"]["structured_lineage_artifact_count"] == 0
    assert report["summary"]["structured_oos_artifact_status"] == "request_invalid_fails_closed"
    assert report["summary"]["structured_oos_artifact_count"] == 0
