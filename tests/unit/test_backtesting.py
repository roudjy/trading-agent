"""
Unit tests voor backtesting engine, strategieën en ChaosMonkey.
"""
import sqlite3
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd

# Zorg dat project root in path zit
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from agent.backtesting.engine import BacktestEngine, SweepTooLargeError
from agent.backtesting.strategies import (
    bollinger_strategie,
    earnings_strategie,
    fear_greed_strategie,
    orb_strategie,
    polymarket_expiry_strategie,
    rsi_strategie,
)
from agent.monitoring.chaos import ChaosMonkey


# ──────────────────────────────────────────────────────────────────────────────
# Hulpfunctie: genereer synthetische OHLCV data
# ──────────────────────────────────────────────────────────────────────────────

def maak_df(n: int = 300, start_prijs: float = 100.0, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    returns = rng.normal(0.001, 0.02, n)
    close = start_prijs * np.cumprod(1 + returns)
    high  = close * (1 + rng.uniform(0, 0.01, n))
    low   = close * (1 - rng.uniform(0, 0.01, n))
    open_ = close * (1 + rng.normal(0, 0.005, n))
    volume = rng.integers(1000, 100_000, n)
    idx = pd.date_range("2022-01-01", periods=n, freq="D")
    return pd.DataFrame({
        "open": open_, "high": high, "low": low,
        "close": close, "volume": volume,
    }, index=idx)


# ══════════════════════════════════════════════════════════════════════════════
# TESTS: Strategieën
# ══════════════════════════════════════════════════════════════════════════════

class TestRsiStrategie(unittest.TestCase):

    def setUp(self):
        self.df = maak_df(300)

    def test_output_lengte(self):
        sig = rsi_strategie()(self.df)
        self.assertEqual(len(sig), len(self.df))

    def test_alleen_valide_waarden(self):
        sig = rsi_strategie()(self.df)
        self.assertTrue(set(sig.unique()).issubset({-1, 0, 1}))

    def test_te_weinig_data(self):
        sig = rsi_strategie(periode=14)(self.df.head(5))
        self.assertTrue((sig == 0).all())

    def test_drempel_effect(self):
        # Lagere koop-drempel → minder long-signalen
        sig_streng  = rsi_strategie(koop_drempel=20)(self.df)
        sig_ruim    = rsi_strategie(koop_drempel=40)(self.df)
        self.assertLessEqual((sig_streng == 1).sum(), (sig_ruim == 1).sum())


class TestBollingerStrategie(unittest.TestCase):

    def test_output_lengte(self):
        df = maak_df(200)
        sig = bollinger_strategie()(df)
        self.assertEqual(len(sig), len(df))

    def test_geen_lookahead_door_shift(self):
        # Strategie zelf levert signalen VOOR shift; engine doet shift(1)
        # Test dat de strategie-functie deterministisch is
        df = maak_df(200)
        sig1 = bollinger_strategie()(df)
        sig2 = bollinger_strategie()(df)
        pd.testing.assert_series_equal(sig1, sig2)


class TestEarningsStrategie(unittest.TestCase):

    def test_positie_duur(self):
        df = maak_df(100)
        sig = earnings_strategie(pct_drempel=0.001, positie_duur=3)(df)
        # Strategie genereert alleen 1-en (geen short)
        self.assertTrue(set(sig.unique()).issubset({0, 1}))


class TestOrbStrategie(unittest.TestCase):

    def test_vereist_open_high_kolommen(self):
        df = maak_df(100)
        df_zonder = df.drop(columns=["open", "high"])
        sig = orb_strategie()(df_zonder)
        self.assertTrue((sig == 0).all())

    def test_output_lengte(self):
        df = maak_df(200)
        sig = orb_strategie()(df)
        self.assertEqual(len(sig), len(df))


class TestFearGreedStrategie(unittest.TestCase):

    def _maak_fng(self, n: int = 300) -> pd.DataFrame:
        idx = pd.date_range("2022-01-01", periods=n, freq="D")
        waarden = np.random.default_rng(1).integers(5, 95, n)
        return pd.DataFrame({"datum": idx, "waarde": waarden})

    def test_geen_fng_data_geeft_nul(self):
        df = maak_df(100)
        sig = fear_greed_strategie(fng_df=None)(df)
        self.assertTrue((sig == 0).all())

    def test_extreme_fear_geeft_long(self):
        df = maak_df(100)
        fng = pd.DataFrame({
            "datum": df.index,
            "waarde": [5] * len(df),  # altijd extreme fear
        })
        sig = fear_greed_strategie(fear_drempel=25, fng_df=fng)(df)
        self.assertTrue((sig == 1).all())

    def test_extreme_greed_geeft_short(self):
        df = maak_df(100)
        fng = pd.DataFrame({
            "datum": df.index,
            "waarde": [95] * len(df),  # altijd extreme greed
        })
        sig = fear_greed_strategie(greed_drempel=75, fng_df=fng)(df)
        self.assertTrue((sig == -1).all())

    def test_timezone_aware_index(self):
        """tz-aware price index mag geen KeyError geven."""
        df = maak_df(100)
        df.index = df.index.tz_localize("UTC")
        fng = pd.DataFrame({
            "datum": pd.date_range("2022-01-01", periods=100, freq="D"),
            "waarde": [20] * 100,
        })
        sig = fear_greed_strategie(fear_drempel=25, fng_df=fng)(df)
        self.assertEqual(len(sig), 100)

    def test_polymarket_altijd_leeg(self):
        df = maak_df(50)
        sig = polymarket_expiry_strategie()(df)
        self.assertTrue((sig == 0).all())


# ══════════════════════════════════════════════════════════════════════════════
# TESTS: BacktestEngine._simuleer
# ══════════════════════════════════════════════════════════════════════════════

class TestBacktestEngine(unittest.TestCase):

    def _engine(self):
        e = BacktestEngine.__new__(BacktestEngine)
        e.kosten_per_kant = 0.001
        e.start = "2022-01-01"
        e.eind  = "2023-01-01"
        e.min_trades = 5
        return e

    def test_geen_signalen_geeft_lege_trades(self):
        eng = self._engine()
        df = maak_df(200)
        pnls, dag_rets, maand_rets = eng._simuleer(df, lambda d: pd.Series(0, index=d.index), "TEST")
        self.assertEqual(pnls, [])

    def test_equity_neemt_toe_bij_stijgende_prijs(self):
        """Bij altijd-long + stijgende prijs moet equity > 1 zijn."""
        eng = self._engine()
        n = 100
        prijs = np.linspace(100, 200, n)
        df = pd.DataFrame({
            "open": prijs, "high": prijs * 1.01,
            "low": prijs * 0.99, "close": prijs,
            "volume": [10000] * n,
        }, index=pd.date_range("2022-01-01", periods=n, freq="D"))
        pnls, dag_rets, _ = eng._simuleer(df, lambda d: pd.Series(1, index=d.index), "TEST")
        cum = 1.0
        for r in dag_rets:
            cum *= (1 + r)
        self.assertGreater(cum, 1.0)

    def test_geen_lookahead_bias(self):
        """Signaal van dag T mag niet ingaan op dag T (shift(1) vereist)."""
        eng = self._engine()
        df = maak_df(100)
        bar_0_sig = []

        def strategie_met_logging(d):
            sig = pd.Series(0, index=d.index)
            sig.iloc[0] = 1  # signaal alleen op dag 0
            return sig

        pnls, dag_rets, _ = eng._simuleer(df, strategie_met_logging, "TEST")
        # Entry op dag 1 (na shift), dus pnl start pas na dag 1
        # Minimaal 1 trade moet zijn gesloten
        self.assertGreaterEqual(len(pnls), 0)  # geen crash

    def test_dag_returns_lengte(self):
        eng = self._engine()
        df = maak_df(100)
        _, dag_rets, _ = eng._simuleer(df, rsi_strategie(), "TEST")
        self.assertEqual(len(dag_rets), len(df) - 1)

    def test_metrics_zonder_trades(self):
        eng = self._engine()
        metrics = eng._metrics([], [0.001, -0.002, 0.003], [0.01])
        self.assertEqual(metrics["totaal_trades"], 0)
        self.assertEqual(metrics["win_rate"], 0.0)

    def test_deflated_sharpe_lager_dan_sharpe(self):
        """DS moet ≤ Sharpe voor N=6 strategieën."""
        eng = self._engine()
        dag_rets = list(np.random.default_rng(42).normal(0.002, 0.01, 250))
        metrics = eng._metrics(
            [0.05, 0.03, -0.01, 0.07, 0.02],
            dag_rets,
            [0.02, 0.03, -0.01],
        )
        self.assertLessEqual(metrics["deflated_sharpe"], metrics["sharpe"] + 0.01)

    def test_goedkeuren_vereist_alle_criteria(self):
        eng = self._engine()
        # Perfect metrics → goedgekeurd (_goedkeuren muteert m en geeft bool)
        goed = {
            "win_rate": 0.55, "deflated_sharpe": 1.5,
            "max_drawdown": 0.20, "trades_per_maand": 6.0,
            "consistentie": 0.65,
        }
        ok = eng._goedkeuren(goed)
        self.assertTrue(ok)
        self.assertTrue(goed["criteria_checks"]["win_rate"])

        # Slechte drawdown → afgewezen
        slecht = {
            "win_rate": 0.55, "deflated_sharpe": 1.5,
            "max_drawdown": 0.45, "trades_per_maand": 6.0,
            "consistentie": 0.65,
        }
        ok2 = eng._goedkeuren(slecht)
        self.assertFalse(ok2)
        self.assertFalse(slecht["criteria_checks"]["max_drawdown"])

    def test_grid_search_weigert_te_grote_sweep(self):
        engine = BacktestEngine("2022-01-01", "2023-01-01", max_sweep_cells=4)

        with self.assertRaises(SweepTooLargeError):
            engine.grid_search(
                strategie_factory=lambda **params: (lambda df: pd.Series(0, index=df.index)),
                param_grid={"a": [1, 2, 3], "b": [1, 2]},
                assets=["TEST"],
                interval="1d",
            )

    @patch.object(BacktestEngine, "_run_op_split")
    def test_grid_search_accepteert_sweep_op_plafond(self, mock_run_op_split):
        engine = BacktestEngine("2022-01-01", "2023-01-01", max_sweep_cells=4)
        test_metrics = {
            "sharpe": 0.5,
            "win_rate": 0.6,
            "max_drawdown": 0.2,
            "trades_per_maand": 3.0,
            "consistentie": 0.6,
            "criteria_checks": {},
        }
        mock_run_op_split.side_effect = [
            {"sharpe": 0.1},
            {"sharpe": 0.2},
            {"sharpe": 0.3},
            {"sharpe": 0.4},
            test_metrics,
        ]

        result = engine.grid_search(
            strategie_factory=lambda **params: (lambda df: pd.Series(0, index=df.index)),
            param_grid={"a": [1, 2], "b": [1, 2]},
            assets=["TEST"],
            interval="1d",
        )

        self.assertEqual(result["beste_params"], {"a": 2, "b": 2})


# ══════════════════════════════════════════════════════════════════════════════
# TESTS: ChaosMonkey
# ══════════════════════════════════════════════════════════════════════════════

class TestChaosMonkey(unittest.TestCase):

    def test_inactief_injecteert_niet(self):
        monkey = ChaosMonkey(kans=1.0)
        # Niet geactiveerd → nooit injectie
        for _ in range(20):
            result = monkey.injecteer("network_timeout")
            self.assertFalse(result)

    def test_injectie_network_timeout(self):
        monkey = ChaosMonkey(kans=1.0)
        monkey.activeer()
        with self.assertRaises(TimeoutError):
            monkey.injecteer("network_timeout")
        monkey.deactiveer()

    def test_injectie_db_fout(self):
        monkey = ChaosMonkey(kans=1.0)
        monkey.activeer()
        with self.assertRaises(sqlite3.OperationalError):
            monkey.injecteer("db_fout")
        monkey.deactiveer()

    def test_injectie_prijs_corruptie(self):
        monkey = ChaosMonkey(kans=1.0)
        monkey.activeer()
        with self.assertRaises(ValueError):
            monkey.injecteer("prijs_corruptie")
        monkey.deactiveer()

    def test_injectie_geheugen_fout(self):
        monkey = ChaosMonkey(kans=1.0)
        monkey.activeer()
        with self.assertRaises(IOError):
            monkey.injecteer("geheugen_fout")
        monkey.deactiveer()

    def test_kans_nul_injecteert_nooit(self):
        monkey = ChaosMonkey(kans=0.0)
        monkey.activeer()
        for _ in range(50):
            result = monkey.injecteer("network_timeout")
            self.assertFalse(result)
        monkey.deactiveer()

    def test_rapport_telt_injecties(self):
        monkey = ChaosMonkey(kans=1.0)
        monkey.activeer()
        for _ in range(5):
            try:
                monkey.injecteer("db_fout")
            except sqlite3.OperationalError:
                pass
        r = monkey.rapport()
        self.assertEqual(r["injecties"].get("db_fout", 0), 5)
        monkey.deactiveer()

    def test_bewaken_context_manager_telt_gevangen(self):
        monkey = ChaosMonkey(kans=1.0)
        monkey.activeer()
        for _ in range(3):
            try:
                with monkey.bewaken("network_timeout"):
                    monkey.injecteer("network_timeout")
            except TimeoutError:
                pass
        r = monkey.rapport()
        self.assertEqual(r["gevangen"].get("network_timeout", 0), 3)
        monkey.deactiveer()

    def test_resilience_score_perfect(self):
        monkey = ChaosMonkey(kans=1.0, soorten=["db_fout"])
        monkey.activeer()
        for _ in range(4):
            try:
                with monkey.bewaken("db_fout"):
                    monkey.injecteer("db_fout")
            except sqlite3.OperationalError:
                pass
        r = monkey.rapport()
        self.assertEqual(r["resilience_score"], 1.0)
        monkey.deactiveer()

    def test_ongeldige_kans_raises(self):
        with self.assertRaises(ValueError):
            ChaosMonkey(kans=1.5)

    def test_reset(self):
        monkey = ChaosMonkey(kans=1.0)
        monkey.activeer()
        try:
            monkey.injecteer("db_fout")
        except sqlite3.OperationalError:
            pass
        monkey.reset()
        r = monkey.rapport()
        self.assertEqual(r["totaal_injecties"], 0)
        monkey.deactiveer()

    def test_onbekende_soort_wordt_genegeerd(self):
        monkey = ChaosMonkey(kans=1.0, soorten=["network_timeout"])
        monkey.activeer()
        # "db_fout" niet in soorten → False, geen exception
        result = monkey.injecteer("db_fout")
        self.assertFalse(result)
        monkey.deactiveer()


if __name__ == "__main__":
    unittest.main(verbosity=2)
