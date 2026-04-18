from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from agent.backtesting.engine import EngineExecutionSnapshot, EngineInterrupted
from research.candidate_pipeline import SCREENING_PROMOTED
from research.candidate_resume import candidate_resume_state_path
from research.screening_process import execute_screening_candidate_isolated


def _quick_strategy_factory(**params):
    return SimpleNamespace(params=params)


class _QuickIsolationEngine:
    def __init__(self, start_datum, eind_datum, evaluation_config=None, regime_config=None):
        self.start = start_datum
        self.end = eind_datum
        self._provenance_events = []
        self.last_evaluation_report = None

    def run(self, strategie_func, assets, interval="1d"):
        self.last_evaluation_report = {
            "evaluation_samples": {
                "daily_returns": [0.01, -0.01],
            }
        }
        return {
            "totaal_trades": 12,
            "goedgekeurd": True,
        }


class _InterruptingIsolationEngine:
    def __init__(self, start_datum, eind_datum, evaluation_config=None, regime_config=None):
        self.start = start_datum
        self.end = eind_datum
        self._provenance_events = []
        self.last_evaluation_report = None

    def run(
        self,
        strategie_func,
        assets,
        interval="1d",
        deadline_monotonic=None,
        resume_snapshot=None,
    ):
        periode = int(strategie_func.params["periode"])
        if periode == 21 and resume_snapshot is None:
            raise EngineInterrupted(
                reason="stop_requested",
                snapshot=EngineExecutionSnapshot(
                    phase="evaluate_out_of_sample",
                    asset_index=0,
                    fold_index=0,
                    completed_window_ids=(("BTC-USD", "train", 0),),
                ),
            )
        self.last_evaluation_report = {
            "evaluation_samples": {
                "daily_returns": [0.01, -0.01],
            }
        }
        return {
            "totaal_trades": 12,
            "goedgekeurd": periode == 14,
        }


class _FailsWithoutFreshRestartEngine:
    def __init__(self, start_datum, eind_datum, evaluation_config=None, regime_config=None):
        self.start = start_datum
        self.end = eind_datum
        self._provenance_events = []
        self.last_evaluation_report = None

    def run(
        self,
        strategie_func,
        assets,
        interval="1d",
        deadline_monotonic=None,
        resume_snapshot=None,
    ):
        if resume_snapshot is not None:
            raise AssertionError("invalid sidecar should have been discarded before execution")
        self.last_evaluation_report = {
            "evaluation_samples": {
                "daily_returns": [0.01, -0.01],
            }
        }
        return {
            "totaal_trades": 12,
            "goedgekeurd": True,
        }


class _HardFailureIsolationEngine:
    def __init__(self, start_datum, eind_datum, evaluation_config=None, regime_config=None):
        self.start = start_datum
        self.end = eind_datum
        self._provenance_events = []
        self.last_evaluation_report = None

    def run(
        self,
        strategie_func,
        assets,
        interval="1d",
        deadline_monotonic=None,
        resume_snapshot=None,
    ):
        raise RuntimeError("non-resumable failure")


def _candidate() -> dict:
    return {
        "candidate_id": "candidate-1",
        "strategy_name": "quick_strategy",
        "asset": "BTC-USD",
        "interval": "1d",
    }


def _resume_path(history_root: Path, run_id: str) -> Path:
    return candidate_resume_state_path(
        history_root=history_root,
        run_id=run_id,
        batch_id="batch-1",
        candidate_id="candidate-1",
    )


def test_execute_screening_candidate_isolated_completes_within_budget():
    result = execute_screening_candidate_isolated(
        strategy={
            "name": "quick_strategy",
            "factory": _quick_strategy_factory,
            "params": {"periode": [14]},
        },
        candidate={
            "candidate_id": "candidate-1",
            "strategy_name": "quick_strategy",
            "asset": "BTC-USD",
            "interval": "1d",
        },
        interval_range={"start": "2026-01-01", "end": "2026-02-01"},
        evaluation_config={},
        regime_config=None,
        budget_seconds=5,
        max_samples=1,
        engine_class=_QuickIsolationEngine,
    )

    assert result["execution_state"] == "completed"
    assert result["outcome"]["final_status"] == "passed"
    assert result["outcome"]["samples_completed"] == 1


