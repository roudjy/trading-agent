"""Strategy determinism tests pinned to the registry-defined Tier 1 surface."""

from __future__ import annotations

from copy import deepcopy

import pandas as pd
import pytest

from research.registry import get_enabled_strategies
from tests._harness_helpers import (
    assert_frame_matches,
    assert_signal_matches,
    build_ohlcv_frame,
)


EXPECTED_STRATEGY_NAMES = {
    "bollinger_mr",
    "bollinger_regime",
    "breakout_momentum",
    "rsi",
    "trend_pullback",
    "trend_pullback_tp_sl",
}


def _strategy_cases() -> list[object]:
    cases = []
    enabled = get_enabled_strategies()
    names = {strategy["name"] for strategy in enabled}
    missing = EXPECTED_STRATEGY_NAMES - names
    assert not missing, f"Missing expected Tier 1 strategies: {sorted(missing)}"

    for strategy in enabled:
        params = {key: values[0] for key, values in strategy["params"].items()}
        cases.append(
            pytest.param(
                strategy["name"],
                strategy["factory"],
                deepcopy(params),
                id=strategy["name"],
            )
        )
    return cases


STRATEGY_CASES = _strategy_cases()


def _input_frame(strategy_name: str) -> pd.DataFrame:
    frame = build_ohlcv_frame(length=260, seed=29)
    if strategy_name == "bollinger_regime":
        frame["_mr_regime_ok"] = True
    return frame


@pytest.mark.parametrize(("strategy_name", "factory", "params"), STRATEGY_CASES)
def test_strategy_outputs_are_identical_for_repeated_calls(
    strategy_name: str,
    factory,
    params: dict,
) -> None:
    frame = _input_frame(strategy_name)
    strategy = factory(**deepcopy(params))

    first = strategy(frame)
    second = strategy(frame)

    assert_signal_matches(first, second)
    assert first.to_numpy(copy=True).tobytes() == second.to_numpy(copy=True).tobytes()


@pytest.mark.parametrize(("strategy_name", "factory", "params"), STRATEGY_CASES)
def test_strategy_repeated_calls_do_not_mutate_input_frame(
    strategy_name: str,
    factory,
    params: dict,
) -> None:
    frame = _input_frame(strategy_name)
    before = frame.copy(deep=True)
    strategy = factory(**deepcopy(params))

    strategy(frame)
    strategy(frame)

    assert_frame_matches(frame, before)


@pytest.mark.parametrize(("strategy_name", "factory", "params"), STRATEGY_CASES)
def test_strategy_repeated_calls_preserve_index_alignment_and_dtype(
    strategy_name: str,
    factory,
    params: dict,
) -> None:
    frame = _input_frame(strategy_name)
    strategy = factory(**deepcopy(params))

    first = strategy(frame)
    second = strategy(frame)

    assert first.index.equals(second.index)
    assert first.dtype == second.dtype
    assert_signal_matches(first, second)
