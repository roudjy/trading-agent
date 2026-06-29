from __future__ import annotations

import pandas as pd

from agent.backtesting.thin_strategy import FeatureRequirement, declare_thin

STRATEGY_ID = "qgs_e565b01bd0a162d0"
STRATEGY_SPEC_ID = "qsp_28cdbc0005ae7c93"
GENERATOR_VERSION = "ade-qre-019.1"
TEMPLATE_VERSION = "thin-strategy-template.1"

FEATURE_REQUIREMENTS = [
    FeatureRequirement(
        name="cross_sectional_rank",
        params={"lookback_bars": 20, "ascending": False, "rank_mode": "PERCENTILE", "tie_policy": "AVERAGE", "missing_value_policy": "FAIL_CLOSED", "minimum_universe_size": 3},
        alias="cross_sectional_rank",
    ),
]

def _raw(df: pd.DataFrame, features: dict[str, pd.Series]) -> pd.Series:
    rank = features["cross_sectional_rank"].astype("Float64")
    signal = pd.Series(0, index=df.index, dtype=int)
    signal.loc[rank >= 0.75] = 1
    signal.loc[rank <= 0.25] = -1
    return signal

generated_strategy = declare_thin(
    _raw,
    feature_requirements=FEATURE_REQUIREMENTS,
    sizing_spec={"mode": "unit_notional_research_only"},
)

