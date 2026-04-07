"""
Resilience tests: het systeem moet graceful degraden bij fouten.
- Geen crashes bij ontbrekende data
- Timeout handling (analyst 5s)
- Slechte API responses
- Lege marktdata
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch


CFG = {
    'kapitaal': {'start': 300.0, 'max_positie_grootte': 0.10, 'drawdown_limiet': 0.75},
    'strategie': {},
    'ai': {'anthropic_api_key': 'test_key'},
    'database': {'pad': ':memory:'},
}


# ── RSI agent met lege marktdata ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_rsi_agent_lege_marktdata():
    """RSI agent crasht niet bij lege marktdata."""
    from agent.agents.rsi_agent import RSIAgent

    executor = MagicMock()
    executor.voer_uit = AsyncMock(return_value=None)
    executor.sluit_positie = AsyncMock(return_value=None)
    geheugen = MagicMock()
    geheugen.tel_open_posities = MagicMock(return_value=0)
    geheugen.heeft_open_positie_db = MagicMock(return_value=False)
    geheugen.analyseer_prestaties = MagicMock(return_value={'per_strategie': {}})

    agent = RSIAgent(CFG, executor, geheugen)

    # Geen enkel symbool in marktdata
    await agent.run_cyclus(markt_data={}, regime={}, sentiment=None, bot_patronen=None)
    assert len(agent.open_posities) == 0


@pytest.mark.asyncio
async def test_rsi_agent_missende_indicatoren():
    """RSI agent crasht niet bij missende indicatoren."""
    from agent.agents.rsi_agent import RSIAgent

    executor = MagicMock()
    executor.voer_uit = AsyncMock(return_value=None)
    geheugen = MagicMock()
    geheugen.tel_open_posities = MagicMock(return_value=0)
    geheugen.heeft_open_positie_db = MagicMock(return_value=False)
    geheugen.analyseer_prestaties = MagicMock(return_value={'per_strategie': {}})
    agent = RSIAgent(CFG, executor, geheugen)

    # Data zonder indicatoren
    markt_data = {'BTC/EUR': {'prijs': 50000, 'volume': 1000}}
    signalen = await agent._genereer_signalen(
        markt_data=markt_data, regime={}, sentiment=None, bot_patronen=None
    )
    assert signalen == []


# ── EMA agent bij ontbrekende EMA waarden ───────────────────────────────────

@pytest.mark.asyncio
async def test_ema_agent_geen_ema_waarden():
    """EMA agent crasht niet als EMA waarden ontbreken."""
    from agent.agents.ema_agent import EMAAgent
    from datetime import time

    executor = MagicMock()
    executor.voer_uit = AsyncMock(return_value=None)
    geheugen = MagicMock()
    geheugen.tel_open_posities = MagicMock(return_value=0)
    geheugen.heeft_open_positie_db = MagicMock(return_value=False)
    geheugen.analyseer_prestaties = MagicMock(return_value={'per_strategie': {}})
    agent = EMAAgent(CFG, executor, geheugen)

    markt_data = {
        'NVDA': {
            'prijs': 500,
            'volume': 1200,
            'gem_volume': 1000,
            'indicatoren': {}  # Leeg — geen EMA waarden
        }
    }

    with patch('agent.agents.ema_agent.datetime') as mock_dt:
        mock_dt.now.return_value.time.return_value = time(17, 0)
        signalen = await agent._genereer_signalen(
            markt_data=markt_data, regime={}, sentiment=None, bot_patronen=None
        )

    assert signalen == []


# ── Analyst Layer 1: timeout geeft ga_door terug ─────────────────────────────

@pytest.mark.asyncio
async def test_analyst_timeout_geeft_ga_door():
    """Bij timeout geeft analyst 'ga_door' terug — signaal wordt niet geblokkeerd."""
    from agent.brain.analyst import ClaudeAnalyst
    from agent.risk.risk_manager import TradeSignaal

    analyst = ClaudeAnalyst(CFG)

    # Simuleer timeout
    async def trage_api(*args, **kwargs):
        await asyncio.sleep(10)  # Langer dan 5s timeout

    analyst._vraag_haiku = trage_api

    signaal = MagicMock(spec=TradeSignaal)
    signaal.symbool = 'BTC/EUR'
    signaal.richting = 'long'
    signaal.strategie_type = 'sentiment'
    signaal.bron = 'test'
    signaal.zekerheid = 0.75

    resultaat = await analyst.filter_signaal(signaal, sentiment_score=0.80)
    assert resultaat['beslissing'] == 'ga_door'


# ── Analyst zonder API key ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_analyst_zonder_api_key():
    """Analyst zonder API key laat signalen door."""
    from agent.brain.analyst import ClaudeAnalyst
    from agent.risk.risk_manager import TradeSignaal

    cfg_zonder_key = {**CFG, 'ai': {'anthropic_api_key': ''}}
    analyst = ClaudeAnalyst(cfg_zonder_key)

    signaal = MagicMock()
    signaal.symbool = 'BTC/EUR'
    signaal.richting = 'long'
    signaal.strategie_type = 'sentiment'
    signaal.bron = 'test'
    signaal.zekerheid = 0.75

    resultaat = await analyst.filter_signaal(signaal, sentiment_score=0.80)
    assert resultaat['beslissing'] == 'ga_door'


# ── Bot agent zonder patronen ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_bot_agent_geen_patronen():
    """Bot agent crasht niet als er geen bot-patronen zijn."""
    from agent.agents.bot_agent import BotAgent

    executor = MagicMock()
    executor.voer_uit = AsyncMock(return_value=None)
    geheugen = MagicMock()
    geheugen.tel_open_posities = MagicMock(return_value=0)
    geheugen.heeft_open_positie_db = MagicMock(return_value=False)
    geheugen.analyseer_prestaties = MagicMock(return_value={'per_strategie': {}})
    agent = BotAgent(CFG, executor, geheugen)

    signalen = await agent._genereer_signalen(
        markt_data={}, regime={}, sentiment=None, bot_patronen=[]
    )
    assert signalen == []


# ── Zelfverbeteraar met te weinig trades ─────────────────────────────────────

@pytest.mark.asyncio
async def test_zelfverbeteraar_te_weinig_trades():
    """Zelfverbeteraar stopt graceful bij < 10 trades."""
    from agent.learning.self_improver import ZelfVerbeteraar

    zv = ZelfVerbeteraar(CFG)

    # Mock lees_trades geeft maar 5 trades terug
    with patch.object(zv, '_lees_trades', return_value=[{'pnl': 1.0}] * 5):
        resultaat = await zv.verbeter(agent_stats={})

    assert resultaat == ""
