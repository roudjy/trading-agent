"""Deterministic tests for standalone math helpers that exist on this branch.

The current repo does not expose independent SMA, EMA, z-score, rolling volatility,
ATR, spread, or hedge-ratio routines as standalone functions. Those are therefore
documented as absent here rather than invented for test coverage. The only reusable
math helper in the backtesting surface today is BacktestEngine._maand_returns.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from agent.backtesting.engine import BacktestEngine
from tests._harness_helpers import build_ohlcv_frame


def _engine() -> BacktestEngine:
    engine = BacktestEngine.__new__(BacktestEngine)
    engine.interval = "1d"
    return engine


def test_maand_returns_is_deterministic_for_seeded_input() -> None:
    engine = _engine()
    frame = build_ohlcv_frame(length=120, seed=11)
    equity = pd.Series(np.linspace(1.0, 1.4, len(frame)), dtype=float)

    first = engine._maand_returns(equity, frame)
    second = engine._maand_returns(equity, frame)

    assert first == second


def test_maand_returns_handles_leading_nans_deterministically() -> None:
    engine = _engine()
    frame = build_ohlcv_frame(length=120, seed=13)
    equity = pd.Series(np.linspace(1.0, 1.2, len(frame)), dtype=float)
    equity.iloc[:5] = np.nan

    first = engine._maand_returns(equity, frame)
    second = engine._maand_returns(equity, frame)

    assert first == second


def test_maand_returns_constant_series_returns_zero_changes() -> None:
    engine = _engine()
    frame = build_ohlcv_frame(length=120, seed=19)
    equity = pd.Series(1.0, index=frame.index, dtype=float)

    result = engine._maand_returns(equity, frame)

    assert result
    assert set(result) == {0.0}


def test_maand_returns_repeated_calls_return_identical_values() -> None:
    engine = _engine()
    frame = build_ohlcv_frame(length=150, seed=23)
    equity = pd.Series(np.linspace(0.95, 1.25, len(frame)), dtype=float)

    first = engine._maand_returns(equity, frame)
    second = engine._maand_returns(equity, frame)

    assert first == second
