"""
BACKTESTING ENGINE
==================
Walk-forward validatie: train=70%, test=30%.
Anti-lookahead: signaal dag X -> uitvoering dag X+1.
Kosten: 0.5% bitvavo + 0.1% slippage = 0.6% round-trip.
"""

# AGENTS.md rules violation - scheduled for Phase 2 replacement.
# This file currently performs a brute-force Cartesian parameter sweep.
# Phase 1 adds a size guard; Phase 2 will replace it with a hypothesis-driven envelope.

import logging
import math
from datetime import UTC
from typing import Callable, Optional

import numpy as np
import pandas as pd

from data.contracts import Instrument
from data.repository import DataUnavailableError, MarketRepository

log = logging.getLogger(__name__)

KOSTEN_RT = 0.006
HANDEL_JAAR = 252
MIN_TRADES = 10
GAMMA_EM = 0.5772
MAX_SWEEP_CELLS = 64

CRITERIA = {
    'win_rate': ('gt', 0.50),
    'deflated_sharpe': ('gt', 0.50),
    'max_drawdown': ('lt', 0.40),
    'trades_per_maand': ('gte', 2.0),
    'consistentie': ('gt', 0.45),
}


class SweepTooLargeError(RuntimeError):
    """Raised when a brute-force sweep exceeds the Phase 1 safety ceiling."""


