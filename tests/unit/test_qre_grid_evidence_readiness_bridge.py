from __future__ import annotations

import json
from pathlib import Path

from research import qre_grid_evidence_readiness_bridge as bridge


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _materialization_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "basket_id": "seed::trend_pullback_continuation_daily_v1::AAPL",
        "asset": "AAPL",
        "canonical_symbol": "AAPL",
        "provider_symbol": "AAPL",
        "timeframe": "1d",
        "preset": "trend_pullback_continuation_daily_v1",
        "matched_grid_rows_count": 1,
        "matched_grid_rows": [
            {
                "run_id": "grid-run-1",
                "sequence_number": 1,
                "instrument_symbol": "AAPL",
                "behavior_preset_id": "trend_pullback_continuation_daily_v1",
                "status": "completed",
                "outcome_class": "sufficient_oos_evidence",
                "criteria_status": "criteria_consistentie_failed",
            }
        ],
        "evidence_exists_in_grid": True,
        "source_identity_status": "provider_symbol_verified",
        "source_identity_blocker": "",
        "metric_consistency_status": "clean_consistent",
        "preset_executability_classification": "executable",
        "candidate_lineage_status": "visible",
        "oos_evidence_status": "sufficient_oos_evidence_present",
        "sufficient_oos_evidence_status": "present",
        "join_key_status": "grid_row_match_found",
        "exact_next_action": "review_criteria_failures",
        "survivor_stage_classification": "degenerate_legitimate_no_survivors",
    }
    row.update(overrides)
    return row


def test_bridge_marks_clean_sufficient_oos_as_readiness_visible_not_promotable(
    tmp_path: Path,
) -> None:
    _write_json(
        tmp_path / "logs" / "qre_discovery_basket_grid_evidence_materialization" / "latest.json",
        {"rows": [_materialization_row()]},
    )

    report = bridge.build_grid_evidence_readiness_bridge(repo_root=tmp_path, max_candidates=1)

    row = report["rows"][0]
    assert row["readiness_screening_evidence_visible"] is True
    assert row["readiness_oos_evidence_visible"] is True
    assert row["readiness_sufficient_oos_visible"] is True
    assert row["readiness_bridge_status"] == "bridged_sufficient_oos_but_not_promotion_ready"
    assert row["promotion_allowed"] is False
    assert row["promotion_candidate_from_grid"] is False


def test_bridge_blocks_metric_inconsistent_grid_rows(
    tmp_path: Path,
) -> None:
    _write_json(
        tmp_path / "logs" / "qre_discovery_basket_grid_evidence_materialization" / "latest.json",
        {
            "rows": [
                _materialization_row(
                    metric_consistency_status="inconsistent_oos_gt_total",
                    exact_next_action="inspect_metric_consistency",
                )
            ]
        },
    )

    report = bridge.build_grid_evidence_readiness_bridge(repo_root=tmp_path, max_candidates=1)

    row = report["rows"][0]
    assert row["readiness_oos_evidence_visible"] is False
    assert row["readiness_sufficient_oos_visible"] is False
    assert row["readiness_bridge_status"] == "blocked_metric_inconsistent"


def test_bridge_blocks_missing_lineage_even_when_sufficient_oos_exists(
    tmp_path: Path,
) -> None:
    _write_json(
        tmp_path / "logs" / "qre_discovery_basket_grid_evidence_materialization" / "latest.json",
        {"rows": [_materialization_row(candidate_lineage_status="missing")]},
    )

    report = bridge.build_grid_evidence_readiness_bridge(repo_root=tmp_path, max_candidates=1)

    row = report["rows"][0]
    assert row["readiness_screening_evidence_visible"] is True
    assert row["readiness_oos_evidence_visible"] is True
    assert row["readiness_sufficient_oos_visible"] is False
    assert row["readiness_bridge_status"] == "blocked_candidate_lineage_missing"


def test_bridge_fails_closed_when_no_grid_match_exists(
    tmp_path: Path,
) -> None:
    _write_json(
        tmp_path / "logs" / "qre_discovery_basket_grid_evidence_materialization" / "latest.json",
        {
            "rows": [
                _materialization_row(
                    matched_grid_rows_count=0,
                    matched_grid_rows=[],
                    evidence_exists_in_grid=False,
                    join_key_status="grid_row_match_not_found",
                    oos_evidence_status="missing",
                    sufficient_oos_evidence_status="missing",
                )
            ]
        },
    )

    report = bridge.build_grid_evidence_readiness_bridge(repo_root=tmp_path, max_candidates=1)

    row = report["rows"][0]
    assert row["readiness_bridge_status"] == "blocked_no_grid_match"
    assert row["readiness_screening_evidence_visible"] is False


def test_bridge_render_and_write_outputs_are_deterministic(
    tmp_path: Path,
) -> None:
    _write_json(
        tmp_path / "logs" / "qre_discovery_basket_grid_evidence_materialization" / "latest.json",
        {"rows": [_materialization_row()]},
    )
    report = bridge.build_grid_evidence_readiness_bridge(repo_root=tmp_path, max_candidates=1)
    markdown = bridge.render_operator_summary(report)
    paths = bridge.write_outputs(report, repo_root=tmp_path)

    assert "# QRE Grid Evidence Readiness Bridge" in markdown
    assert paths["latest"] == "logs/qre_grid_evidence_readiness_bridge/latest.json"
    assert paths["operator_summary"] == "logs/qre_grid_evidence_readiness_bridge/operator_summary.md"
