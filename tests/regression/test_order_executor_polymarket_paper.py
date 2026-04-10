"""Regression coverage for Polymarket paper execution delegation."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from agent.risk.risk_manager import TradeSignaal
from execution.paper.polymarket_sim import MaxEntryPriceExceededError, NoLiquidityError
from execution.protocols import Fill, LiveGateClosedError


CFG = {
    'kapitaal': {'start': 300.0, 'max_positie_grootte': 0.10, 'drawdown_limiet': 0.75},
    'strategie': {'momentum': {'stop_loss': 0.03, 'take_profit': 0.06}},
    'ai': {'anthropic_api_key': ''},
    'database': {'pad': ':memory:'},
    'exchanges': {
        'bitvavo': {'actief': False, 'paper_trading': True, 'api_key': '', 'api_secret': ''},
        'kraken': {'actief': False, 'paper_trading': True, 'api_key': '', 'api_secret': ''},
        'ibkr': {'actief': False, 'paper_trading': True},
    },
}


def _polymarket_signaal() -> TradeSignaal:
    return TradeSignaal(
        symbool='pm-market-001',
        richting='long',
        strategie_type='data_arbitrage',
        verwacht_rendement=0.20,
        win_kans=0.90,
        stop_loss_pct=1.0,
        take_profit_pct=0.80,
        bron='polymarket-test',
        zekerheid=0.90,
        regime='polymarket',
    )


class _FakeBroker:
    name = "fake-polymarket"

    def __init__(self, outcome):
        self.outcome = outcome
        self.calls = []

    def place_paper_order(self, intent, market_snapshot):
        self.calls.append((intent, market_snapshot))
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome

    def place_live_order(self, intent, market_snapshot):
        raise NotImplementedError


def _fill(fill_price: float = 0.44, slippage_bps: float = 22.5) -> Fill:
    return Fill(
        instrument_id='pm-market-001',
        side='buy',
        size=20.0,
        intended_price=0.43,
        fill_price=fill_price,
        slippage_bps=slippage_bps,
        fee_ccy='USDC',
        fee_amount=1.76,
        timestamp_utc=datetime(2026, 4, 10, 12, 0, tzinfo=UTC),
        venue='polymarket',
    )


@pytest.mark.asyncio
async def test_polymarket_happy_path_uses_broker_fill_on_trade():
    from agent.execution.order_executor import OrderExecutor

    broker = _FakeBroker(_fill())
    executor = OrderExecutor(CFG, polymarket_broker=broker)

    trade = await executor.voer_uit(
        _polymarket_signaal(),
        markt_data={'pm-market-001': {'prijs': 0.43, 'volume': 50.0}},
        max_bedrag=10.0,
    )

    assert trade is not None
    assert trade.entry_prijs == 0.44
    assert trade.slippage_bps == 22.5
    assert broker.calls


@pytest.mark.asyncio
async def test_polymarket_no_liquidity_returns_no_trade():
    from agent.execution.order_executor import OrderExecutor

    executor = OrderExecutor(CFG, polymarket_broker=_FakeBroker(NoLiquidityError("empty book")))

    trade = await executor.voer_uit(
        _polymarket_signaal(),
        markt_data={'pm-market-001': {'prijs': 0.43, 'volume': 50.0}},
        max_bedrag=10.0,
    )

    assert trade is None


@pytest.mark.asyncio
async def test_polymarket_max_entry_price_returns_no_trade():
    from agent.execution.order_executor import OrderExecutor

    executor = OrderExecutor(CFG, polymarket_broker=_FakeBroker(MaxEntryPriceExceededError("too expensive")))

    trade = await executor.voer_uit(
        _polymarket_signaal(),
        markt_data={'pm-market-001': {'prijs': 0.61, 'volume': 50.0}},
        max_bedrag=10.0,
    )

    assert trade is None


@pytest.mark.asyncio
async def test_polymarket_live_gate_closed_returns_no_trade():
    from agent.execution.order_executor import OrderExecutor

    executor = OrderExecutor(CFG, polymarket_broker=_FakeBroker(LiveGateClosedError("closed")))

    trade = await executor.voer_uit(
        _polymarket_signaal(),
        markt_data={'pm-market-001': {'prijs': 0.43, 'volume': 50.0}},
        max_bedrag=10.0,
    )

    assert trade is None


@pytest.mark.asyncio
async def test_crypto_branch_is_unaffected_by_polymarket_broker_parameter():
    from agent.execution.order_executor import OrderExecutor

    class _FailIfCalledBroker(_FakeBroker):
        def place_paper_order(self, intent, market_snapshot):
            raise AssertionError("Polymarket broker should not be used for crypto symbols")

    executor = OrderExecutor(CFG, polymarket_broker=_FailIfCalledBroker(_fill()))
    signaal = TradeSignaal(
        symbool='BTC/EUR',
        richting='long',
        strategie_type='rsi',
        verwacht_rendement=0.02,
        win_kans=0.60,
        stop_loss_pct=0.05,
        take_profit_pct=0.08,
        bron='crypto-test',
        zekerheid=0.70,
        regime='trend',
    )

    trade = await executor.voer_uit(
        signaal,
        markt_data={'BTC/EUR': {'prijs': 50000.0}},
        max_bedrag=10.0,
    )

    assert trade is not None
    assert trade.entry_prijs == 50000.0
    assert trade.slippage_bps is None
