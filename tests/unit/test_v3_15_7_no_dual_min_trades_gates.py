"""v3.15.7 — the trade-count gate is unique.

The engine.min_trades pre-check in
``research/screening_runtime.py:283-285`` remains the only
trade-count gate. ``research/screening_criteria.py`` must NOT
introduce its own ``EXPLORATORY_MIN_TRADES`` constant — that
would risk drift between two parallel gates.
"""

from __future__ import annotations

import inspect

import research.screening_criteria as screening_criteria


def test_no_exploratory_min_trades_constant():
    """The module's docstring may MENTION the forbidden name to
    document the discipline; what we forbid is a real assignment.
    """
    assert not hasattr(screening_criteria, "EXPLORATORY_MIN_TRADES"), (
        "v3.15.7: do NOT introduce EXPLORATORY_MIN_TRADES. "
        "The trade-count gate lives upstream in screening_runtime "
        "via engine.min_trades; duplicating it here risks drift."
    )
    # Defensive: also ensure no assignment-style line defines it.
    src = inspect.getsource(screening_criteria)
    forbidden_assignments = (
        "EXPLORATORY_MIN_TRADES =",
        "EXPLORATORY_MIN_TRADES:",
    )
    for needle in forbidden_assignments:
        assert needle not in src, (
            f"v3.15.7: assignment {needle!r} found in screening_criteria.py"
        )


def test_module_attributes_only_known_thresholds():
    """Pin the constants surface so future drift is visible."""
    expected = {
        "EXPLORATORY_MIN_EXPECTANCY",
        "EXPLORATORY_MIN_PROFIT_FACTOR",
        "EXPLORATORY_MAX_DRAWDOWN",
    }
    actual = {
        name for name, value in vars(screening_criteria).items()
        if name.startswith("EXPLORATORY_") and not callable(value)
    }
    assert actual == expected, f"unexpected EXPLORATORY_* constants: {actual}"
