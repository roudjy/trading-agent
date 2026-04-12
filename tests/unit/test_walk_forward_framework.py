from __future__ import annotations

from datetime import UTC

import pandas as pd
import pytest

from agent.backtesting.engine import (
    BacktestEngine,
    EvaluationScheduleError,
    FoldLeakageError,
    anchored_walk_forward,
    build_evaluation_folds,
    rolling_walk_forward,
    single_split,
    validate_no_leakage,
)


def _frame_from_closes(closes: list[float]) -> pd.DataFrame:
    index = pd.date_range("2024-01-01", periods=len(closes), freq="D", tz=UTC)
    return pd.DataFrame(
        {
            "open": closes,
            "high": [price * 1.01 for price in closes],
            "low": [price * 0.99 for price in closes],
            "close": closes,
            "volume": [1_000] * len(closes),
        },
        index=index,
    )


def test_single_split_boundaries_deterministic():
    assert single_split(10, 0.7) == [((0, 6), (7, 9))]


def test_rolling_walk_forward_generates_expected_folds():
    folds = rolling_walk_forward(n=10, train_bars=4, test_bars=2, step_bars=2)

    assert folds == [
        ((0, 3), (4, 5)),
        ((2, 5), (6, 7)),
        ((4, 7), (8, 9)),
    ]


def test_anchored_walk_forward_grows_training_window():
    folds = anchored_walk_forward(n=12, initial_train_bars=4, test_bars=2, step_bars=2)

    assert folds == [
        ((0, 3), (4, 5)),
        ((0, 5), (6, 7)),
        ((0, 7), (8, 9)),
        ((0, 9), (10, 11)),
    ]


def test_leakage_validator_rejects_overlapping_fold():
    with pytest.raises(FoldLeakageError, match=r"max\(train_index\)=5 >= min\(test_index\)=5"):
        validate_no_leakage([((0, 5), (5, 9))])


def test_schedule_raises_on_zero_train_or_test_folds():
    with pytest.raises(EvaluationScheduleError, match="single_split produced invalid boundaries"):
        single_split(1, 0.7)

    with pytest.raises(EvaluationScheduleError, match="rolling schedule produced zero folds"):
        rolling_walk_forward(n=10, train_bars=10, test_bars=2, step_bars=1)


def test_default_config_matches_current_70_30_split():
    engine = BacktestEngine(
        start_datum="2024-01-01",
        eind_datum="2024-04-30",
    )

    assert engine.evaluation_config == {
        "mode": "single_split",
        "selection_metric": "sharpe",
        "train_ratio": 0.7,
    }
    assert build_evaluation_folds(100, None) == [((0, 69), (70, 99))]


def test_grid_search_selection_uses_train_windows_only(monkeypatch):
    closes = [100.0 + step for step in range(70)] + [170.0 - step for step in range(30)]
    frame = _frame_from_closes(closes)
    engine = BacktestEngine(
        start_datum="2024-01-01",
        eind_datum="2024-04-30",
    )
    engine.min_trades = 1

    monkeypatch.setattr(engine, "_laad_data", lambda asset, interval: frame)

    def strategie_factory(direction: int):
        return lambda df: pd.Series(direction, index=df.index, dtype=int)

    result = engine.grid_search(
        strategie_factory=strategie_factory,
        param_grid={"direction": [1, -1]},
        assets=["BTC-USD"],
        interval="1d",
    )

    assert result["beste_params"] == {"direction": 1}
    assert result["sharpe"] == engine.last_evaluation_report["oos_summary"]["sharpe"]
    assert engine.last_evaluation_report["is_summary"]["sharpe"] > 0
    assert engine.last_evaluation_report["oos_summary"]["sharpe"] < 0
