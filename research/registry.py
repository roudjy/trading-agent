"""
Research registry:
centrale bron voor alle strategieën, param-grids en metadata.
"""

from itertools import product

from agent.backtesting.strategies import (
    rsi_strategie,
    bollinger_strategie,
    bollinger_regime_strategie,
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
