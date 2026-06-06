from __future__ import annotations

import json
from pathlib import Path

from research import qre_controlled_discovery_survivor_stage_attribution as survivor


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


def _seed_run_row(tmp_path: Path, row: dict, sidecar: dict | None = None) -> None:
    row = dict(row)
    if sidecar is not None:
        row["artifact_paths"] = {
            "execution_result": "research/controlled_discovery_grid_runs/run-001/combination_001/execution_result.v1.json"
        }
        _write_json(
            tmp_path
            / "research"
            / "controlled_discovery_grid_runs"
            / "run-001"
            / "combination_001"
            / "execution_result.v1.json",
            sidecar,
        )
    _write_jsonl(
        tmp_path / "research" / "controlled_discovery_grid_runs" / "run-001" / "combination_results.v1.jsonl",
        [row],
    )


def _seed_metric_and_preset_sidecars(tmp_path: Path, *, metric: str = "", preset: str = "") -> None:
    _write_json(
        tmp_path / "logs" / "qre_controlled_discovery_metric_consistency_audit" / "latest.json",
        {
            "rows": [
                {
                    "instrument_symbol": "AAPL",
                    "behavior_preset_id": "trend_continuation_daily_v1",
                    "classification": metric or "clean_consistent",
                    "affected_basket_ids": [],
                }
            ]
        },
    )
    _write_json(
        tmp_path / "logs" / "qre_controlled_discovery_preset_executability" / "latest.json",
        {
            "rows": [
                {
                    "instrument_symbol": "AAPL",
                    "behavior_preset_id": "trend_continuation_daily_v1",
                    "classification": preset or "executable",
                    "affected_basket_ids": [],
                }
            ]
        },
    )


def test_no_candidates_generated_and_oos_stage_are_attributed(tmp_path: Path) -> None:
    _seed_metric_and_preset_sidecars(tmp_path)
    _seed_run_row(
        tmp_path,
        {
            "sequence_number": 1,
            "instrument_symbol": "AAPL",
            "behavior_preset_id": "trend_continuation_daily_v1",
            "blocker_class": "degenerate_no_survivors",
        },
        {
            "observation": {"candidate_count": 0},
            "artifact_snapshot": {"matching_screening_rows": []},
        },
    )

    report = survivor.build_survivor_stage_attribution(repo_root=tmp_path)
    assert report["rows"][0]["stage_classification"] == "no_candidates_generated"

    _seed_run_row(
        tmp_path,
        {
            "sequence_number": 1,
            "instrument_symbol": "AAPL",
            "behavior_preset_id": "trend_continuation_daily_v1",
            "blocker_class": "degenerate_no_survivors",
        },
        {
            "observation": {"candidate_count": 1},
            "artifact_snapshot": {
                "matching_screening_rows": [
                    {"validation_evidence": {"status": "no_oos_trades"}}
                ]
            },
        },
    )
    report = survivor.build_survivor_stage_attribution(repo_root=tmp_path)
    assert report["rows"][0]["stage_classification"] == "oos_stage_no_survivors"


def test_criteria_metric_source_identity_and_preset_mapping_are_attributed(tmp_path: Path) -> None:
    _seed_metric_and_preset_sidecars(tmp_path)
    _seed_run_row(
        tmp_path,
        {
            "sequence_number": 1,
            "instrument_symbol": "AAPL",
            "behavior_preset_id": "trend_continuation_daily_v1",
            "blocker_class": "degenerate_no_survivors",
        },
        {
            "observation": {"candidate_count": 1},
            "artifact_snapshot": {
                "matching_screening_rows": [
                    {"promotion_guard": {"blocked_by": ["consistentie"]}}
                ]
            },
        },
    )
    report = survivor.build_survivor_stage_attribution(repo_root=tmp_path)
    assert report["rows"][0]["stage_classification"] == "criteria_stage_no_survivors"

    _seed_metric_and_preset_sidecars(tmp_path, metric="inconsistent_oos_gt_total")
    report = survivor.build_survivor_stage_attribution(repo_root=tmp_path)
    assert report["rows"][0]["stage_classification"] == "metric_consistency_stage_no_survivors"

    _seed_metric_and_preset_sidecars(tmp_path, metric="clean_consistent", preset="source_identity_blocked")
    report = survivor.build_survivor_stage_attribution(repo_root=tmp_path)
    assert report["rows"][0]["stage_classification"] == "source_identity_stage_blocked"

    _seed_metric_and_preset_sidecars(tmp_path, metric="clean_consistent", preset="mapping_missing")
    report = survivor.build_survivor_stage_attribution(repo_root=tmp_path)
    assert report["rows"][0]["stage_classification"] == "preset_mapping_stage_blocked"


def test_artifact_missing_adapter_join_and_unknown_fail_closed_are_supported(tmp_path: Path) -> None:
    _seed_metric_and_preset_sidecars(tmp_path)
    _seed_run_row(
        tmp_path,
        {
            "sequence_number": 1,
            "instrument_symbol": "AAPL",
            "behavior_preset_id": "trend_continuation_daily_v1",
            "blocker_class": "degenerate_no_survivors",
        },
    )
    report = survivor.build_survivor_stage_attribution(repo_root=tmp_path)
    assert report["rows"][0]["stage_classification"] == "artifact_missing_stage_blocked"

    _seed_run_row(
        tmp_path,
        {
            "sequence_number": 1,
            "instrument_symbol": "AAPL",
            "behavior_preset_id": "trend_continuation_daily_v1",
            "blocker_class": "degenerate_no_survivors",
            "degenerate_stage_hint": "adapter_join_stage_blocked",
        },
        {"observation": {"candidate_count": 1}, "artifact_snapshot": {"matching_screening_rows": []}},
    )
    report = survivor.build_survivor_stage_attribution(repo_root=tmp_path)
    assert report["rows"][0]["stage_classification"] == "adapter_join_stage_blocked"

    _seed_run_row(
        tmp_path,
        {
            "sequence_number": 1,
            "instrument_symbol": "AAPL",
            "behavior_preset_id": "trend_continuation_daily_v1",
            "blocker_class": "degenerate_no_survivors",
            "degenerate_stage_hint": "unknown_fail_closed",
        },
        {"observation": {"candidate_count": 1}, "artifact_snapshot": {"matching_screening_rows": []}},
    )
    report = survivor.build_survivor_stage_attribution(repo_root=tmp_path)
    assert report["rows"][0]["stage_classification"] == "unknown_fail_closed"
