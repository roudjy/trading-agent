"""Integratie test: signaal generatie → risico check → executie pipeline."""
import pytest
from unittest.mock import AsyncMock, MagicMock


CFG = {
    'kapitaal': {'start': 300.0, 'max_positie_grootte': 0.10, 'drawdown_limiet': 0.75},
    'strategie': {},
    'ai': {'anthropic_api_key': ''},
    'database': {'pad': ':memory:'},
}

MARKT_DATA = {
    'BTC/EUR': {
        'prijs': 50000.0,
        'volume': 1000,
        'gem_volume': 800,
        'indicatoren': {
            'rsi': 24.0,         # Oversold → long signaal
            'ema_20': 49000,
            'ema_50': 48000,
            'macd': 0.5,
            'macd_signaal': 0.3,
            'bb_boven': 52000,
            'bb_midden': 50000,
            'bb_onder': 48000,
            'atr': 1200,
        }
    }
}


@pytest.mark.asyncio
async def test_rsi_signaal_leidt_tot_trade():
    """RSI oversold → signaal → executor aangeroepen."""
    from agent.agents.rsi_agent import RSIAgent

    trade_mock = MagicMock()
    trade_mock.id = 'test_trade_1'
    trade_mock.symbool = 'BTC/EUR'
    trade_mock.euro_bedrag = 30.0
    trade_mock.pnl = None
    trade_mock.stop_loss_pct = 0.05
    trade_mock.take_profit_pct = 0.08
    trade_mock.bereken_pnl_pct = MagicMock(return_value=0.01)

    executor = MagicMock()
    executor.voer_uit = AsyncMock(return_value=trade_mock)
    executor.sluit_positie = AsyncMock(return_value=None)
    geheugen = MagicMock()
    geheugen.tel_open_posities = MagicMock(return_value=0)
    geheugen.heeft_open_positie_db = MagicMock(return_value=False)
    geheugen.analyseer_prestaties = MagicMock(return_value={'per_strategie': {}})
    geheugen.cooldown_actief = MagicMock(return_value=False)

    agent = RSIAgent(CFG, executor, geheugen)

    await agent.run_cyclus(
        markt_data=MARKT_DATA,
        regime={},
        sentiment=None,
        bot_patronen=None,
    )

    executor.voer_uit.assert_called_once()
    assert 'test_trade_1' in agent.open_posities


@pytest.mark.asyncio
async def test_dedup_blokkeert_tweede_trade():
    """Geen tweede trade voor zelfde symbool."""
    from agent.agents.rsi_agent import RSIAgent

    trade_mock = MagicMock()
    trade_mock.id = 'trade_1'
    trade_mock.symbool = 'BTC/EUR'
    trade_mock.euro_bedrag = 30.0

    executor = MagicMock()
    executor.voer_uit = AsyncMock(return_value=trade_mock)
    executor.sluit_positie = AsyncMock(return_value=None)
    geheugen = MagicMock()
    geheugen.tel_open_posities = MagicMock(return_value=0)
    geheugen.heeft_open_positie_db = MagicMock(return_value=False)
    geheugen.analyseer_prestaties = MagicMock(return_value={'per_strategie': {}})
    geheugen.cooldown_actief = MagicMock(return_value=False)

    agent = RSIAgent(CFG, executor, geheugen)

    # Eerste run: trade geopend
    await agent.run_cyclus(
        markt_data=MARKT_DATA, regime={}, sentiment=None, bot_patronen=None
    )
    assert executor.voer_uit.call_count == 1

    # Tweede run: zelfde symbool al open → geen nieuwe trade
    await agent.run_cyclus(
        markt_data=MARKT_DATA, regime={}, sentiment=None, bot_patronen=None
    )
    assert executor.voer_uit.call_count == 1  # Nog steeds 1


@pytest.mark.asyncio
async def test_stop_loss_sluit_positie():
    """Stop-loss triggered → positie gesloten."""
    from agent.agents.rsi_agent import RSIAgent

    # Open positie
    positie = MagicMock()
    positie.symbool = 'BTC/EUR'
    positie.richting = 'long'
    positie.stop_loss_pct = 0.05
    positie.take_profit_pct = 0.08
    positie.bereken_pnl_pct = MagicMock(return_value=-0.06)  # -6% → boven stop 5%

    resultaat = MagicMock()
    resultaat.pnl = -300.0
    resultaat.euro_bedrag = 30.0

    executor = MagicMock()
    executor.voer_uit = AsyncMock(return_value=None)
    executor.sluit_positie = AsyncMock(return_value=resultaat)
    geheugen = MagicMock()
    geheugen.tel_open_posities = MagicMock(return_value=0)
    geheugen.heeft_open_positie_db = MagicMock(return_value=False)
    geheugen.analyseer_prestaties = MagicMock(return_value={'per_strategie': {}})
    geheugen.cooldown_actief = MagicMock(return_value=False)

    agent = RSIAgent(CFG, executor, geheugen)
    agent.open_posities['trade_1'] = positie

    markt_data = {'BTC/EUR': {'prijs': 47000}}  # Gedaald
    await agent._monitor_posities(markt_data, {})

    executor.sluit_positie.assert_called_once()
    assert 'trade_1' not in agent.open_posities
