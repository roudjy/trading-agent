from __future__ import annotations

import json
from types import SimpleNamespace

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
    fake_execution = SimpleNamespace(
        execute_grid_row=lambda item, output_dir: {
            **item,
            "status": "completed",
            "outcome_class": "promotion_candidate",
            "blocker_class": None,
            "error_class": None,
            "trades_total": 12.0,
            "oos_trades": 10,
            "hd_trades": 2.0,
            "criteria_status": "promotion_allowed",
            "promotion_candidate": True,
            "near_pass": False,
            "safe_to_promote": True,
            "artifact_paths": {"execution_result": (output_dir / "execution_result.v1.json").as_posix()},
            "result_path": (output_dir / "execution_result.v1.json").as_posix(),
            "validation_campaign_id": f"cmp-{item['sequence_number']}",
            "strategy_or_preset_reference": "trend_equities_4h_baseline",
            "run_label": f"run-{item['sequence_number']}",
            "output_subdir": output_dir.name,
            "started_at_utc": "2026-06-05T12:00:00Z",
            "finished_at_utc": "2026-06-05T12:00:01Z",
            "duration_seconds": 1.0,
            "execution_notes": ["stubbed"],
        }
    )
    runner._execution_module = lambda: fake_execution  # type: ignore[assignment]

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
    assert payload["execution_integration_deferred"] is False
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
    assert {row["status"] for row in results} == {"completed"}
    assert {row["outcome_class"] for row in results} == {"promotion_candidate"}


def test_execute_range_resume_skips_existing_sequence_numbers(tmp_path) -> None:
    fake_execution = SimpleNamespace(
        execute_grid_row=lambda item, output_dir: {
            **item,
            "status": "skipped" if int(item["sequence_number"]) % 2 == 0 else "completed",
            "outcome_class": "skipped" if int(item["sequence_number"]) % 2 == 0 else "screening_pass",
            "blocker_class": "preset_not_executable" if int(item["sequence_number"]) % 2 == 0 else None,
            "error_class": None,
            "trades_total": 8.0,
            "oos_trades": 0,
            "hd_trades": 8.0,
            "criteria_status": None,
            "promotion_candidate": False,
            "near_pass": False,
            "safe_to_promote": False,
            "artifact_paths": {"execution_result": (output_dir / "execution_result.v1.json").as_posix()},
            "result_path": (output_dir / "execution_result.v1.json").as_posix(),
            "validation_campaign_id": f"cmp-{item['sequence_number']}",
            "strategy_or_preset_reference": "trend_pullback_equities_4h",
            "run_label": f"run-{item['sequence_number']}",
            "output_subdir": output_dir.name,
            "started_at_utc": "2026-06-05T12:00:00Z",
            "finished_at_utc": "2026-06-05T12:00:01Z",
            "duration_seconds": 1.0,
            "execution_notes": ["stubbed"],
        }
    )
    runner._execution_module = lambda: fake_execution  # type: ignore[assignment]

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


def test_execute_range_accepts_output_dir_as_run_dir_without_explicit_run_id(tmp_path) -> None:
    fake_execution = SimpleNamespace(
        execute_grid_row=lambda item, output_dir: {
            **item,
            "status": "failed",
            "outcome_class": "unknown",
            "blocker_class": "controlled_validation_failed",
            "error_class": "RuntimeError",
            "trades_total": None,
            "oos_trades": None,
            "hd_trades": None,
            "criteria_status": None,
            "promotion_candidate": False,
            "near_pass": False,
            "safe_to_promote": False,
            "artifact_paths": {"execution_result": (output_dir / "execution_result.v1.json").as_posix()},
            "result_path": (output_dir / "execution_result.v1.json").as_posix(),
            "validation_campaign_id": f"cmp-{item['sequence_number']}",
            "strategy_or_preset_reference": "trend_equities_4h_baseline",
            "run_label": f"run-{item['sequence_number']}",
            "output_subdir": output_dir.name,
            "started_at_utc": "2026-06-05T12:00:00Z",
            "finished_at_utc": "2026-06-05T12:00:01Z",
            "duration_seconds": 1.0,
            "execution_notes": ["stubbed"],
        }
    )
    runner._execution_module = lambda: fake_execution  # type: ignore[assignment]

    output_dir = tmp_path / "vps-grid-test"
    payload = runner.execute_range(
        start=1,
        end=2,
        output_dir=output_dir,
        run_id=None,
        resume=False,
    )

    assert payload["run_id"] == "vps-grid-test"
    assert (output_dir / "grid_plan.v1.json").exists()
