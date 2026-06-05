from __future__ import annotations

import json

from reporting import qre_controlled_validation_execution as execution
from reporting import qre_controlled_validation_result_analysis as analysis




def _ready_bridge_snapshot() -> dict:
    return {
        "report_kind": "qre_executable_hypothesis_identity_bridge_diagnostics",
        "final_recommendation": "executable_hypothesis_identity_bridge_ready_for_regeneration",
        "controlled_validation_bridge_readiness": {
            "ready": True,
            "executable_hypothesis_count": 1,
            "ready_count": 1,
            "blocked_count": 0,
            "rows": [
                {
                    "preset_name": "trend_pullback_equities_4h",
                    "executable_hypothesis_id": "trend_pullback_v1",
                    "ready": True,
                    "primary_blocker": "no_primary_blocker",
                }
            ],
        },
    }

def test_analysis_blocks_when_execution_not_authorized() -> None:
    snapshot = analysis.collect_snapshot(
        profile_name="equities_exploratory_v1",
        generated_at_utc="2026-06-03T18:00:00Z",
    )

    assert snapshot["report_kind"] == "qre_controlled_validation_result_analysis"
    assert snapshot["safe_to_execute"] is False
    assert snapshot["read_only"] is True
    assert snapshot["analysis_status"] == "analysis_blocked_execution_not_authorized"
    assert snapshot["counts"]["blocked"] == 1
    assert snapshot["result_summary"]["completed_run_available"] is False
    assert snapshot["writes_research_action_queue"] is False


def test_analysis_blocks_when_runner_not_connected_even_if_authorized() -> None:
    execution_snapshot = execution.collect_snapshot(
        profile_name="equities_exploratory_v1",
        execute_controlled_validation=True,
        operator_go=execution.REQUIRED_OPERATOR_GO_PHRASE,
        controlled_validation_bridge_snapshot=_ready_bridge_snapshot(),
        generated_at_utc="2026-06-03T17:00:00Z",
    )

    snapshot = analysis.collect_snapshot(
        profile_name="equities_exploratory_v1",
        execution_snapshot=execution_snapshot,
        generated_at_utc="2026-06-03T18:00:00Z",
    )

    assert snapshot["analysis_status"] == "analysis_blocked_runner_not_connected"
    assert snapshot["execution_summary"]["controlled_validation_authorized"] is True
    assert snapshot["execution_summary"]["runner_adapter_status"] == "not_connected"
    assert snapshot["result_summary"]["completed_run_available"] is False
    assert snapshot["next_required_step"] == (
        "connect controlled validation runner before result analysis"
    )


def test_analysis_blocks_when_connected_runner_has_no_completed_run() -> None:
    execution_snapshot = {
        "report_kind": "qre_controlled_validation_execution",
        "selection_profile_name": "equities_exploratory_v1",
        "execution_status": "execution_authorized_runner_connected",
        "controlled_validation_authorized": True,
        "runner_adapter_status": "connected",
        "executed_anything": False,
        "final_recommendation": "controlled_validation_execution_ready",
    }

    snapshot = analysis.collect_snapshot(
        execution_snapshot=execution_snapshot,
        generated_at_utc="2026-06-03T18:00:00Z",
    )

    assert snapshot["analysis_status"] == "analysis_blocked_no_completed_run"
    assert snapshot["execution_summary"]["runner_adapter_status"] == "connected"
    assert snapshot["execution_summary"]["executed_anything"] is False


def test_analysis_blocks_execution_completed_without_evidence_report() -> None:
    execution_snapshot = {
        "report_kind": "qre_controlled_validation_execution",
        "selection_profile_name": "equities_exploratory_v1",
        "execution_status": "execution_completed",
        "controlled_validation_authorized": True,
        "runner_adapter_status": "connected",
        "executed_anything": True,
        "final_recommendation": "controlled_validation_execution_completed",
    }

    snapshot = analysis.collect_snapshot(
        execution_snapshot=execution_snapshot,
        generated_at_utc="2026-06-03T18:00:00Z",
    )

    assert snapshot["analysis_status"] == "analysis_blocked_no_completed_run"
    assert snapshot["counts"]["ready"] == 0
    assert snapshot["counts"]["blocked"] == 1
    assert snapshot["controlled_eval_report"]["present"] is False
    assert snapshot["result_summary"]["completed_run_available"] is False
    assert snapshot["result_summary"]["evidence_refs"] == []

