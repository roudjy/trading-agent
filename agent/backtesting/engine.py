"""
Backtesting engine with deterministic OOS / walk-forward evaluation.
"""

import itertools
import logging
import math
from dataclasses import dataclass
from datetime import UTC
from typing import Any, Callable, Optional

import numpy as np
import pandas as pd

from data.contracts import Instrument
from data.repository import DataUnavailableError, MarketRepository

log = logging.getLogger(__name__)

KOSTEN_RT = 0.006
HANDEL_JAAR = 252
MIN_TRADES = 10
MIN_DATA_BARS = 100
GAMMA_EM = 0.5772
MAX_SWEEP_CELLS = 64
DEFAULT_SELECTION_METRIC = "sharpe"
DEFAULT_TRAIN_RATIO = 0.7

CRITERIA = {
    "win_rate": ("gt", 0.50),
    "deflated_sharpe": ("gt", 0.50),
    "max_drawdown": ("lt", 0.40),
    "trades_per_maand": ("gte", 2.0),
    "consistentie": ("gt", 0.45),
}

METRIC_KEYS = (
    "win_rate",
    "sharpe",
    "sortino",
    "calmar",
    "max_drawdown",
    "trades_per_maand",
    "consistentie",
    "totaal_trades",
    "deflated_sharpe",
    "goedgekeurd",
    "criteria_checks",
)

IndexRange = tuple[int, int]
Fold = tuple[IndexRange, IndexRange]


class SweepTooLargeError(RuntimeError):
    """Raised when a brute-force sweep exceeds the Phase 1 safety ceiling."""


class EvaluationScheduleError(ValueError):
    """Raised when an evaluation schedule cannot produce valid folds."""


class FoldLeakageError(EvaluationScheduleError):
    """Raised when train and test windows overlap or touch."""


@dataclass(frozen=True)
class AssetContext:
    asset: str
    frame: pd.DataFrame
    folds: list[Fold]


def normalize_evaluation_config(evaluation_config: Optional[dict[str, Any]]) -> dict[str, Any]:
    config = dict(evaluation_config or {})
    mode = config.get("mode", "single_split")
    normalized: dict[str, Any] = {
        "mode": mode,
        "selection_metric": config.get("selection_metric", DEFAULT_SELECTION_METRIC),
    }

    if mode == "single_split":
        train_ratio = float(config.get("train_ratio", DEFAULT_TRAIN_RATIO))
        if not 0 < train_ratio < 1:
            raise EvaluationScheduleError(
                f"single_split requires 0 < train_ratio < 1, got {train_ratio!r}"
            )
        normalized["train_ratio"] = train_ratio
        return normalized

    if mode == "rolling":
        normalized["train_bars"] = _require_positive_int(config, "train_bars")
        normalized["test_bars"] = _require_positive_int(config, "test_bars")
        normalized["step_bars"] = _require_positive_int(config, "step_bars")
        return normalized

    if mode == "anchored":
        normalized["initial_train_bars"] = _require_positive_int(config, "initial_train_bars")
        normalized["test_bars"] = _require_positive_int(config, "test_bars")
        normalized["step_bars"] = _require_positive_int(config, "step_bars")
        return normalized

    raise EvaluationScheduleError(f"Unsupported evaluation mode: {mode!r}")


def single_split(n: int, train_ratio: float) -> list[Fold]:
    split = int(n * train_ratio)
    if split < 1 or split >= n:
        raise EvaluationScheduleError(
            f"single_split produced invalid boundaries for n={n}, train_ratio={train_ratio}"
        )
    folds = [((0, split - 1), (split, n - 1))]
    validate_no_leakage(folds)
    return folds


def rolling_walk_forward(n: int, train_bars: int, test_bars: int, step_bars: int) -> list[Fold]:
    folds: list[Fold] = []
    start = 0
    while True:
        train_start = start
        train_end = train_start + train_bars - 1
        test_start = train_end + 1
        test_end = test_start + test_bars - 1
        if test_end >= n:
            break
        folds.append(((train_start, train_end), (test_start, test_end)))
        start += step_bars

    if not folds:
        raise EvaluationScheduleError(
            "rolling schedule produced zero folds "
            f"for n={n}, train_bars={train_bars}, test_bars={test_bars}, step_bars={step_bars}"
        )
    validate_no_leakage(folds)
    return folds


def anchored_walk_forward(
    n: int,
    initial_train_bars: int,
    test_bars: int,
    step_bars: int,
) -> list[Fold]:
    folds: list[Fold] = []
    train_end = initial_train_bars - 1
    while True:
        test_start = train_end + 1
        test_end = test_start + test_bars - 1
        if test_end >= n:
            break
        folds.append(((0, train_end), (test_start, test_end)))
        train_end += step_bars

    if not folds:
        raise EvaluationScheduleError(
            "anchored schedule produced zero folds "
            f"for n={n}, initial_train_bars={initial_train_bars}, "
            f"test_bars={test_bars}, step_bars={step_bars}"
        )
    validate_no_leakage(folds)
    return folds


