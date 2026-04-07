"""Unit tests voor RSIAgent."""
import pytest
from unittest.mock import MagicMock, AsyncMock

CFG = {
    'kapitaal': {'start': 300.0, 'max_positie_grootte': 0.10, 'drawdown_limiet': 0.75},
    'strategie': {},
    'ai': {'anthropic_api_key': ''},
    'database': {'pad': ':memory:'},
}


def _maak_rsi_agent():
    from agent.agents.rsi_agent import RSIAgent
    executor = MagicMock()
    executor.voer_uit = AsyncMock(return_value=None)
    geheugen = MagicMock()
    geheugen.tel_open_posities = MagicMock(return_value=0)
    geheugen.heeft_open_positie_db = MagicMock(return_value=False)
    geheugen.analyseer_prestaties = MagicMock(return_value={'per_strategie': {}})
    return RSIAgent(CFG, executor, geheugen)


def _markt_data(symbool: str, rsi: float, prijs: float = 50000.0) -> dict:
    return {
        symbool: {
            'prijs': prijs,
            'volume': 1000,
            'gem_volume': 800,
            'indicatoren': {'rsi': rsi, 'ema_20': 49000, 'ema_50': 48000}
        }
    }


@pytest.mark.asyncio
async def test_long_signaal_bij_lage_rsi():
    agent = _maak_rsi_agent()
    data = _markt_data('BTC/EUR', rsi=22.0)
    signalen = await agent._genereer_signalen(
        markt_data=data, regime={}, sentiment=None, bot_patronen=None
    )
    btc_signalen = [s for s in signalen if s.symbool == 'BTC/EUR']
    assert len(btc_signalen) == 1
    assert btc_signalen[0].richting == 'long'


@pytest.mark.asyncio
async def test_short_signaal_bij_hoge_rsi():
    agent = _maak_rsi_agent()
    data = _markt_data('ETH/EUR', rsi=78.0, prijs=2000.0)
    signalen = await agent._genereer_signalen(
        markt_data=data, regime={}, sentiment=None, bot_patronen=None
    )
    eth_signalen = [s for s in signalen if s.symbool == 'ETH/EUR']
    assert len(eth_signalen) == 1
    assert eth_signalen[0].richting == 'short'


@pytest.mark.asyncio
async def test_geen_signaal_neutrale_rsi():
    agent = _maak_rsi_agent()
    data = _markt_data('BTC/EUR', rsi=50.0)
    signalen = await agent._genereer_signalen(
        markt_data=data, regime={}, sentiment=None, bot_patronen=None
    )
    btc = [s for s in signalen if s.symbool == 'BTC/EUR']
    assert len(btc) == 0


@pytest.mark.asyncio
async def test_geen_signaal_bij_crisis_regime():
    from agent.brain.regime_detector import Regime
    agent = _maak_rsi_agent()
    data = _markt_data('BTC/EUR', rsi=22.0)

    regime_mock = MagicMock()
    regime_mock.regime = Regime.CRISIS
    regime = {'BTC/EUR': regime_mock}

    signalen = await agent._genereer_signalen(
        markt_data=data, regime=regime, sentiment=None, bot_patronen=None
    )
    btc = [s for s in signalen if s.symbool == 'BTC/EUR']
    assert len(btc) == 0


def test_stop_loss_max_8_procent():
    agent = _maak_rsi_agent()
    # RSI agent gebruikt 5% — moet onder ceiling blijven
    assert agent._clamp_stop_loss(0.05) == 0.05


def test_kapitaal_pool_is_300():
    agent = _maak_rsi_agent()
    assert agent.kapitaal_pool == 300.0
