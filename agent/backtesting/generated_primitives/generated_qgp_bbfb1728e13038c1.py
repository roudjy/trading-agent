from __future__ import annotations

import pandas as pd

from agent.backtesting.features import FeatureSpec

PRIMITIVE_ID = "cross_sectional_rank"
GENERATED_PRIMITIVE_ID = "qgp_bbfb1728e13038c1"
PRIMITIVE_SPEC_ID = "qps_008aa161c214b2b5"
GENERATOR_VERSION = "ade-qre-021.1"
IMPLEMENTATION_TEMPLATE_VERSION = "cross-sectional-rank-template.1"

def _warmup(params: dict) -> int:
    return int(params.get("lookback_bars", 20))

def cross_sectional_rank(
    close: pd.Series,
    *,
    lookback_bars: int = 20,
    ascending: bool = False,
    rank_mode: str = "PERCENTILE",
    tie_policy: str = "AVERAGE",
    missing_value_policy: str = "FAIL_CLOSED",
    minimum_universe_size: int = 3,
) -> pd.Series:
    if not isinstance(close.index, pd.MultiIndex):
        raise ValueError("cross_sectional_rank requires MultiIndex(timestamp, asset)")
    if close.index.nlevels != 2:
        raise ValueError("cross_sectional_rank requires exactly two index levels")
    if minimum_universe_size < 2:
        raise ValueError("minimum_universe_size must be >= 2")
    if rank_mode not in {"ORDINAL", "DENSE", "PERCENTILE", "NORMALIZED"}:
        raise ValueError("unsupported rank_mode")
    if tie_policy not in {"STABLE_IDENTITY_ORDER", "MIN", "MAX", "AVERAGE"}:
        raise ValueError("unsupported tie_policy")
    if missing_value_policy not in {"EXCLUDE_WITH_REASON", "RANK_LAST", "FAIL_CLOSED"}:
        raise ValueError("unsupported missing_value_policy")
    ordered = close.astype(float).sort_index(level=[0, 1])
    timestamps = ordered.index.get_level_values(0)
    assets = ordered.index.get_level_values(1)
    duplicate_mask = pd.MultiIndex.from_arrays([timestamps, assets]).duplicated()
    if bool(duplicate_mask.any()):
        raise ValueError("duplicate asset/timestamp rows are not allowed")
    relative_strength = ordered.groupby(level=1).pct_change(periods=int(lookback_bars))
    if missing_value_policy == 'FAIL_CLOSED' and bool(relative_strength.isna().any()):
        return pd.Series(pd.NA, index=ordered.index, dtype='Float64')
    ranks = pd.Series(index=ordered.index, dtype=float)
    for timestamp, group in relative_strength.groupby(level=0, sort=True):
        values = group.droplevel(0)
        if len(values) < int(minimum_universe_size):
            for asset in values.index:
                ranks.loc[(timestamp, asset)] = pd.NA
            continue
        if values.isna().any():
            if missing_value_policy == 'FAIL_CLOSED':
                for asset in values.index:
                    ranks.loc[(timestamp, asset)] = pd.NA
                continue
            if missing_value_policy == 'EXCLUDE_WITH_REASON':
                valid = values.dropna()
            else:
                fill_value = float('inf') if ascending else float('-inf')
                valid = values.fillna(fill_value)
        else:
            valid = values
        method = {
            'STABLE_IDENTITY_ORDER': 'first',
            'MIN': 'min',
            'MAX': 'max',
            'AVERAGE': 'average',
        }[tie_policy]
        ranked = valid.rank(method=method, ascending=ascending, pct=(rank_mode == 'PERCENTILE'))
        if rank_mode == 'NORMALIZED':
            denominator = max(len(valid) - 1, 1)
            ranked = (ranked - 1.0) / denominator
        elif rank_mode == 'ORDINAL' and tie_policy == 'STABLE_IDENTITY_ORDER':
            ranked = ranked.astype(float)
        for asset in values.index:
            if asset in ranked.index:
                ranks.loc[(timestamp, asset)] = float(ranked.loc[asset])
            else:
                ranks.loc[(timestamp, asset)] = pd.NA
    return ranks.astype('Float64')

GENERATED_FEATURE_SPECS = {
    "cross_sectional_rank": FeatureSpec(
        fn=cross_sectional_rank,
        param_names=("lookback_bars", "ascending", "rank_mode", "tie_policy", "missing_value_policy", "minimum_universe_size"),
        required_columns=("close",),
        warmup_bars_fn=_warmup,
    )
}

