from __future__ import annotations

import pandas as pd

from agent.backtesting.thin_strategy import FeatureRequirement, declare_thin

STRATEGY_ID = "qgs_5af8f605ba82ae53"
STRATEGY_SPEC_ID = "qsp_16800d656bf28677"
GENERATOR_VERSION = "ade-qre-019.1"
TEMPLATE_VERSION = "thin-strategy-template.1"

FEATURE_REQUIREMENTS = [
    FeatureRequirement(name="trend_anchor", params={"window": 50}, alias="trend_anchor"),
    FeatureRequirement(name="trend_anchor_delta", params={"window": 50}, alias="trend_anchor_delta"),
    FeatureRequirement(name="normalized_trend_move", params={"trend_anchor_window": 50, "atr_window": 14}, alias="normalized_trend_move"),
]

def _raw(df: pd.DataFrame, features: dict[str, pd.Series]) -> pd.Series:
    anchor_delta = features["trend_anchor_delta"]
    normalized_move = features["normalized_trend_move"]
    signal = pd.Series(0, index=df.index, dtype=int)
    active = False
    for idx in range(len(signal)):
        if bool(anchor_delta.iloc[idx] > 0) and bool(normalized_move.iloc[idx] >= 0.75):
            active = True
        elif bool(anchor_delta.iloc[idx] < 0) or bool(normalized_move.iloc[idx] <= 0.10):
            active = False
        signal.iloc[idx] = 1 if active else 0
    return signal

generated_strategy = declare_thin(
    _raw,
    feature_requirements=FEATURE_REQUIREMENTS,
    sizing_spec={"mode": "unit_notional_research_only"},
)

