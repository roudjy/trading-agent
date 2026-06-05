from __future__ import annotations

import json
from pathlib import Path

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


def _screening_payload() -> dict:
    return {
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
            }
        ]
    }


def test_controlled_sprint_rerun_smoke_contract_stays_safety_bounded(
    monkeypatch, tmp_path: Path
) -> None:
    screening_path = tmp_path / "research" / "screening_evidence_latest.v1.json"
    screening_path.parent.mkdir(parents=True, exist_ok=True)
    screening_path.write_text(json.dumps(_screening_payload()), encoding="utf-8")

    def fake_run_controlled_eval(**kwargs: object) -> int:
        report_json = kwargs["report_json"]
        report_md = kwargs["report_md"]
        report_json.parent.mkdir(parents=True, exist_ok=True)
        report_json.write_text(
            json.dumps(
                {
                    "verdict": {"status": "useful_observation", "reason_codes": []},
                    "campaigns_completed": 1,
                    "campaign_level_evidence_valid": True,
                    "recommended_next_action": "inspect_results",
                    "git_revision": "abc123",
                    "screening_evidence_summary": {
                        "present": True,
                        "total_candidates": 1,
                        "passed_screening": 1,
                        "rejected_screening": 0,
                        "promotion_grade_candidates": 0,
                        "sufficient_oos_evidence_candidates": 1,
                        "qre_linkage_blocked_candidates": 0,
                        "sufficient_oos_but_unlinked_candidates": 0,
                    },
                }
            ),
            encoding="utf-8",
        )
        report_md.write_text("# controlled eval\n", encoding="utf-8")
        kwargs["out"].write("controlled_eval: completed=1 verdict=useful_observation\n")
        return 0

    class FakeControlledEval:
        @staticmethod
        def run_controlled_eval(**kwargs: object) -> int:
            return fake_run_controlled_eval(**kwargs)

    monkeypatch.setattr(execution, "_load_controlled_eval_module", lambda: FakeControlledEval)
    monkeypatch.setattr(
        execution,
        "_campaign_invariant_preflight",
        lambda: {
            "status": "passed",
            "completed_campaign_count": 0,
            "campaign_completed_ledger_event_count": 0,
            "missing_completed_ledger_event_ids": [],
            "diagnostics": {},
        },
    )
    monkeypatch.setattr(execution, "ARTIFACT_DIR", tmp_path / "logs")
    monkeypatch.setattr(
        execution,
        "CONTROLLED_EVAL_REPORT_JSON",
        tmp_path / "logs" / "controlled_eval_latest.v1.json",
    )
    monkeypatch.setattr(
        execution,
        "CONTROLLED_EVAL_REPORT_MD",
        tmp_path / "logs" / "controlled_eval_latest.md",
    )
    monkeypatch.setattr(analysis, "SCREENING_EVIDENCE_LATEST", screening_path)

    execution_snapshot = execution.collect_snapshot(
        profile_name="equities_exploratory_v1",
        execute_controlled_validation=True,
        operator_go=execution.REQUIRED_OPERATOR_GO_PHRASE,
        connect_runner_adapter=True,
        timeout_seconds_per_campaign=60,
        controlled_validation_bridge_snapshot=_ready_bridge_snapshot(),
        generated_at_utc="2026-06-05T23:45:00Z",
    )
    analysis_snapshot = analysis.collect_snapshot(
        execution_snapshot=execution_snapshot,
        generated_at_utc="2026-06-05T23:46:00Z",
        current_git_revision="abc123",
    )

    assert execution_snapshot["execution_status"] == "execution_completed"
    assert execution_snapshot["mutates_paper_shadow_live_runtime"] is False
    assert execution_snapshot["writes_research_action_queue"] is False
    assert execution_snapshot["writes_development_work_queue"] is False
    report_paths = execution_snapshot["controlled_eval_result"]["report_paths"]
    assert report_paths["report_json"].endswith("controlled_eval_latest.v1.json")
    assert report_paths["report_md"].endswith("controlled_eval_latest.md")
    assert (tmp_path / "logs" / "controlled_eval_latest.v1.json").exists()
    assert (tmp_path / "logs" / "controlled_eval_latest.md").exists()

    assert analysis_snapshot["analysis_status"] == "analysis_ready"
    assert analysis_snapshot["mutates_paper_shadow_live_runtime"] is False
    assert analysis_snapshot["writes_research_action_queue"] is False
    assert analysis_snapshot["writes_development_work_queue"] is False
    hd_row = analysis_snapshot["operator_summary"]["selected_asset_explanations"][0]
    assert hd_row["asset"] == "HD"
    assert hd_row["qre_validation_linkage_status"] == "linked_catalog_active_discovery"
    assert hd_row["validation_evidence_status"] == "sufficient_oos_evidence"
    assert hd_row["oos_trade_count"] == 14
    assert hd_row["blocked_by"] == [
        "criteria_consistentie_failed",
        "criteria_trades_per_maand_failed",
        "criteria_win_rate_failed",
    ]


