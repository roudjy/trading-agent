"""
BASE AGENT
==========
Abstracte basisklasse voor alle sub-agents.
Bevat gedeelde logica: cooldown, dedup, force exit, stop-loss, take-profit, paper trading.

Elke sub-agent implementeert:
- naam: str
- kapitaal_euro: float
- _genereer_signalen(markt_data) -> list[TradeSignaal]
- _mag_handelen(symbool, markt_data) -> bool
"""

import logging
import math
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Optional
from agent.risk.risk_manager import TradeSignaal
from agent.learning.memory import Trade

log = logging.getLogger(__name__)

MAX_POSITIES_PER_AGENT: int = 3
MAX_POSITIES_TOTAAL: int = 15


class BaseAgent(ABC):
    """
    Abstracte basisklasse. Sub-agents erven hiervan.

    Gedeelde regels (hard, niet overschrijfbaar):
    1. Max 1 open positie per symbool
    2. Min 4 uur cooldown per symbool (standaard, overschrijfbaar via cooldown_uren)
    3. Force exit bij 75% drawdown op eigen kapitaalpool
    4. Stop-loss max 8% (hard ceiling, zelfs als strategie lager zit)
    5. Paper trading zolang paper_trading=True in config
    """

    naam: str = "base"
    cooldown_uren: int = 4

    def __init__(self, config: dict, executor, geheugen):
        self.config = config
        self.executor = executor
        self.geheugen = geheugen

        self.open_posities: dict[str, Trade] = {}
        self.laatste_trade_per_symbool: dict[str, datetime] = {}
        self.kapitaal_pool: float = self._initieel_kapitaal()
        self.piek_kapitaal: float = self.kapitaal_pool
        self.dagelijkse_trades: list[Trade] = []
        log.info(
            f"[{self.naam.upper()} AGENT] Gestart | "
            f"Kapitaal: €{self.kapitaal_pool:.0f} | "
            f"Cooldown: {self.cooldown_uren}u"
        )

    def _initieel_kapitaal(self) -> float:
        """Sub-agents overschrijven dit om hun eigen pool te zetten."""
        return float(self.config['kapitaal']['start'])

    def _cooldown_voorbij(self, symbool: str) -> bool:
        """
        Check cooldown persistent vanuit database.
        Werkt correct na Docker herstart.
        In-memory cache als fallback voor dezelfde sessie.
        """
        # DB-check (primair, persistent)
        if self.geheugen.cooldown_actief(symbool, self.naam, self.cooldown_uren):
            return False
        return True

    def _heeft_open_positie(self, symbool: str) -> bool:
        if any(p.symbool == symbool for p in self.open_posities.values()):
            return True
        return self.geheugen.heeft_open_positie_db(symbool)

    def _drawdown_ok(self) -> bool:
        """Force exit bij 75% drawdown op eigen pool."""
        if self.piek_kapitaal <= 0:
            return False
        drawdown = 1 - (self.kapitaal_pool / self.piek_kapitaal)
        if drawdown >= 0.75:
            log.warning(
                f"[{self.naam}] FORCE EXIT: drawdown {drawdown:.0%} >= 75%. "
                f"Agent stopt met handelen."
            )
            return False
        return True

    def _clamp_stop_loss(self, stop_loss_pct: float) -> float:
        """Hard ceiling: stop-loss nooit meer dan 8%."""
        return min(stop_loss_pct, 0.08)

    @staticmethod
    def _is_polymarket_strategie(strategie_type: str) -> bool:
        """Herken strategieen waarvoor geen stop-loss mag worden geforceerd."""
        return (strategie_type or '').startswith('polymarket_')

    def _persisted_thresholds(self, positie: Trade) -> tuple[Optional[float], Optional[float], bool]:
        """Lees persisted stop-loss/take-profit zonder defaults te verzinnen."""
        strategie_type = getattr(positie, 'strategie_type', '')
        is_polymarket = self._is_polymarket_strategie(strategie_type)

        raw_stop = getattr(positie, 'stop_loss_pct', None)
        raw_take = getattr(positie, 'take_profit_pct', None)

        stop = None if raw_stop is None else self._clamp_stop_loss(float(raw_stop))
        take = None if raw_take is None else float(raw_take)

        if take is None:
            return stop, take, False
        if stop is None and not is_polymarket:
            return stop, take, False
        return stop, take, True

    async def run_cyclus(self, markt_data: dict, regime: dict, sentiment, bot_patronen):
        """
        Wordt elke minuut aangeroepen door de orchestrator.
        1. Check drawdown
        2. Genereer signalen
        3. Valideer en voer uit
        4. Monitor posities
        """
        if not self._drawdown_ok():
            await self._sluit_alle_posities(markt_data)
            return

        if self.geheugen.tel_open_posities() >= MAX_POSITIES_TOTAAL:
            log.warning(f"[{self.naam}] Globale positielimiet ({MAX_POSITIES_TOTAAL}) bereikt.")
            await self._monitor_posities(markt_data, regime)
            return

        try:
            signalen = await self._genereer_signalen(
                markt_data=markt_data,
                regime=regime,
                sentiment=sentiment,
                bot_patronen=bot_patronen
            )

            for signaal in signalen:
                if len(self.open_posities) >= MAX_POSITIES_PER_AGENT:
                    log.debug(f"[{self.naam}] Per-agent limiet ({MAX_POSITIES_PER_AGENT}) bereikt.")
                    break

                if self._heeft_open_positie(signaal.symbool):
                    log.debug(f"[{self.naam}] Skip {signaal.symbool}: al open positie")
                    continue

                if not self._cooldown_voorbij(signaal.symbool):
                    log.debug(f"[{self.naam}] Skip {signaal.symbool}: cooldown actief")
                    continue

                if not await self._mag_handelen(signaal.symbool, markt_data):
                    continue

                # Bayesiaans updaten van win_kans
                signaal.win_kans = self._bayesiaanse_win_kans(signaal.win_kans)

                # Hard ceiling stop-loss
                signaal.stop_loss_pct = self._clamp_stop_loss(signaal.stop_loss_pct)

                # Kapitaalcheck: genoeg om te handelen?
                max_bedrag = self.kapitaal_pool * self.config['kapitaal']['max_positie_grootte']
                if max_bedrag < 10:
                    log.warning(f"[{self.naam}] Te weinig kapitaal: €{self.kapitaal_pool:.2f}")
                    continue

                trade = await self.executor.voer_uit(signaal, markt_data=markt_data, max_bedrag=max_bedrag)
                if trade:
                    self.open_posities[trade.id] = trade
                    self.dagelijkse_trades.append(trade)
                    self.geheugen.sla_trade_op(trade)
                    self.laatste_trade_per_symbool[signaal.symbool] = datetime.now()
                    self.geheugen.sla_cooldown_op(signaal.symbool, self.naam, self.cooldown_uren)
                    self.kapitaal_pool -= trade.euro_bedrag
                    self.piek_kapitaal = max(self.piek_kapitaal, self.kapitaal_pool)
                    log.info(f"[{self.naam}] Trade: {trade.samenvatting()}")

        except Exception as e:
            log.error(f"[{self.naam}] Fout in run_cyclus: {e}", exc_info=True)

        await self._monitor_posities(markt_data, regime)

    async def _monitor_posities(self, markt_data: dict, regime: dict):
        """Controleer stop-loss en take-profit voor alle open posities."""
        te_sluiten = []

        for positie_id, positie in self.open_posities.items():
            data = markt_data.get(positie.symbool, {})
            huidige_prijs = data.get('prijs')
            if not huidige_prijs:
                continue

            try:
                pnl_pct = float(positie.bereken_pnl_pct(huidige_prijs))
            except (TypeError, ValueError):
                pnl_pct = 0.0

            try:
                stop, take, thresholds_ok = self._persisted_thresholds(positie)
            except (TypeError, ValueError):
                stop, take, thresholds_ok = None, None, False

            if not thresholds_ok:
                log.error(
                    f"[{self.naam}] Ontbrekende persisted exit-waarden voor "
                    f"{positie.symbool} ({getattr(positie, 'strategie_type', 'onbekend')}). "
                    "Positie wordt defensief gesloten."
                )
                te_sluiten.append((positie_id, huidige_prijs))
                continue

            if stop is not None and pnl_pct <= -stop:
                log.info(f"[{self.naam}] Stop-loss: {positie.symbool} {pnl_pct:.1%}")
                te_sluiten.append((positie_id, huidige_prijs))
            elif pnl_pct >= take:
                log.info(f"[{self.naam}] Take-profit: {positie.symbool} {pnl_pct:.1%}")
                te_sluiten.append((positie_id, huidige_prijs))
            elif self._moet_sluiten_strategie(positie, huidige_prijs, regime):
                te_sluiten.append((positie_id, huidige_prijs))

        for positie_id, prijs in te_sluiten:
            resultaat = await self.executor.sluit_positie(positie_id, prijs)
            if resultaat:
                self.geheugen.sla_resultaat_op(resultaat)
                self.kapitaal_pool += resultaat.euro_bedrag + (resultaat.pnl or 0)
                self.piek_kapitaal = max(self.piek_kapitaal, self.kapitaal_pool)
                del self.open_posities[positie_id]

    async def _sluit_alle_posities(self, markt_data: dict):
        """Force-sluit alle posities bij drawdown limiet."""
        for positie_id, positie in list(self.open_posities.items()):
            prijs = markt_data.get(positie.symbool, {}).get('prijs')
            if prijs:
                resultaat = await self.executor.sluit_positie(positie_id, prijs)
                if resultaat:
                    self.geheugen.sla_resultaat_op(resultaat)
                    self.kapitaal_pool += resultaat.euro_bedrag + (resultaat.pnl or 0)
                    del self.open_posities[positie_id]

    def prestatie_stats(self) -> dict:
        """Geef statistieken terug voor self_improver en dashboard."""
        trades = [t for t in self.dagelijkse_trades if t.pnl is not None]
        if not trades:
            return {
                'naam': self.naam,
                'totaal_trades': 0,
                'win_rate': 0,
                'gem_pnl_pct': 0,
                'kapitaal_pool': self.kapitaal_pool,
                'drawdown': 0,
            }
        winst = [t for t in trades if t.pnl > 0]
        win_rate = len(winst) / len(trades)
        gem_pnl = sum(t.pnl_pct for t in trades if t.pnl_pct) / len(trades)
        drawdown = 1 - (self.kapitaal_pool / self.piek_kapitaal) if self.piek_kapitaal > 0 else 0

        return {
            'naam': self.naam,
            'totaal_trades': len(trades),
            'win_rate': win_rate,
            'gem_pnl_pct': gem_pnl,
            'kapitaal_pool': self.kapitaal_pool,
            'drawdown': drawdown,
        }


    def _bayesiaanse_win_kans(self, prior: float) -> float:
        """
        Bayesiaans geüpdatete win-kans via Beta-Binomiaal model.

        Prior: Beta(α₀, β₀) afgeleid van het signaal zelf.
          α₀ = prior * PRIOR_STERKTE
          β₀ = (1 - prior) * PRIOR_STERKTE
        Likelihood: historische trades van deze agent (DB).
        Posterior mean = (α₀ + wins) / (α₀ + β₀ + wins + losses)

        Resultaat: gewogen blend van prior en posterior.
        """
        PRIOR_STERKTE = 10  # Effectieve steekproefomvang van het signaal

        prestaties = self.geheugen.analyseer_prestaties()
        agent_stats = prestaties.get("per_strategie", {}).get(self.naam, {})
        totaal = agent_stats.get("totaal_trades", 0)
        wins   = round(agent_stats.get("win_rate", 0) * totaal)
        losses = totaal - wins

        alpha_0 = prior * PRIOR_STERKTE
        beta_0  = (1.0 - prior) * PRIOR_STERKTE

        posterior = (alpha_0 + wins) / (alpha_0 + beta_0 + wins + losses)

        # Blend: bij weinig data vertrouwen we meer op de prior
        gewicht_posterior = min(1.0, totaal / 20.0)
        geblendt = prior * (1 - gewicht_posterior) + posterior * gewicht_posterior

        return round(min(max(geblendt, 0.01), 0.99), 4)

    # ── Abstracte methodes ───────────────────────────────────────────────

    @abstractmethod
    async def _genereer_signalen(
        self,
        markt_data: dict,
        regime: dict,
        sentiment,
        bot_patronen
    ) -> list[TradeSignaal]:
        """Geef lijst van trade-signalen terug."""
        ...

    async def _mag_handelen(self, symbool: str, markt_data: dict) -> bool:
        """Hook: sub-agents kunnen extra condities toevoegen (bv. markttijden)."""
        return True

    def _moet_sluiten_strategie(self, positie, huidige_prijs: float, regime: dict) -> bool:
        """Hook: strategie-specifieke exit logica."""
        return False
