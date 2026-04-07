"""Unit tests voor ZelfVerbeteraar."""
import pytest
from unittest.mock import MagicMock, patch, mock_open
import json

CFG = {
    'kapitaal': {'start': 1000.0, 'drawdown_limiet': 0.75},
    'ai': {'anthropic_api_key': ''},
    'database': {'pad': ':memory:'},
    'zelfverbetering': {
        'stop_loss_pct': 0.05,
        'take_profit_pct': 0.08,
        'positie_factor': 1.0,
    }
}


def _maak_verbeteraar():
    from agent.learning.self_improver import ZelfVerbeteraar
    return ZelfVerbeteraar(CFG)


def test_bereken_stats_leeg():
    zv = _maak_verbeteraar()
    stats = zv._bereken_stats([], None)
    assert stats['totaal_trades'] == 0
    assert stats['globaal_win_rate'] == 0


def test_bereken_stats_50_procent():
    zv = _maak_verbeteraar()
    trades = [
        {'pnl': 10.0, 'strategie_type': 'rsi'},
        {'pnl': -5.0, 'strategie_type': 'rsi'},
        {'pnl': 8.0, 'strategie_type': 'ema'},
        {'pnl': -3.0, 'strategie_type': 'ema'},
    ]
    stats = zv._bereken_stats(trades, None)
    assert stats['totaal_trades'] == 4
    # Exact 50% voor beide helften
    assert stats['globaal_win_rate'] == pytest.approx(0.50, abs=0.01)


def test_veiligheidscheck_win_rate_te_laag():
    zv = _maak_verbeteraar()
    stats = {'recent_win_rate': 0.30, 'oud_win_rate': 0.40}
    ok, reden = zv._veiligheidscheck(stats, None)
    assert ok is False
    assert 'win rate' in reden.lower()


def test_veiligheidscheck_cascade_failure():
    zv = _maak_verbeteraar()
    stats = {'recent_win_rate': 0.55, 'oud_win_rate': 0.50}
    agent_stats = {
        'rsi': {'gem_pnl_pct': -0.05, 'kapitaal_pool': 200, 'drawdown': 0.10},
        'ema': {'gem_pnl_pct': -0.03, 'kapitaal_pool': 200, 'drawdown': 0.05},
        'bot': {'gem_pnl_pct': -0.02, 'kapitaal_pool': 150, 'drawdown': 0.05},
        'sentiment': {'gem_pnl_pct': 0.01, 'kapitaal_pool': 80, 'drawdown': 0.05},
    }
    ok, reden = zv._veiligheidscheck(stats, agent_stats)
    assert ok is False
    assert 'cascade' in reden.lower()


def test_veiligheidscheck_ok():
    zv = _maak_verbeteraar()
    stats = {'recent_win_rate': 0.60, 'oud_win_rate': 0.55}
    agent_stats = {
        'rsi': {'gem_pnl_pct': 0.02, 'kapitaal_pool': 300, 'drawdown': 0.05},
        'ema': {'gem_pnl_pct': 0.01, 'kapitaal_pool': 300, 'drawdown': 0.03},
    }
    ok, reden = zv._veiligheidscheck(stats, agent_stats)
    assert ok is True


def test_valideer_en_pas_toe_clampt_grenzen():
    zv = _maak_verbeteraar()
    aanbevelingen = {
        'wijzigingen': {
            'stop_loss_pct': 0.15,    # Boven max 0.08
            'take_profit_pct': 0.10,  # Geldig
        }
    }
    wijzigingen = zv._valideer_en_pas_toe(aanbevelingen)
    # stop_loss_pct moet geclampt zijn
    assert zv.config['zelfverbetering']['stop_loss_pct'] <= 0.08
    # take_profit_pct is geldig
    assert 'take_profit_pct' in wijzigingen


def test_valideer_onbekende_parameter_overgeslagen():
    zv = _maak_verbeteraar()
    aanbevelingen = {
        'wijzigingen': {
            'onbekende_param': 999,
        }
    }
    wijzigingen = zv._valideer_en_pas_toe(aanbevelingen)
    assert 'onbekende_param' not in wijzigingen


def test_valideer_max_20_procent_stap():
    zv = _maak_verbeteraar()
    # Huidige stop_loss_pct = 0.05, max stap = 20% = 0.01
    zv.config['zelfverbetering']['stop_loss_pct'] = 0.05
    aanbevelingen = {
        'wijzigingen': {'stop_loss_pct': 0.08}  # Sprong van 0.03, max 0.01
    }
    zv._valideer_en_pas_toe(aanbevelingen)
    nieuwe_waarde = zv.config['zelfverbetering']['stop_loss_pct']
    # Max stap: 0.05 * 0.20 = 0.01, dus max 0.06
    assert nieuwe_waarde <= 0.06