def test_cli_no_write_does_not_create_artifact(tmp_path, monkeypatch, capsys) -> None:
    artifact_path = tmp_path / "latest.json"
    monkeypatch.setattr(analysis, "ARTIFACT_LATEST", artifact_path)

    rc = analysis.main(
        [
            "--profile",
            "equities_exploratory_v1",
            "--no-write",
            "--frozen-utc",
            "2026-06-03T18:00:00Z",
        ]
    )

    assert rc == 0
    assert not artifact_path.exists()
    payload = json.loads(capsys.readouterr().out)
    assert payload["analysis_status"] == "analysis_blocked_execution_not_authorized"


def test_cli_writes_only_own_artifact(tmp_path, monkeypatch) -> None:
    artifact_dir = tmp_path / "qre_controlled_validation_result_analysis"
    artifact_path = artifact_dir / "latest.json"
    monkeypatch.setattr(analysis, "ARTIFACT_DIR", artifact_dir)
    monkeypatch.setattr(analysis, "ARTIFACT_LATEST", artifact_path)

    rc = analysis.main(
        [
            "--profile",
            "equities_exploratory_v1",
            "--frozen-utc",
            "2026-06-03T18:00:00Z",
        ]
    )

    assert rc == 0
    assert artifact_path.exists()
    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert payload["analysis_status"] == "analysis_blocked_execution_not_authorized"
    assert payload["read_only"] is True

def test_analysis_reads_completed_controlled_eval_report(tmp_path) -> None:
    report_path = tmp_path / "controlled_eval_latest.v1.json"
    report_path.write_text(
        json.dumps(
            {
                "verdict": {
                    "status": "useful_observation",
                    "reason_codes": ["degenerate_no_survivors"],
                },
                "campaigns_completed": 1,
                "campaign_level_evidence_valid": True,
                "recommended_next_action": "inspect_results",
                "git_revision": "abc123",
                "screening_evidence_summary": {
                    "present": True,
                    "total_candidates": 15,
                    "passed_screening": 6,
                    "rejected_screening": 9,
                    "promotion_grade_candidates": 0,
                    "sufficient_oos_evidence_candidates": 1,
                    "qre_linkage_blocked_candidates": 1,
                    "sufficient_oos_but_unlinked_candidates": 1,
                },
            }
        ),
        encoding="utf-8",
    )
    execution_snapshot = {
        "report_kind": "qre_controlled_validation_execution",
        "selection_profile_name": "equities_exploratory_v1",
        "execution_status": "execution_completed",
        "controlled_validation_authorized": True,
        "runner_adapter_status": "connected",
        "executed_anything": True,
        "final_recommendation": "controlled_validation_execution_completed",
        "controlled_eval_result": {
            "returncode": 0,
            "report_paths": {"report_json": report_path.as_posix()},
        },
    }

    snapshot = analysis.collect_snapshot(
        execution_snapshot=execution_snapshot,
        generated_at_utc="2026-06-03T23:00:00Z",
        current_git_revision="abc123",
    )

    assert snapshot["analysis_status"] == "analysis_ready"
    assert snapshot["controlled_eval_report"]["present"] is True
    assert snapshot["controlled_eval_report"]["verdict_status"] == "useful_observation"
    assert snapshot["controlled_eval_report"]["campaigns_completed"] == 1
    assert snapshot["result_summary"]["completed_run_available"] is True
    assert snapshot["result_summary"]["pass_fail"] == "pass"
    assert snapshot["result_summary"]["trade_count"] == 1
    assert snapshot["result_summary"]["primary_failure_class"] is None
    assert snapshot["controlled_eval_report"]["artifact_freshness"] == {
        "artifact_git_revision": "abc123",
        "current_git_revision": "abc123",
        "artifact_may_be_stale": False,
        "reason_codes": ["artifact_git_revision_matches_current_head"],
    }
    assert snapshot["result_summary"]["artifact_freshness"] == {
        "artifact_git_revision": "abc123",
        "current_git_revision": "abc123",
        "artifact_may_be_stale": False,
        "reason_codes": ["artifact_git_revision_matches_current_head"],
    }
    assert snapshot["result_summary"]["screening_evidence_summary"] == {
        "present": True,
        "total_candidates": 15,
        "passed_screening": 6,
        "rejected_screening": 9,
        "promotion_grade_candidates": 0,
        "sufficient_oos_evidence_candidates": 1,
        "qre_linkage_blocked_candidates": 1,
        "sufficient_oos_but_unlinked_candidates": 1,
    }
    assert snapshot["result_summary"]["evidence_quality_bottleneck"] == {
        "primary_bottleneck": "linkage_blocker",
        "reason_codes": ["sufficient_oos_evidence_blocked_by_qre_linkage"],
        "artifact_freshness": {
            "artifact_git_revision": "abc123",
            "current_git_revision": "abc123",
            "artifact_may_be_stale": False,
            "reason_codes": ["artifact_git_revision_matches_current_head"],
        },
        "screening_evidence_summary": {
            "present": True,
            "total_candidates": 15,
            "passed_screening": 6,
            "rejected_screening": 9,
            "promotion_grade_candidates": 0,
            "sufficient_oos_evidence_candidates": 1,
            "qre_linkage_blocked_candidates": 1,
            "sufficient_oos_but_unlinked_candidates": 1,
        },
    }
    assert snapshot["result_summary"]["evidence_refs"] == [report_path.as_posix()]


