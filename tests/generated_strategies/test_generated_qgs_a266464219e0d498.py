from __future__ import annotations

import importlib
import pandas as pd

from agent.backtesting.thin_strategy import build_features_for, is_thin_strategy
from tests._harness_helpers import build_ohlcv_frame

MODULE_NAME = "agent.backtesting.generated_strategies.generated_qgs_a266464219e0d498"
EXPECTED_STRATEGY_ID = "qgs_a266464219e0d498"
EXPECTED_SPEC_ID = "qsp_66fc66cd3f17afa7"

def _load_module():
    return importlib.import_module(MODULE_NAME)

def test_generated_strategy_imports_and_declares_thin_contract() -> None:
    module = _load_module()
    assert module.STRATEGY_ID == EXPECTED_STRATEGY_ID
    assert module.STRATEGY_SPEC_ID == EXPECTED_SPEC_ID
    assert is_thin_strategy(module.generated_strategy)

def test_generated_strategy_is_deterministic() -> None:
    module = _load_module()
    frame = build_ohlcv_frame(length=96, seed=19)
    features = build_features_for(module.generated_strategy._feature_requirements, frame)
    first = module.generated_strategy(frame, features)
    second = module.generated_strategy(frame, features)
    pd.testing.assert_series_equal(first, second)
    assert set(first.dropna().unique()) <= {0, 1}

def test_generated_strategy_handles_empty_signal_path() -> None:
    module = _load_module()
    frame = build_ohlcv_frame(length=24, seed=7)
    frame["close"] = frame["close"].iloc[0]
    features = build_features_for(module.generated_strategy._feature_requirements, frame)
    result = module.generated_strategy(frame, features)
    assert result.index.equals(frame.index)
    assert set(result.dropna().unique()) <= {0, 1}

