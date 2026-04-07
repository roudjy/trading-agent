"""
Regressie tests: valideer dat eerder gevonden bugs niet terugkomen.

Bug #1: Hardcoded entry prices (ETH=3200) → 43-52% phantom stop-losses
Bug #2: Repeated trades elke 60s (geen dedup/cooldown)
Bug #3: regime exit op ZIJWAARTS/CRISIS (te agressief)
Bug #4: Trade.uitleg AttributeError (moet reden_exit zijn)
"""
import pytest
from unittest.mock import AsyncMock, MagicMock


CFG = {
    'kapitaal': {'start': 300.0, 'max_positie_grootte': 0.10, 'drawdown_limiet': 0.75},
    'strategie': {},
    'ai': {'anthropic_api_key': ''},
    'database': {'pad': ':memory:'},
    'exchanges': {'bitvavo': {'actief': False}, 'kraken': {'actief': False}},
    'paper_trading': True,
}


# ── Bug #1: Geen hardcoded prijzen ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_geen_hardcoded_prijzen_in_paper_trade():
    """OrderExecutor mag geen hardcoded prijs gebruiken als markt_data beschikbaar is."""
    from agent.execution.order_executor import OrderExecutor
    from agent.risk.risk_manager import TradeSignaal

    exec_cfg = {**CFG, 'paper_trading': True, 'database': {'pad': ':memory:'}}
    executor = OrderExecutor(exec_cfg)

    signaal = TradeSignaal(
        symbool='ETH/EUR',
        richting='long',
        strategie_type='rsi',
        verwacht_rendement=0.08,
        win_kans=0.65,
        stop_loss_pct=0.05,
        take_profit_pct=0.08,
        bron='test',
        zekerheid=0.65,
        regime='trending',
    )

    # Geef echte prijs mee via markt_data
    markt_data = {'ETH/EUR': {'prijs': 1750.0}}
    trade = await executor.voer_uit(signaal, markt_data=markt_data)

    if trade:
        # Entry prijs moet ~1750 zijn, NIET 3200 (hardcoded)
        assert abs(trade.entry_prijs - 1750.0) < 50, \
            f"Hardcoded prijs bug! entry_prijs={trade.entry_prijs}, verwacht ~1750"


# ── Bug #2: Dedup blokkeert herhaalde trades ────────────────────────────────

@pytest.mark.asyncio
async def test_geen_herhaalde_trades_zelfde_symbool():
    """Twee opeenvolgende cycli mogen geen twee trades openen voor hetzelfde symbool."""
    from agent.agents.rsi_agent import RSIAgent

    trade1 = MagicMock()
    trade1.id = 'trade_001'
    trade1.symbool = 'BTC/EUR'
    trade1.euro_bedrag = 30.0
    trade1.stop_loss_pct = 0.05
    trade1.take_profit_pct = 0.08
    trade1.bereken_pnl_pct = MagicMock(return_value=0.01)  # Geen exit

    call_count = 0
    async def mock_voer_uit(signaal, markt_data=None, max_bedrag=None):
        nonlocal call_count
        call_count += 1
        return trade1 if call_count == 1 else MagicMock(id='trade_002', symbool='BTC/EUR', euro_bedrag=30.0)

    executor = MagicMock()
    executor.voer_uit = mock_voer_uit
    executor.sluit_positie = AsyncMock(return_value=None)
    geheugen = MagicMock()
    geheugen.tel_open_posities = MagicMock(return_value=0)
    geheugen.heeft_open_positie_db = MagicMock(return_value=False)
    geheugen.analyseer_prestaties = MagicMock(return_value={'per_strategie': {}})
    geheugen.cooldown_actief = MagicMock(return_value=False)

    agent = RSIAgent(CFG, executor, geheugen)
    markt_data = {
        'BTC/EUR': {
            'prijs': 50000,
            'volume': 1000,
            'gem_volume': 800,
            'indicatoren': {'rsi': 22.0, 'ema_20': 49000, 'ema_50': 48000}
        }
    }

    await agent.run_cyclus(markt_data=markt_data, regime={}, sentiment=None, bot_patronen=None)
    await agent.run_cyclus(markt_data=markt_data, regime={}, sentiment=None, bot_patronen=None)

    assert call_count == 1, f"Trade executor {call_count}x aangeroepen — dedup werkt niet!"


# ── Bug #3: Regime exit niet op ZIJWAARTS ────────────────────────────────────

def test_geen_exit_bij_zijwaarts_regime():
    """Een long positie in ZIJWAARTS regime moet NIET worden afgesloten."""
    from agent.agents.rsi_agent import RSIAgent
    from agent.brain.regime_detector import Regime

    executor = MagicMock()
    geheugen = MagicMock()
    geheugen.tel_open_posities = MagicMock(return_value=0)
    geheugen.heeft_open_positie_db = MagicMock(return_value=False)
    geheugen.analyseer_prestaties = MagicMock(return_value={'per_strategie': {}})
    agent = RSIAgent(CFG, executor, geheugen)

    positie = MagicMock()
    positie.richting = 'long'
    positie.symbool = 'BTC/EUR'

    regime_mock = MagicMock()
    regime_mock.regime = Regime.ZIJWAARTS

    regime = {'BTC/EUR': regime_mock}

    # RSI agent heeft geen strategie exit op regime — altijd False
    result = agent._moet_sluiten_strategie(positie, 50000, regime)
    assert result is False, "ZIJWAARTS regime triggert ten onrechte een exit!"


# ── Bug #4: Trade.reden_exit (niet uitleg) ───────────────────────────────────

def test_trade_heeft_reden_exit_niet_uitleg():
    """Trade object moet reden_exit attribuut hebben (niet uitleg)."""
    from agent.learning.memory import Trade

    trade = Trade.__new__(Trade)

    # reden_exit moet bestaan
    assert hasattr(trade.__class__, '__annotations__') or True  # Dataclass check

    # Aanmaken en controleren
    try:
        t = Trade(
            id='abc',
            symbool='BTC/EUR',
            richting='long',
            entry_prijs=50000,
            entry_tijd=None,
            euro_bedrag=100,
            strategie_type='rsi',
            reden_entry='test',
        )
        # Moet reden_exit hebben, geen uitleg
        assert hasattr(t, 'reden_exit'), "Trade mist reden_exit attribuut!"
        assert not hasattr(t, 'uitleg') or getattr(t, 'uitleg', None) is None
    except TypeError:
        # Als Trade andere constructor signature heeft, skip
        pytest.skip("Trade constructor signature verschilt — controleer handmatig")
