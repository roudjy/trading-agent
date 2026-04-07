"""Integratie tests voor Orchestrator."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path


CFG = {
    'kapitaal': {
        'start': 1000.0,
        'max_positie_grootte': 0.10,
        'drawdown_limiet': 0.75,
    },
    'agent': {'rapport_tijd': '23:00'},
    'strategie': {'adversarial': {'min_bot_confidence': 0.75}},
    'ai': {'anthropic_api_key': ''},
    'database': {'pad': ':memory:'},
    'zelfverbetering': {},
}


@pytest.fixture
def mock_orchestrator():
    """Orchestrator met gemockte externe dependencies."""
    with patch('agent.brain.orchestrator.MarketDataFetcher') as MockFetcher, \
         patch('agent.brain.orchestrator.SentimentScraper'), \
         patch('agent.brain.orchestrator.BotDetector'), \
         patch('agent.brain.orchestrator.NieuwsFetcher'), \
         patch('agent.brain.orchestrator.RegimeDetector'), \
         patch('agent.brain.orchestrator.SignalAggregator'), \
         patch('agent.brain.orchestrator.RiskManager'), \
         patch('agent.brain.orchestrator.DagelijksRapport'), \
         patch('agent.brain.orchestrator.ZelfVerbeteraar'), \
         patch('agent.brain.orchestrator.ClaudeAnalyst'), \
         patch('agent.brain.orchestrator.AgentMemory'), \
         patch('agent.brain.orchestrator.OrderExecutor'), \
         patch('agent.brain.orchestrator.DataArbitrageAgent'):

        mock_data = {
            'BTC/EUR': {'prijs': 50000, 'volume': 1000, 'gem_volume': 900,
                        'indicatoren': {'rsi': 45, 'ema_20': 49000, 'ema_50': 48000}},
        }
        MockFetcher.return_value.haal_alles_op = AsyncMock(return_value=mock_data)

        from agent.brain.orchestrator import Orchestrator
        orch = Orchestrator(CFG)
        yield orch


def test_orchestrator_heeft_4_agents(mock_orchestrator):
    assert len(mock_orchestrator.agents) == 5
    assert set(mock_orchestrator.agents.keys()) == {'rsi', 'ema', 'bot', 'sentiment', 'data_arbitrage'}


def test_agent_stats_geeft_4_items(mock_orchestrator):
    stats = mock_orchestrator.agent_stats()
    assert len(stats) == 5


def test_alle_open_posities_leeg_bij_start(mock_orchestrator):
    posities = mock_orchestrator.alle_open_posities()
    assert posities == {}


@pytest.mark.asyncio
async def test_hoofd_loop_stopt_bij_pause_flag(tmp_path, mock_orchestrator):
    """Loop pauzeer als pause flag bestaat."""
    # Maak pause flag
    logs_dir = Path('logs')
    logs_dir.mkdir(exist_ok=True)
    pause_flag = logs_dir / 'agent_pause.flag'
    pause_flag.touch()

    calls = []

    async def mock_sleep(n):
        calls.append(n)
        mock_orchestrator.actief = False  # Stop na eerste iteratie

    with patch('asyncio.sleep', side_effect=mock_sleep):
        await mock_orchestrator._hoofd_loop()

    # Sleep van 30s = pauze gedrag
    assert 30 in calls

    # Opruimen
    pause_flag.unlink(missing_ok=True)