def test_stale_artifact_blocking_contract_explains_exact_operator_action(monkeypatch) -> None:
    stale_id = "col-20260604T203711765074Z-trend_pullback_equities_4h-3e5f6de0b6"
    monkeypatch.setattr(
        execution,
        "_campaign_invariant_preflight",
        lambda: {
            "status": "failed",
            "completed_campaign_count": 1,
            "campaign_completed_ledger_event_count": 0,
            "missing_completed_ledger_event_ids": [stale_id],
            "diagnostics": {
                "stale_campaign_ids": [stale_id],
                "active_stale_files": [
                    "research/campaign_registry_latest.v1.json",
                    "research/run_campaign_latest.v1.json",
                ],
                "completed_campaign_count_per_source": {
                    "research/campaign_registry_latest.v1.json": 1,
                },
                "ledger_event_count_per_source": {
                    "research/campaign_evidence_ledger_latest.v1.jsonl": 0,
                },
                "suggested_operator_action": "quarantine generated runtime artifacts",
                "safe_cleanup_available": True,
                "safe_cleanup_mode": "operator_quarantine_only",
                "quarantine_command_preview": [
                    "$target = 'logs/qre_controlled_validation_execution/quarantine/<timestamp>'"
                ],
            },
        },
    )

    snapshot = execution.collect_snapshot(
        profile_name="equities_exploratory_v1",
        execute_controlled_validation=True,
        operator_go=execution.REQUIRED_OPERATOR_GO_PHRASE,
        connect_runner_adapter=True,
        timeout_seconds_per_campaign=60,
        controlled_validation_bridge_snapshot=_ready_bridge_snapshot(),
        generated_at_utc="2026-06-05T23:47:00Z",
    )

    assert snapshot["execution_status"] == "execution_blocked_campaign_invariant_violation"
    assert snapshot["executed_anything"] is False
    assert snapshot["mutates_paper_shadow_live_runtime"] is False
    assert snapshot["writes_research_action_queue"] is False
    assert snapshot["writes_development_work_queue"] is False
    assert snapshot["campaign_invariant_preflight"]["diagnostics"] == {
        "stale_campaign_ids": [stale_id],
        "active_stale_files": [
            "research/campaign_registry_latest.v1.json",
            "research/run_campaign_latest.v1.json",
        ],
        "completed_campaign_count_per_source": {
            "research/campaign_registry_latest.v1.json": 1,
        },
        "ledger_event_count_per_source": {
            "research/campaign_evidence_ledger_latest.v1.jsonl": 0,
        },
        "suggested_operator_action": "quarantine generated runtime artifacts",
        "safe_cleanup_available": True,
        "safe_cleanup_mode": "operator_quarantine_only",
        "quarantine_command_preview": [
            "$target = 'logs/qre_controlled_validation_execution/quarantine/<timestamp>'"
        ],
    }
