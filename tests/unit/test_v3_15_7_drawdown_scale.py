"""v3.15.7 — pin engine ``max_drawdown`` sign / scale convention.

The exploratory threshold (``EXPLORATORY_MAX_DRAWDOWN = 0.45``) is
applied directly to the engine output. The engine returns
``max_drawdown`` as ``abs(dd.min())`` — always positive, scale 0..1.
A regression that flipped the sign would silently invert the gate.
"""

from __future__ import annotations

from agent.backtesting.engine import BacktestEngine
from research.screening_criteria import EXPLORATORY_MAX_DRAWDOWN


def _metrics(trade_pnls, dag_returns):
    e = BacktestEngine.__new__(BacktestEngine)
    return e._metrics(list(trade_pnls), list(dag_returns), [])


def test_max_drawdown_is_non_negative_on_simple_path():
    """A purely losing daily-return path produces a positive drawdown."""
    m = _metrics([], [-0.01, -0.02, -0.03, -0.01])
    assert m["max_drawdown"] >= 0.0


def test_max_drawdown_is_zero_when_no_dag_returns():
    m = _metrics([], [])
    assert m["max_drawdown"] == 0.0


def test_max_drawdown_scale_is_fraction_of_one():
    """Engine's max_drawdown is on the 0..1 scale (40% = 0.40),
    not 0..100. Threshold 0.45 must be on the same scale.
    """
    # Construct a path with peak at 1.0 and trough at 0.5
    # → drawdown = 0.5 (50%).
    m = _metrics([], [0.0, -0.50])
    assert 0.0 <= m["max_drawdown"] <= 1.0


def test_exploratory_max_drawdown_threshold_is_on_zero_one_scale():
    assert 0.0 < EXPLORATORY_MAX_DRAWDOWN < 1.0
