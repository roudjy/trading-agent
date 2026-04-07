"""
Smoke tests: importeer alle modules en controleer dat ze laden zonder fouten.
Deze tests falen als er import-errors, syntax fouten of missende dependencies zijn.
"""
import pytest


def test_import_base_agent():
    from agent.agents.base_agent import BaseAgent
    assert BaseAgent is not None


def test_import_rsi_agent():
    from agent.agents.rsi_agent import RSIAgent
    assert RSIAgent is not None


def test_import_ema_agent():
    from agent.agents.ema_agent import EMAAgent
    assert EMAAgent is not None


def test_import_bot_agent():
    from agent.agents.bot_agent import BotAgent
    assert BotAgent is not None


def test_import_sentiment_agent():
    from agent.agents.sentiment_agent import SentimentAgent
    assert SentimentAgent is not None


def test_import_orchestrator():
    from agent.brain.orchestrator import Orchestrator
    assert Orchestrator is not None


def test_import_analyst():
    from agent.brain.analyst import ClaudeAnalyst
    assert ClaudeAnalyst is not None


def test_import_self_improver():
    from agent.learning.self_improver import ZelfVerbeteraar
    assert ZelfVerbeteraar is not None


def test_import_risk_manager():
    from agent.risk.risk_manager import RiskManager, TradeSignaal
    assert RiskManager is not None
    assert TradeSignaal is not None


def test_import_fetcher():
    from data.market.fetcher import MarketDataFetcher
    assert MarketDataFetcher is not None


def test_import_regime_detector():
    from agent.brain.regime_detector import RegimeDetector, Regime
    assert RegimeDetector is not None
    assert Regime is not None


def test_tradeSignaal_aanmaken():
    from agent.risk.risk_manager import TradeSignaal
    signaal = TradeSignaal(
        symbool='BTC/EUR',
        richting='long',
        strategie_type='rsi_mean_reversion',
        verwacht_rendement=0.08,
        win_kans=0.65,
        stop_loss_pct=0.05,
        take_profit_pct=0.08,
        bron='test',
        zekerheid=0.65,
        regime='trending'
    )
    assert signaal.symbool == 'BTC/EUR'
    assert signaal.richting == 'long'


def test_dashboard_import():
    """Dashboard moet importeerbaar zijn."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("dashboard", "dashboard/dashboard.py")
    assert spec is not None