def build_evaluation_folds(n: int, evaluation_config: Optional[dict[str, Any]]) -> list[Fold]:
    config = normalize_evaluation_config(evaluation_config)
    mode = config["mode"]
    if mode == "single_split":
        return single_split(n, config["train_ratio"])
    if mode == "rolling":
        return rolling_walk_forward(
            n=n,
            train_bars=config["train_bars"],
            test_bars=config["test_bars"],
            step_bars=config["step_bars"],
        )
    return anchored_walk_forward(
        n=n,
        initial_train_bars=config["initial_train_bars"],
        test_bars=config["test_bars"],
        step_bars=config["step_bars"],
    )


def validate_no_leakage(folds: list[Fold]) -> None:
    for fold_index, (train_bounds, test_bounds) in enumerate(folds):
        train_start, train_end = train_bounds
        test_start, test_end = test_bounds
        if train_start < 0 or test_start < 0:
            raise FoldLeakageError(
                f"Fold {fold_index} has negative boundaries: train={train_bounds}, test={test_bounds}"
            )
        if train_start > train_end:
            raise FoldLeakageError(
                f"Fold {fold_index} has invalid train bounds: train={train_bounds}"
            )
        if test_start > test_end:
            raise FoldLeakageError(
                f"Fold {fold_index} has invalid test bounds: test={test_bounds}"
            )
        if train_end >= test_start:
            raise FoldLeakageError(
                f"Fold {fold_index} leaks: max(train_index)={train_end} >= min(test_index)={test_start}"
            )


def _require_positive_int(config: dict[str, Any], key: str) -> int:
    if key not in config:
        raise EvaluationScheduleError(f"Missing required evaluation key: {key}")
    value = int(config[key])
    if value <= 0:
        raise EvaluationScheduleError(f"{key} must be > 0, got {value!r}")
    return value