def test_operator_summary_surfaces_hd_blockers_and_candidate_rollup(tmp_path) -> None:
    report_path = tmp_path / "controlled_eval_latest.v1.json"
    report_path.write_text(
        json.dumps(
            {
                "verdict": {
                    "status": "useful_observation",
                    "reason_codes": [],
                },
                "campaigns_completed": 1,
                "campaign_level_evidence_valid": True,
                "recommended_next_action": "inspect_results",
                "git_revision": "abc123",
                "screening_evidence_summary": {
                    "present": True,
                    "total_candidates": 3,
                    "passed_screening": 2,
                    "rejected_screening": 1,
                    "promotion_grade_candidates": 0,
                    "sufficient_oos_evidence_candidates": 1,
                    "qre_linkage_blocked_candidates": 0,
                    "sufficient_oos_but_unlinked_candidates": 0,
                },
            }
        ),
        encoding="utf-8",
    )
    execution_snapshot = {
        "report_kind": "qre_controlled_validation_execution",
        "selection_profile_name": "equities_exploratory_v1",
        "execution_status": "execution_completed",
        "controlled_validation_authorized": True,
        "runner_adapter_status": "connected",
        "executed_anything": True,
        "final_recommendation": "controlled_validation_execution_completed",
        "controlled_eval_result": {
            "returncode": 0,
            "report_paths": {"report_json": report_path.as_posix()},
        },
    }
    screening_evidence_payload = {
        "candidates": [
            {
                "asset": "HD",
                "preset_name": "trend_pullback_equities_4h",
                "strategy_name": "trend_pullback_v1",
                "interval": "4h",
                "stage_result": "screening_pass",
                "qre_validation_linkage_status": "linked_catalog_active_discovery",
                "validation_evidence": {
                    "status": "sufficient_oos_evidence",
                    "oos_trade_count": 14,
                    "min_oos_trades": 10,
                },
                "promotion_guard": {
                    "promotion_allowed": False,
                    "blocked_by": [
                        "criteria_consistentie_failed",
                        "criteria_trades_per_maand_failed",
                        "criteria_win_rate_failed",
                    ],
                },
                "failure_reasons": [],
                "near_pass": {"is_near_pass": False},
                "metrics": {
                    "win_rate": 0.5,
                    "trades_per_maand": 1.1,
                    "consistentie": 0.333,
                    "deflated_sharpe": 0.534,
                },
            },
            {
                "asset": "NVDA",
                "preset_name": "trend_pullback_equities_4h",
                "strategy_name": "trend_pullback_v1",
                "interval": "4h",
                "stage_result": "screening_pass",
                "qre_validation_linkage_status": "linked_catalog_active_discovery",
                "validation_evidence": {
                    "status": "no_oos_trades",
                    "oos_trade_count": 0,
                    "min_oos_trades": 10,
                },
                "promotion_guard": {
                    "promotion_allowed": False,
                    "blocked_by": ["criteria_deflated_sharpe_failed"],
                },
                "failure_reasons": [],
                "near_pass": {"is_near_pass": True},
                "metrics": {
                    "win_rate": 0.52,
                    "trades_per_maand": 1.8,
                    "consistentie": 0.4,
                    "deflated_sharpe": 0.1,
                },
            },
            {
                "asset": "AMD",
                "preset_name": "trend_pullback_equities_4h",
                "strategy_name": "trend_pullback_v1",
                "interval": "4h",
                "stage_result": "screening_reject",
                "qre_validation_linkage_status": "linked_catalog_active_discovery",
                "validation_evidence": {
                    "status": "no_oos_trades",
                    "oos_trade_count": 0,
                    "min_oos_trades": 10,
                },
                "promotion_guard": {
                    "promotion_allowed": False,
                    "blocked_by": [
                        "criteria_expectancy_above_zero_failed",
                        "criteria_sufficient_trades_failed",
                    ],
                },
                "failure_reasons": ["insufficient_trades"],
                "near_pass": {"is_near_pass": False},
                "metrics": {
                    "win_rate": 0.0,
                    "trades_per_maand": 0.0,
                    "consistentie": None,
                    "deflated_sharpe": None,
                },
            },
        ]
    }

    snapshot = analysis.collect_snapshot(
        execution_snapshot=execution_snapshot,
        generated_at_utc="2026-06-05T23:00:00Z",
        current_git_revision="abc123",
        screening_evidence_payload=screening_evidence_payload,
    )

    summary = snapshot["operator_summary"]
    assert summary["total_candidates"] == 3
    assert summary["linked_catalog_active_discovery_count"] == 3
    assert summary["sufficient_oos_evidence_count"] == 1
    assert summary["promotion_allowed_count"] == 0
    assert summary["promotion_blocked_count"] == 3
    assert summary["near_pass_count"] == 1
    assert summary["campaign_verdict"] == "useful_observation"
    assert summary["next_recommendation"] == "inspect_results"
    assert summary["safety_flags"] == {
        "artifact_may_be_stale": False,
        "controlled_validation_authorized": True,
        "runner_adapter_status": "connected",
        "mutates_paper_shadow_live_runtime": False,
        "writes_development_work_queue": False,
        "writes_research_action_queue": False,
    }
    assert summary["top_promotion_blockers"][0] == {
        "reason": "criteria_consistentie_failed",
        "count": 1,
    }
    assert summary["top_failure_reasons"] == [
        {"reason": "insufficient_trades", "count": 1}
    ]
    hd_row = next(
        row for row in summary["selected_asset_explanations"] if row["asset"] == "HD"
    )
    assert hd_row == {
        "asset": "HD",
        "asset_group": None,
        "region": None,
        "hypothesis_id": None,
        "preset_name": "trend_pullback_equities_4h",
        "strategy_name": "trend_pullback_v1",
        "interval": "4h",
        "stage_result": "screening_pass",
        "qre_validation_linkage_status": "linked_catalog_active_discovery",
        "validation_evidence_status": "sufficient_oos_evidence",
        "oos_trade_count": 14,
        "min_oos_trades": 10,
        "promotion_allowed": False,
        "blocked_by": [
            "criteria_consistentie_failed",
            "criteria_trades_per_maand_failed",
            "criteria_win_rate_failed",
        ],
        "failure_reasons": [],
        "near_pass": False,
        "outcome_class": "reject_criteria_consistentie_failed",
        "fixture_candidate": False,
        "not_real_market_evidence": False,
        "no_paper_activation": False,
        "no_live_activation": False,
        "no_shadow_activation": False,
        "metrics": {
            "win_rate": 0.5,
            "trades_per_maand": 1.1,
            "consistentie": 0.333,
            "deflated_sharpe": 0.534,
        },
    }


