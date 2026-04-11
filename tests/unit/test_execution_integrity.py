"""Execution integrity tests for the current backtesting engine contract."""

from __future__ import annotations

import pandas as pd
import pytest

from agent.backtesting.engine import BacktestEngine
from tests._harness_helpers import assert_signal_matches, build_ohlcv_frame


def _engine(cost_per_side: float = 0.0) -> BacktestEngine:
    engine = BacktestEngine.__new__(BacktestEngine)
    engine.kosten_per_kant = cost_per_side
    engine.start = "2024-01-01"
    engine.eind = "2024-12-31"
    engine.interval = "1d"
    return engine


def _price_frame(closes: list[float]) -> pd.DataFrame:
    frame = build_ohlcv_frame(length=len(closes), seed=31)
    close = pd.Series(closes, index=frame.index, dtype=float)
    frame["close"] = close
    frame["open"] = close
    frame["high"] = close * 1.01
    frame["low"] = close * 0.99
    frame["volume"] = 5_000
    return frame


def test_fills_only_occur_on_shifted_signal_timestamps() -> None:
    engine = _engine(cost_per_side=0.0)
    frame = _price_frame([100.0, 110.0, 121.0, 121.0])

    def strategy(data: pd.DataFrame) -> pd.Series:
        return pd.Series([1, 1, 0, 0], index=data.index, dtype=int)

    trade_pnls, day_returns, month_returns = engine._simuleer(frame, strategy, "TEST")

    assert trade_pnls == [pytest.approx(0.1)]
    assert day_returns == [pytest.approx(0.0), pytest.approx(0.1), pytest.approx(0.0)]
    assert month_returns == []


def test_identical_runs_apply_slippage_and_fees_consistently() -> None:
    engine = _engine(cost_per_side=0.01)
    frame = _price_frame([100.0, 110.0, 121.0, 121.0])

    def strategy(data: pd.DataFrame) -> pd.Series:
        return pd.Series([1, 1, 0, 0], index=data.index, dtype=int)

    first = engine._simuleer(frame.copy(deep=True), strategy, "TEST")
    second = engine._simuleer(frame.copy(deep=True), strategy, "TEST")

    assert first == second
    assert first[0] == [pytest.approx(0.09)]
    assert first[1] == [pytest.approx(-0.01), pytest.approx(0.1), pytest.approx(-0.01)]


def test_no_trade_is_generated_when_signal_never_changes() -> None:
    engine = _engine(cost_per_side=0.0)
    frame = _price_frame([100.0, 102.0, 101.0, 103.0, 104.0])

    def strategy(data: pd.DataFrame) -> pd.Series:
        return pd.Series(0, index=data.index, dtype=int)

    trade_pnls, day_returns, month_returns = engine._simuleer(frame, strategy, "TEST")

    assert trade_pnls == []
    assert day_returns == [0.0, 0.0, 0.0, 0.0]
    assert month_returns == []


@pytest.mark.parametrize(
    ("closes", "expected"),
    [
        ([100.0, 100.0, 105.0, 105.0, 105.0], [0, 1, 0, 0, 0]),
        ([100.0, 100.0, 97.0, 97.0, 97.0], [0, 1, 0, 0, 0]),
    ],
    ids=["take-profit", "stop-loss"],
)
def test_tp_sl_managed_signals_enforce_current_risk_rules(
    closes: list[float],
    expected: list[int],
) -> None:
    engine = _engine(cost_per_side=0.0)
    frame = _price_frame(closes)

    def strategy(data: pd.DataFrame) -> pd.Series:
        return pd.Series([0, 1, 1, 0, 0], index=data.index, dtype=int)

    strategy._trend_pullback_tp_sl_config = {
        "ema_kort": 2,
        "ema_lang": 3,
        "take_profit": 0.04,
        "stop_loss": 0.02,
    }

    managed = engine._prepare_trend_pullback_tp_sl_sig(frame, strategy)
    expected_signal = pd.Series(expected, index=frame.index, dtype=int)

    assert managed is not None
    assert_signal_matches(managed, expected_signal)
