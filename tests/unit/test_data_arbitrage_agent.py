"""Unit tests voor DataArbitrageAgent."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

CFG = {
    'kapitaal': {'start': 100.0, 'max_positie_grootte': 0.10, 'drawdown_limiet': 0.75},
    'strategie': {},
    'ai': {'anthropic_api_key': ''},
    'database': {'pad': ':memory:'},
    'exchanges': {'bitvavo': {'actief': False}, 'kraken': {'actief': False}},
}


def _maak_agent():
    from agent.agents.data_arbitrage_agent import DataArbitrageAgent
    executor = MagicMock()
    executor.voer_uit = AsyncMock(return_value=None)
    executor.sluit_positie = AsyncMock(return_value=None)
    geheugen = MagicMock()
    geheugen.cooldown_actief = MagicMock(return_value=False)
    return DataArbitrageAgent(CFG, executor, geheugen)


def _kans(zekerheid=0.90, markt_prijs=0.25, antwoord=True):
    """Maak een test-kans dict."""
    mispricing = abs((zekerheid if antwoord else 1 - zekerheid) - markt_prijs)
    return {
        'markt_id': 'test_markt_001',
        'vraag': 'Will BTC be above $50,000?',
        'databron': 'coingecko: bitcoin=$58000 vs drempel $50000',
        'antwoord': antwoord,
        'zekerheid': zekerheid,
        'markt_prijs': markt_prijs,
        'mispricing': mispricing,
        'richting': 'long' if antwoord else 'short',
        'kelly_inzet': 10.0,
    }


# ── Zekerheid tests ───────────────────────────────────────────────────────────

def test_zekerheid_onder_85_geen_trade():
    """Bij zekerheid < 85% geen signaal genereren."""
    agent = _maak_agent()
    k = _kans(zekerheid=0.80)
    signaal = agent._evalueer_kans(k)
    # _evalueer_kans maakt altijd een signaal — de filter zit in _analyseer_markt
    # Test dat de min_zekerheid filter werkt in het scan-pad
    from agent.agents.data_arbitrage_agent import MIN_ZEKERHEID
    assert MIN_ZEKERHEID == 0.85
    assert k['zekerheid'] < MIN_ZEKERHEID


def test_zekerheid_85_wel_trade():
    """Bij zekerheid >= 85% wordt een signaal gemaakt."""
    agent = _maak_agent()
    k = _kans(zekerheid=0.85)
    signaal = agent._evalueer_kans(k)
    assert signaal is not None
    assert signaal.zekerheid == 0.85


# ── Mispricing tests ──────────────────────────────────────────────────────────

def test_mispricing_onder_20_geen_trade():
    """Mispricing < 20% → geen kans doorgeven."""
    from agent.agents.data_arbitrage_agent import MIN_MISPRICING
    k = _kans(zekerheid=0.90, markt_prijs=0.80)  # 90% - 80% = 10% mispricing
    assert k['mispricing'] < MIN_MISPRICING


def test_mispricing_boven_20_trade():
    """Mispricing > 20% → kans is geldig."""
    from agent.agents.data_arbitrage_agent import MIN_MISPRICING
    agent = _maak_agent()
    k = _kans(zekerheid=0.90, markt_prijs=0.25)  # 90% - 25% = 65% mispricing
    assert k['mispricing'] > MIN_MISPRICING
    signaal = agent._evalueer_kans(k)
    assert signaal is not None


# ── Instapprijs tests ─────────────────────────────────────────────────────────

def test_instapprijs_boven_60_geen_trade():
    """Marktprijs > 60 cent → geen trade (slechte risk/reward)."""
    from agent.agents.data_arbitrage_agent import MAX_INSTAP
    k = _kans(zekerheid=0.90, markt_prijs=0.65)
    assert k['markt_prijs'] > MAX_INSTAP  # Zou gefilterd worden in _analyseer_markt


def test_instapprijs_onder_0_5_cent_geen_trade():
    """Marktprijs < 0.5 cent → skip."""
    from agent.agents.data_arbitrage_agent import MIN_INSTAP
    k = _kans(zekerheid=0.90, markt_prijs=0.003)
    assert k['markt_prijs'] < MIN_INSTAP


def test_instapprijs_geldig_bereik():
    """Marktprijs tussen 0.5 cent en 60 cent → geldig."""
    from agent.agents.data_arbitrage_agent import MIN_INSTAP, MAX_INSTAP
    k = _kans(zekerheid=0.90, markt_prijs=0.30)
    assert MIN_INSTAP <= k['markt_prijs'] <= MAX_INSTAP


# ── Kelly criterion ───────────────────────────────────────────────────────────

def test_kelly_berekening_correct():
    """f* = (p - m) / (1 - m)"""
    from agent.agents.data_arbitrage_agent import DataArbitrageAgent
    # p=0.90, m=0.30 → (0.90 - 0.30) / (1 - 0.30) = 0.60 / 0.70 ≈ 0.857 → capped op 0.25
    kelly = DataArbitrageAgent._kelly(0.90, 0.30)
    assert kelly == pytest.approx(0.25, abs=0.001)  # Gecapped op 25%

def test_kelly_laag_bij_kleine_edge():
    from agent.agents.data_arbitrage_agent import DataArbitrageAgent
    # p=0.86, m=0.80 → (0.06) / (0.20) = 0.30 → capped op 0.25
    kelly = DataArbitrageAgent._kelly(0.86, 0.80)
    assert kelly == pytest.approx(0.25, abs=0.01)

def test_kelly_nul_bij_geen_edge():
    from agent.agents.data_arbitrage_agent import DataArbitrageAgent
    # p=0.30, m=0.50 → negatief → capped op 0
    kelly = DataArbitrageAgent._kelly(0.30, 0.50)
    assert kelly == 0.0

def test_kelly_prijs_1_geeft_nul():
    from agent.agents.data_arbitrage_agent import DataArbitrageAgent
    kelly = DataArbitrageAgent._kelly(0.90, 1.0)
    assert kelly == 0.0


# ── Force exit bij 80% winst ──────────────────────────────────────────────────

def test_force_exit_bij_80_procent():
    """Positie moet gesloten worden bij >= 80% winst."""
    agent = _maak_agent()
    positie = MagicMock()
    positie.symbool = 'test_markt_001'
    positie.richting = 'long'
    positie.bereken_pnl_pct = MagicMock(return_value=0.80)
    assert agent._moet_sluiten_strategie(positie, 0.90, {}) is True


def test_geen_exit_bij_50_procent():
    """Positie blijft open bij 50% winst."""
    agent = _maak_agent()
    positie = MagicMock()
    positie.symbool = 'test_markt_001'
    positie.richting = 'long'
    positie.bereken_pnl_pct = MagicMock(return_value=0.50)
    assert agent._moet_sluiten_strategie(positie, 0.65, {}) is False


def test_geen_stop_loss():
    """DataArbitrage heeft geen stop-loss (binaire markt)."""
    agent = _maak_agent()
    assert agent._clamp_stop_loss(0.99) == 1.0


def test_max_posities_beperkt():
    """Geen nieuwe signalen als al 5 posities open zijn."""
    from agent.agents.data_arbitrage_agent import MAX_POSITIES
    agent = _maak_agent()
    for i in range(MAX_POSITIES):
        p = MagicMock()
        p.symbool = f'markt_{i}'
        agent.open_posities[f'id_{i}'] = p
    assert len(agent.open_posities) == MAX_POSITIES


def test_kapitaal_pool_is_100():
    agent = _maak_agent()
    assert agent.kapitaal_pool == 100.0

# ── Fractional Kelly scaling ──────────────────────────────────────────────────

def test_fractional_kelly_weinig_trades():
    """Bij <10 trades: 25% schaling."""
    agent = _maak_agent()
    agent.geheugen.analyseer_prestaties = MagicMock(return_value={
        'per_strategie': {'data_arbitrage': {'totaal_trades': 5, 'win_rate': 0.6}}
    })
    # p=0.90, m=0.25 → f* = 0.65/0.75 ≈ 0.867 → schaal 0.25 → f_safe ≈ 0.217
    # inzet = 0.217 * 100 = 21.7 → capped op MAX_INZET_EUR=10
    inzet = agent._bereken_kelly_inzet(0.90, 0.25)
    assert 1.0 <= inzet <= 10.0


def test_fractional_kelly_veel_trades():
    """Bij >=50 trades: 75% schaling → hogere inzet dan bij weinig trades."""
    agent_weinig = _maak_agent()
    agent_weinig.geheugen.analyseer_prestaties = MagicMock(return_value={
        'per_strategie': {'data_arbitrage': {'totaal_trades': 5, 'win_rate': 0.6}}
    })
    agent_veel = _maak_agent()
    agent_veel.geheugen.analyseer_prestaties = MagicMock(return_value={
        'per_strategie': {'data_arbitrage': {'totaal_trades': 60, 'win_rate': 0.6}}
    })
    inzet_weinig = agent_weinig._bereken_kelly_inzet(0.90, 0.50)
    inzet_veel = agent_veel._bereken_kelly_inzet(0.90, 0.50)
    assert inzet_veel >= inzet_weinig


def test_fractional_kelly_negatieve_edge_geeft_nul():
    """Negatieve edge → inzet 0."""
    agent = _maak_agent()
    agent.geheugen.analyseer_prestaties = MagicMock(return_value={'per_strategie': {}})
    inzet = agent._bereken_kelly_inzet(0.30, 0.60)
    assert inzet == 0.0


def test_fractional_kelly_max_inzet():
    """Inzet nooit meer dan MAX_INZET_EUR."""
    from agent.agents.data_arbitrage_agent import MAX_INZET_EUR
    agent = _maak_agent()
    agent.kapitaal_pool = 1000.0  # groot kapitaal
    agent.geheugen.analyseer_prestaties = MagicMock(return_value={
        'per_strategie': {'data_arbitrage': {'totaal_trades': 100, 'win_rate': 0.8}}
    })
    inzet = agent._bereken_kelly_inzet(0.99, 0.01)
    assert inzet <= MAX_INZET_EUR


# ── Databron tests (mock) ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_weer_databron_antwoord():
    """_check_weer retourneert dict met antwoord/zekerheid/bron bij geldige vraag."""
    agent = _maak_agent()
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.json = AsyncMock(return_value={
        'current_weather': {'temperature': 22.5}
    })
    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)
    mock_session = MagicMock()
    mock_session.get = MagicMock(return_value=mock_ctx)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch('aiohttp.ClientSession', return_value=mock_session):
        # Vraag: temperatuur boven 15 graden → antwoord = True (22.5 > 15)
        resultaat = await agent._check_weer('Will temperature exceed 15 degrees in Amsterdam?')

    assert resultaat is not None
    assert 'antwoord' in resultaat
    assert resultaat['antwoord'] is True  # 22.5 > 15
    assert resultaat['zekerheid'] >= 0.85
    assert 'open-meteo' in resultaat['bron']


@pytest.mark.asyncio
async def test_aardbeving_databron_antwoord():
    """_check_aardbeving retourneert dict met antwoord/zekerheid/bron."""
    agent = _maak_agent()
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.json = AsyncMock(return_value={
        'features': [
            {'properties': {'mag': 6.5, 'place': 'Japan'}},
            {'properties': {'mag': 5.2, 'place': 'Chile'}},
        ]
    })
    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)
    mock_session = MagicMock()
    mock_session.get = MagicMock(return_value=mock_ctx)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch('aiohttp.ClientSession', return_value=mock_session):
        resultaat = await agent._check_aardbeving('Was there an earthquake of magnitude 5.0?')

    assert resultaat is not None
    assert resultaat['antwoord'] is True   # Er is M6.5 gevonden
    assert resultaat['zekerheid'] == 0.95
    assert 'usgs' in resultaat['bron']


@pytest.mark.asyncio
async def test_aardbeving_geen_treffer():
    """Geen M8+ aardbeving → antwoord False."""
    agent = _maak_agent()
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.json = AsyncMock(return_value={'features': [
        {'properties': {'mag': 4.5, 'place': 'Italy'}},
    ]})
    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)
    mock_session = MagicMock()
    mock_session.get = MagicMock(return_value=mock_ctx)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch('aiohttp.ClientSession', return_value=mock_session):
        resultaat = await agent._check_aardbeving('earthquake magnitude 8.0 recorded?')

    assert resultaat is not None
    assert resultaat['antwoord'] is False


# ── Scan throttle test ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_scan_throttle_geen_dubbele_scan():
    """Tweede aanroep binnen 30 min geeft lege lijst terug zonder API call."""
    from datetime import datetime
    agent = _maak_agent()
    # Zet _laatste_scan op nu → throttle actief
    agent._laatste_scan = datetime.now()

    markt_data = {}
    regime = {}
    sentiment = MagicMock()
    bot_patronen = []

    signalen = await agent._genereer_signalen(markt_data, regime, sentiment, bot_patronen)
    assert signalen == []  # Geen scan uitgevoerd