class BacktestEngine:
    """Walk-forward backtesting engine met Deflated Sharpe goedkeuring."""

    def __init__(
        self,
        start_datum: str,
        eind_datum: str,
        transactiekosten: float = 0.005,
        max_sweep_cells: int = MAX_SWEEP_CELLS,
        evaluation_config: Optional[dict[str, Any]] = None,
    ):
        self.start = start_datum
        self.eind = eind_datum
        self.kosten_per_kant = transactiekosten / 2 + 0.001
        self.max_sweep_cells = max_sweep_cells
        self.evaluation_config = normalize_evaluation_config(evaluation_config)
        self.min_trades = MIN_TRADES
        self._provenance_events: list[Any] = []
        self.last_evaluation_report: Optional[dict[str, Any]] = None

    def run(self, strategie_func: Callable, assets: list, interval: str = "1d") -> dict:
        """Run fixed-parameter evaluation and return public OOS metrics only."""
        self.interval = interval
        asset_contexts = self._load_asset_contexts(assets, interval)
        is_summary = self._evaluate_windows(strategie_func, asset_contexts, use_train=True)
        oos_summary = self._evaluate_windows(strategie_func, asset_contexts, use_train=False)

        result = dict(oos_summary)
        if result["totaal_trades"] < self.min_trades:
            result["reden"] = f"Te weinig trades: {result['totaal_trades']}"

        self.last_evaluation_report = self._build_evaluation_report(
            asset_contexts=asset_contexts,
            selected_params={},
            is_summary=is_summary,
            oos_summary=oos_summary,
            selection_metric=self.evaluation_config["selection_metric"],
        )
        return result

    def grid_search(
        self,
        strategie_factory: Callable,
        param_grid: dict,
        assets: list,
        interval: str = "1d",
    ) -> dict:
        """
        Grid search over parameterruimte op train folds.
        Beste params worden opnieuw gevalideerd op train en test folds.
        """
        self.interval = interval
        beste_params = None
        beste_score = None
        beste_train_metrics = None
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

        asset_contexts = self._load_asset_contexts(assets, interval)
        selection_metric = self.evaluation_config["selection_metric"]
        log.info(f"[BT] Grid search: {n_combis} combinaties op train folds")

        param_namen = list(param_grid.keys())
        param_waarden = list(param_grid.values())

        for combo in itertools.product(*param_waarden):
            params = dict(zip(param_namen, combo))
            train_metrics = self._run_op_split(
                strategie_factory(**params),
                assets,
                interval,
                train=True,
                _asset_contexts=asset_contexts,
            )
            score = self._selection_score(train_metrics, selection_metric)
            if beste_score is None or score > beste_score:
                beste_score = score
                beste_params = params
                beste_train_metrics = train_metrics

        if beste_params is None:
            return {**self._leeg(), "reden": "Grid search geen resultaat"}

        frozen_strategy = strategie_factory(**beste_params)
        is_summary = self._evaluate_windows(frozen_strategy, asset_contexts, use_train=True)
        oos_summary = self._run_op_split(
            frozen_strategy,
            assets,
            interval,
            train=False,
            _asset_contexts=asset_contexts,
        )

        log.info(
            f"[BT] Beste params: {beste_params} "
            f"(train {selection_metric}={beste_train_metrics.get(selection_metric, 0.0):.3f})"
        )

        result = dict(oos_summary)
        result["beste_params"] = beste_params
        self.last_evaluation_report = self._build_evaluation_report(
            asset_contexts=asset_contexts,
            selected_params=beste_params,
            is_summary=is_summary,
            oos_summary=oos_summary,
            selection_metric=selection_metric,
        )
        return result

    def _run_op_split(
        self,
        strategie_func: Callable,
        assets: list,
        interval: str,
        train: bool,
        _asset_contexts: Optional[list[AssetContext]] = None,
    ) -> dict:
        """Voer backtest uit op train of test windows binnen de huidige scheduler."""
        self.interval = interval
        asset_contexts = _asset_contexts or self._load_asset_contexts(assets, interval)
        return self._evaluate_windows(strategie_func, asset_contexts, use_train=train)

    def _load_asset_contexts(self, assets: list[str], interval: str) -> list[AssetContext]:
        asset_contexts: list[AssetContext] = []
        for asset in assets:
            df = self._laad_data(asset, interval)
            if df is None or len(df) < MIN_DATA_BARS:
                log.warning(f"[BT] Te weinig data: {asset}")
                continue
            folds = build_evaluation_folds(len(df), self.evaluation_config)
            asset_contexts.append(AssetContext(asset=asset, frame=df, folds=folds))
        return asset_contexts

    def _evaluate_windows(
        self,
        strategie_func: Callable,
        asset_contexts: list[AssetContext],
        use_train: bool,
    ) -> dict:
        trade_pnls: list[float] = []
        dag_returns: list[float] = []
        maand_returns: list[float] = []

        for context in asset_contexts:
            for train_bounds, test_bounds in context.folds:
                start_idx, end_idx = train_bounds if use_train else test_bounds
                df_window = context.frame.iloc[start_idx : end_idx + 1].copy()
                trades, dag, maand = self._simuleer(df_window, strategie_func, context.asset)
                trade_pnls.extend(trades)
                dag_returns.extend(dag)
                maand_returns.extend(maand)

        if len(trade_pnls) < self.min_trades:
            return self._finalize_metrics(self._leeg())

        return self._finalize_metrics(self._metrics(trade_pnls, dag_returns, maand_returns))

    def _build_evaluation_report(
        self,
        asset_contexts: list[AssetContext],
        selected_params: dict[str, Any],
        is_summary: dict[str, Any],
        oos_summary: dict[str, Any],
        selection_metric: str,
    ) -> dict[str, Any]:
        folds_by_asset = {
            context.asset: self._serialize_folds(context.folds)
            for context in asset_contexts
        }
        leakage_checks_ok = all(
            fold["leakage_ok"]
            for folds in folds_by_asset.values()
            for fold in folds
        )
        report = {
            "evaluation_config": dict(self.evaluation_config),
            "selection_metric": selection_metric,
            "selected_params": dict(selected_params),
            "is_summary": self._summary_payload(is_summary),
            "oos_summary": self._summary_payload(oos_summary),
            "folds_by_asset": folds_by_asset,
            "leakage_checks_ok": leakage_checks_ok,
        }
        if len(folds_by_asset) == 1:
            report["folds"] = next(iter(folds_by_asset.values()))
        return report

    @staticmethod
    def _serialize_folds(folds: list[Fold]) -> list[dict[str, Any]]:
        return [
            {
                "train": [train_start, train_end],
                "test": [test_start, test_end],
                "leakage_ok": train_end < test_start,
            }
            for (train_start, train_end), (test_start, test_end) in folds
        ]

    @staticmethod
    def _summary_payload(metrics: dict[str, Any]) -> dict[str, Any]:
        return {key: metrics.get(key) for key in METRIC_KEYS}

    def _selection_score(self, metrics: dict[str, Any], selection_metric: str) -> float:
        value = float(metrics.get(selection_metric, 0.0))
        operator = CRITERIA.get(selection_metric, ("gt", 0.0))[0]
        return -value if operator in {"lt", "lte"} else value

    def _finalize_metrics(self, metrics: dict[str, Any]) -> dict[str, Any]:
        finalized = dict(metrics)
        finalized["deflated_sharpe"] = self._deflated_sharpe(finalized["sharpe"])
        finalized["goedgekeurd"] = self._goedkeuren(finalized)
        return finalized

    def _laad_data(self, asset: str, interval: str) -> Optional[pd.DataFrame]:
        """Download en prepareer OHLCV data. auto_adjust=True altijd."""
        try:
            if not hasattr(self, "_market_repository"):
                self._market_repository = MarketRepository()

            ticker = asset.replace("/", "-")
            quote_ccy = ticker.split("-")[-1] if "-" in ticker else "USD"
            instrument = Instrument(
                id=ticker.lower(),
                asset_class="crypto" if self._is_crypto_ticker(ticker) else "equity",
                venue="yahoo",
                native_symbol=ticker,
                quote_ccy=quote_ccy,
            )

            response = self._market_repository.get_bars(
                instrument=instrument,
                interval=interval,
                start_utc=self._parse_utc_bound(self.start),
                end_utc=self._parse_utc_bound(self.eind),
            )
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
        return "-EUR" in ticker or "-USD" in ticker or "-BTC" in ticker

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
        df["sig"] = sig.shift(1).fillna(0)

        trade_pnls: list[float] = []
        equity = 1.0
        equity_serie: list[float] = [equity]
        positie = 0
        entry_prijs = 0.0

        for i in range(1, len(df)):
            prijs = float(df["close"].iloc[i])
            vorige_prijs = float(df["close"].iloc[i - 1])
            signaal = int(df["sig"].iloc[i])

            if positie != 0 and vorige_prijs > 0:
                dag_ret = (prijs / vorige_prijs - 1.0) * positie
                equity *= 1.0 + dag_ret

            if positie != 0 and (signaal != positie or i == len(df) - 1):
                if entry_prijs > 0:
                    pnl = (prijs / entry_prijs - 1.0) * positie - self.kosten_per_kant
                    trade_pnls.append(pnl)
                equity *= 1.0 - self.kosten_per_kant
                positie = 0

            if positie == 0 and signaal != 0:
                entry_prijs = prijs
                equity *= 1.0 - self.kosten_per_kant
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
            window = prijzen[i - (lookback + 1) : i]
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
            equity = equity[: len(df)]
        try:
            eq = pd.Series(equity.values, index=df.index)
            return list(eq.resample("ME").last().pct_change().dropna())
        except Exception:
            return []

    def _metrics(self, trade_pnls: list, dag_returns: list, maand_returns: list) -> dict:
        """Bereken alle prestatiemetrieken."""
        arr = np.array(trade_pnls)
        dag = np.array(dag_returns)

        win_rate = float(np.mean(arr > 0)) if len(arr) > 0 else 0.0

        factor = {
            "1d": 252,
            "1h": 24 * 365,
            "15m": 4 * 24 * 365,
            "5m": 12 * 24 * 365,
        }.get(getattr(self, "interval", "1d"), 252)

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
            "1d": 1,
            "1h": 24,
            "15m": 96,
            "5m": 288,
        }.get(getattr(self, "interval", "1d"), 1)

        n_perioden = max(1, len(dag))
        n_maanden = max(1 / 30, n_perioden / (perioden_per_dag * 30))
        trades_pm = len(trade_pnls) / n_maanden

        consistentie = float(np.mean(np.array(maand_returns) > 0)) if maand_returns else 0.0

        return {
            "win_rate": round(win_rate, 4),
            "sharpe": round(sharpe, 3),
            "sortino": round(sortino, 3),
            "calmar": round(calmar, 3),
            "max_drawdown": round(max_dd, 4),
            "trades_per_maand": round(trades_pm, 1),
            "consistentie": round(consistentie, 3),
            "totaal_trades": len(trade_pnls),
            "deflated_sharpe": 0.0,
            "goedgekeurd": False,
            "criteria_checks": {},
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
            "gt": lambda a, b: a > b,
            "gte": lambda a, b: a >= b,
            "lt": lambda a, b: a < b,
            "lte": lambda a, b: a <= b,
        }

        checks = {}
        for naam, (op, grens) in CRITERIA.items():
            checks[naam] = ops[op](metrics[naam], grens)

        metrics["criteria_checks"] = checks
        return all(checks.values())

    def _leeg(self) -> dict:
        """Lege metrics bij onvoldoende data."""
        return {
            "win_rate": 0.0,
            "sharpe": 0.0,
            "sortino": 0.0,
            "calmar": 0.0,
            "max_drawdown": 0.0,
            "trades_per_maand": 0.0,
            "consistentie": 0.0,
            "deflated_sharpe": 0.0,
            "totaal_trades": 0,
            "goedgekeurd": False,
            "criteria_checks": {},
        }
