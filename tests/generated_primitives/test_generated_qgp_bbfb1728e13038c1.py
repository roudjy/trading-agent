from __future__ import annotations

import importlib

import pandas as pd

from tests._harness_helpers import build_cross_sectional_frame

MODULE_NAME = "agent.backtesting.generated_primitives.generated_qgp_bbfb1728e13038c1"
EXPECTED_PRIMITIVE_ID = "cross_sectional_rank"
EXPECTED_GENERATED_PRIMITIVE_ID = "qgp_bbfb1728e13038c1"

def _load_module():
    return importlib.import_module(MODULE_NAME)

def test_generated_primitive_imports_and_exposes_expected_ids() -> None:
    module = _load_module()
    assert module.PRIMITIVE_ID == EXPECTED_PRIMITIVE_ID
    assert module.GENERATED_PRIMITIVE_ID == EXPECTED_GENERATED_PRIMITIVE_ID

def test_cross_sectional_rank_is_deterministic_and_order_independent() -> None:
    module = _load_module()
    frame = build_cross_sectional_frame(periods=28, seed=41)
    shuffled = frame.sample(frac=1.0, random_state=7)
    first = module.cross_sectional_rank(frame['close'])
    second = module.cross_sectional_rank(shuffled['close'])
    pd.testing.assert_series_equal(first.sort_index(), second.sort_index())

def test_cross_sectional_rank_handles_minimum_breadth_fail_closed() -> None:
    module = _load_module()
    frame = build_cross_sectional_frame(periods=10, assets=('AAA', 'BBB'), seed=11)
    result = module.cross_sectional_rank(frame['close'], minimum_universe_size=3)
    assert result.isna().all()

