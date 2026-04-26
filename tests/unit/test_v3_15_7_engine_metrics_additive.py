"""v3.15.7 — engine metrics additivity (expectancy + profit_factor)."""

from __future__ import annotations

import json

from agent.backtesting.engine import (
    METRIC_KEYS,
    PROFIT_FACTOR_NO_LOSS_CAP,
    BacktestEngine,
)


def _engine_with_metrics(trade_pnls, dag_returns=(), maand_returns=()):
    e = BacktestEngine.__new__(BacktestEngine)
    return e._metrics(list(trade_pnls), list(dag_returns), list(maand_returns))


def test_metric_keys_include_expectancy_and_profit_factor():
    assert "expectancy" in METRIC_KEYS
    assert "profit_factor" in METRIC_KEYS


def test_profit_factor_no_loss_cap_is_999():
    assert PROFIT_FACTOR_NO_LOSS_CAP == 999.0


def test_empty_trades_yields_zero_expectancy_and_profit_factor():
    m = _engine_with_metrics([])
    assert m["expectancy"] == 0.0
    assert m["profit_factor"] == 0.0


def test_only_winners_yields_capped_profit_factor():
    m = _engine_with_metrics([0.01, 0.02, 0.03])
    assert m["expectancy"] > 0
    assert m["profit_factor"] == PROFIT_FACTOR_NO_LOSS_CAP


def test_only_losers_yields_zero_profit_factor():
    m = _engine_with_metrics([-0.01, -0.02, -0.03])
    assert m["expectancy"] < 0
    assert m["profit_factor"] == 0.0


def test_mixed_trades_yields_finite_ratio():
    # 3 winners totalling 0.06, 2 losers totalling 0.02.
    m = _engine_with_metrics([0.01, 0.02, 0.03, -0.01, -0.01])
    assert m["expectancy"] > 0
    assert 0 < m["profit_factor"] < PROFIT_FACTOR_NO_LOSS_CAP
    # Float comparison: 0.06 / 0.02 == 3.00.
    assert abs(m["profit_factor"] - 3.0) < 1e-9


def test_metrics_are_json_safe_with_allow_nan_false():
    """Both new metrics must serialize through json.dumps with
    allow_nan=False — guarantees no NaN/inf leaks downstream.
    """
    m = _engine_with_metrics([0.01, -0.005])
    payload = {"expectancy": m["expectancy"], "profit_factor": m["profit_factor"]}
    json.dumps(payload, allow_nan=False)


def test_only_winners_metrics_are_json_safe():
    """Cap path also JSON-safe."""
    m = _engine_with_metrics([0.05, 0.10])
    payload = {"expectancy": m["expectancy"], "profit_factor": m["profit_factor"]}
    json.dumps(payload, allow_nan=False)


def test_leeg_metrics_include_new_keys():
    e = BacktestEngine.__new__(BacktestEngine)
    leeg = e._leeg()
    assert "expectancy" in leeg
    assert "profit_factor" in leeg
    assert leeg["expectancy"] == 0.0
    assert leeg["profit_factor"] == 0.0
