"""
TRADING AGENT - HOOFD BREIN
===========================
Dit is het hart van het systeem. De agent:
1. Observeert continu markten, sentiment, en andere bots
2. Detecteert het marktregime (trending / zijwaarts / volatiel)
3. Kiest de juiste strategie per asset class
4. Voert trades uit via de juiste exchange
5. Leert van elke fout en past zichzelf aan
6. Schrijft dagelijks een Nederlandstalig rapport

Jij hoeft dit bestand NOOIT aan te passen.
Alles configureer je via config/config.yaml
"""

import asyncio
import logging
import yaml
from datetime import datetime
from pathlib import Path

# Interne modules
from agent.brain.regime_detector import RegimeDetector
from agent.brain.signal_aggregator import SignalAggregator
from agent.risk.risk_manager import RiskManager
from agent.execution.order_executor import OrderExecutor
from agent.learning.memory import AgentMemory
from agent.learning.reporter import DagelijksRapport
from agent.learning.self_improver import ZelfVerbeteraar
from data.market.fetcher import MarketDataFetcher
from data.sentiment.scraper import SentimentScraper
from data.botdetection.detector import BotDetector
from data.news.nieuws_fetcher import NieuwsFetcher
from strategies.momentum.momentum import MomentumStrategie
from strategies.meanreversion.mean_reversion import MeanReversionStrategie
from strategies.polymarket.polymarket import PolymarketStrategie
from strategies.adversarial.adversarial import AdversarialStrategie

# Logging instellen - alles wordt opgeslagen voor het dagrapport
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    handlers=[
        logging.FileHandler('logs/agent.log'),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)