def test_analysis_marks_no_campaign_completed_as_failure(tmp_path) -> None:
    report_path = tmp_path / "controlled_eval_latest.v1.json"
    report_path.write_text(
        json.dumps(
            {
                "verdict": {
                    "status": "no_campaign_completed",
                    "reason_codes": ["no_campaign_completed"],
                },
                "campaigns_completed": 0,
                "recommended_next_action": "rerun_with_more_campaigns",
            }
        ),
        encoding="utf-8",
    )
    execution_snapshot = {
        "report_kind": "qre_controlled_validation_execution",
        "selection_profile_name": "equities_exploratory_v1",
        "execution_status": "execution_completed",
        "controlled_validation_authorized": True,
        "runner_adapter_status": "connected",
        "executed_anything": True,
        "final_recommendation": "controlled_validation_execution_completed",
        "controlled_eval_result": {
            "returncode": 0,
            "report_paths": {"report_json": report_path.as_posix()},
        },
    }

    snapshot = analysis.collect_snapshot(
        execution_snapshot=execution_snapshot,
        generated_at_utc="2026-06-03T23:00:00Z",
    )

    assert snapshot["analysis_status"] == "analysis_blocked_no_completed_run"
    assert snapshot["counts"]["ready"] == 0
    assert snapshot["counts"]["blocked"] == 1
    assert snapshot["result_summary"]["completed_run_available"] is False
    assert snapshot["result_summary"]["pass_fail"] == "fail"
    assert snapshot["result_summary"]["primary_failure_class"] == "no_campaign_completed"

