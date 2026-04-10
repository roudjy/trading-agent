from __future__ import annotations

import json
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path

import pytest

from execution.paper.polymarket_sim import (
    MaxEntryPriceExceededError,
    NoLiquidityError,
    POLYMARKET_FEE_BPS,
    PolymarketPaperBroker,
)
from execution.protocols import OrderIntent


FIXTURE_PATH = Path("tests/fixtures/polymarket/snapshot_basic.json")


def _snapshot() -> dict:
    snapshot = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    snapshot["timestamp_utc"] = datetime.fromisoformat(snapshot["timestamp_utc"])
    return snapshot


def _intent(size: float, side: str = "buy") -> OrderIntent:
    return OrderIntent(
        instrument_id="pm-market-001",
        side=side,
        size=size,
        limit_price=None,
        venue="polymarket",
        client_tag="unit-test",
    )


def test_full_fill_on_top_ask_level():
    broker = PolymarketPaperBroker()

    fill = broker.place_paper_order(_intent(size=10.0), _snapshot())

    assert fill.size == 10.0
    assert fill.intended_price == 0.50
    assert fill.fill_price == 0.50
    assert fill.slippage_bps == 0.0
    assert fill.timestamp_utc == datetime(2026, 4, 10, 12, 0, tzinfo=UTC)


def test_multi_level_walk_uses_weighted_average_fill_price():
    broker = PolymarketPaperBroker()

    fill = broker.place_paper_order(_intent(size=60.0), _snapshot())

    expected_price = ((25.0 * 0.50) + (30.0 * 0.52) + (5.0 * 0.55)) / 60.0
    assert fill.size == 60.0
    assert fill.fill_price == pytest.approx(expected_price)


def test_partial_fill_when_book_is_exhausted():
    broker = PolymarketPaperBroker()

    fill = broker.place_paper_order(_intent(size=120.0), _snapshot())

    assert fill.size == 95.0
    assert fill.fill_price == pytest.approx(((25.0 * 0.50) + (30.0 * 0.52) + (40.0 * 0.55)) / 95.0)


def test_no_liquidity_error_when_relevant_book_side_is_empty():
    broker = PolymarketPaperBroker()
    snapshot = _snapshot()
    snapshot["yes_asks"] = []

    with pytest.raises(NoLiquidityError):
        broker.place_paper_order(_intent(size=1.0), snapshot)


def test_max_entry_price_exceeded_when_buy_fills_above_sixty_cents():
    broker = PolymarketPaperBroker()
    snapshot = _snapshot()
    snapshot["yes_asks"] = [[0.61, 2.0]]

    with pytest.raises(MaxEntryPriceExceededError):
        broker.place_paper_order(_intent(size=1.0), snapshot)


def test_determinism_same_inputs_produce_identical_fill():
    broker = PolymarketPaperBroker()
    snapshot = _snapshot()
    intent = _intent(size=55.0)

    fill_one = broker.place_paper_order(intent, deepcopy(snapshot))
    fill_two = broker.place_paper_order(intent, deepcopy(snapshot))

    assert fill_one == fill_two


def test_slippage_math_matches_hand_computed_example():
    broker = PolymarketPaperBroker()

    fill = broker.place_paper_order(_intent(size=40.0), _snapshot())

    expected_fill_price = ((25.0 * 0.50) + (15.0 * 0.52)) / 40.0
    expected_slippage = round((expected_fill_price - 0.50) / 0.50 * 10000, 4)
    assert fill.slippage_bps == expected_slippage


def test_fee_math_matches_hand_computed_example():
    broker = PolymarketPaperBroker()

    fill = broker.place_paper_order(_intent(size=10.0), _snapshot())

    expected_fee = 0.50 * 10.0 * POLYMARKET_FEE_BPS / 10000
    assert fill.fee_ccy == "USDC"
    assert fill.fee_amount == pytest.approx(expected_fee)
