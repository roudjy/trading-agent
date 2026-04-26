"""v3.15.7 — diagnostic_metrics produced by screening_runtime is
JSON-safe (allow_nan=False) for every phase × pass/fail path.

We synthesize an outcome dict's diagnostic_metrics directly from
the engine output to keep the test pure (no full screening engine
runs).
"""

from __future__ import annotations

import json

from agent.backtesting.engine import BacktestEngine


def _diagnostic_metrics_from(engine_metrics: dict) -> dict:
    """Mirror the screening_runtime aggregate construction."""
    return {
        "expectancy": float(engine_metrics.get("expectancy", 0.0)),
        "profit_factor": float(engine_metrics.get("profit_factor", 0.0)),
        "win_rate": float(engine_metrics.get("win_rate", 0.0)),
        "max_drawdown": float(engine_metrics.get("max_drawdown", 0.0)),
    }


def _engine_metrics(trade_pnls):
    e = BacktestEngine.__new__(BacktestEngine)
    return e._metrics(list(trade_pnls), [], [])


def test_diagnostic_metrics_json_safe_mixed():
    diag = _diagnostic_metrics_from(_engine_metrics([0.01, -0.005, 0.02]))
    json.dumps(diag, allow_nan=False)


def test_diagnostic_metrics_json_safe_only_winners():
    """Cap path: profit_factor = 999.0; still finite."""
    diag = _diagnostic_metrics_from(_engine_metrics([0.05, 0.10]))
    json.dumps(diag, allow_nan=False)
    assert diag["profit_factor"] == 999.0


def test_diagnostic_metrics_json_safe_only_losers():
    diag = _diagnostic_metrics_from(_engine_metrics([-0.01, -0.02]))
    json.dumps(diag, allow_nan=False)
    assert diag["profit_factor"] == 0.0


def test_diagnostic_metrics_json_safe_empty():
    diag = _diagnostic_metrics_from(_engine_metrics([]))
    json.dumps(diag, allow_nan=False)


def test_diagnostic_metrics_no_nan_no_inf():
    """Defensive: explicitly verify no NaN/inf can leak."""
    import math

    cases = [
        _engine_metrics([]),
        _engine_metrics([0.05, 0.10]),       # cap
        _engine_metrics([-0.01, -0.02]),     # zeros
        _engine_metrics([0.01, -0.005]),     # ratio
    ]
    for engine_metrics in cases:
        diag = _diagnostic_metrics_from(engine_metrics)
        for key, value in diag.items():
            assert math.isfinite(value), f"{key} not finite: {value}"
