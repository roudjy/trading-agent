from __future__ import annotations

import csv
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from agent.backtesting.engine import EngineExecutionSnapshot, EngineInterrupted
from research import batch_execution as batch_execution_module
from research import run_research as run_research_module
from tests.unit.test_run_research_observability import _HealthyEngine, _patch_common_runner


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _factory(name_hint: str):
    def _build(**params):
        return SimpleNamespace(name_hint=name_hint)

    return _build


class _RetryableFailureEngine(_HealthyEngine):
    failing_strategies: set[str] = set()

    def grid_search(self, strategie_factory, param_grid, assets, interval="1d"):
        built = strategie_factory()
        strategy_name = getattr(built, "name_hint", "unknown")
        if strategy_name in _RetryableFailureEngine.failing_strategies:
            raise RuntimeError(f"forced validation failure for {strategy_name}")
        return super().grid_search(strategie_factory, param_grid, assets, interval=interval)


class _InterruptibleValidationEngine(_HealthyEngine):
    interrupt_strategies: set[str] = set()

    def grid_search(self, strategie_factory, param_grid, assets, interval="1d"):
        built = strategie_factory()
        strategy_name = getattr(built, "name_hint", "unknown")
        if strategy_name in _InterruptibleValidationEngine.interrupt_strategies:
            raise KeyboardInterrupt(f"forced interrupt for {strategy_name}")
        return super().grid_search(strategie_factory, param_grid, assets, interval=interval)


class _InterruptibleScreeningEngine(_HealthyEngine):
    def run(
        self,
        strategie_func,
        assets,
        interval="1d",
        deadline_monotonic=None,
        resume_snapshot=None,
    ):
        if resume_snapshot is None:
            raise EngineInterrupted(
                reason="stop_requested",
                snapshot=EngineExecutionSnapshot(
                    phase="evaluate_out_of_sample",
                    asset_index=0,
                    fold_index=0,
                    completed_window_ids=(),
                ),
            )
        return super().run(strategie_func, assets, interval=interval)


def _set_multi_batch_strategies(monkeypatch) -> None:
    strategies = [
        {
            "name": "alpha_strategy",
            "family": "trend",
            "strategy_family": "a_family",
            "position_structure": "outright",
            "initial_lane_support": "supported",
            "hypothesis": "alpha",
            "factory": _factory("alpha_strategy"),
            "params": {"periode": [14]},
        },
        {
            "name": "omega_strategy",
            "family": "trend",
            "strategy_family": "z_family",
            "position_structure": "outright",
            "initial_lane_support": "supported",
            "hypothesis": "omega",
            "factory": _factory("omega_strategy"),
            "params": {"periode": [14]},
        },
    ]
    monkeypatch.setattr(run_research_module, "get_enabled_strategies", lambda: strategies)
    monkeypatch.setattr(batch_execution_module, "get_enabled_strategies", lambda: strategies)


def test_resume_with_retry_failed_batches_reuses_completed_batches_and_creates_new_run_id(monkeypatch, workspace_tmp_path: Path):
    _patch_common_runner(monkeypatch, workspace_tmp_path, _RetryableFailureEngine)
    _set_multi_batch_strategies(monkeypatch)
    _RetryableFailureEngine.failing_strategies = {"omega_strategy"}

    with pytest.raises(RuntimeError, match="forced validation failure for omega_strategy"):
        run_research_module.run_research()

    failed_state = _load_json(workspace_tmp_path / "research" / "run_state.v1.json")
    failed_batches = _load_json(workspace_tmp_path / "research" / "run_batches_latest.v1.json")
    assert failed_state["status"] == "failed"
    assert [batch["status"] for batch in failed_batches["batches"]] == ["completed", "failed"]

    first_run_id = failed_state["run_id"]
    _RetryableFailureEngine.failing_strategies = set()

    run_research_module.run_research(resume=True, retry_failed_batches=True)

    resumed_state = _load_json(workspace_tmp_path / "research" / "run_state.v1.json")
    resumed_manifest = _load_json(workspace_tmp_path / "research" / "run_manifest_latest.v1.json")
    resumed_batches = _load_json(workspace_tmp_path / "research" / "run_batches_latest.v1.json")
    public_json = _load_json(workspace_tmp_path / "research" / "research_latest.json")
    with (workspace_tmp_path / "research" / "strategy_matrix.csv").open(encoding="utf-8", newline="") as handle:
        csv_rows = list(csv.DictReader(handle))

    assert resumed_state["run_id"] != first_run_id
    assert resumed_manifest["lifecycle_mode"] == "resume"
    assert resumed_manifest["resumed_from_run_id"] == first_run_id
    assert resumed_manifest["retry_failed_batches"] is True
    assert resumed_manifest["continuation_summary"] == {
        "fresh_batch_count": 1,
        "reused_terminal_batch_count": 1,
        "resumed_pending_batch_count": 0,
        "resumed_stale_batch_count": 0,
        "retried_failed_batch_count": 1,
    }
    assert [batch["status"] for batch in resumed_batches["batches"]] == ["completed", "completed"]
    assert resumed_batches["batches"][0]["attempt_count"] == 1
    assert resumed_batches["batches"][0]["last_attempt_reason"] == "fresh_run"
    assert resumed_batches["batches"][1]["attempt_count"] == 2
    assert resumed_batches["batches"][1]["last_attempt_reason"] == "retry_failed_batch"
    assert public_json["count"] == 2
    assert [row["strategy_name"] for row in public_json["results"]] == ["alpha_strategy", "omega_strategy"]
    assert [row["strategy_name"] for row in csv_rows] == ["alpha_strategy", "omega_strategy"]


