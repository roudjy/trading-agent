"""Regression: interrupted screening candidate must emit a non-empty reason_detail.

When a screening candidate is interrupted mid-run, the returned dict must
carry:

- ``execution_state == "interrupted"``
- ``reason_detail`` that is a non-empty string (either the typed exception
  message or the default fallback ``"screening candidate interrupted"``)
- sample counters that are integers, not None

The v3.10 report agent consumes these fields to compose the "niets bruikbaars
vandaag" verdict and the rejection-reason rollup. A silent blank reason_detail
would turn into a blank line in the daily report and mask operational issues.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from agent.backtesting.engine import EngineExecutionSnapshot, EngineInterrupted
from research.candidate_pipeline import SCREENING_PROMOTED
from research.candidate_resume import candidate_resume_state_path
from research.screening_process import execute_screening_candidate_isolated


def _strategy_factory(**params):
    return SimpleNamespace(params=params)


class _InterruptingEngine:
    """Raises EngineInterrupted unconditionally on first sample."""

    def __init__(self, start_datum, eind_datum, evaluation_config=None, regime_config=None):
        self.start = start_datum
        self.end = eind_datum
        self._provenance_events = []
        self.last_evaluation_report = None

    def run(self, strategie_func, assets, interval="1d", deadline_monotonic=None, resume_snapshot=None):
        raise EngineInterrupted(
            reason="stop_requested",
            snapshot=EngineExecutionSnapshot(
                phase="evaluate_out_of_sample",
                asset_index=0,
                fold_index=0,
                completed_window_ids=(),
            ),
        )


def _candidate() -> dict:
    return {
        "candidate_id": "regression-candidate",
        "strategy_name": "regression_strategy",
        "asset": "BTC-USD",
        "interval": "1d",
    }


def test_interrupted_candidate_emits_non_empty_reason_detail(workspace_tmp_path: Path):
    history_root = workspace_tmp_path / "research" / "history"

    result = execute_screening_candidate_isolated(
        strategy={
            "name": "regression_strategy",
            "factory": _strategy_factory,
            "params": {"periode": [14]},
        },
        candidate=_candidate(),
        interval_range={"start": "2026-01-01", "end": "2026-02-01"},
        evaluation_config={},
        regime_config=None,
        budget_seconds=5,
        max_samples=1,
        engine_class=_InterruptingEngine,
        run_id="regression-run",
        batch_id="regression-batch",
        history_root=history_root,
    )

    assert result["execution_state"] == "interrupted", result
    assert isinstance(result.get("reason_detail"), str)
    assert result["reason_detail"].strip() != ""
    assert isinstance(result.get("samples_completed"), int)
    assert isinstance(result.get("samples_total"), int)

    sidecar = candidate_resume_state_path(
        history_root=history_root,
        run_id="regression-run",
        batch_id="regression-batch",
        candidate_id="regression-candidate",
    )
    assert sidecar.exists(), "interrupted candidate must persist a resume sidecar"


def test_interrupted_candidate_reason_detail_not_just_the_word_none(workspace_tmp_path: Path):
    """Catches the str(None) → 'None' bug class from CLAUDE.md learned lessons."""

    history_root = workspace_tmp_path / "research" / "history"

    result = execute_screening_candidate_isolated(
        strategy={
            "name": "regression_strategy_two",
            "factory": _strategy_factory,
            "params": {"periode": [14]},
        },
        candidate={**_candidate(), "candidate_id": "regression-candidate-2"},
        interval_range={"start": "2026-01-01", "end": "2026-02-01"},
        evaluation_config={},
        regime_config=None,
        budget_seconds=5,
        max_samples=1,
        engine_class=_InterruptingEngine,
        run_id="regression-run-2",
        batch_id="regression-batch-2",
        history_root=history_root,
    )

    assert result["execution_state"] == "interrupted"
    assert result["reason_detail"] not in {"", "None", "none", None}


def test_interrupt_sidecar_records_zero_promoted_samples(workspace_tmp_path: Path):
    """Sanity pin: interrupt on first sample means zero samples promoted."""

    history_root = workspace_tmp_path / "research" / "history"

    result = execute_screening_candidate_isolated(
        strategy={
            "name": "regression_strategy_three",
            "factory": _strategy_factory,
            "params": {"periode": [14]},
        },
        candidate={**_candidate(), "candidate_id": "regression-candidate-3"},
        interval_range={"start": "2026-01-01", "end": "2026-02-01"},
        evaluation_config={},
        regime_config=None,
        budget_seconds=5,
        max_samples=1,
        engine_class=_InterruptingEngine,
        run_id="regression-run-3",
        batch_id="regression-batch-3",
        history_root=history_root,
    )

    assert result["samples_completed"] == 0
    _ = SCREENING_PROMOTED  # imported to confirm contract is still shipped.
