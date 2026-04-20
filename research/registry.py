"""
Research registry:
centrale bron voor alle strategieen, param-grids en metadata.
"""

# AGENTS.md rules violation - scheduled for Phase 2 replacement.
# This file currently performs a brute-force Cartesian parameter sweep.
# Phase 1 adds a size guard; Phase 2 will replace it with a hypothesis-driven envelope.

from itertools import product

from agent.backtesting.strategies import (
    bollinger_regime_strategie,
    bollinger_strategie,
    breakout_momentum_strategie,
    pairs_zscore_strategie,
    rsi_strategie,
    sma_crossover_strategie,
    trend_pullback_strategie,
    trend_pullback_tp_sl_strategie,
    zscore_mean_reversion_strategie,
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
        "strategy_family": "mean_reversion",
        "position_structure": "outright",
        "initial_lane_support": "supported",
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
        "strategy_family": "mean_reversion",
        "position_structure": "outright",
        "initial_lane_support": "supported",
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
        "strategy_family": "mean_reversion",
        "position_structure": "outright",
        "initial_lane_support": "supported",
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
        "strategy_family": "trend_following",
        "position_structure": "outright",
        "initial_lane_support": "supported",
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
        "strategy_family": "trend_following",
        "position_structure": "outright",
        "initial_lane_support": "supported",
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
        "strategy_family": "breakout",
        "position_structure": "outright",
        "initial_lane_support": "supported",
        "hypothesis": "Crypto kan sterker reageren op breakout momentum dan op mean reversion.",
        "enabled": True,
    },
    {
        "name": "sma_crossover",
        "factory": sma_crossover_strategie,
        "params": {
            "fast_window": [10, 20],
            "slow_window": [50, 100],
        },
        "family": "trend",
        "strategy_family": "trend_following",
        "position_structure": "outright",
        "initial_lane_support": "supported",
        "hypothesis": (
            "Klassieke SMA crossover capturet persistent directional moves "
            "per orchestrator_brief §4.1 tier 1 baseline."
        ),
        "enabled": True,
        "contract_version": "1.0",
    },
    {
        "name": "zscore_mean_reversion",
        "factory": zscore_mean_reversion_strategie,
        "params": {
            "lookback": [20, 30],
            "entry_z": [2.0],
            "exit_z": [0.5],
        },
        "family": "mean_reversion",
        "strategy_family": "mean_reversion",
        "position_structure": "outright",
        "initial_lane_support": "supported",
        "hypothesis": (
            "Price z-score mean reversion capturet deviations from "
            "equilibrium per orchestrator_brief §4.2 tier 1 baseline."
        ),
        "enabled": True,
        "contract_version": "1.0",
    },
    # -------------------------------------------------------------------
    # pairs_zscore — enabled=False is intentional.
    # Blocker: the backtest engine currently loads one DataFrame per
    # asset (see agent/backtesting/engine.py:_run_op_split). A
    # 'close_ref' column is never populated, so the pairs factory
    # cannot run inside the existing pipeline. Wiring is deferred to
    # a separate future multi-asset loader scaffold prompt. Do NOT
    # flip this flag to True without that scaffold in place.
    # -------------------------------------------------------------------
    {
        "name": "pairs_zscore",
        "factory": pairs_zscore_strategie,
        "params": {
            "lookback": [30],
            "entry_z": [2.0],
            "exit_z": [0.5],
            "hedge_ratio": [1.0],
        },
        "family": "stat_arb",
        "strategy_family": "stat_arb",
        "position_structure": "spread",
        "initial_lane_support": "blocked",
        "hypothesis": (
            "Spread z-score pairs trading per orchestrator_brief §4.3 "
            "tier 1 baseline. enabled=False is intentional: the "
            "current engine has no multi-asset loader to populate "
            "'close_ref'. Pipeline wiring deferred to a separate "
            "future multi-asset loader scaffold prompt."
        ),
        "enabled": False,
        "contract_version": "1.0",
    },
]


def get_enabled_strategies():
    return [s for s in STRATEGIES if s.get("enabled", True)]


def count_param_combinations(strategy_dict):
    total = 1
    for values in strategy_dict.get("params", {}).values():
        total *= len(values)
    return total


def iter_strategy_families():
    families = {}
    for strategy in get_enabled_strategies():
        families.setdefault(strategy["family"], []).append(strategy)

    for family in sorted(families):
        yield family, sorted(families[family], key=lambda strategy: strategy["name"])


def expand_param_grid(param_grid):
    keys = list(param_grid.keys())
    values = list(param_grid.values())

    combinations = []
    for combo in product(*values):
        combinations.append(dict(zip(keys, combo)))

    return combinations