def test_resume_recovers_stale_running_validation_batch_with_new_run_id(monkeypatch, workspace_tmp_path: Path):
    _patch_common_runner(monkeypatch, workspace_tmp_path, _InterruptibleValidationEngine)
    _set_multi_batch_strategies(monkeypatch)
    _InterruptibleValidationEngine.interrupt_strategies = {"omega_strategy"}

    with pytest.raises(KeyboardInterrupt, match="forced interrupt for omega_strategy"):
        run_research_module.run_research()

    stale_state = _load_json(workspace_tmp_path / "research" / "run_state.v1.json")
    stale_batches = _load_json(workspace_tmp_path / "research" / "run_batches_latest.v1.json")
    first_run_id = stale_state["run_id"]
    assert stale_state["status"] == "running"
    assert [batch["status"] for batch in stale_batches["batches"]] == ["completed", "running"]
    assert stale_batches["batches"][1]["current_stage"] == "validation"

    monkeypatch.setattr("research.run_state._pid_is_live", lambda pid: False)
    _InterruptibleValidationEngine.interrupt_strategies = set()

    run_research_module.run_research(resume=True)

    resumed_state = _load_json(workspace_tmp_path / "research" / "run_state.v1.json")
    resumed_manifest = _load_json(workspace_tmp_path / "research" / "run_manifest_latest.v1.json")
    resumed_batches = _load_json(workspace_tmp_path / "research" / "run_batches_latest.v1.json")
    public_json = _load_json(workspace_tmp_path / "research" / "research_latest.json")

    assert resumed_state["run_id"] != first_run_id
    assert resumed_manifest["lifecycle_mode"] == "resume"
    assert resumed_manifest["resumed_from_run_id"] == first_run_id
    assert resumed_manifest["retry_failed_batches"] is False
    assert resumed_manifest["continuation_summary"] == {
        "fresh_batch_count": 1,
        "reused_terminal_batch_count": 1,
        "resumed_pending_batch_count": 0,
        "resumed_stale_batch_count": 1,
        "retried_failed_batch_count": 0,
    }
    assert [batch["status"] for batch in resumed_batches["batches"]] == ["completed", "completed"]
    assert resumed_batches["batches"][0]["attempt_count"] == 1
    assert resumed_batches["batches"][1]["attempt_count"] == 2
    assert resumed_batches["batches"][1]["last_attempt_reason"] == "resume_stale_batch"
    assert public_json["count"] == 2


def test_resume_recovers_stale_running_screening_batch_from_candidate_sidecar(monkeypatch, workspace_tmp_path: Path):
    _patch_common_runner(monkeypatch, workspace_tmp_path, _InterruptibleScreeningEngine)

    with pytest.raises(KeyboardInterrupt, match="screening candidate interrupted"):
        run_research_module.run_research()

    stale_state = _load_json(workspace_tmp_path / "research" / "run_state.v1.json")
    stale_batches = _load_json(workspace_tmp_path / "research" / "run_batches_latest.v1.json")
    screening_payload = _load_json(workspace_tmp_path / "research" / "run_screening_candidates_latest.v1.json")
    first_run_id = stale_state["run_id"]
    candidate_id = screening_payload["candidates"][0]["candidate_id"]
    sidecar_path = (
        workspace_tmp_path
        / "research"
        / "history"
        / first_run_id
        / "batches"
        / stale_batches["batches"][0]["batch_id"]
        / "candidate_resume"
        / f"{candidate_id}.v1.json"
    )

    assert stale_state["status"] == "running"
    assert stale_batches["batches"][0]["status"] == "running"
    assert sidecar_path.exists()

    monkeypatch.setattr("research.run_state._pid_is_live", lambda pid: False)

    run_research_module.run_research(resume=True)

    resumed_state = _load_json(workspace_tmp_path / "research" / "run_state.v1.json")
    resumed_manifest = _load_json(workspace_tmp_path / "research" / "run_manifest_latest.v1.json")
    resumed_batches = _load_json(workspace_tmp_path / "research" / "run_batches_latest.v1.json")
    public_json = _load_json(workspace_tmp_path / "research" / "research_latest.json")
    with (workspace_tmp_path / "research" / "strategy_matrix.csv").open(encoding="utf-8", newline="") as handle:
        csv_rows = list(csv.DictReader(handle))

    assert resumed_state["run_id"] != first_run_id
    assert resumed_manifest["lifecycle_mode"] == "resume"
    assert resumed_manifest["resumed_from_run_id"] == first_run_id
    assert resumed_manifest["continuation_summary"] == {
        "fresh_batch_count": 1,
        "reused_terminal_batch_count": 0,
        "resumed_pending_batch_count": 0,
        "resumed_stale_batch_count": 1,
        "retried_failed_batch_count": 0,
    }
    assert resumed_batches["batches"][0]["status"] == "completed"
    assert public_json["count"] == 1
    assert [row["strategy_name"] for row in csv_rows] == ["fake_strategy"]
    assert not sidecar_path.exists()
