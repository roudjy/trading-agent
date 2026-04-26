"""v3.15.8 — pin v3.15.7 exploratory threshold constants. v3.15.8
must change sampling and never the screening criteria.
"""

from __future__ import annotations

from research.screening_criteria import (
    EXPLORATORY_MAX_DRAWDOWN,
    EXPLORATORY_MIN_EXPECTANCY,
    EXPLORATORY_MIN_PROFIT_FACTOR,
)


def test_v3_15_7_exploratory_min_expectancy_unchanged() -> None:
    assert EXPLORATORY_MIN_EXPECTANCY == 0.0


def test_v3_15_7_exploratory_min_profit_factor_unchanged() -> None:
    assert EXPLORATORY_MIN_PROFIT_FACTOR == 1.05


def test_v3_15_7_exploratory_max_drawdown_unchanged() -> None:
    assert EXPLORATORY_MAX_DRAWDOWN == 0.45