class BacktestEngine:
    """Walk-forward backtesting engine met Deflated Sharpe goedkeuring."""

    def __init__(
        self,
        start_datum: str,
        eind_datum: str,
        transactiekosten: float = 0.005,
        max_sweep_cells: int = MAX_SWEEP_CELLS,
    ):
        self.start = start_datum
        self.eind = eind_datum
        self.kosten_per_kant = transactiekosten / 2 + 0.001
        self.max_sweep_cells = max_sweep_cells
        self._provenance_events = []
        self.last_evaluation_report: dict = {}
        self.last_evaluation_samples: dict[str, list[float]] = {}

    def run(self, strategie_func: Callable, assets: list, interval: str = '1d') -> dict:
        """Walk-forward backtest over meerdere assets. Return metrics dict."""
        self.interval = interval
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
            trade_pnl, dag_ret, maand_ret = self._simuleer(df_test, strategie_func, asset)
            trade_pnls.extend(trade_pnl)
            dag_returns.extend(dag_ret)
            maand_returns.extend(maand_ret)

        self._capture_evaluation_report(trade_pnls, dag_returns, maand_returns)
        if len(trade_pnls) < MIN_TRADES:
            return {**self._leeg(), 'reden': f'Te weinig trades: {len(trade_pnls)}'}

        metrics = self._metrics(trade_pnls, dag_returns, maand_returns)
        metrics['deflated_sharpe'] = self._deflated_sharpe(metrics['sharpe'])
        metrics['goedgekeurd'] = self._goedkeuren(metrics)
        return metrics

    def grid_search(
        self,
        strategie_factory: Callable,
        param_grid: dict,
        assets: list,
        interval: str = '1d',
    ) -> dict:
        """
        Grid search over parameterruimte op train-set.
        Beste params worden gevalideerd op test-set.
        """
        beste_params = None
        beste_sharpe = -999.0
        n_combis = 1
        for values in param_grid.values():
            n_combis *= len(values)

        if n_combis > self.max_sweep_cells:
            log.warning(
                f"[BT] Sweep geweigerd: {n_combis} combinaties voor plafond {self.max_sweep_cells}"
            )
            raise SweepTooLargeError(
                f"Sweep van {n_combis} combinaties overschrijdt MAX_SWEEP_CELLS={self.max_sweep_cells}"
            )

        log.info(f"[BT] Grid search: {n_combis} combinaties op train-set")

        param_namen = list(param_grid.keys())
        param_waarden = list(param_grid.values())

        import itertools
        for combo in itertools.product(*param_waarden):
            params = dict(zip(param_namen, combo))
            train_metrics = self._run_op_split(
                strategie_factory(**params),
                assets,
                interval,
                train=True,
            )
            if train_metrics['sharpe'] > beste_sharpe:
                beste_sharpe = train_metrics['sharpe']
                beste_params = params

        if beste_params is None:
            return {**self._leeg(), 'reden': 'Grid search geen resultaat'}

        log.info(f"[BT] Beste params: {beste_params} (train Sharpe={beste_sharpe:.2f})")
        result = self._run_op_split(
            strategie_factory(**beste_params),
            assets,
            interval,
            train=False,
        )
        result['beste_params'] = beste_params
        result['deflated_sharpe'] = self._deflated_sharpe(result['sharpe'])
        result['goedgekeurd'] = self._goedkeuren(result)
        return result

    def _run_op_split(self, strategie_func: Callable, assets: list, interval: str, train: bool) -> dict:
        """Voer backtest uit op specifieke split (train of test)."""
        self.interval = interval
        trade_pnls, dag_returns, maand_returns = [], [], []
        for asset in assets:
            df = self._laad_data(asset, interval)
            if df is None or len(df) < 100:
                continue
            split = int(len(df) * 0.70)
            df_deel = df.iloc[:split] if train else df.iloc[split:]
            trades, dag, maand = self._simuleer(df_deel.copy(), strategie_func, asset)
            trade_pnls.extend(trades)
            dag_returns.extend(dag)
            maand_returns.extend(maand)
        self._capture_evaluation_report(trade_pnls, dag_returns, maand_returns)
        if len(trade_pnls) < MIN_TRADES:
            return self._leeg()
        return self._metrics(trade_pnls, dag_returns, maand_returns)

    def _laad_data(self, asset: str, interval: str) -> Optional[pd.DataFrame]:
        """Download en prepareer OHLCV data. auto_adjust=True altijd."""
        try:
            if not hasattr(self, "_market_repository"):
                self._market_repository = MarketRepository()

            ticker = asset.replace('/', '-')
            quote_ccy = ticker.split('-')[-1] if '-' in ticker else 'USD'
            instrument = Instrument(
                id=ticker.lower(),
                asset_class='crypto' if self._is_crypto_ticker(ticker) else 'equity',
                venue='yahoo',
                native_symbol=ticker,
                quote_ccy=quote_ccy,
            )

            response = self._market_repository.get_bars(
                instrument=instrument,
                interval=interval,
                start_utc=self._parse_utc_bound(self.start),
                end_utc=self._parse_utc_bound(self.eind),
            )
            if not hasattr(self, "_provenance_events"):
                self._provenance_events = []
            self._provenance_events.append(response.provenance)
            df = response.frame
            if df.empty:
                return None
            return df
        except DataUnavailableError as e:
            log.error(f"[BT] Data laden mislukt {asset}: {e}")
            return None
        except Exception as e:
            log.error(f"[BT] Data laden mislukt {asset}: {e}")
            return None

    @staticmethod
    def _is_crypto_ticker(ticker: str) -> bool:
        return '-EUR' in ticker or '-USD' in ticker or '-BTC' in ticker

    @staticmethod
    def _parse_utc_bound(value: str) -> pd.Timestamp:
        timestamp = pd.Timestamp(value)
        if timestamp.tzinfo is None:
            return timestamp.tz_localize(UTC)
        return timestamp.tz_convert(UTC)

    def _simuleer(self, df: pd.DataFrame, strategie_func: Callable, asset: str) -> tuple[list, list, list]:
        """
        Simuleer trades zonder lookahead bias.
        Signaal dag X -> uitvoering dag X+1.
        Equity dagelijks bijgehouden voor correcte Sharpe/Sortino.
        """
        df = self._prepare_bollinger_regime_df(df, strategie_func)
        sig = self._prepare_trend_pullback_tp_sl_sig(df, strategie_func)
        if sig is None:
            sig = strategie_func(df)
        df['sig'] = sig.shift(1).fillna(0)

        trade_pnls: list[float] = []
        equity = 1.0
        equity_serie: list[float] = [equity]
        positie = 0
        entry_prijs = 0.0

        for i in range(1, len(df)):
            prijs = float(df['close'].iloc[i])
            vorige_prijs = float(df['close'].iloc[i - 1])
            signaal = int(df['sig'].iloc[i])

            if positie != 0 and vorige_prijs > 0:
                dag_ret = (prijs / vorige_prijs - 1.0) * positie
                equity *= (1.0 + dag_ret)

            if positie != 0 and (signaal != positie or i == len(df) - 1):
                if entry_prijs > 0:
                    pnl = (prijs / entry_prijs - 1.0) * positie - self.kosten_per_kant
                    trade_pnls.append(pnl)
                equity *= (1.0 - self.kosten_per_kant)
                positie = 0

            if positie == 0 and signaal != 0:
                entry_prijs = prijs
                equity *= (1.0 - self.kosten_per_kant)
                positie = signaal

            equity_serie.append(equity)

        dag_returns = [
            equity_serie[i] / equity_serie[i - 1] - 1.0
            for i in range(1, len(equity_serie))
        ]
        maand_returns = self._maand_returns(pd.Series(equity_serie, dtype=float), df)
        return trade_pnls, dag_returns, maand_returns

    def _prepare_bollinger_regime_df(self, df: pd.DataFrame, strategie_func: Callable) -> pd.DataFrame:
        """Precompute regime gating only for bollinger_regime."""
        df = df.copy()
        regime_config = getattr(strategie_func, "_mr_regime_config", None)
        if regime_config is None:
            return df

        close = df["close"].astype(float)
        prijzen = close.to_numpy()
        lookback = regime_config["lookback_periode"]
        vol_drempel = regime_config["volatiliteit_drempel"]

        regime_ok = pd.Series(False, index=df.index)

        for i in range(lookback + 1, len(df)):
            window = prijzen[i - (lookback + 1):i]
            rendementen = np.diff(np.log(window))
            recent = rendementen[-lookback:]

            volatiliteit = np.std(recent) * np.sqrt(252)
            x = np.arange(len(recent))
            helling = np.polyfit(x, recent.cumsum(), 1)[0]
            trend_sterkte = abs(helling) / (volatiliteit + 1e-8)

            kortetermijn_ma = np.mean(window[-5:])
            langetermijn_ma = np.mean(window[-lookback:])
            ma_verhouding = (kortetermijn_ma - langetermijn_ma) / langetermijn_ma

            regime_ok.iloc[i] = (
                volatiliteit <= vol_drempel * 3
                and (
                    volatiliteit > vol_drempel * 1.5
                    or not (
                        (ma_verhouding > 0.02 and trend_sterkte > 0.5)
                        or (ma_verhouding < -0.02 and trend_sterkte > 0.5)
                    )
                )
            )

        df["_mr_regime_ok"] = regime_ok
        return df

    def _prepare_trend_pullback_tp_sl_sig(
        self,
        df: pd.DataFrame,
        strategie_func: Callable,
    ) -> Optional[pd.Series]:
        """Precompute TP/SL-managed signals only for trend_pullback_tp_sl."""
        strategy_config = getattr(strategie_func, "_trend_pullback_tp_sl_config", None)
        if strategy_config is None:
            return None

        raw_sig = strategie_func(df).fillna(0)
        close = df["close"].astype(float)
        ema_fast = close.ewm(span=strategy_config["ema_kort"], adjust=False).mean()
        ema_slow = close.ewm(span=strategy_config["ema_lang"], adjust=False).mean()
        take_profit = strategy_config["take_profit"]
        stop_loss = strategy_config["stop_loss"]

        managed_sig = pd.Series(0, index=df.index)
        in_position = False
        entry_price = None

        for i in range(1, len(df)):
            prijs = close.iloc[i]

            if not in_position:
                if bool(raw_sig.iloc[i]):
                    managed_sig.iloc[i] = 1
                    in_position = True
                    entry_price = prijs
            else:
                pnl = (prijs / entry_price) - 1.0 if entry_price else 0.0

                if pnl >= take_profit or pnl <= -stop_loss or ema_fast.iloc[i] <= ema_slow.iloc[i]:
                    managed_sig.iloc[i] = 0
                    in_position = False
                    entry_price = None
                else:
                    managed_sig.iloc[i] = 1

        return managed_sig

    def _maand_returns(self, equity: pd.Series, df: pd.DataFrame) -> list[float]:
        """Bereken maandelijkse rendementen voor consistentie-check."""
        if len(equity) != len(df) + 1:
            equity = equity[:len(df)]
        try:
            eq = pd.Series(equity.values, index=df.index)
            return list(eq.resample('ME').last().pct_change().dropna())
        except Exception:
            return []

    def _capture_evaluation_report(
        self,
        trade_pnls: list[float],
        dag_returns: list[float],
        maand_returns: list[float],
    ) -> None:
        evaluation_samples = {
            'daily_returns': list(dag_returns),
            'trade_pnls': list(trade_pnls),
            'monthly_returns': list(maand_returns),
        }
        self.last_evaluation_samples = evaluation_samples
        self.last_evaluation_report = {
            'evaluation_samples': evaluation_samples,
            'sample_statistics': {
                naam: self._sample_statistics(values)
                for naam, values in evaluation_samples.items()
            },
        }

    @staticmethod
    def _sample_statistics(values: list[float]) -> dict[str, float]:
        array = np.asarray(values, dtype=float)
        if array.size == 0:
            return {
                'count': 0,
                'mean': 0.0,
                'std': 0.0,
                'skew': 0.0,
                'kurt': 0.0,
            }

        mean = float(array.mean())
        std = float(array.std())
        if std == 0.0:
            skew = 0.0
            kurt = 3.0
        else:
            centered = (array - mean) / std
            skew = float(np.mean(centered ** 3))
            kurt = float(np.mean(centered ** 4))

        return {
            'count': int(array.size),
            'mean': mean,
            'std': std,
            'skew': skew,
            'kurt': kurt,
        }

    def _metrics(self, trade_pnls: list, dag_returns: list, maand_returns: list) -> dict:
        """Bereken alle prestatiemetrieken."""
        arr = np.array(trade_pnls)
        dag = np.array(dag_returns)

        win_rate = float(np.mean(arr > 0)) if len(arr) > 0 else 0.0

        factor = {
            '1d': 252,
            '1h': 24 * 365,
            '15m': 4 * 24 * 365,
            '5m': 12 * 24 * 365,
        }.get(getattr(self, 'interval', '1d'), 252)

        sharpe = 0.0
        if len(dag) > 1 and dag.std() > 0:
            sharpe = float((dag.mean() / dag.std()) * math.sqrt(factor))

        neg = dag[dag < 0]
        sortino = 0.0
        if len(neg) > 1 and neg.std() > 0:
            sortino = float((dag.mean() / neg.std()) * math.sqrt(factor))

        eq = np.cumprod(1 + dag)
        peak = np.maximum.accumulate(eq)
        dd = (eq - peak) / np.where(peak > 0, peak, 1)
        max_dd = float(abs(dd.min())) if len(dd) > 0 else 0.0

        totaal_ret = float(eq[-1] - 1) if len(eq) > 0 else 0.0
        n_jaar = max(0.01, len(dag) / HANDEL_JAAR)
        ann_ret = (1 + totaal_ret) ** (1 / n_jaar) - 1
        calmar = float(ann_ret / max_dd) if max_dd > 0 else 0.0

        perioden_per_dag = {
            '1d': 1,
            '1h': 24,
            '15m': 96,
            '5m': 288,
        }.get(getattr(self, 'interval', '1d'), 1)

        n_perioden = max(1, len(dag))
        n_maanden = max(1 / 30, n_perioden / (perioden_per_dag * 30))
        trades_pm = len(trade_pnls) / n_maanden

        consistentie = float(np.mean(np.array(maand_returns) > 0)) if maand_returns else 0.0

        return {
            'win_rate': round(win_rate, 4),
            'sharpe': round(sharpe, 3),
            'sortino': round(sortino, 3),
            'calmar': round(calmar, 3),
            'max_drawdown': round(max_dd, 4),
            'trades_per_maand': round(trades_pm, 1),
            'consistentie': round(consistentie, 3),
            'totaal_trades': len(trade_pnls),
            'deflated_sharpe': 0.0,
            'goedgekeurd': False,
        }

    def _deflated_sharpe(self, sharpe: float, n_strategieen: int = 6) -> float:
        """
        Deflated Sharpe: straft voor multiple testing.
        DS = SR x (1 - gamma x ln(N) / N)
        """
        factor = 1.0 - (GAMMA_EM * math.log(max(1, n_strategieen))) / n_strategieen
        return round(sharpe * max(0.0, factor), 3)

    def _goedkeuren(self, metrics: dict) -> bool:
        """Alle criteria moeten slagen op basis van centrale CRITERIA-config."""
        ops = {
            'gt': lambda a, b: a > b,
            'gte': lambda a, b: a >= b,
            'lt': lambda a, b: a < b,
            'lte': lambda a, b: a <= b,
        }

        checks = {}
        for naam, (op, grens) in CRITERIA.items():
            checks[naam] = ops[op](metrics[naam], grens)

        metrics['criteria_checks'] = checks
        return all(checks.values())

    def _leeg(self) -> dict:
        """Lege metrics bij onvoldoende data."""
        return {k: 0.0 for k in [
            'win_rate',
            'sharpe',
            'sortino',
            'calmar',
            'max_drawdown',
            'trades_per_maand',
            'consistentie',
            'deflated_sharpe',
            'totaal_trades',
        ]} | {'goedgekeurd': False, 'criteria_checks': {}}
