"""Regression tests for price availability safety in the order executor."""

import inspect
import logging

import pytest

from agent.risk.risk_manager import TradeSignaal

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


def _signaal() -> TradeSignaal:
    return TradeSignaal(
        symbool='ETH/EUR',
        richting='long',
        strategie_type='rsi',
        verwacht_rendement=0.02,
        win_kans=0.60,
        stop_loss_pct=0.05,
        take_profit_pct=0.08,
        bron='regression-test',
        zekerheid=0.70,
        regime='trend',
    )


def test_hardcoded_price_dictionary_removed():
    from agent.execution.order_executor import OrderExecutor

    source = inspect.getsource(OrderExecutor._haal_huidige_prijs)
    assert "prijzen = {" not in source
    assert "65000.0" not in source


def test_price_unavailable_error_propagates():
    from agent.execution.order_executor import OrderExecutor, PriceUnavailableError

    executor = OrderExecutor(CFG)
    with pytest.raises(PriceUnavailableError, match='ETH/EUR'):
        executor._haal_huidige_prijs('ETH/EUR')


@pytest.mark.asyncio
async def test_missing_price_logs_and_skips_trade(caplog):
    from agent.execution.order_executor import OrderExecutor

    executor = OrderExecutor(CFG)
    caplog.set_level(logging.ERROR)

    result = await executor._paper_trade(_signaal(), markt_data={})

    assert result is None
    assert "Geen prijs beschikbaar voor ETH/EUR" in caplog.text
