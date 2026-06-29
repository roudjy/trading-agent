from __future__ import annotations

import importlib
import pandas as pd

from agent.backtesting.thin_strategy import build_features_for, is_thin_strategy
from tests._harness_helpers import build_cross_sectional_frame

MODULE_NAME = "agent.backtesting.generated_strategies.generated_qgs_e565b01bd0a162d0"
EXPECTED_STRATEGY_ID = "qgs_e565b01bd0a162d0"
EXPECTED_SPEC_ID = "qsp_28cdbc0005ae7c93"

def _load_module():
    return importlib.import_module(MODULE_NAME)

def test_generated_strategy_imports_and_declares_thin_contract() -> None:
    module = _load_module()
    assert module.STRATEGY_ID == EXPECTED_STRATEGY_ID
    assert module.STRATEGY_SPEC_ID == EXPECTED_SPEC_ID
    assert is_thin_strategy(module.generated_strategy)

def test_generated_strategy_is_deterministic() -> None:
    module = _load_module()
    frame = build_cross_sectional_frame(periods=28, seed=17)
    features = build_features_for(module.generated_strategy._feature_requirements, frame)
    first = module.generated_strategy(frame, features)
    second = module.generated_strategy(frame, features)
    pd.testing.assert_series_equal(first, second)
    assert set(first.dropna().unique()) <= {-1, 0, 1}

def test_generated_strategy_handles_insufficient_breadth() -> None:
    module = _load_module()
    frame = build_cross_sectional_frame(periods=12, assets=('AAA', 'BBB'), seed=7)
    features = build_features_for(module.generated_strategy._feature_requirements, frame)
    result = module.generated_strategy(frame, features)
    assert result.index.equals(frame.index)
    assert set(result.dropna().unique()) <= {-1, 0, 1}

