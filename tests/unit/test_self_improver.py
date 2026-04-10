"""Unit tests voor ZelfVerbeteraar."""

import json

import pytest

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


def _maak_verbeteraar(tmp_path=None):
    from agent.learning.self_improver import ZelfVerbeteraar

    verbeteraar = ZelfVerbeteraar(CFG.copy())
    if tmp_path is not None:
        verbeteraar.audit_pad = tmp_path / "zelfverbeteringen.log"
        verbeteraar.recommendation_dir = tmp_path / "candidate_recommendations"
        verbeteraar.recommendation_dir.mkdir(parents=True, exist_ok=True)
    return verbeteraar


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


def test_valideer_en_pas_toe_clampt_grenzen_zonder_config_write():
    zv = _maak_verbeteraar()
    aanbevelingen = {
        'wijzigingen': {
            'stop_loss_pct': 0.15,
            'take_profit_pct': 0.10,
        }
    }
    wijzigingen = zv._valideer_en_pas_toe(aanbevelingen)
    assert wijzigingen['stop_loss_pct']['nieuw'] <= 0.08
    assert 'take_profit_pct' in wijzigingen
    assert zv.config['zelfverbetering']['stop_loss_pct'] == 0.05
    assert zv.config['zelfverbetering']['take_profit_pct'] == 0.08


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
    aanbevelingen = {
        'wijzigingen': {'stop_loss_pct': 0.08}
    }
    wijzigingen = zv._valideer_en_pas_toe(aanbevelingen)
    assert wijzigingen['stop_loss_pct']['nieuw'] <= 0.06


@pytest.mark.asyncio
async def test_verbeter_schrijft_read_only_recommendation(tmp_path, caplog):
    zv = _maak_verbeteraar(tmp_path)
    zv._lees_trades = lambda _n: [
        {'pnl': 10.0, 'pnl_pct': 0.02, 'strategie_type': 'rsi'},
        {'pnl': 6.0, 'pnl_pct': 0.01, 'strategie_type': 'rsi'},
        {'pnl': 4.0, 'pnl_pct': 0.03, 'strategie_type': 'ema'},
        {'pnl': 3.0, 'pnl_pct': 0.01, 'strategie_type': 'ema'},
        {'pnl': 2.0, 'pnl_pct': 0.01, 'strategie_type': 'ema'},
        {'pnl': 1.0, 'pnl_pct': 0.01, 'strategie_type': 'bot'},
        {'pnl': 1.0, 'pnl_pct': 0.01, 'strategie_type': 'bot'},
        {'pnl': -1.0, 'pnl_pct': -0.01, 'strategie_type': 'bot'},
        {'pnl': 2.0, 'pnl_pct': 0.01, 'strategie_type': 'sentiment'},
        {'pnl': 1.0, 'pnl_pct': 0.01, 'strategie_type': 'sentiment'},
    ]
    zv._vraag_ai = lambda stats, agent_stats: _async_result({
        'wijzigingen': {'take_profit_pct': 0.10},
        'onderbouwing': 'Meer ruimte voor trend exits.',
    })

    rapport = await zv.verbeter({
        'rsi': {'gem_pnl_pct': 0.02, 'kapitaal_pool': 250, 'drawdown': 0.05},
        'ema': {'gem_pnl_pct': 0.01, 'kapitaal_pool': 250, 'drawdown': 0.03},
    })

    artifacts = list(zv.recommendation_dir.glob("recommendation_*.json"))
    assert len(artifacts) == 1
    artifact = json.loads(artifacts[0].read_text(encoding="utf-8"))
    assert artifact['ai_rationale'] == 'Meer ruimte voor trend exits.'
    assert artifact['proposed_parameter_diff']['take_profit_pct']['nieuw'] == pytest.approx(0.096)
    assert artifact['safety_check_outcome']['passed'] is True
    assert "[SELF-IMPROVER] READ-ONLY MODE" in caplog.text
    assert "read-only" in rapport.lower()

    audit_entries = [
        json.loads(line)
        for line in zv.audit_pad.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert audit_entries[-1]['actie'] == 'recommendation_only'


async def _async_result(value):
    return value
