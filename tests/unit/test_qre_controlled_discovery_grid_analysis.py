from __future__ import annotations

import json
from pathlib import Path

from reporting import qre_controlled_discovery_grid_analysis as analysis


def test_build_summary_counts_deferred_rows_as_unknown() -> None:
    summary = analysis.build_summary(
        run_dir=Path("research/controlled_discovery_grid_runs/run-001"),
        results=[
            {
                "status": "execution_integration_deferred",
                "blocker_class": "execution_integration_deferred",
                "outcome_class": "unknown",
                "region": "NL/EU",
                "instrument_symbol": "ASML",
                "behavior_preset_id": "trend_continuation_daily_v1",
            },
            {
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
