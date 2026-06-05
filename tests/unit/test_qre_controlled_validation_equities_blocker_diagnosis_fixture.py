from __future__ import annotations

import json
from pathlib import Path

from reporting import qre_controlled_validation_result_analysis as analysis


FIXTURE_PATH = (
    Path(__file__).resolve().parent.parent
    / "fixtures"
    / "qre_controlled_validation"
    / "equities_exploratory_v1_blocker_diagnosis.json"
)


def test_equities_exploratory_blocker_diagnosis_fixture_reproduces_known_summary(
    tmp_path: Path,
) -> None:
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    report_path = tmp_path / "controlled_eval_latest.v1.json"
    report_path.write_text(
        json.dumps(fixture["controlled_eval_report"]),
        encoding="utf-8",
    )
    execution_snapshot = dict(fixture["execution_snapshot"])
    execution_snapshot["controlled_eval_result"] = {
        "returncode": 0,
        "report_paths": {"report_json": report_path.as_posix()},
    }

    snapshot = analysis.collect_snapshot(
        execution_snapshot=execution_snapshot,
        generated_at_utc="2026-06-05T23:30:00Z",
        current_git_revision="abc123",
        screening_evidence_payload=fixture["screening_evidence_payload"],
    )

    summary = snapshot["operator_summary"]
    assert summary["total_candidates"] == 15
    assert summary["linked_catalog_active_discovery_count"] == 15
    assert summary["sufficient_oos_evidence_count"] == 1
    assert summary["promotion_allowed_count"] == 0
    assert summary["promotion_blocked_count"] == 15
    assert summary["runtime_gate_failed_assets"] == [
        "AMD",
        "AMZN",
        "AVGO",
        "GOOGL",
        "LLY",
        "META",
        "MSFT",
        "NVDA",
        "TSM",
    ]
    assert summary["public_result_criteria_blocked_assets"] == [
        "AAPL",
        "ASML",
        "COST",
        "HD",
        "JPM",
        "XOM",
    ]
    assert summary["near_pass_assets"] == []
    assert summary["top_failure_reasons"] == [
        {"reason": "insufficient_trades", "count": 9}
    ]
    assert summary["top_promotion_blockers"] == [
        {"reason": "criteria_expectancy_above_zero_failed", "count": 9},
        {"reason": "criteria_profit_factor_at_or_above_floor_failed", "count": 9},
        {"reason": "criteria_sufficient_trades_failed", "count": 9},
        {"reason": "criteria_consistentie_failed", "count": 6},
        {"reason": "criteria_trades_per_maand_failed", "count": 6},
    ]

    hd_row = next(
        row for row in summary["selected_asset_explanations"] if row["asset"] == "HD"
    )
    assert hd_row["qre_validation_linkage_status"] == "linked_catalog_active_discovery"
    assert hd_row["validation_evidence_status"] == "sufficient_oos_evidence"
    assert hd_row["oos_trade_count"] == 14
    assert hd_row["promotion_allowed"] is False
    assert hd_row["blocked_by"] == [
        "criteria_consistentie_failed",
        "criteria_trades_per_maand_failed",
        "criteria_win_rate_failed",
    ]
