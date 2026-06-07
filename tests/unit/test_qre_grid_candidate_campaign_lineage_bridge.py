from __future__ import annotations

import json
from pathlib import Path

from research import qre_grid_candidate_campaign_lineage_bridge as bridge


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "basket_id": "seed::trend_pullback_continuation_daily_v1::AAPL",
        "asset": "AAPL",
        "preset": "trend_pullback_continuation_daily_v1",
        "join_key_status": "grid_row_match_found",
        "matched_grid_rows_count": 1,
        "candidate_lineage_status": "visible",
    }
    row.update(overrides)
    return row


def test_lineage_bridge_fails_closed_without_grid_match(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "logs" / "qre_discovery_basket_grid_evidence_materialization" / "latest.json",
        {"rows": [_row(join_key_status="grid_row_match_not_found", matched_grid_rows_count=0)]},
    )
    report = bridge.build_grid_candidate_campaign_lineage_bridge(repo_root=tmp_path, max_candidates=1)
    row = report["rows"][0]
    assert row["lineage_bridge_status"] == "blocked_no_grid_match"
    assert row["exact_next_action"] == "restore_or_run_grid_artifacts"


def test_lineage_bridge_surfaces_partial_and_full_lineage(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "logs" / "qre_discovery_basket_grid_evidence_materialization" / "latest.json",
        {
            "rows": [
                _row(asset="AAPL", candidate_lineage_status="visible"),
                _row(asset="ASML", candidate_lineage_status="candidate_visible_campaign_missing"),
                _row(asset="BESI", candidate_lineage_status="missing"),
            ]
        },
    )
    report = bridge.build_grid_candidate_campaign_lineage_bridge(repo_root=tmp_path, max_candidates=3)
    rows = {row["asset"]: row for row in report["rows"]}
    assert rows["AAPL"]["lineage_bridge_status"] == "lineage_visible"
    assert rows["ASML"]["lineage_bridge_status"] == "blocked_campaign_lineage_missing"
    assert rows["BESI"]["lineage_bridge_status"] == "blocked_candidate_and_campaign_lineage_missing"


def test_lineage_bridge_writes_outputs(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "logs" / "qre_discovery_basket_grid_evidence_materialization" / "latest.json",
        {"rows": [_row()]},
    )
    report = bridge.build_grid_candidate_campaign_lineage_bridge(repo_root=tmp_path, max_candidates=1)
    paths = bridge.write_outputs(report, repo_root=tmp_path)
    markdown = (tmp_path / paths["operator_summary"]).read_text(encoding="utf-8")
    assert paths["latest"] == "logs/qre_grid_candidate_campaign_lineage_bridge/latest.json"
    assert "# QRE Grid Candidate / Campaign Lineage Bridge" in markdown
