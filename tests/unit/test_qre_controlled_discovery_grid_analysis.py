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