def test_execute_screening_candidate_isolated_persists_and_resumes_sidecar(workspace_tmp_path: Path):
    history_root = workspace_tmp_path / "research" / "history"
    strategy = {
        "name": "quick_strategy",
        "factory": _quick_strategy_factory,
        "params": {"periode": [14, 21]},
    }

    interrupted = execute_screening_candidate_isolated(
        strategy=strategy,
        candidate=_candidate(),
        interval_range={"start": "2026-01-01", "end": "2026-02-01"},
        evaluation_config={},
        regime_config=None,
        budget_seconds=5,
        max_samples=2,
        engine_class=_InterruptingIsolationEngine,
        run_id="run-1",
        batch_id="batch-1",
        history_root=history_root,
    )

    sidecar_path = _resume_path(history_root, "run-1")
    assert interrupted["execution_state"] == "interrupted"
    assert sidecar_path.exists()
    payload = json.loads(sidecar_path.read_text(encoding="utf-8"))
    assert payload["completed_samples"] == [{"status": SCREENING_PROMOTED, "reason": None}]
    assert payload["active_resume"]["sample_index"] == 1

    resumed = execute_screening_candidate_isolated(
        strategy=strategy,
        candidate=_candidate(),
        interval_range={"start": "2026-01-01", "end": "2026-02-01"},
        evaluation_config={},
        regime_config=None,
        budget_seconds=5,
        max_samples=2,
        engine_class=_InterruptingIsolationEngine,
        run_id="run-2",
        resume_run_id="run-1",
        batch_id="batch-1",
        history_root=history_root,
    )

    assert resumed["execution_state"] == "completed"
    assert resumed["outcome"]["final_status"] == "passed"
    assert not _resume_path(history_root, "run-1").exists()
    assert not _resume_path(history_root, "run-2").exists()


def test_invalid_resume_sidecar_is_discarded_and_candidate_restarts_fresh(workspace_tmp_path: Path):
    history_root = workspace_tmp_path / "research" / "history"
    source_path = _resume_path(history_root, "run-1")
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_text("{not-json", encoding="utf-8")

    result = execute_screening_candidate_isolated(
        strategy={
            "name": "quick_strategy",
            "factory": _quick_strategy_factory,
            "params": {"periode": [14]},
        },
        candidate=_candidate(),
        interval_range={"start": "2026-01-01", "end": "2026-02-01"},
        evaluation_config={},
        regime_config=None,
        budget_seconds=5,
        max_samples=1,
        engine_class=_FailsWithoutFreshRestartEngine,
        run_id="run-2",
        resume_run_id="run-1",
        batch_id="batch-1",
        history_root=history_root,
    )

    assert result["execution_state"] == "completed"
    assert result["outcome"]["final_status"] == "passed"
    assert not source_path.exists()


def test_resume_sidecar_is_cleaned_up_after_non_resumable_failure(workspace_tmp_path: Path):
    history_root = workspace_tmp_path / "research" / "history"
    strategy = {
        "name": "quick_strategy",
        "factory": _quick_strategy_factory,
        "params": {"periode": [14, 21]},
    }
    interrupted = execute_screening_candidate_isolated(
        strategy=strategy,
        candidate=_candidate(),
        interval_range={"start": "2026-01-01", "end": "2026-02-01"},
        evaluation_config={},
        regime_config=None,
        budget_seconds=5,
        max_samples=2,
        engine_class=_InterruptingIsolationEngine,
        run_id="run-1",
        batch_id="batch-1",
        history_root=history_root,
    )

    assert interrupted["execution_state"] == "interrupted"
    failed = execute_screening_candidate_isolated(
        strategy=strategy,
        candidate=_candidate(),
        interval_range={"start": "2026-01-01", "end": "2026-02-01"},
        evaluation_config={},
        regime_config=None,
        budget_seconds=5,
        max_samples=2,
        engine_class=_HardFailureIsolationEngine,
        run_id="run-2",
        resume_run_id="run-1",
        batch_id="batch-1",
        history_root=history_root,
    )

    assert failed["execution_state"] == "completed"
    assert failed["outcome"]["final_status"] == "errored"
    assert not _resume_path(history_root, "run-1").exists()
    assert not _resume_path(history_root, "run-2").exists()
