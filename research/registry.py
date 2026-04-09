"""
Research registry:
centrale bron voor alle strategieën, param-grids en metadata.
"""

from itertools import product

from agent.backtesting.strategies import (
    rsi_strategie,
    bollinger_strategie,
    bollinger_regime_strategie,
    trend_pullback_strategie,
    trend_pullback_tp_sl_strategie,
    breakout_momentum_strategie,
)

STRATEGIES = [
    {
        "name": "rsi",
        "factory": rsi_strategie,
        "params": {
            "koop_drempel": [28, 30],
            "short_drempel": [70, 72],
            "periode": [14],
        },
        "family": "mean_reversion",
        "hypothesis": "RSI mean reversion werkt mogelijk alleen in niet-trending regimes.",
        "enabled": True,
    },
    {
        "name": "bollinger_mr",
        "factory": bollinger_strategie,
        "params": {
            "periode": [20],
            "std": [2.0],
        },
        "family": "mean_reversion",
        "hypothesis": "Bollinger mean reversion is waarschijnlijk zwak op intraday crypto.",
        "enabled": True,
    },
    {
        "name": "bollinger_regime",
        "factory": bollinger_regime_strategie,
        "params": {
            "config": [
                {
                    "strategie": {
                        "regime_detectie": {
                            "lookback_periode": 50,
                            "volatiliteit_drempel": 0.4,
                        }
                    }
                }
            ],
            "periode": [20],
            "std": [2.0],
        },
        "family": "mean_reversion",
        "hypothesis": "Regime filtering kan Bollinger verbeteren, maar lost zwakke MR-edge mogelijk niet op.",
        "enabled": True,
    },
    {
        "name": "trend_pullback",
        "factory": trend_pullback_strategie,
        "params": {
            "ema_kort": [20],
            "ema_lang": [100],
            "pullback_buffer": [0.01, 0.02],
            "slope_lookback": [3, 5],
            "vol_lookback": [20],
            "max_volatility": [0.02, 0.03],
        },
        "family": "trend",
        "hypothesis": "Crypto momentum maakt trend pullback plausibeler dan mean reversion.",
        "enabled": True,
    },
    {
        "name": "trend_pullback_tp_sl",
        "factory": trend_pullback_tp_sl_strategie,
        "params": {
            "ema_kort": [20],
            "ema_lang": [100],
            "pullback_buffer": [0.02],
            "slope_lookback": [3],
            "vol_lookback": [20],
            "max_volatility": [0.03],
            "take_profit": [0.03, 0.04, 0.05],
            "stop_loss": [0.01, 0.015, 0.02],
        },
        "family": "trend",
        "hypothesis": "Trend pullback kan verbeteren met expliciete take-profit en stop-loss trade management.",
        "enabled": True,
    },
    {
        "name": "breakout_momentum",
        "factory": breakout_momentum_strategie,
        "params": {
            "lookback": [20, 30],
            "ema_exit": [10, 20],
        },
        "family": "trend",
        "hypothesis": "Crypto kan sterker reageren op breakout momentum dan op mean reversion.",
        "enabled": True,
    },
]


def get_enabled_strategies():
    return [s for s in STRATEGIES if s.get("enabled", True)]


def expand_param_grid(param_grid):
    keys = list(param_grid.keys())
    values = list(param_grid.values())

    combinations = []
    for combo in product(*values):
        combinations.append(dict(zip(keys, combo)))

    return combinations
