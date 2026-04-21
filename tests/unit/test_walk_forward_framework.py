from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pandas as pd
import pytest

from agent.backtesting.engine import (
    MIN_ROBUSTNESS_FOLDS,
    BacktestEngine,
    EvaluationScheduleError,
    FoldLeakageError,
    anchored_walk_forward,
    build_evaluation_folds,
    normalize_evaluation_config,
    rolling_walk_forward,
    single_split,
    validate_no_leakage,
)
from agent.backtesting.multi_asset_loader import load_aligned_pair
from data.contracts import Provenance
from data.repository import BarsResponse


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


def test_default_config_is_anchored_walk_forward():
    engine = BacktestEngine(
        start_datum="2024-01-01",
        eind_datum="2024-04-30",
    )

    assert engine.evaluation_config == {
        "mode": "anchored",
        "selection_metric": "sharpe",
        "initial_train_bars": 500,
        "test_bars": 100,
        "step_bars": 100,
    }


def test_default_anchored_produces_multiple_folds():
    folds = build_evaluation_folds(1000, None)
    assert len(folds) > 1
    assert len(folds) >= MIN_ROBUSTNESS_FOLDS


def test_explicit_single_split_still_produces_one_fold():
    config = {"mode": "single_split", "train_ratio": 0.7}
    folds = build_evaluation_folds(100, config)
    assert folds == [((0, 69), (70, 99))]
    assert len(folds) == 1


def test_normalize_none_config_returns_anchored_defaults():
    config = normalize_evaluation_config(None)
    assert config["mode"] == "anchored"
    assert config["initial_train_bars"] == 500
    assert config["test_bars"] == 100
    assert config["step_bars"] == 100


def test_rolling_mode_uses_safe_defaults_when_bars_omitted():
    config = normalize_evaluation_config({"mode": "rolling"})
    assert config["train_bars"] == 500
    assert config["test_bars"] == 100
    assert config["step_bars"] == 100


def _ohlcv(index: pd.DatetimeIndex, base: float) -> pd.DataFrame:
    n = len(index)
    return pd.DataFrame(
        {
            "open": [base + i for i in range(n)],
            "high": [base + i + 0.5 for i in range(n)],
            "low": [base + i - 0.5 for i in range(n)],
            "close": [base + i + 0.25 for i in range(n)],
            "volume": [1_000.0 + i for i in range(n)],
        },
        index=index,
    )


def _repo_returning(primary: pd.DataFrame, reference: pd.DataFrame) -> MagicMock:
    provenance = Provenance(
        adapter="fixture",
        fetched_at_utc=datetime(2026, 4, 20, 12, 0, tzinfo=UTC),
        config_hash="cfg",
        source_version="1.0",
        cache_hit=False,
    )
    repo = MagicMock()

    def _get_bars(*, instrument, interval, start_utc, end_utc):
        if instrument.native_symbol.startswith("BTC"):
            frame = primary
        else:
            frame = reference
        return BarsResponse(frame=frame, provenance=provenance)

    repo.get_bars.side_effect = _get_bars
    return repo


def test_multi_asset_fold_slices_match_direct_alignment_per_fold():
    """v3.6 fold-safety invariant: slicing a full-range AlignedPairFrame
    at a fold boundary produces exactly the same primary/reference pair
    as invoking the loader directly over that fold's date range.

    If this ever drifts, fold iteration can leak information across
    boundaries through the reference leg — the multi-asset analogue of
    FoldLeakageError. Pinned here because the engine's fold loop does
    `context.reference_frame.iloc[start:end+1]` and must not diverge
    from a direct alignment over the same window.
    """
    start = pd.Timestamp("2026-01-01", tz="UTC")
    end = pd.Timestamp("2026-02-09", tz="UTC")
    full_index = pd.date_range("2026-01-01", periods=40, freq="D")
    primary = _ohlcv(full_index, base=100.0)
    reference = _ohlcv(full_index, base=200.0)

    full = load_aligned_pair(
        "BTC-EUR",
        "ETH-EUR",
        "1d",
        start,
        end,
        market_repository=_repo_returning(primary, reference),
    )

    folds = anchored_walk_forward(
        n=40, initial_train_bars=10, test_bars=5, step_bars=5
    )
    assert len(folds) >= MIN_ROBUSTNESS_FOLDS

    for (train_start, train_end), (test_start, test_end) in folds:
        window_start = train_start
        window_end = test_end
        sliced_primary = full.primary.iloc[window_start : window_end + 1]
        sliced_reference = full.reference.iloc[window_start : window_end + 1]

        truncated_primary = primary.iloc[window_start : window_end + 1]
        truncated_reference = reference.iloc[window_start : window_end + 1]
        direct = load_aligned_pair(
            "BTC-EUR",
            "ETH-EUR",
            "1d",
            start,
            end,
            market_repository=_repo_returning(
                truncated_primary, truncated_reference
            ),
        )

        pd.testing.assert_frame_equal(sliced_primary, direct.primary)
        pd.testing.assert_frame_equal(sliced_reference, direct.reference)
        assert sliced_primary.index.equals(sliced_reference.index)


def test_grid_search_selection_uses_train_windows_only(monkeypatch):
    closes = [100.0 + step for step in range(70)] + [170.0 - step for step in range(30)]
    frame = _frame_from_closes(closes)
    engine = BacktestEngine(
        start_datum="2024-01-01",
        eind_datum="2024-04-30",
        evaluation_config={"mode": "single_split", "train_ratio": 0.7},
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