def test_analysis_blocks_timeout_without_completed_campaign_evidence(tmp_path) -> None:
    report_path = tmp_path / "controlled_eval_latest.v1.json"
    report_path.write_text(
        json.dumps(
            {
                "verdict": {
                    "status": "timeout",
                    "reason_codes": ["launcher_timeout"],
                },
                "campaigns_attempted": 1,
                "campaigns_completed": 0,
                "campaign_level_evidence_valid": False,
                "recommended_next_action": "operator_review_required",
            }
        ),
        encoding="utf-8",
    )
    execution_snapshot = {
        "report_kind": "qre_controlled_validation_execution",
        "selection_profile_name": "equities_exploratory_v1",
        "execution_status": "execution_completed",
        "controlled_validation_authorized": True,
        "runner_adapter_status": "connected",
        "executed_anything": True,
        "final_recommendation": "controlled_validation_execution_completed",
        "controlled_eval_result": {
            "returncode": 0,
            "report_paths": {"report_json": report_path.as_posix()},
        },
    }

    snapshot = analysis.collect_snapshot(
        execution_snapshot=execution_snapshot,
        generated_at_utc="2026-06-04T23:00:00Z",
    )

    assert snapshot["analysis_status"] == "analysis_blocked_no_completed_run"
    assert snapshot["counts"]["ready"] == 0
    assert snapshot["counts"]["blocked"] == 1
    assert snapshot["controlled_eval_report"]["verdict_status"] == "timeout"
    assert snapshot["controlled_eval_report"]["campaigns_completed"] == 0
    assert snapshot["controlled_eval_report"]["campaign_level_evidence_valid"] is False
    assert snapshot["result_summary"]["completed_run_available"] is False
    assert snapshot["result_summary"]["pass_fail"] is None
    assert snapshot["result_summary"]["trade_count"] == 0



