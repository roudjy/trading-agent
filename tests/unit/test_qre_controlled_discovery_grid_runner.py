from __future__ import annotations

import json

from reporting import qre_controlled_discovery_grid_runner as runner


def test_plan_snapshot_reports_expected_328_grid() -> None:
    snapshot = runner.plan_snapshot()

    assert snapshot["instrument_count"] == 41
    assert snapshot["behavior_preset_count"] == 8
    assert snapshot["total_combinations"] == 328
    assert snapshot["paper_activation_allowed"] is False
    assert snapshot["shadow_activation_allowed"] is False
    assert snapshot["live_activation_allowed"] is False


def test_execute_range_writes_sidecar_only_artifacts(tmp_path) -> None:
    payload = runner.execute_range(
        start=1,
        end=5,
        output_dir=tmp_path,
        run_id="run-001",
        resume=False,
    )

    run_dir = tmp_path / "run-001"
    assert payload["selected_count"] == 5
    assert payload["written_count"] == 5
    assert payload["execution_integration_deferred"] is True
    assert (run_dir / "grid_plan.v1.json").exists()
    assert (run_dir / "combination_results.v1.jsonl").exists()
    assert (run_dir / "summary_latest.v1.json").exists()
    assert (run_dir / "operator_summary.md").exists()
    results = [
        json.loads(line)
        for line in (run_dir / "combination_results.v1.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    assert len(results) == 5
    assert {row["status"] for row in results} == {"execution_integration_deferred"}
    assert {row["blocker_class"] for row in results} == {"execution_integration_deferred"}
    assert {row["outcome_class"] for row in results} == {"unknown"}


def test_execute_range_resume_skips_existing_sequence_numbers(tmp_path) -> None:
    first = runner.execute_range(
        start=1,
        end=3,
        output_dir=tmp_path,
        run_id="run-002",
        resume=False,
    )
    second = runner.execute_range(
        start=1,
        end=5,
        output_dir=tmp_path,
        run_id="run-002",
        resume=True,
    )

    assert first["written_count"] == 3
    assert second["selected_count"] == 5
    assert second["written_count"] == 2
