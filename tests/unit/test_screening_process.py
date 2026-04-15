from __future__ import annotations

from types import SimpleNamespace

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
