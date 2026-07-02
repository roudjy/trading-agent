from __future__ import annotations

import pandas as pd

from agent.backtesting.thin_strategy import FeatureRequirement, declare_thin

STRATEGY_ID = "qgs_a266464219e0d498"
STRATEGY_SPEC_ID = "qsp_66fc66cd3f17afa7"
GENERATOR_VERSION = "ade-qre-019.1"
TEMPLATE_VERSION = "thin-strategy-template.1"

FEATURE_REQUIREMENTS = [
    FeatureRequirement(name="compression_ratio", params={"atr_short_window": 5, "atr_long_window": 20}, alias="compression_ratio"),
    FeatureRequirement(name="rolling_high_previous", params={"window": 20}, alias="rolling_high_previous"),
    FeatureRequirement(name="rolling_low_previous", params={"window": 20}, alias="rolling_low_previous"),
]

def _raw(df: pd.DataFrame, features: dict[str, pd.Series]) -> pd.Series:
    compression = features["compression_ratio"]
    roll_high_prev = features["rolling_high_previous"]
    roll_low_prev = features["rolling_low_previous"]
    close = df["close"].astype(float)
    signal = pd.Series(0, index=df.index, dtype=int)
    prev_compression = compression.shift(1)
    compressed_prior = prev_compression < 0.6
    breakout_up = close > roll_high_prev
    breakdown = close < roll_low_prev
    compression_released = prev_compression > 1.0
    signal.loc[compressed_prior & breakout_up] = 1
    signal.loc[breakdown | compression_released] = 0
    return signal

generated_strategy = declare_thin(
    _raw,
    feature_requirements=FEATURE_REQUIREMENTS,
    sizing_spec={"mode": "unit_notional_research_only"},
)

