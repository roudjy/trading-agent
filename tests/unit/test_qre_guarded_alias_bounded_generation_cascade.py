from __future__ import annotations

from pathlib import Path

from research import qre_guarded_alias_bounded_generation_cascade as cascade


def test_guarded_alias_cascade_keeps_legacy_evidence_context_only(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        cascade.alias_policy,
        "build_guarded_preset_timeframe_alias_policy",
        lambda **_: {
            "summary": {
                "final_recommendation": "guarded_alias_policy_context_only",
            },
            "rows": [
                {
                    "symbol": "AAPL",
                    "legacy_preset_id": "trend_pullback_v1",
                    "legacy_timeframe": "4h",
                    "safe_for_operator_context": True,
                    "safe_for_oos_context": False,
                    "safe_for_campaign_lineage": False,
                    "safe_for_evidence_completion": False,
                    "policy_reason": "context only",
                    "required_evidence_for_upgrade": ["approved_current_basket_generation_artifact"],
                },
                {
                    "symbol": "NVDA",
                    "legacy_preset_id": "trend_pullback_v1",
                    "legacy_timeframe": "4h",
                    "safe_for_operator_context": True,
                    "safe_for_oos_context": False,
                    "safe_for_campaign_lineage": False,
                    "safe_for_evidence_completion": False,
                    "policy_reason": "context only",
                    "required_evidence_for_upgrade": ["approved_current_basket_generation_artifact"],
                },
            ],
        },
    )
    monkeypatch.setattr(
        cascade.closure,
        "build_evidence_complete_basket_closure",
        lambda **_: {
            "summary": {"evidence_complete_count": 0, "unknown_blocker_count": 0},
            "rows": [
                {"symbol": "AAPL", "exact_blockers": ["campaign_lineage_missing", "no_oos_evidence"]},
                {"symbol": "NVDA", "exact_blockers": ["campaign_lineage_missing", "no_oos_evidence"]},
            ],
        },
    )
    monkeypatch.setattr(
        cascade.first_batch_cascade,
        "build_first_batch_evidence_recovery_cascade",
        lambda **_: {
            "overall_result": "PRESET_TIMEFRAME_ALIAS_BLOCKED",
            "fundamental_stop_condition": "preset_timeframe_alias_unproven",
        },
    )
    monkeypatch.setattr(
        cascade.generation_decision,
        "build_bounded_first_batch_generation_decision",
        lambda **_: {"summary": {"final_recommendation": "operator_approve_bounded_aapl_nvda_current_basket_grid_generation"}},
    )
    monkeypatch.setattr(
        cascade.acceptance_verifier,
        "build_bounded_generation_artifact_acceptance_verifier",
        lambda **_: {"summary": {"final_recommendation": "artifact_acceptance_verifier_ready"}},
    )

    report = cascade.build_guarded_alias_bounded_generation_cascade(repo_root=tmp_path)

    assert report["overall_result"] == "ALIAS_POLICY_CONTEXT_ONLY_BOUNDED_GENERATION_READY"
    assert report["summary"]["evidence_complete_count"] == 0
    assert report["summary"]["unknown_blocker_count"] == 0
    assert report["fundamental_stop_condition"] == "operator_approval_required_for_bounded_generation"
    assert report["summary"]["bounded_generation_decision_status"] == "operator_approve_bounded_aapl_nvda_current_basket_grid_generation"
    rows = {row["symbol"]: row for row in report["legacy_evidence_usage_matrix"]}
    assert rows["AAPL"]["context_usage_allowed"] is True
    assert rows["AAPL"]["campaign_lineage_proof_allowed"] is False
    assert rows["AAPL"]["evidence_completeness_allowed"] is False
    assert rows["AAPL"]["after_blockers"] == ["campaign_lineage_missing", "no_oos_evidence"]
    assert rows["NVDA"]["oos_proof_allowed"] is False
    assert report["dry_run_simulation"]["hypothetical_only"] is True


def test_guarded_alias_cascade_write_outputs_stays_allowlisted(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        cascade.alias_policy,
        "build_guarded_preset_timeframe_alias_policy",
        lambda **_: {"summary": {}, "rows": []},
    )
    monkeypatch.setattr(
        cascade.closure,
        "build_evidence_complete_basket_closure",
        lambda **_: {"summary": {"evidence_complete_count": 0, "unknown_blocker_count": 0}, "rows": []},
    )
    monkeypatch.setattr(
        cascade.first_batch_cascade,
        "build_first_batch_evidence_recovery_cascade",
        lambda **_: {},
    )
    monkeypatch.setattr(
        cascade.generation_decision,
        "build_bounded_first_batch_generation_decision",
        lambda **_: {"summary": {}},
    )
    monkeypatch.setattr(
        cascade.acceptance_verifier,
        "build_bounded_generation_artifact_acceptance_verifier",
        lambda **_: {"summary": {}},
    )

    report = cascade.build_guarded_alias_bounded_generation_cascade(repo_root=tmp_path)
    paths = cascade.write_outputs(report, repo_root=tmp_path)

    assert paths["latest"] == "logs/qre_guarded_alias_bounded_generation_cascade/latest.json"
    assert paths["operator_summary"] == "logs/qre_guarded_alias_bounded_generation_cascade/operator_summary.md"