def test_analysis_marks_controlled_eval_report_stale_when_git_revision_differs(
    tmp_path,
) -> None:
    report_path = tmp_path / "controlled_eval_latest.v1.json"
    report_path.write_text(
        json.dumps(
            {
                "git_revision": "old123",
                "verdict": {
                    "status": "useful_observation",
                    "reason_codes": ["degenerate_no_survivors"],
                },
                "campaigns_completed": 1,
                "campaign_level_evidence_valid": True,
                "recommended_next_action": "inspect_results",
            }
        ),
        encoding="utf-8",
    )
    execution_snapshot = {
        "report_kind": "qre_controlled_validation_execution",
        "selection_profile_name": "equities_exploratory_v1",
        "execution_status": "execution_completed",
        "controlled_validation_authorized": True,
        "runner_adapter_status": "connected",
        "executed_anything": True,
        "final_recommendation": "controlled_validation_execution_completed",
        "controlled_eval_result": {
            "returncode": 0,
            "report_paths": {"report_json": report_path.as_posix()},
        },
    }

    snapshot = analysis.collect_snapshot(
        execution_snapshot=execution_snapshot,
        generated_at_utc="2026-06-03T23:00:00Z",
        current_git_revision="new456",
    )

    assert snapshot["analysis_status"] == "analysis_ready"
    assert snapshot["controlled_eval_report"]["artifact_freshness"] == {
        "artifact_git_revision": "old123",
        "current_git_revision": "new456",
        "artifact_may_be_stale": True,
        "reason_codes": ["artifact_git_revision_differs_from_current_head"],
    }
    assert snapshot["result_summary"]["artifact_freshness"] == snapshot[
        "controlled_eval_report"
    ]["artifact_freshness"]


def test_analysis_marks_controlled_eval_report_stale_when_git_revision_missing(
    tmp_path,
) -> None:
    report_path = tmp_path / "controlled_eval_latest.v1.json"
    report_path.write_text(
        json.dumps(
            {
                "verdict": {
                    "status": "useful_observation",
                    "reason_codes": ["degenerate_no_survivors"],
                },
                "campaigns_completed": 1,
                "campaign_level_evidence_valid": True,
                "recommended_next_action": "inspect_results",
            }
        ),
        encoding="utf-8",
    )
    execution_snapshot = {
        "report_kind": "qre_controlled_validation_execution",
        "selection_profile_name": "equities_exploratory_v1",
        "execution_status": "execution_completed",
        "controlled_validation_authorized": True,
        "runner_adapter_status": "connected",
        "executed_anything": True,
        "final_recommendation": "controlled_validation_execution_completed",
        "controlled_eval_result": {
            "returncode": 0,
            "report_paths": {"report_json": report_path.as_posix()},
        },
    }

    snapshot = analysis.collect_snapshot(
        execution_snapshot=execution_snapshot,
        generated_at_utc="2026-06-03T23:00:00Z",
        current_git_revision="new456",
    )

    assert snapshot["controlled_eval_report"]["artifact_freshness"] == {
        "artifact_git_revision": None,
        "current_git_revision": "new456",
        "artifact_may_be_stale": True,
        "reason_codes": ["artifact_git_revision_missing"],
    }


def test_evidence_quality_bottleneck_prioritizes_stale_artifact(tmp_path) -> None:
    report_path = tmp_path / "controlled_eval_latest.v1.json"
    report_path.write_text(
        json.dumps(
            {
                "git_revision": "old123",
                "verdict": {
                    "status": "useful_observation",
                    "reason_codes": ["degenerate_no_survivors"],
                },
                "campaigns_completed": 1,
                "campaign_level_evidence_valid": True,
                "recommended_next_action": "inspect_results",
                "screening_evidence_summary": {
                    "passed_screening": 6,
                    "rejected_screening": 9,
                    "sufficient_oos_evidence_candidates": 1,
                    "qre_linkage_blocked_candidates": 1,
                    "sufficient_oos_but_unlinked_candidates": 1,
                },
            }
        ),
        encoding="utf-8",
    )
    execution_snapshot = {
        "report_kind": "qre_controlled_validation_execution",
        "selection_profile_name": "equities_exploratory_v1",
        "execution_status": "execution_completed",
        "controlled_validation_authorized": True,
        "runner_adapter_status": "connected",
        "executed_anything": True,
        "final_recommendation": "controlled_validation_execution_completed",
        "controlled_eval_result": {
            "returncode": 0,
            "report_paths": {"report_json": report_path.as_posix()},
        },
    }

    snapshot = analysis.collect_snapshot(
        execution_snapshot=execution_snapshot,
        generated_at_utc="2026-06-03T23:00:00Z",
        current_git_revision="new456",
    )

    assert snapshot["result_summary"]["evidence_quality_bottleneck"]["primary_bottleneck"] == (
        "stale_artifact"
    )
    assert snapshot["result_summary"]["evidence_quality_bottleneck"]["reason_codes"] == [
        "controlled_eval_artifact_may_be_stale"
    ]


