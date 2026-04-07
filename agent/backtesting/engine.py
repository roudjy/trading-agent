"""
BACKTESTING ENGINE
==================
Walk-forward validatie: train=70%, test=30%.
Anti-lookahead: signaal dag X → uitvoering dag X+1.
Kosten: 0.5% bitvavo + 0.1% slippage = 0.6% round-trip.
"""
import math
import logging
from datetime import datetime
from typing import Callable, Optional

import numpy as np
import pandas as pd
import yfinance as yf

log = logging.getLogger(__name__)

KOSTEN_RT    = 0.006   # 0.6% round-trip (0.3% per kant)
HANDEL_JAAR  = 252
MIN_TRADES   = 10
GAMMA_EM     = 0.5772  # Euler-Mascheroni

CRITERIA = {
    'win_rate':         ('gt', 0.50),
    'deflated_sharpe':  ('gt', 0.50),
    'max_drawdown':     ('lt', 0.40),
    'trades_per_maand': ('gte', 2.0),
    'consistentie':     ('gt', 0.45),
}


class BacktestEngine:
    """Walk-forward backtesting engine met Deflated Sharpe goedkeuring."""

    def __init__(self, start_datum: str, eind_datum: str,
                 transactiekosten: float = 0.005):
        self.start = start_datum
        self.eind  = eind_datum
        self.kosten_per_kant = transactiekosten / 2 + 0.001  # + slippage

    # ── Publieke API ─────────────────────────────────────────────────────────

    def run(self, strategie_func: Callable, assets: list,
            interval: str = '1d') -> dict:
        """Walk-forward backtest over meerdere assets. Return metrics dict."""
        trade_pnls: list[float] = []
        dag_returns: list[float] = []
        maand_returns: list[float] = []

        for asset in assets:
            df = self._laad_data(asset, interval)
            if df is None or len(df) < 100:
                log.warning(f"[BT] Te weinig data: {asset}")
                continue

            split = int(len(df) * 0.70)
            df_test = df.iloc[split:].copy()
            t_pnl, d_ret, m_ret = self._simuleer(df_test, strategie_func, asset)
            trade_pnls.extend(t_pnl)
            dag_returns.extend(d_ret)
            maand_returns.extend(m_ret)

        if len(trade_pnls) < MIN_TRADES:
            return {**self._leeg(), 'reden': f'Te weinig trades: {len(trade_pnls)}'}

        m = self._metrics(trade_pnls, dag_returns, maand_returns)
        m['deflated_sharpe'] = self._deflated_sharpe(m['sharpe'])
        m['goedgekeurd']     = self._goedkeuren(m)
        return m

    def grid_search(self, strategie_factory: Callable, param_grid: dict,
                    assets: list, interval: str = '1d') -> dict:
        """
        Grid search over parameterruimte op train-set.
        Beste params worden gevalideerd op test-set.
        """
        beste_params = None
        beste_sharpe = -999.0
        n_combis = 1
        for v in param_grid.values():
            n_combis *= len(v)
        log.info(f"[BT] Grid search: {n_combis} combinaties op train-set")

        param_namen = list(param_grid.keys())
        param_waarden = list(param_grid.values())

        import itertools
        for combo in itertools.product(*param_waarden):
            params = dict(zip(param_namen, combo))
            train_metrics = self._run_op_split(
                strategie_factory(**params), assets, interval, train=True
            )
            if train_metrics['sharpe'] > beste_sharpe:
                beste_sharpe = train_metrics['sharpe']
                beste_params = params

        if beste_params is None:
            return {**self._leeg(), 'reden': 'Grid search geen resultaat'}

        log.info(f"[BT] Beste params: {beste_params} (train Sharpe={beste_sharpe:.2f})")
        result = self._run_op_split(
            strategie_factory(**beste_params), assets, interval, train=False
        )
        result['beste_params'] = beste_params
        result['deflated_sharpe'] = self._deflated_sharpe(result['sharpe'])
        result['goedgekeurd'] = self._goedkeuren(result)
        return result

    # ── Interne methodes ─────────────────────────────────────────────────────

    def _run_op_split(self, strategie_func: Callable, assets: list,
                      interval: str, train: bool) -> dict:
        """Voer backtest uit op specifieke split (train of test)."""
        trade_pnls, dag_returns, maand_returns = [], [], []
        for asset in assets:
            df = self._laad_data(asset, interval)
            if df is None or len(df) < 100:
                continue
            split = int(len(df) * 0.70)
            df_deel = df.iloc[:split] if train else df.iloc[split:]
            t, d, m = self._simuleer(df_deel.copy(), strategie_func, asset)
            trade_pnls.extend(t)
            dag_returns.extend(d)
            maand_returns.extend(m)
        if len(trade_pnls) < MIN_TRADES:
            return self._leeg()
        return self._metrics(trade_pnls, dag_returns, maand_returns)

    def _laad_data(self, asset: str, interval: str) -> Optional[pd.DataFrame]:
        """Download en prepareer OHLCV data. auto_adjust=True altijd."""
        try:
            ticker = asset.replace('/', '-')
            df = yf.download(ticker, start=self.start, end=self.eind,
                             interval=interval, auto_adjust=True,
                             progress=False, multi_level_index=False)
            if df is None or df.empty:
                return None
            df.columns = [c.lower() for c in df.columns]
            # Verwijder weekenddata aandelen (volume=0)
            is_crypto = '-EUR' in ticker or '-USD' in ticker or '-BTC' in ticker
            if not is_crypto:
                df = df[df['volume'] > 0]
            return df.dropna()
        except Exception as e:
            log.error(f"[BT] Data laden mislukt {asset}: {e}")
            return None

    def _simuleer(self, df: pd.DataFrame, strategie_func: Callable,
                  asset: str) -> tuple[list, list, list]:
        """
        Simuleer trades zonder lookahead bias.
        Signaal dag X → uitvoering dag X+1.
        Equity dagelijks bijgehouden voor correcte Sharpe/Sortino.
        """
        df = df.copy()
        df['sig'] = strategie_func(df).shift(1).fillna(0)

        trade_pnls: list[float] = []
        equity = 1.0
        equity_serie: list[float] = [equity]
        positie = 0
        entry_prijs = 0.0

        for i in range(1, len(df)):
            prijs  = float(df['close'].iloc[i])
            prev_p = float(df['close'].iloc[i - 1])
            sig    = int(df['sig'].iloc[i])

            # Dagelijkse equity update (correcte tracking in positie)
            if positie != 0 and prev_p > 0:
                dag_ret = (prijs / prev_p - 1.0) * positie
                equity *= (1.0 + dag_ret)

            # Exit: signaal verandert of laatste bar
            if positie != 0 and (sig != positie or i == len(df) - 1):
                if entry_prijs > 0:
                    pnl = (prijs / entry_prijs - 1.0) * positie - self.kosten_per_kant
                    trade_pnls.append(pnl)
                equity *= (1.0 - self.kosten_per_kant)  # exit kosten
                positie = 0

            # Enter nieuwe positie
            if positie == 0 and sig != 0:
                entry_prijs = prijs
                equity *= (1.0 - self.kosten_per_kant)  # entry kosten
                positie = sig

            equity_serie.append(equity)

        dag_returns = [
            equity_serie[i] / equity_serie[i - 1] - 1.0
            for i in range(1, len(equity_serie))
        ]
        maand_returns = self._maand_returns(pd.Series(equity_serie, dtype=float), df)
        return trade_pnls, dag_returns, maand_returns

    def _maand_returns(self, equity: pd.Series, df: pd.DataFrame) -> list[float]:
        """Bereken maandelijkse rendementen voor consistentie-check."""
        if len(equity) != len(df) + 1:
            equity = equity[:len(df)]
        try:
            eq = pd.Series(equity.values, index=df.index)
            return list(eq.resample('ME').last().pct_change().dropna())
        except Exception:
            return []

    def _metrics(self, trade_pnls: list, dag_returns: list,
                 maand_returns: list) -> dict:
        """Bereken alle prestatiemetrieken."""
        arr = np.array(trade_pnls)
        dag = np.array(dag_returns)

        win_rate = float(np.mean(arr > 0)) if len(arr) > 0 else 0.0

        # Sharpe (dagelijks geannualiseerd)
        sharpe = 0.0
        if len(dag) > 1 and dag.std() > 0:
            sharpe = float((dag.mean() / dag.std()) * math.sqrt(HANDEL_JAAR))

        # Sortino (alleen neerwaartse volatiliteit)
        neg = dag[dag < 0]
        sortino = 0.0
        if len(neg) > 1 and neg.std() > 0:
            sortino = float((dag.mean() / neg.std()) * math.sqrt(HANDEL_JAAR))

        # Max drawdown via equity curve
        eq = np.cumprod(1 + dag)
        peak = np.maximum.accumulate(eq)
        dd = (eq - peak) / np.where(peak > 0, peak, 1)
        max_dd = float(abs(dd.min())) if len(dd) > 0 else 0.0

        # Calmar
        totaal_ret = float(eq[-1] - 1) if len(eq) > 0 else 0.0
        n_jaar = max(0.01, len(dag) / HANDEL_JAAR)
        ann_ret = (1 + totaal_ret) ** (1 / n_jaar) - 1
        calmar = float(ann_ret / max_dd) if max_dd > 0 else 0.0

        # Trades per maand (op basis van echte kalenderduur, werkt ook voor intraday)
        n_perioden = max(1, len(dag))
        n_maanden = max(1 / 30, n_perioden / (24 * 30))
        trades_pm = len(trade_pnls) / n_maanden

        # Consistentie
        consistentie = float(np.mean(np.array(maand_returns) > 0)) if maand_returns else 0.0

        return {
            'win_rate':         round(win_rate, 4),
            'sharpe':           round(sharpe, 3),
            'sortino':          round(sortino, 3),
            'calmar':           round(calmar, 3),
            'max_drawdown':     round(max_dd, 4),
            'trades_per_maand': round(trades_pm, 1),
            'consistentie':     round(consistentie, 3),
            'totaal_trades':    len(trade_pnls),
            'deflated_sharpe':  0.0,
            'goedgekeurd':      False,
        }

    def _deflated_sharpe(self, sharpe: float, n_strategieen: int = 6) -> float:
        """
        Deflated Sharpe: straft voor multiple testing.
        DS = SR × (1 - γ × ln(N) / N)
        """
        factor = 1.0 - (GAMMA_EM * math.log(max(1, n_strategieen))) / n_strategieen
        return round(sharpe * max(0.0, factor), 3)

    def _goedkeuren(self, m: dict) -> bool:
    	"""Alle criteria moeten slagen op basis van centrale CRITERIA-config."""
    	ops = {
        	'gt':  lambda a, b: a > b,
        	'gte': lambda a, b: a >= b,
        	'lt':  lambda a, b: a < b,
        	'lte': lambda a, b: a <= b,
    	}

    	checks = {}
    	for naam, (op, grens) in CRITERIA.items():
        	checks[naam] = ops[op](m[naam], grens)

    	m['criteria_checks'] = checks
    	return all(checks.values())

    def _leeg(self) -> dict:
        """Lege metrics bij onvoldoende data."""
        return {k: 0.0 for k in [
            'win_rate', 'sharpe', 'sortino', 'calmar',
            'max_drawdown', 'trades_per_maand', 'consistentie',
            'deflated_sharpe', 'totaal_trades'
        ]} | {'goedgekeurd': False, 'criteria_checks': {}}
