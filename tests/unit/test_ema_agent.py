"""Unit tests voor EMAAgent."""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import time


CFG = {
    'kapitaal': {'start': 300.0, 'max_positie_grootte': 0.10, 'drawdown_limiet': 0.75},
    'strategie': {},
    'ai': {'anthropic_api_key': ''},
    'database': {'pad': ':memory:'},
}


def _maak_ema_agent():
    from agent.agents.ema_agent import EMAAgent
    executor = MagicMock()
    executor.voer_uit = AsyncMock(return_value=None)
    geheugen = MagicMock()
    geheugen.tel_open_posities = MagicMock(return_value=0)
    geheugen.heeft_open_positie_db = MagicMock(return_value=False)
    geheugen.analyseer_prestaties = MagicMock(return_value={'per_strategie': {}})
    return EMAAgent(CFG, executor, geheugen)


def _markt_data(symbool: str, ema_20: float, ema_50: float,
                volume: float = 1200, gem_volume: float = 1000) -> dict:
    return {
        symbool: {
            'prijs': ema_20,
            'volume': volume,
            'gem_volume': gem_volume,
            'indicatoren': {
                'rsi': 55, 'ema_20': ema_20, 'ema_50': ema_50,
                'macd': 0.5, 'macd_signaal': 0.3
            }
        }
    }


@pytest.mark.asyncio
async def test_bullish_crossover_in_markttijden():
    agent = _maak_ema_agent()
    data = _markt_data('NVDA', ema_20=500, ema_50=490)

    # Mock markttijden: 17:00 NL
    with patch('agent.agents.ema_agent.datetime') as mock_dt:
        mock_dt.now.return_value.time.return_value = time(17, 0)
        signalen = await agent._genereer_signalen(
            markt_data=data, regime={}, sentiment=None, bot_patronen=None
        )

    nvda = [s for s in signalen if s.symbool == 'NVDA']
    assert len(nvda) == 1
    assert nvda[0].richting == 'long'


@pytest.mark.asyncio
async def test_geen_signaal_buiten_markttijden():
    agent = _maak_ema_agent()
    data = _markt_data('NVDA', ema_20=500, ema_50=490)

    # 08:00 NL — voor markt open
    with patch('agent.agents.ema_agent.datetime') as mock_dt:
        mock_dt.now.return_value.time.return_value = time(8, 0)
        signalen = await agent._genereer_signalen(
            markt_data=data, regime={}, sentiment=None, bot_patronen=None
        )

    assert signalen == []


@pytest.mark.asyncio
async def test_geen_signaal_onvoldoende_volume():
    agent = _maak_ema_agent()
    # Volume slechts 1.10x gem — onder de 1.20x drempel
    data = _markt_data('NVDA', ema_20=500, ema_50=490, volume=1100, gem_volume=1000)

    with patch('agent.agents.ema_agent.datetime') as mock_dt:
        mock_dt.now.return_value.time.return_value = time(17, 0)
        signalen = await agent._genereer_signalen(
            markt_data=data, regime={}, sentiment=None, bot_patronen=None
        )

    nvda = [s for s in signalen if s.symbool == 'NVDA']
    assert len(nvda) == 0


@pytest.mark.asyncio
async def test_mag_niet_handelen_buiten_uren():
    agent = _maak_ema_agent()
    with patch('agent.agents.ema_agent.datetime') as mock_dt:
        mock_dt.now.return_value.time.return_value = time(23, 0)
        result = await agent._mag_handelen('NVDA', {})
    assert result is False


@pytest.mark.asyncio
async def test_mag_handelen_in_uren():
    agent = _maak_ema_agent()
    with patch('agent.agents.ema_agent.datetime') as mock_dt:
        mock_dt.now.return_value.time.return_value = time(18, 0)
        result = await agent._mag_handelen('NVDA', {})
    assert result is True


def test_cooldown_24_uur():
    agent = _maak_ema_agent()
    assert agent.cooldown_uren == 24


def test_kapitaal_pool_is_300():
    agent = _maak_ema_agent()
    assert agent.kapitaal_pool == 300.0
