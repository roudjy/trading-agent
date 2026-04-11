"""Evaluation integrity tests for deterministic metric and schema behavior."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from agent.backtesting.engine import BacktestEngine, CRITERIA
from research.results import make_result_row


def _engine(interval: str = "1d") -> BacktestEngine:
    engine = BacktestEngine.__new__(BacktestEngine)
    engine.interval = interval
    return engine


def _row_schema_keys() -> set[str]:
    row = make_result_row(
        strategy={"name": "fixture", "family": "trend", "hypothesis": "fixture"},
        asset="BTC-USD",
        interval="1d",
        params={"periode": 14},
        as_of_utc=datetime(2024, 1, 1, tzinfo=timezone.utc),
        metrics={"win_rate": 0.5},
    )
    return set(row.keys())


def test_repeated_evaluation_returns_identical_metric_values() -> None:
    engine = _engine()
    trade_pnls = [0.1, -0.05, 0.02]
    day_returns = [0.01, -0.005, 0.003, 0.002]
    month_returns = [0.02, -0.01, 0.03]

    first = engine._metrics(trade_pnls, day_returns, month_returns)
    second = engine._metrics(trade_pnls, day_returns, month_returns)

    for key in (
        "sharpe",
        "max_drawdown",
        "win_rate",
        "trades_per_maand",
        "consistentie",
        "totaal_trades",
    ):
        assert first[key] == second[key]


def test_metrics_match_small_analytic_case() -> None:
    engine = _engine(interval="1d")
    metrics = engine._metrics(
        trade_pnls=[0.1, -0.05],
        dag_returns=[0.1, -0.05],
        maand_returns=[0.02, -0.01],
    )

    assert metrics["win_rate"] == 0.5
    assert metrics["sharpe"] == pytest.approx(5.292)
    assert metrics["max_drawdown"] == 0.05
    assert metrics["trades_per_maand"] == 30.0
    assert metrics["consistentie"] == 0.5
    assert metrics["totaal_trades"] == 2


def test_metrics_do_not_double_count_across_repeated_calls() -> None:
    engine = _engine()
    trade_pnls = [0.03, -0.01, 0.02]
    day_returns = [0.01, -0.005, 0.004]

    first = engine._metrics(trade_pnls, day_returns, [0.01])
    second = engine._metrics(trade_pnls, day_returns, [0.01])

    assert first["totaal_trades"] == len(trade_pnls)
    assert second["totaal_trades"] == len(trade_pnls)
    assert first == second


def test_turnover_metric_is_absent() -> None:
    """Delete this the day turnover is intentionally added to the frozen output schema."""
    engine = _engine()
    metric_keys = set(engine._metrics([0.1], [0.01, -0.01], [0.02]).keys())
    row_schema_keys = _row_schema_keys()

    assert "turnover" not in metric_keys
    assert "turnover" not in row_schema_keys


def test_goedkeuren_mutates_input_dict_as_currently_implemented() -> None:
    """Intentional: mutation is load-bearing current behavior; this test pins it so a future refactor cannot silently remove it without review."""
    engine = _engine()
    metrics = {
        "win_rate": 0.55,
        "deflated_sharpe": 0.75,
        "max_drawdown": 0.35,
        "trades_per_maand": 2.0,
        "consistentie": 0.5,
    }
    original = dict(metrics)

    approved = engine._goedkeuren(metrics)

    expected_checks = {
        name: {
            "gt": original[name] > threshold,
            "gte": original[name] >= threshold,
            "lt": original[name] < threshold,
            "lte": original[name] <= threshold,
        }[operator]
        for name, (operator, threshold) in CRITERIA.items()
    }

    assert approved is True
    assert set(metrics.keys()) == set(original.keys()) | {"criteria_checks"}
    for key, value in original.items():
        assert metrics[key] == value
    assert metrics["criteria_checks"] == expected_checks
