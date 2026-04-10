from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest

from execution.protocols import BrokerProtocol, Fill, LiveGateClosedError, OrderIntent, PaperBrokerBase


class _DummyPaperBroker(PaperBrokerBase):
    name = "dummy-paper"

    def place_paper_order(self, intent: OrderIntent, market_snapshot: dict) -> Fill:
        return Fill(
            instrument_id=intent.instrument_id,
            side=intent.side,
            size=intent.size,
            intended_price=0.5,
            fill_price=0.5,
            slippage_bps=0.0,
            fee_ccy="USDC",
            fee_amount=0.0,
            timestamp_utc=datetime(2026, 4, 10, tzinfo=UTC),
            venue=intent.venue,
        )


def test_fill_is_frozen():
    fill = Fill(
        instrument_id="pm-1",
        side="buy",
        size=1.0,
        intended_price=0.4,
        fill_price=0.41,
        slippage_bps=250.0,
        fee_ccy="USDC",
        fee_amount=0.0082,
        timestamp_utc=datetime(2026, 4, 10, tzinfo=UTC),
        venue="polymarket",
    )

    with pytest.raises(FrozenInstanceError):
        fill.fill_price = 0.42


def test_order_intent_rejects_empty_instrument_id():
    with pytest.raises(ValueError, match="instrument_id"):
        OrderIntent(
            instrument_id="   ",
            side="buy",
            size=1.0,
            limit_price=None,
            venue="polymarket",
            client_tag=None,
        )


def test_place_live_order_raises_live_gate_closed(monkeypatch):
    broker = _DummyPaperBroker()
    intent = OrderIntent(
        instrument_id="pm-1",
        side="buy",
        size=1.0,
        limit_price=None,
        venue="polymarket",
        client_tag="test",
    )

    monkeypatch.setattr("execution.protocols.live_gate.is_live_armed", lambda: False)

    with pytest.raises(LiveGateClosedError):
        broker.place_live_order(intent, {})


def test_place_live_order_raises_not_implemented_when_armed(monkeypatch):
    broker = _DummyPaperBroker()
    intent = OrderIntent(
        instrument_id="pm-1",
        side="buy",
        size=1.0,
        limit_price=None,
        venue="polymarket",
        client_tag="test",
    )

    monkeypatch.setattr("execution.protocols.live_gate.is_live_armed", lambda: True)

    with pytest.raises(NotImplementedError):
        broker.place_live_order(intent, {})


def test_runtime_protocol_conformance():
    broker = _DummyPaperBroker()
    assert isinstance(broker, BrokerProtocol)
