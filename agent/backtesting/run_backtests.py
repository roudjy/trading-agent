"""
RUN ALL BACKTESTS
=================
Draait alle strategieën, slaat resultaten op in reports/.
Start via: python agent/backtesting/run_backtests.py
"""
import json
import logging
import sys
import os
from datetime import datetime, timedelta
from pathlib import Path

# Voeg project root toe aan path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from agent.backtesting.engine import BacktestEngine
from agent.backtesting.strategies import (
    rsi_strategie, fear_greed_strategie, laad_fear_greed,
    bollinger_strategie, earnings_strategie,
    orb_strategie, polymarket_expiry_strategie
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
log = logging.getLogger(__name__)

EIND  = datetime.now().strftime('%Y-%m-%d')
START_2J = (datetime.now() - timedelta(days=730)).strftime('%Y-%m-%d')
START_3J = (datetime.now() - timedelta(days=1095)).strftime('%Y-%m-%d')

CRYPTO_ASSETS  = ['BTC-EUR', 'ETH-EUR', 'SOL-EUR']
STOCK_ASSETS   = ['NVDA', 'AMD', 'ASML', 'AAPL', 'MSFT']
EARNINGS_STOCKS = ['NVDA', 'AMD', 'AAPL', 'MSFT']
ORB_STOCKS     = ['NVDA', 'AMD']

resultaten = {}


def run_rsi():
    """STAP 3: Grid search RSI op crypto."""
    log.info("=== RSI Backtest ===")
    engine = BacktestEngine(START_2J, EIND)
    result = engine.grid_search(
        strategie_factory=rsi_strategie,
        param_grid={
            'koop_drempel':  [25, 28, 30],
            'short_drempel': [70, 72, 75],
        },
        assets=CRYPTO_ASSETS,
        interval='1d'
    )
    result['strategie'] = 'RSI Mean Reversion'
    result['assets']    = CRYPTO_ASSETS
    log.info(f"RSI: {_samenvatting(result)}")
    return result


def run_fear_greed():
    """STAP 4: Fear & Greed op BTC."""
    log.info("=== Fear & Greed Backtest ===")
    fng_df = laad_fear_greed(limit=1100)
    if fng_df is None or fng_df.empty:
        log.warning("Fear&Greed data niet beschikbaar")
        return _leeg('Fear & Greed', ['BTC-EUR'], 'API niet bereikbaar')

    engine = BacktestEngine(START_3J, EIND)
    result = engine.grid_search(
        strategie_factory=lambda fear_drempel, greed_drempel: fear_greed_strategie(
            fear_drempel=fear_drempel, greed_drempel=greed_drempel, fng_df=fng_df
        ),
        param_grid={
            'fear_drempel':  [15, 20, 25],
            'greed_drempel': [75, 80, 85],
        },
        assets=['BTC-EUR'],
        interval='1d'
    )
    result['strategie'] = 'Fear & Greed'
    result['assets']    = ['BTC-EUR']
    log.info(f"Fear&Greed: {_samenvatting(result)}")
    return result


def run_bollinger():
    """STAP 5: Bollinger Breakout op aandelen."""
    log.info("=== Bollinger Backtest ===")
    engine = BacktestEngine(START_3J, EIND)
    # Vaste parameters (geen grid search voor bollinger)
    result = engine.run(
        strategie_func=bollinger_strategie(periode=20, std=2.0),
        assets=STOCK_ASSETS,
        interval='1d'
    )
    result['strategie']  = 'Bollinger Breakout'
    result['assets']     = STOCK_ASSETS
    result['beste_params'] = {'periode': 20, 'std': 2.0}
    log.info(f"Bollinger: {_samenvatting(result)}")
    return result


def run_earnings():
    """STAP 6: Earnings Drift op tech-aandelen."""
    log.info("=== Earnings Drift Backtest ===")
    engine = BacktestEngine(START_3J, EIND)
    result = engine.run(
        strategie_func=earnings_strategie(pct_drempel=0.05, positie_duur=5),
        assets=EARNINGS_STOCKS,
        interval='1d'
    )
    result['strategie']    = 'Earnings Drift'
    result['assets']       = EARNINGS_STOCKS
    result['beste_params'] = {'pct_drempel': 0.05, 'positie_duur': 5}
    log.info(f"Earnings: {_samenvatting(result)}")
    return result


def run_orb():
    """STAP 7: Opening Range Breakout proxy op aandelen."""
    log.info("=== ORB Backtest ===")
    engine = BacktestEngine(START_2J, EIND)
    result = engine.run(
        strategie_func=orb_strategie(gap_drempel=0.005, positie_duur=1),
        assets=ORB_STOCKS,
        interval='1d'
    )
    result['strategie']    = 'Opening Range Breakout'
    result['assets']       = ORB_STOCKS
    result['beste_params'] = {'gap_drempel': 0.005, 'positie_duur': 1}
    log.info(f"ORB: {_samenvatting(result)}")
    return result


def run_polymarket_expiry():
    """STAP 8: Polymarket Expiry — geen historische data."""
    log.info("=== Polymarket Expiry Backtest ===")
    return _leeg('Polymarket Expiry', ['Polymarket'],
                 'Geen historische Polymarket data beschikbaar')


def _samenvatting(r: dict) -> str:
    status = '✅ GOEDGEKEURD' if r.get('goedgekeurd') else '❌ AFGEWEZEN'
    return (f"{status} | WR={r.get('win_rate',0):.0%} "
            f"DS={r.get('deflated_sharpe',0):.2f} "
            f"DD={r.get('max_drawdown',0):.0%} "
            f"T/m={r.get('trades_per_maand',0):.1f} "
            f"Cons={r.get('consistentie',0):.0%}")


def _leeg(naam, assets, reden='') -> dict:
    return {
        'strategie': naam, 'assets': assets, 'reden': reden,
        'win_rate': 0, 'sharpe': 0, 'sortino': 0, 'calmar': 0,
        'max_drawdown': 0, 'trades_per_maand': 0, 'consistentie': 0,
        'deflated_sharpe': 0, 'totaal_trades': 0,
        'goedgekeurd': False, 'criteria_checks': {}
    }


if __name__ == '__main__':
    log.info("Start backtests...")

    resultaten = {
        'rsi':        run_rsi(),
        'fear_greed': run_fear_greed(),
        'bollinger':  run_bollinger(),
        'earnings':   run_earnings(),
        'orb':        run_orb(),
        'polymarket_expiry': run_polymarket_expiry(),
    }

    # Opslaan
    pad = Path('reports/backtest_resultaten.json')
    pad.parent.mkdir(exist_ok=True)
    with open(pad, 'w') as f:
        json.dump({
            'gegenereerd_op': datetime.now().isoformat(),
            'strategieen': resultaten
        }, f, indent=2, default=str)
    log.info(f"Resultaten opgeslagen: {pad}")

    # Overzicht
    print("\n" + "="*60)
    print("BACKTEST OVERZICHT")
    print("="*60)
    for naam, r in resultaten.items():
        status = '✅' if r.get('goedgekeurd') else '❌'
        print(f"{status} {r['strategie']}")
        if r.get('reden'):
            print(f"   Reden: {r['reden']}")
        else:
            print(f"   WR={r['win_rate']:.0%} DS={r['deflated_sharpe']:.2f} "
                  f"DD={r['max_drawdown']:.0%} T/m={r['trades_per_maand']:.1f}")
        params = r.get('beste_params', {})
        if params:
            print(f"   Params: {params}")
    print("="*60)
