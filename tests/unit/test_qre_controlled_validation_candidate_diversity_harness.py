from __future__ import annotations

import json
from pathlib import Path

from reporting import qre_controlled_validation_result_analysis as analysis


FIXTURE_PATH = (
    Path(__file__).resolve().parent.parent
    / "fixtures"
    / "qre_controlled_validation"
    / "candidate_diversity_harness.json"
)


def test_candidate_diversity_harness_proves_multiple_candidates_and_outcomes(
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
        generated_at_utc="2026-06-06T10:00:00Z",
        current_git_revision="abc123",
        screening_evidence_payload=fixture["screening_evidence_payload"],
    )

    summary = snapshot["operator_summary"]
    assert summary["total_candidates"] == 15
    assert summary["promotion_allowed_count"] == 1
    assert summary["near_pass_count"] == 1
    assert summary["candidate_diversity"] == {
        "preset_count": 8,
        "hypothesis_count": 7,
        "region_count": 4,
        "fixture_candidate_count": 15,
        "promotion_eligible_fixture_candidate_count": 1,
        "outcome_class_summary": [
            {"reason": "reject_insufficient_trades", "count": 4},
            {"reason": "reject_criteria_consistentie_failed", "count": 2},
            {"reason": "reject_criteria_trades_per_maand_failed", "count": 2},
            {"reason": "reject_criteria_win_rate_failed", "count": 2},
            {"reason": "reject_no_oos_evidence", "count": 2},
            {"reason": "near_pass", "count": 1},
            {"reason": "promotion_eligible_fixture_candidate", "count": 1},
            {"reason": "sufficient_oos_but_not_promoted", "count": 1},
        ],
    }

    rows = summary["selected_asset_explanations"]
    assert [row["asset"] for row in rows[:4]] == ["ADYEN", "AIR", "ASML", "BABA"]
    assert len({row["preset_name"] for row in rows}) == 8
    assert len({row["hypothesis_id"] for row in rows}) == 7
    assert len({row["region"] for row in rows}) == 4

    prx_row = next(row for row in rows if row["asset"] == "PRX")
    assert prx_row["promotion_allowed"] is True
    assert prx_row["outcome_class"] == "promotion_eligible_fixture_candidate"
    assert prx_row["fixture_candidate"] is True
    assert prx_row["not_real_market_evidence"] is True
    assert prx_row["no_paper_activation"] is True
    assert prx_row["no_live_activation"] is True
    assert prx_row["no_shadow_activation"] is True

    ewj_row = next(row for row in rows if row["asset"] == "EWJ")
    assert ewj_row["near_pass"] is True
    assert ewj_row["outcome_class"] == "near_pass"

    assert summary["runtime_gate_failed_assets"] == [
        "ADYEN",
        "GOOGL",
        "NESN",
        "TSLA",
    ]
