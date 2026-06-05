from __future__ import annotations

import json
from pathlib import Path

from reporting import qre_controlled_discovery_grid_analysis as analysis


def test_build_summary_counts_deferred_rows_as_unknown() -> None:
    summary = analysis.build_summary(
        run_dir=Path("research/controlled_discovery_grid_runs/run-001"),
        results=[
            {
                "sequence_number": 1,
                "status": "execution_integration_deferred",
                "blocker_class": "execution_integration_deferred",
                "outcome_class": "unknown",
                "region": "NL/EU",
                "instrument_symbol": "ASML",
                "behavior_preset_id": "trend_continuation_daily_v1",
            },
            {
                "sequence_number": 2,
                "status": "execution_integration_deferred",
                "blocker_class": "execution_integration_deferred",
                "outcome_class": "unknown",
                "region": "US",
                "instrument_symbol": "AAPL",
                "behavior_preset_id": "trend_continuation_daily_v1",
            },
        ],
    )

    assert summary["counts"]["total_combinations_planned"] == 2
    assert summary["counts"]["total_attempted"] == 2
    assert summary["counts"]["execution_integration_deferred"] == 2
    assert summary["counts"]["unknown"] == 2
    assert summary["counts"]["promotion_candidate"] == 0
    assert summary["next_action"] == "DEFER_EXECUTION_INTEGRATION"


