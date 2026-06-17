from __future__ import annotations

from pathlib import Path

from research import qre_basket_operator_action_plan as action_plan


def test_operator_action_plan_prioritizes_aapl_and_nvda_first_batch(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        action_plan.next_action_queue,
        "build_basket_next_action_queue",
        lambda **_: {
            "rows": [
                {
                    "candidate_id": "cand-a",
                    "symbol": "AAPL",
                    "region": "US",
                    "asset_class": "equity",
                    "preset_id": "preset-a",
                    "hypothesis_id": "hyp-a",
                    "priority_rank": 1,
                    "priority_bucket": "lineage_first",
                    "exact_next_action": "materialize_lineage_from_existing_artifacts",
                    "recommended_batch": "batch_lineage_oos",
                    "candidate_score": 86,
                    "lineage_proof_status": "candidate_proven_campaign_missing",
                    "campaign_lineage_proof_status": "gap",
                    "allowed_command_template": "python -m research.qre_basket_lineage_recovery_diagnostics --write",
                    "requires_operator_review": True,
                    "safe_action_type": "report_only",
                    "blocker_code": "campaign_lineage_missing",
                    "blocker_family": "lineage",
                    "blocked_by_identity": False,
                    "blocked_by_source_cache": False,
                    "blocked_by_lineage": True,
                    "blocked_by_screening": False,
                    "blocked_by_oos": True,
                    "operator_explanation": "AAPL remains blocked by campaign_lineage_missing.",
                },
                {
                    "candidate_id": "cand-n",
                    "symbol": "NVDA",
                    "region": "US",
                    "asset_class": "equity",
                    "preset_id": "preset-n",
                    "hypothesis_id": "hyp-n",
                    "priority_rank": 1,
                    "priority_bucket": "lineage_first",
                    "exact_next_action": "collect_oos_evidence",
                    "recommended_batch": "batch_lineage_oos",
                    "candidate_score": 86,
                    "lineage_proof_status": "candidate_proven_campaign_missing",
                    "campaign_lineage_proof_status": "gap",
                    "allowed_command_template": "python -m research.qre_evidence_complete_basket_closure --write",
                    "requires_operator_review": True,
                    "safe_action_type": "report_only",
                    "blocker_code": "no_oos_evidence",
                    "blocker_family": "oos",
                    "blocked_by_identity": False,
                    "blocked_by_source_cache": False,
                    "blocked_by_lineage": True,
                    "blocked_by_screening": False,
                    "blocked_by_oos": True,
                    "operator_explanation": "NVDA remains blocked by no_oos_evidence.",
                },
                {
                    "candidate_id": "cand-s",
                    "symbol": "ASMI",
                    "region": "NL/EU",
                    "asset_class": "equity",
                    "preset_id": "preset-s",
                    "hypothesis_id": "hyp-s",
                    "priority_rank": 0,
                    "priority_bucket": "identity_first",
                    "exact_next_action": "require_identity_resolution",
                    "recommended_batch": "batch_identity_review",
                    "candidate_score": 0,
                    "lineage_proof_status": "lineage_gap",
                    "campaign_lineage_proof_status": "gap",
                    "allowed_command_template": "python -m research.qre_discovery_source_identity_diagnostics --write",
                    "requires_operator_review": True,
                    "safe_action_type": "report_only",
                    "blocker_code": "source_identity_blocked",
                    "blocker_family": "identity",
                    "blocked_by_identity": True,
                    "blocked_by_source_cache": False,
                    "blocked_by_lineage": False,
                    "blocked_by_screening": False,
                    "blocked_by_oos": False,
                    "operator_explanation": "ASMI remains blocked by source_identity_blocked.",
                },
            ],
            "summary": {"row_count": 3},
        },
    )
    monkeypatch.setattr(
        action_plan.lineage_diag,
        "build_basket_lineage_recovery_diagnostics",
        lambda **_: {
            "rows": [
                {"candidate_id": "cand-a", "symbol": "AAPL"},
                {"candidate_id": "cand-n", "symbol": "NVDA"},
                {"candidate_id": "cand-s", "symbol": "ASMI"},
            ]
        },
    )
    monkeypatch.setattr(
        action_plan.first_batch_readiness,
        "build_first_batch_evidence_recovery_readiness",
        lambda **_: {
            "report_kind": "qre_first_batch_evidence_recovery_readiness",
            "first_batch_summary": {"first_batch": ["AAPL", "NVDA"]},
        },
    )
    monkeypatch.setattr(
        action_plan.first_batch_cascade,
        "build_first_batch_evidence_recovery_cascade",
        lambda **_: {
            "report_kind": "qre_first_batch_evidence_recovery_cascade",
            "overall_result": "PRESET_TIMEFRAME_ALIAS_BLOCKED",
            "first_batch_summary": {"current_top_blocker": "preset_timeframe_alias_unproven"},
        },
    )

    report = action_plan.build_basket_operator_action_plan(repo_root=tmp_path, max_candidates=3)

    assert report["summary"]["recommended_first_batch"] == "lineage_repair"
    assert report["summary"]["top_candidates"] == ["AAPL", "NVDA"]
    assert report["summary"]["top_actions"] == [
        "materialize_lineage_from_existing_artifacts",
        "collect_oos_evidence",
    ]
    assert report["summary"]["blockers_targeted"] == {
        "campaign_lineage_missing": 1,
        "no_oos_evidence": 1,
    }
    first_batch = {row["symbol"]: row for row in report["first_batch"]}
    assert first_batch["AAPL"]["requires_operator_review"] is True
    assert first_batch["NVDA"]["allowed_command_template"] == "python -m research.qre_evidence_complete_basket_closure --write"
    assert any("registration" in item for item in report["commands_not_allowed"])
    assert report["safe_commands_to_run_manually"][0] == "python -m research.qre_basket_evidence_density_materialization --write"
    assert report["summary"]["first_batch_readiness_available"] is True
    assert report["summary"]["first_batch_recovery_cascade_available"] is True
    assert report["summary"]["first_batch_recovery_cascade_result"] == "PRESET_TIMEFRAME_ALIAS_BLOCKED"


def test_operator_action_plan_write_outputs_stays_allowlisted(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(action_plan.next_action_queue, "build_basket_next_action_queue", lambda **_: {"rows": [], "summary": {"row_count": 0}})
    monkeypatch.setattr(action_plan.lineage_diag, "build_basket_lineage_recovery_diagnostics", lambda **_: {"rows": []})
    monkeypatch.setattr(
        action_plan.first_batch_readiness,
        "build_first_batch_evidence_recovery_readiness",
        lambda **_: {"report_kind": "qre_first_batch_evidence_recovery_readiness", "first_batch_summary": {"first_batch": []}},
    )
    monkeypatch.setattr(
        action_plan.first_batch_cascade,
        "build_first_batch_evidence_recovery_cascade",
        lambda **_: {"report_kind": "qre_first_batch_evidence_recovery_cascade", "first_batch_summary": {}, "overall_result": "PRESET_TIMEFRAME_ALIAS_BLOCKED"},
    )

    report = action_plan.build_basket_operator_action_plan(repo_root=tmp_path, max_candidates=1)
    paths = action_plan.write_outputs(report, repo_root=tmp_path)

    assert paths["latest"] == "logs/qre_basket_operator_action_plan/latest.json"
    assert (tmp_path / paths["latest"]).is_file()
    assert (tmp_path / paths["operator_summary"]).is_file()
