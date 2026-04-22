"""Regression: `make_result_row` must never emit a None/empty strategy_name.

The public output contract pins strategy_name as a required, non-empty
string column. A silent None leak would poison `strategy_matrix.csv` and
any downstream analytics that groups by strategy. See ADR-011 (v3.10
architecture) for the data-integrity rationale.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from research.registry import get_enabled_strategies
from research.results import make_result_row


@pytest.mark.parametrize(
    "strategy",
    get_enabled_strategies(),
    ids=lambda s: s["name"],
)
def test_make_result_row_populates_strategy_name(strategy):
    row = make_result_row(
        strategy=strategy,
        asset="BTC-USD",
        interval="1h",
        params={},
        as_of_utc=datetime(2026, 4, 22, tzinfo=UTC),
    )
    assert isinstance(row["strategy_name"], str)
    assert row["strategy_name"] == strategy["name"]
    assert row["strategy_name"] != ""


@pytest.mark.parametrize(
    "broken_name",
    [None, "", 0, False, 123],
)
def test_make_result_row_raises_on_missing_strategy_name(broken_name):
    broken_strategy = {
        "name": broken_name,
        "family": "x",
        "hypothesis": "x",
    }
    with pytest.raises(ValueError, match="strategy\\['name'\\]"):
        make_result_row(
            strategy=broken_strategy,
            asset="BTC-USD",
            interval="1h",
            params={},
            as_of_utc=datetime(2026, 4, 22, tzinfo=UTC),
        )


def test_make_result_row_raises_when_strategy_is_not_a_dict():
    with pytest.raises(ValueError, match="strategy\\['name'\\]"):
        make_result_row(
            strategy=None,  # type: ignore[arg-type]
            asset="BTC-USD",
            interval="1h",
            params={},
            as_of_utc=datetime(2026, 4, 22, tzinfo=UTC),
        )