def test_summarize_run_writes_summary_and_operator_markdown(tmp_path) -> None:
    run_dir = tmp_path / "run-003"
    run_dir.mkdir()
    (run_dir / "combination_results.v1.jsonl").write_text(
        json.dumps(
            {
                "status": "execution_integration_deferred",
                "blocker_class": "execution_integration_deferred",
                "outcome_class": "unknown",
                "region": "Asia/proxies",
                "instrument_symbol": "TSM",
                "behavior_preset_id": "post_shock_stabilization_daily_v1",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    summary = analysis.summarize_run(input_dir=run_dir, write_summary=True)

    assert summary["result_count"] == 1
    assert (run_dir / "summary_latest.v1.json").exists()
    assert (run_dir / "operator_summary.md").exists()
    assert "NEXT_ACTION: DEFER_EXECUTION_INTEGRATION" in (
        run_dir / "operator_summary.md"
    ).read_text(encoding="utf-8")


def test_build_summary_counts_completed_skipped_failed_and_dedupes_latest_rows() -> None:
    summary = analysis.build_summary(
        run_dir=Path("research/controlled_discovery_grid_runs/run-002"),
        total_planned=328,
        results=[
            {
                "sequence_number": 1,
                "status": "completed",
                "blocker_class": None,
                "outcome_class": "near_pass",
                "near_pass": True,
                "promotion_candidate": False,
                "region": "NL/EU",
                "instrument_symbol": "ASML",
                "behavior_preset_id": "trend_continuation_daily_v1",
                "trades_total": 12.0,
                "oos_trades": 4,
            },
            {
                "sequence_number": 2,
                "status": "skipped",
                "blocker_class": "preset_not_executable",
                "outcome_class": "skipped",
                "near_pass": False,
                "promotion_candidate": False,
                "region": "US",
                "instrument_symbol": "AAPL",
                "behavior_preset_id": "relative_strength_vs_sector_daily_v1",
            },
            {
                "sequence_number": 3,
                "status": "failed",
                "blocker_class": "controlled_validation_failed",
                "outcome_class": "unknown",
                "near_pass": False,
                "promotion_candidate": False,
                "region": "US",
                "instrument_symbol": "MSFT",
                "behavior_preset_id": "vol_compression_breakout_daily_v1",
            },
            {
                "sequence_number": 3,
                "status": "completed",
                "blocker_class": None,
                "outcome_class": "promotion_candidate",
                "near_pass": False,
                "promotion_candidate": True,
                "region": "US",
                "instrument_symbol": "MSFT",
                "behavior_preset_id": "vol_compression_breakout_daily_v1",
                "trades_total": 18.0,
                "oos_trades": 11,
                "criteria_status": "promotion_allowed",
            },
        ],
    )

    assert summary["counts"]["total_combinations_planned"] == 328
    assert summary["counts"]["total_attempted"] == 3
    assert summary["counts"]["total_completed"] == 2
    assert summary["counts"]["total_skipped"] == 1
    assert summary["counts"]["total_failed"] == 0
    assert summary["counts"]["execution_integration_deferred"] == 0
    assert summary["counts"]["near_pass"] == 1
    assert summary["counts"]["promotion_candidate"] == 1
    assert summary["next_action"] == "MERGE_AND_RUN_ON_VPS"
    assert summary["top_promotion_candidates"][0]["instrument_symbol"] == "MSFT"


def test_sufficient_oos_evidence_rows_explain_criteria_blockers() -> None:
    summary = analysis.build_summary(
        run_dir=Path("research/controlled_discovery_grid_runs/run-004"),
        results=[
            {
                "sequence_number": 10,
                "status": "completed",
                "blocker_class": "criteria_consistentie_failed",
                "outcome_class": "sufficient_oos_evidence",
                "near_pass": False,
                "promotion_candidate": False,
                "safe_to_promote": False,
                "region": "FR/EU",
                "instrument_symbol": "AIR",
                "behavior_preset_id": "trend_continuation_daily_v1",
                "trades_total": 30.0,
                "oos_trades": 20,
                "hd_trades": 10.0,
                "criteria_status": "criteria_consistentie_failed,criteria_deflated_sharpe_failed,criteria_trades_per_maand_failed",
                "artifact_paths": {"execution_result": "tmp/execution_result.v1.json"},
                "result_path": "tmp/execution_result.v1.json",
            }
        ],
    )

    assert summary["counts"]["sufficient_oos_evidence"] == 1
    assert summary["counts"]["oos_evidence_no_promotion_due_to_criteria"] == 1
    row = summary["sufficient_oos_evidence_blockers"][0]
    assert row["primary_blocker"] == "oos_evidence_no_promotion_due_to_criteria"
    assert row["criteria_failure_classes"] == [
        "criteria_consistentie_failed",
        "criteria_deflated_sharpe_failed",
        "criteria_trades_per_maand_failed",
    ]
    assert row["metric_consistency_status"] == "consistent"
    assert row["follow_up"] == "review_criteria_failures"
    assert summary["top_oos_follow_up_diagnostics"][0]["promotion_candidate"] is False
    assert summary["top_oos_follow_up_diagnostics"][0]["safe_to_promote"] is False
    assert summary["top_oos_follow_up_diagnostics"][0]["near_pass"] is False


def test_oos_metric_inconsistency_is_flagged_explicitly() -> None:
    summary = analysis.build_summary(
        run_dir=Path("research/controlled_discovery_grid_runs/run-005"),
        results=[
            {
                "sequence_number": 11,
                "status": "completed",
                "blocker_class": "criteria_trades_per_maand_failed",
                "outcome_class": "sufficient_oos_evidence",
                "near_pass": False,
                "promotion_candidate": False,
                "safe_to_promote": False,
                "region": "FR/EU",
                "instrument_symbol": "TTE",
                "behavior_preset_id": "trend_pullback_continuation_daily_v1",
                "trades_total": 11.0,
                "oos_trades": 20,
                "hd_trades": 0.0,
                "criteria_status": "criteria_trades_per_maand_failed",
                "artifact_paths": {"execution_result": "tmp/execution_result.v1.json"},
                "result_path": "tmp/execution_result.v1.json",
            }
        ],
    )

    assert summary["counts"]["oos_evidence_metric_inconsistent"] == 1
    row = summary["sufficient_oos_evidence_blockers"][0]
    assert row["primary_blocker"] == "oos_evidence_metric_inconsistent"
    assert row["metric_consistency_status"] == "inconsistent"
    assert row["metric_consistency_warnings"] == ["oos_hd_exceeds_trades_total"]


def test_unknown_rows_reduce_to_known_source_identity_reason_when_present() -> None:
    summary = analysis.build_summary(
        run_dir=Path("research/controlled_discovery_grid_runs/run-006"),
        results=[
            {
                "sequence_number": 12,
                "status": "completed",
                "blocker_class": None,
                "outcome_class": "unknown",
                "near_pass": False,
                "promotion_candidate": False,
                "safe_to_promote": False,
                "region": "NL/EU",
                "instrument_symbol": "ADYEN",
                "behavior_preset_id": "trend_continuation_daily_v1",
                "provider_symbol_status": "candidate_alias_requires_verification",
            }
        ],
    )

    assert summary["counts"]["unknown"] == 0
    assert summary["by_outcome_class"] == [
        {"value": "source_identity_candidate_alias_unverified", "count": 1}
    ]


def test_operator_summary_includes_oos_blocker_explanation_section() -> None:
    summary = analysis.build_summary(
        run_dir=Path("research/controlled_discovery_grid_runs/run-007"),
        results=[
            {
                "sequence_number": 13,
                "status": "completed",
                "blocker_class": "criteria_win_rate_failed",
                "outcome_class": "sufficient_oos_evidence",
                "near_pass": False,
                "promotion_candidate": False,
                "safe_to_promote": False,
                "region": "US",
                "instrument_symbol": "AMD",
                "behavior_preset_id": "trend_continuation_daily_v1",
                "trades_total": 13.0,
                "oos_trades": 13,
                "hd_trades": 0.0,
                "criteria_status": "criteria_consistentie_failed,criteria_win_rate_failed",
                "artifact_paths": {"execution_result": "tmp/execution_result.v1.json"},
                "result_path": "tmp/execution_result.v1.json",
            }
        ],
    )

    markdown = analysis.render_operator_summary(summary)

    assert "## 5. Sufficient OOS evidence blocker explanation" in markdown
    assert "## 6. Top OOS follow-up diagnostics" in markdown
    assert "| Sequence | Instrument | Preset | OOS trades | HD trades | Trades total | Promotion | Primary blocker | Criteria failures | Metric consistency | Follow-up |" in markdown
    assert "| 13 | AMD | trend_continuation_daily_v1 | 13.0 | 0.0 | 13.0 | false | oos_evidence_no_promotion_due_to_criteria | criteria_consistentie_failed, criteria_win_rate_failed | consistent | review_criteria_failures |" in markdown