class TradingAgent:
    """
    De autonome trading agent.
    Start met agent.start() en hij doet de rest.
    """

    def __init__(self, config_pad: str = "config/config.yaml"):
        # Laad configuratie
        with open(config_pad) as f:
            self.config = yaml.safe_load(f)

        log.info(f"Agent gestart: {self.config['agent']['naam']}")
        log.info(f"Startkapitaal: €{self.config['kapitaal']['start']}")
        log.info(f"Doel: €{self.config['doel']['maandinkomen']}/maand netto")

        # Initialiseer alle componenten
        self.geheugen = AgentMemory(self.config)
        self.markt_data = MarketDataFetcher(self.config)
        self.sentiment = SentimentScraper(self.config)
        self.bot_detector = BotDetector(self.config)
        self.nieuws = NieuwsFetcher(self.config)
        self.regime_detector = RegimeDetector(self.config)
        self.signaal_aggregator = SignalAggregator(self.config)
        self.risico = RiskManager(self.config, self.geheugen)
        self.executor = OrderExecutor(self.config)
        self.rapport = DagelijksRapport(self.config, self.geheugen)
        self.zelf_verbeteraar = ZelfVerbeteraar(self.config)

        # Strategieën
        self.strategieen = {
            'momentum': MomentumStrategie(self.config),
            'mean_reversion': MeanReversionStrategie(self.config),
            'polymarket': PolymarketStrategie(self.config),
            'adversarial': AdversarialStrategie(self.config)
        }

        # Status bijhouden
        self.actief = True
        self.huidig_regime = {}
        self.open_posities = {}
        self.dagelijkse_trades = []
        self.laatste_zelfverbetering: str = ""  # Opgeslagen voor dagrapport
        # Cooldown: bijhouden wanneer per symbool voor het laatst een trade is geopend
        self.laatste_trade_per_symbool: dict = {}
        self.cooldown_seconden: int = 4 * 3600  # 4 uur tussen trades per symbool

    async def start(self):
        """Start de agent - draait voor altijd tot gestopt."""
        log.info("Agent gestart. Druk Ctrl+C om te stoppen.")

        # Start alle achtergrond taken parallel
        await asyncio.gather(
            self._hoofd_loop(),
            self._sentiment_loop(),
            self._bot_detectie_loop(),
            self._nieuws_loop(),
            self._dagrapport_loop(),
            self._leer_loop(),
            self._zelfverbetering_loop()
        )

    async def _hoofd_loop(self):
        """
        Hoofdlus: elke minuut markten analyseren en handelen.
        Dit is de core trading cyclus.
        """
        while self.actief:
            try:
                if Path("logs/agent_pause.flag").exists():
                    log.info("Agent gepauzeerd via dashboard. Wacht 30s.")
                    await asyncio.sleep(30)
                    continue
                # Stap 1: Verse marktdata ophalen
                markt_data = await self.markt_data.haal_alles_op()

                # Stap 2: Detecteer marktregime per asset class
                self.huidig_regime = await self.regime_detector.detecteer(markt_data)

                # Stap 3: Genereer signalen vanuit alle bronnen
                signalen = await self.signaal_aggregator.aggregeer(
                    markt_data=markt_data,
                    regime=self.huidig_regime,
                    sentiment=self.sentiment.huidig_sentiment,
                    bot_patronen=self.bot_detector.herkende_patronen,
                    nieuws=self.nieuws.laatste_nieuws,
                    geheugen=self.geheugen
                )

                # Stap 4: Risicobeoordeling - mag de agent handelen?
                for signaal in signalen:
                    # Check 1: Zit er al een open positie voor dit symbool?
                    if any(p.symbool == signaal.symbool for p in self.open_posities.values()):
                        log.debug(f"Overgeslagen: al open positie voor {signaal.symbool}")
                        continue

                    # Check 2: Cooldown — minimaal 4 uur tussen trades per symbool
                    laatste = self.laatste_trade_per_symbool.get(signaal.symbool)
                    if laatste:
                        verstreken = (datetime.now() - laatste).total_seconds()
                        if verstreken < self.cooldown_seconden:
                            resterende = int((self.cooldown_seconden - verstreken) / 60)
                            log.debug(f"Cooldown {signaal.symbool}: nog {resterende}m wachten")
                            continue

                    goedgekeurd, reden = self.risico.beoordeel(signaal, self.open_posities)

                    if goedgekeurd:
                        # Stap 5: Voer trade uit met echte marktprijs
                        trade = await self.executor.voer_uit(signaal, markt_data=markt_data)
                        if trade:
                            self.open_posities[trade.id] = trade
                            self.dagelijkse_trades.append(trade)
                            self.geheugen.sla_trade_op(trade)
                            self.laatste_trade_per_symbool[signaal.symbool] = datetime.now()
                            log.info(f"Trade uitgevoerd: {trade.samenvatting()}")
                    else:
                        log.debug(f"Trade geblokkeerd door risico: {reden}")

                # Stap 6: Monitor open posities - exit als doel bereikt of stop-loss
                await self._monitor_posities(markt_data)

            except Exception as e:
                log.error(f"Fout in hoofdlus: {e}", exc_info=True)
                # Agent stopt NIET bij een fout - hij logt en gaat door

            # Wacht 60 seconden voor volgende cyclus
            await asyncio.sleep(60)

    async def _monitor_posities(self, markt_data: dict):
        """
        Controleer alle open posities.
        Sluit als target bereikt of stop-loss geraakt.
        """
        te_sluiten = []

        for positie_id, positie in self.open_posities.items():
            huidige_prijs = markt_data.get(positie.symbool, {}).get('prijs')
            if not huidige_prijs:
                continue

            pnl_pct = positie.bereken_pnl_pct(huidige_prijs)

            # Exit condities op basis van strategie-advies
            strategie = self.strategieen.get(positie.strategie_type)
            if strategie and strategie.moet_sluiten(positie, huidige_prijs, self.huidig_regime):
                te_sluiten.append((positie_id, huidige_prijs, pnl_pct))

        # Sluit posities
        for positie_id, prijs, pnl in te_sluiten:
            trade_resultaat = await self.executor.sluit_positie(positie_id, prijs)
            if trade_resultaat:
                self.geheugen.sla_resultaat_op(trade_resultaat)
                del self.open_posities[positie_id]

                if pnl > 0:
                    log.info(f"Positie gesloten met WINST: {pnl:.1%} | {trade_resultaat.reden_exit}")
                else:
                    log.info(f"Positie gesloten met VERLIES: {pnl:.1%} | {trade_resultaat.reden_exit}")

        # Controleer totale drawdown
        totaal_verlies = self.risico.bereken_totale_drawdown()
        if totaal_verlies >= self.config['kapitaal']['drawdown_limiet']:
            log.warning(f"DRAWDOWN LIMIET BEREIKT: {totaal_verlies:.1%} - Agent pauzeert")
            self.actief = False
            await self.rapport.schrijf_noodrapport(totaal_verlies)

    async def _sentiment_loop(self):
        """Elke 5-15 minuten sentiment updaten van Reddit, X, etc."""
        while self.actief:
            try:
                await self.sentiment.update()
                log.debug(f"Sentiment bijgewerkt: {self.sentiment.samenvatting()}")
            except Exception as e:
                log.error(f"Sentiment fout: {e}")
            await asyncio.sleep(300)  # Elke 5 minuten

    async def _bot_detectie_loop(self):
        """Continu andere bots in de markt observeren en patronen herkennen."""
        while self.actief:
            try:
                patronen = await self.bot_detector.scan()
                if patronen:
                    log.info(f"Bot-patronen gedetecteerd: {len(patronen)} | "
                             f"Adversarial kansen: {self.bot_detector.kansen_samenvatting()}")
            except Exception as e:
                log.error(f"Bot detectie fout: {e}")
            await asyncio.sleep(60)  # Elke minuut

    async def _nieuws_loop(self):
        """Elke 10 minuten nieuws ophalen en analyseren."""
        while self.actief:
            try:
                await self.nieuws.update()
                impactvolle_items = self.nieuws.hoog_impact_nieuws()
                if impactvolle_items:
                    log.info(f"Hoog-impact nieuws: {[n.titel for n in impactvolle_items]}")
            except Exception as e:
                log.error(f"Nieuws fout: {e}")
            await asyncio.sleep(600)  # Elke 10 minuten

    async def _dagrapport_loop(self):
        """Elke ochtend om 07:00 NL tijd een rapport schrijven."""
        while self.actief:
            nu = datetime.now()
            rapport_tijd = self.config['agent']['rapport_tijd']
            uur, minuut = map(int, rapport_tijd.split(':'))

            # Bereken seconden tot volgende 07:00
            doel = nu.replace(hour=uur, minute=minuut, second=0, microsecond=0)
            if nu >= doel:
                # Al voorbij 07:00 vandaag - plan voor morgen
                from datetime import timedelta
                doel = doel + timedelta(days=1)

            wacht_seconden = (doel - nu).total_seconds()
            await asyncio.sleep(wacht_seconden)

            try:
                rapport_pad = await self.rapport.schrijf_dagrapport(self.dagelijkse_trades)
                # Voeg zelfverbeteringsblok toe als er een is
                if self.laatste_zelfverbetering and rapport_pad:
                    try:
                        with open(rapport_pad, 'a', encoding='utf-8') as f:
                            f.write(self.laatste_zelfverbetering)
                        self.laatste_zelfverbetering = ""
                    except Exception:
                        pass
                self.dagelijkse_trades = []  # Reset dagelijkse trades
                log.info("Dagrapport geschreven")
            except Exception as e:
                log.error(f"Rapport fout: {e}")

    async def _zelfverbetering_loop(self):
        """
        Elke zondag om 06:00: analyseer de week en pas parameters aan.
        Resultaat wordt toegevoegd aan het eerstvolgende dagrapport.
        """
        from datetime import timedelta
        while self.actief:
            nu = datetime.now()
            # Bereken seconden tot volgende zondag 06:00
            dagen_tot_zondag = (6 - nu.weekday()) % 7  # 6 = zondag
            doel = nu.replace(hour=6, minute=0, second=0, microsecond=0)
            doel += timedelta(days=dagen_tot_zondag)
            if doel <= nu:
                doel += timedelta(days=7)

            wacht_seconden = (doel - nu).total_seconds()
            log.info(f"Zelfverbetering gepland op {doel.strftime('%Y-%m-%d %H:%M')}")
            await asyncio.sleep(wacht_seconden)

            try:
                samenvatting = await self.zelf_verbeteraar.verbeter()
                if samenvatting:
                    self.laatste_zelfverbetering = samenvatting
                    log.info("Zelfverbeteringsresultaten opgeslagen voor dagrapport")
            except Exception as e:
                log.error(f"Zelfverbetering fout: {e}", exc_info=True)

    async def _leer_loop(self):
        """
        Elke 24 uur: analyseer prestaties en pas strategie aan.
        Dit is hoe de agent beter wordt over tijd.
        """
        while self.actief:
            await asyncio.sleep(86400)  # Wacht 24 uur
            try:
                inzichten = self.geheugen.analyseer_prestaties()
                log.info(f"Leermoment: {inzichten['samenvatting']}")

                # Pas strategie gewichten aan op basis van wat werkt
                for strategie_naam, prestatie in inzichten['per_strategie'].items():
                    if strategie_naam in self.strategieen:
                        self.strategieen[strategie_naam].pas_parameters_aan(prestatie)

                # Pas sentiment bronnen aan
                self.sentiment.pas_weging_aan(inzichten['sentiment_effectiviteit'])

                log.info("Strategie parameters bijgewerkt op basis van leeranalyse")
            except Exception as e:
                log.error(f"Leer-loop fout: {e}")


# Start de agent
if __name__ == "__main__":
    agent = TradingAgent()
    asyncio.run(agent.start())
