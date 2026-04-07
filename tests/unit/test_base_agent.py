"""Unit tests voor BaseAgent."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta

# Minimal config
CFG = {
    'kapitaal': {'start': 300.0, 'max_positie_grootte': 0.10, 'drawdown_limiet': 0.75},
    'strategie': {},
    'ai': {'anthropic_api_key': ''},
    'database': {'pad': ':memory:'},
}


def _maak_agent():
    """Maak een concrete BaseAgent subclass voor testing."""
    from agent.agents.base_agent import BaseAgent
    from agent.risk.risk_manager import TradeSignaal

    class TestAgent(BaseAgent):
        naam = "test"
        async def _genereer_signalen(self, markt_data, regime, sentiment, bot_patronen):
            return []

    executor = MagicMock()
    executor.voer_uit = AsyncMock(return_value=None)
    executor.sluit_positie = AsyncMock(return_value=None)
    geheugen = MagicMock()
    geheugen.tel_open_posities = MagicMock(return_value=0)
    geheugen.heeft_open_positie_db = MagicMock(return_value=False)
    geheugen.analyseer_prestaties = MagicMock(return_value={'per_strategie': {}})
    geheugen.cooldown_actief = MagicMock(return_value=False)  # Cooldown standaard niet actief

    return TestAgent(CFG, executor, geheugen)


def test_initieel_kapitaal():
    agent = _maak_agent()
    assert agent.kapitaal_pool == 300.0


def test_cooldown_nieuw_symbool():
    agent = _maak_agent()
    assert agent._cooldown_voorbij('BTC/EUR') is True


def test_cooldown_actief():
    """Cooldown actief = geheugen.cooldown_actief retourneert True."""
    agent = _maak_agent()
    agent.geheugen.cooldown_actief = MagicMock(return_value=True)
    assert agent._cooldown_voorbij('BTC/EUR') is False


def test_cooldown_verlopen():
    """Cooldown verlopen = geheugen.cooldown_actief retourneert False."""
    agent = _maak_agent()
    agent.geheugen.cooldown_actief = MagicMock(return_value=False)
    assert agent._cooldown_voorbij('BTC/EUR') is True


def test_geen_open_positie():
    agent = _maak_agent()
    assert agent._heeft_open_positie('BTC/EUR') is False


def test_heeft_open_positie():
    agent = _maak_agent()
    positie = MagicMock()
    positie.symbool = 'BTC/EUR'
    agent.open_posities['abc123'] = positie
    assert agent._heeft_open_positie('BTC/EUR') is True


def test_drawdown_ok_bij_start():
    agent = _maak_agent()
    assert agent._drawdown_ok() is True


def test_drawdown_force_exit():
    agent = _maak_agent()
    agent.piek_kapitaal = 300.0
    agent.kapitaal_pool = 50.0   # 83% drawdown
    assert agent._drawdown_ok() is False


def test_stop_loss_ceiling():
    agent = _maak_agent()
    assert agent._clamp_stop_loss(0.10) == 0.08   # Hard ceiling 8%
    assert agent._clamp_stop_loss(0.05) == 0.05   # Onder ceiling: ongewijzigd
    assert agent._clamp_stop_loss(0.02) == 0.02


def test_prestatie_stats_leeg():
    agent = _maak_agent()
    stats = agent.prestatie_stats()
    assert stats['naam'] == 'test'
    assert stats['totaal_trades'] == 0
    assert stats['win_rate'] == 0


@pytest.mark.asyncio
async def test_run_cyclus_geen_signalen():
    agent = _maak_agent()
    await agent.run_cyclus(markt_data={}, regime={}, sentiment=None, bot_patronen=None)
    assert len(agent.open_posities) == 0


@pytest.mark.asyncio
async def test_run_cyclus_geblokkeerd_drawdown():
    agent = _maak_agent()
    agent.piek_kapitaal = 300.0
    agent.kapitaal_pool = 50.0  # >75% drawdown

    # Voeg een open positie toe
    positie = MagicMock()
    positie.symbool = 'BTC/EUR'
    agent.open_posities['abc'] = positie

    agent.executor.sluit_positie = AsyncMock(return_value=None)

    markt_data = {'BTC/EUR': {'prijs': 30000}}
    await agent.run_cyclus(markt_data=markt_data, regime={}, sentiment=None, bot_patronen=None)

    # sluit_positie moet aangeroepen zijn
    agent.executor.sluit_positie.assert_called_once()