def test_evidence_quality_bottleneck_classifies_no_oos_evidence(tmp_path) -> None:
    report_path = tmp_path / "controlled_eval_latest.v1.json"
    report_path.write_text(
        json.dumps(
            {
                "git_revision": "abc123",
                "verdict": {
                    "status": "insufficient_data",
                    "reason_codes": ["campaign_completed_without_decisive_evidence"],
                },
                "campaigns_completed": 1,
                "campaign_level_evidence_valid": True,
                "recommended_next_action": "continue_sprint",
                "screening_evidence_summary": {
                    "passed_screening": 6,
                    "rejected_screening": 9,
                    "sufficient_oos_evidence_candidates": 0,
                    "qre_linkage_blocked_candidates": 0,
                    "sufficient_oos_but_unlinked_candidates": 0,
                },
            }
        ),
        encoding="utf-8",
    )
    execution_snapshot = {
        "report_kind": "qre_controlled_validation_execution",
        "selection_profile_name": "equities_exploratory_v1",
        "execution_status": "execution_completed",
        "controlled_validation_authorized": True,
        "runner_adapter_status": "connected",
        "executed_anything": True,
        "final_recommendation": "controlled_validation_execution_completed",
        "controlled_eval_result": {
            "returncode": 0,
            "report_paths": {"report_json": report_path.as_posix()},
        },
    }

    snapshot = analysis.collect_snapshot(
        execution_snapshot=execution_snapshot,
        generated_at_utc="2026-06-03T23:00:00Z",
        current_git_revision="abc123",
    )

    assert snapshot["result_summary"]["evidence_quality_bottleneck"]["primary_bottleneck"] == (
        "no_oos_evidence"
    )
    assert snapshot["result_summary"]["evidence_quality_bottleneck"]["reason_codes"] == [
        "screening_passed_without_sufficient_oos_evidence"
    ]


def test_evidence_quality_bottleneck_classifies_registry_ledger_invariant_failure(
    tmp_path,
) -> None:
    report_path = tmp_path / "controlled_eval_latest.v1.json"
    report_path.write_text(
        json.dumps(
            {
                "git_revision": "abc123",
                "verdict": {
                    "status": "technical_failure",
                    "reason_codes": [
                        "registry_ledger_invariant_violation",
                        "completed_campaign_missing_campaign_completed_ledger_event",
                    ],
                },
                "campaigns_completed": 1,
                "campaign_level_evidence_valid": False,
                "recommended_next_action": "operator_review_required",
                "screening_evidence_summary": {
                    "passed_screening": 6,
                    "rejected_screening": 9,
                    "sufficient_oos_evidence_candidates": 1,
                    "qre_linkage_blocked_candidates": 1,
                    "sufficient_oos_but_unlinked_candidates": 1,
                },
            }
        ),
        encoding="utf-8",
    )
    execution_snapshot = {
        "report_kind": "qre_controlled_validation_execution",
        "selection_profile_name": "equities_exploratory_v1",
        "execution_status": "execution_completed",
        "controlled_validation_authorized": True,
        "runner_adapter_status": "connected",
        "executed_anything": True,
        "final_recommendation": "controlled_validation_execution_completed",
        "controlled_eval_result": {
            "returncode": 0,
            "report_paths": {"report_json": report_path.as_posix()},
        },
    }

    snapshot = analysis.collect_snapshot(
        execution_snapshot=execution_snapshot,
        generated_at_utc="2026-06-03T23:00:00Z",
        current_git_revision="abc123",
    )

    assert snapshot["result_summary"]["evidence_quality_bottleneck"]["primary_bottleneck"] == (
        "registry_ledger_invariant_violation"
    )
    assert snapshot["result_summary"]["evidence_quality_bottleneck"]["reason_codes"] == [
        "registry_ledger_invariant_violation"
    ]
