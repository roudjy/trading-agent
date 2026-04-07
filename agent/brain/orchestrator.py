"""
ORCHESTRATOR
============
Beheert alle 4 sub-agents en coördineert:
- Kapitaalverdeling (RSI €300, EMA €300, Bot €200, Sentiment €100, Reserve €100)
- Elke minuut: run alle agents parallel
- Dagelijks om 23:00: herbalanceer kapitaal op basis van prestaties
- Drawdown monitoring: agent-level en portfolio-level
- Dagrapport delegeren aan DagelijksRapport
"""

import asyncio
import logging
import math
from datetime import datetime, timedelta
from pathlib import Path

from agent.agents.base_agent import MAX_POSITIES_TOTAAL
from agent.agents.rsi_agent import RSIAgent
from agent.agents.ema_agent import EMAAgent
from agent.agents.bot_agent import BotAgent
from agent.agents.sentiment_agent import SentimentAgent
from agent.agents.data_arbitrage_agent import DataArbitrageAgent
from agent.brain.analyst import ClaudeAnalyst
from agent.execution.order_executor import OrderExecutor
from agent.learning.memory import AgentMemory
from agent.learning.reporter import DagelijksRapport
from agent.learning.self_improver import ZelfVerbeteraar
from agent.risk.risk_manager import RiskManager
from agent.brain.regime_detector import RegimeDetector
from agent.brain.signal_aggregator import SignalAggregator
from data.market.fetcher import MarketDataFetcher
from data.sentiment.scraper import SentimentScraper
from data.botdetection.detector import BotDetector
from data.news.nieuws_fetcher import NieuwsFetcher

log = logging.getLogger(__name__)

# Doelkapitaal per agent
KAPITAAL_VERDELING = {
    'rsi': 300.0,
    'ema': 300.0,
    'bot': 200.0,
    'sentiment': 100.0,
    'data_arbitrage': 100.0,
}
RESERVE = 0.0  # Volledig geïnvesteerd via 5 sub-agents


class Orchestrator:
    """
    Centrale dirigent van alle sub-agents.
    Vervangt de oude TradingAgent._hoofd_loop volledig.
    """

    def __init__(self, config: dict):
        self.config = config
        self.actief = True
        self.laatste_zelfverbetering: str = ""

        # Gedeelde componenten
        self.geheugen = AgentMemory(config)
        self.markt_data = MarketDataFetcher(config)
        self.sentiment = SentimentScraper(config)
        self.bot_detector = BotDetector(config)
        self.nieuws = NieuwsFetcher(config)
        self.regime_detector = RegimeDetector(config)
        self.signaal_aggregator = SignalAggregator(config)
        self.risico = RiskManager(config, self.geheugen)
        self.rapport = DagelijksRapport(config, self.geheugen)
        self.zelf_verbeteraar = ZelfVerbeteraar(config)
        self.analyst = ClaudeAnalyst(config)

        # Sub-agents: elk krijgt eigen executor instantie
        self.agents = {
            'rsi':           RSIAgent(config, OrderExecutor(config), self.geheugen),
            'ema':           EMAAgent(config, OrderExecutor(config), self.geheugen),
            'bot':           BotAgent(config, OrderExecutor(config), self.geheugen),
            'sentiment':     SentimentAgent(config, OrderExecutor(config), self.geheugen),
            'data_arbitrage': DataArbitrageAgent(config, OrderExecutor(config), self.geheugen),
        }

    async def start(self):
        """Start alle loops parallel."""
        log.info("=" * 50)
        log.info("ORCHESTRATOR GESTART")
        log.info(f"  Sub-agents: {list(self.agents.keys())}")
        log.info(f"  Kapitaal RSI:            €{self.agents['rsi'].kapitaal_pool:.0f}")
        log.info(f"  Kapitaal EMA:            €{self.agents['ema'].kapitaal_pool:.0f}")
        log.info(f"  Kapitaal Bot:            €{self.agents['bot'].kapitaal_pool:.0f}")
        log.info(f"  Kapitaal Sentiment:      €{self.agents['sentiment'].kapitaal_pool:.0f}")
        log.info(f"  Kapitaal DataArbitrage:  €{self.agents['data_arbitrage'].kapitaal_pool:.0f}")
        log.info("=" * 50)
        log.info(f"Kapitaalverdeling: RSI €{KAPITAAL_VERDELING['rsi']}, "
                 f"EMA €{KAPITAAL_VERDELING['ema']}, "
                 f"Bot €{KAPITAAL_VERDELING['bot']}, "
                 f"Sentiment €{KAPITAAL_VERDELING['sentiment']}, "
                 f"Reserve €{RESERVE}")

        await asyncio.gather(
            self._hoofd_loop(),
            self._sentiment_loop(),
            self._bot_detectie_loop(),
            self._nieuws_loop(),
            self._dagrapport_loop(),
            self._herbalanceer_loop(),
            self._leer_loop(),
            self._zelfverbetering_loop(),
            self._analyst_evaluatie_loop(),
            self._canary_loop(),
        )

    async def _hoofd_loop(self):
        """Elke minuut: haal marktdata op en draai alle agents."""
        while self.actief:
            try:
                if Path("logs/agent_pause.flag").exists():
                    log.info("Agent gepauzeerd via dashboard. Wacht 30s.")
                    await asyncio.sleep(30)
                    continue

                log.info("Cyclus start: marktdata ophalen...")
                # Verse marktdata
                markt_data = await asyncio.wait_for(
                    self.markt_data.haal_alles_op(),
                    timeout=60.0
                )
                log.info(f"Marktdata opgehaald: {len(markt_data)} symbolen")
                regime = await self.regime_detector.detecteer(markt_data)

                # Run alle sub-agents parallel
                await asyncio.gather(*[
                    agent.run_cyclus(
                        markt_data=markt_data,
                        regime=regime,
                        sentiment=self.sentiment,
                        bot_patronen=self.bot_detector.herkende_patronen
                    )
                    for agent in self.agents.values()
                ])

                # Portfolio drawdown check
                totaal_verlies = self.risico.bereken_totale_drawdown()
                if totaal_verlies >= self.config['kapitaal']['drawdown_limiet']:
                    log.warning(f"PORTFOLIO DRAWDOWN LIMIET: {totaal_verlies:.1%} - alles stoppen")
                    self.actief = False
                    await self.rapport.schrijf_noodrapport(totaal_verlies)

            except asyncio.TimeoutError:
                log.error("Marktdata fetch timeout (60s) — cyclus overgeslagen")
            except Exception as e:
                log.error(f"Fout in orchestrator hoofd_loop: {e}", exc_info=True)

            await asyncio.sleep(60)

    async def _analyst_evaluatie_loop(self):
        """Elke dag om 23:00: Sonnet evalueert alle trades van de dag."""
        while self.actief:
            nu = datetime.now()
            doel = nu.replace(hour=23, minute=0, second=0, microsecond=0)
            if nu >= doel:
                doel += timedelta(days=1)
            await asyncio.sleep((doel - nu).total_seconds())

            try:
                alle_trades = []
                for agent in self.agents.values():
                    alle_trades.extend(agent.dagelijkse_trades)

                if alle_trades:
                    await self.analyst.dagelijkse_evaluatie(alle_trades)
            except Exception as e:
                log.error(f"Analyst evaluatie fout: {e}")

    async def _canary_loop(self):
        """Dagelijks om 08:00: health check van het volledige systeem."""
        while self.actief:
            nu = datetime.now()
            doel = nu.replace(hour=8, minute=0, second=0, microsecond=0)
            if nu >= doel:
                doel += timedelta(days=1)
            await asyncio.sleep((doel - nu).total_seconds())

            await self._canary_check()

    async def _canary_check(self):
        """Voer health check uit en schrijf naar logs/canary.log."""
        import sqlite3 as _sqlite3
        from pathlib import Path as _Path

        fouten = []
        waarschuwingen = []
        resultaten = {}

        # 1. Marktdata bereikbaar?
        try:
            markt_data = await asyncio.wait_for(
                self.markt_data.haal_alles_op(), timeout=30.0
            )
            resultaten['markt_symbolen'] = len(markt_data)
            if len(markt_data) < 3:
                waarschuwingen.append(f"Weinig marktdata: {len(markt_data)} symbolen")
        except Exception as e:
            fouten.append(f"Marktdata FAIL: {e}")
            resultaten['markt_symbolen'] = 0

        # 2. Database schrijfbaar?
        try:
            db_pad = _Path("logs/agent_geheugen.db")
            if not db_pad.exists():
                fouten.append("Database ontbreekt")
            else:
                conn = _sqlite3.connect(str(db_pad), timeout=5)
                conn.execute("SELECT COUNT(*) FROM trades").fetchone()
                conn.close()
                resultaten['db'] = 'ok'
        except Exception as e:
            fouten.append(f"Database FAIL: {e}")

        # 3. Open posities vs limiet
        try:
            open_count = self.geheugen.tel_open_posities()
            resultaten['open_posities'] = open_count
            if open_count >= 12:
                waarschuwingen.append(f"Open posities hoog: {open_count}/{MAX_POSITIES_TOTAAL}")
        except Exception as e:
            waarschuwingen.append(f"Positietelling FAIL: {e}")

        # 4. Agents actief?
        actieve_agents = [naam for naam, agent in self.agents.items()
                          if agent.kapitaal_pool > 0]
        resultaten['actieve_agents'] = len(actieve_agents)
        if len(actieve_agents) < 3:
            fouten.append(f"Weinig actieve agents: {actieve_agents}")

        # 5. Pause flag actief?
        if _Path("logs/agent_pause.flag").exists():
            waarschuwingen.append("Agent is gepauzeerd via dashboard")

        # Schrijf naar canary.log
        status = "FAIL" if fouten else ("WARN" if waarschuwingen else "OK")
        regels = [
            f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] CANARY {status}",
            f"  Markt: {resultaten.get('markt_symbolen',0)} symbolen",
            f"  DB: {resultaten.get('db','?')}",
            f"  Agents: {resultaten.get('actieve_agents',0)}/5 actief",
            f"  Open posities: {resultaten.get('open_posities',0)}",
        ]
        for f_msg in fouten:
            regels.append(f"  FOUT: {f_msg}")
        for w_msg in waarschuwingen:
            regels.append(f"  WARN: {w_msg}")

        log_regel = "\n".join(regels) + "\n"
        try:
            with open("logs/canary.log", "a") as f:
                f.write(log_regel)
        except Exception:
            pass

        if fouten:
            log.error(f"CANARY FAIL — {len(fouten)} fouten: {fouten}")
        elif waarschuwingen:
            log.warning(f"CANARY WARN — {waarschuwingen}")
        else:
            log.info(f"CANARY OK — {resultaten}")


    async def _herbalanceer_kapitaal(self):
        """
        UCB1 kapitaalverdeling op basis van agent prestaties.
        Score = gem_rendement + sqrt(2 * ln(totaal_trades) / agent_trades)
        Agents met weinig data krijgen exploration bonus.
        Min €30, max €400 per agent.
        """
        MIN_KAPITAAL = 30.0
        MAX_KAPITAAL = 400.0

        stats = {naam: agent.prestatie_stats() for naam, agent in self.agents.items()}
        totaal_beschikbaar = sum(KAPITAAL_VERDELING.values())

        totaal_trades = sum(s['totaal_trades'] for s in stats.values())
        if totaal_trades == 0:
            totaal_trades = 1  # Vermijd ln(0)

        scores = {}
        for naam, stat in stats.items():
            agent_trades = stat['totaal_trades']
            gem_rendement = stat.get('gem_pnl_pct', 0) or 0

            if agent_trades >= 5:
                # UCB1: exploitatie + exploratie bonus
                exploratie = math.sqrt(2 * math.log(totaal_trades) / agent_trades)
                scores[naam] = gem_rendement + exploratie
            else:
                # Te weinig data: maximale exploration bonus
                scores[naam] = gem_rendement + math.sqrt(2 * math.log(max(totaal_trades, 1)))

        # Normaliseer scores naar positief domein
        min_score = min(scores.values())
        if min_score < 0:
            scores = {k: v - min_score + 0.01 for k, v in scores.items()}

        totaal_score = sum(scores.values()) or 1
        for naam, score in scores.items():
            nieuw_kapitaal = round((score / totaal_score) * totaal_beschikbaar, 0)
            nieuw_kapitaal = max(MIN_KAPITAAL, min(MAX_KAPITAAL, nieuw_kapitaal))
            oud_kapitaal = self.agents[naam].kapitaal_pool
            if abs(nieuw_kapitaal - oud_kapitaal) > 10:
                log.info(
                    f"UCB1 herbalanceer {naam}: €{oud_kapitaal:.0f} → €{nieuw_kapitaal:.0f} "                    f"(score={score:.3f})"                )
                self.agents[naam].kapitaal_pool = nieuw_kapitaal

    async def _sentiment_loop(self):
        while self.actief:
            try:
                await self.sentiment.update()
            except Exception as e:
                log.error(f"Sentiment fout: {e}")
            await asyncio.sleep(300)

    async def _bot_detectie_loop(self):
        while self.actief:
            try:
                await self.bot_detector.scan()
            except Exception as e:
                log.error(f"Bot detectie fout: {e}")
            await asyncio.sleep(60)

    async def _nieuws_loop(self):
        while self.actief:
            try:
                await self.nieuws.update()
            except Exception as e:
                log.error(f"Nieuws fout: {e}")
            await asyncio.sleep(600)

    async def _dagrapport_loop(self):
        while self.actief:
            nu = datetime.now()
            rapport_tijd = self.config['agent']['rapport_tijd']
            uur, minuut = map(int, rapport_tijd.split(':'))
            doel = nu.replace(hour=uur, minute=minuut, second=0, microsecond=0)
            if nu >= doel:
                doel += timedelta(days=1)
            await asyncio.sleep((doel - nu).total_seconds())

            try:
                alle_trades = []
                for agent in self.agents.values():
                    alle_trades.extend(agent.dagelijkse_trades)

                rapport_pad = await self.rapport.schrijf_dagrapport(alle_trades)
                if self.laatste_zelfverbetering and rapport_pad:
                    try:
                        with open(rapport_pad, 'a', encoding='utf-8') as f:
                            f.write(self.laatste_zelfverbetering)
                        self.laatste_zelfverbetering = ""
                    except Exception:
                        pass

                # Reset dagelijkse trades
                for agent in self.agents.values():
                    agent.dagelijkse_trades = []

                log.info("Dagrapport geschreven")

            except Exception as e:
                log.error(f"Rapport fout: {e}")

    async def _herbalanceer_loop(self):
        """Dagelijks om 06:00: UCB1 kapitaalverdeling."""
        while self.actief:
            nu = datetime.now()
            doel = nu.replace(hour=6, minute=0, second=0, microsecond=0)
            if nu >= doel:
                doel += timedelta(days=1)
            await asyncio.sleep((doel - nu).total_seconds())
            try:
                await self._herbalanceer_kapitaal()
                log.info("UCB1 herbalancering voltooid (06:00)")
            except Exception as e:
                log.error(f"Herbalanceer fout: {e}", exc_info=True)

    async def _leer_loop(self):
        while self.actief:
            await asyncio.sleep(86400)
            try:
                inzichten = self.geheugen.analyseer_prestaties()
                log.info(f"Leermoment: {inzichten.get('samenvatting', 'geen data')}")
            except Exception as e:
                log.error(f"Leer-loop fout: {e}")

    async def _zelfverbetering_loop(self):
        while self.actief:
            nu = datetime.now()
            dagen_tot_zondag = (6 - nu.weekday()) % 7
            doel = nu.replace(hour=6, minute=0, second=0, microsecond=0)
            doel += timedelta(days=dagen_tot_zondag)
            if doel <= nu:
                doel += timedelta(days=7)

            log.info(f"Zelfverbetering gepland op {doel.strftime('%Y-%m-%d %H:%M')}")
            await asyncio.sleep((doel - nu).total_seconds())

            try:
                samenvatting = await self.zelf_verbeteraar.verbeter(agent_stats={
                    naam: agent.prestatie_stats() for naam, agent in self.agents.items()
                })
                if samenvatting:
                    self.laatste_zelfverbetering = samenvatting
            except Exception as e:
                log.error(f"Zelfverbetering fout: {e}", exc_info=True)

    def alle_open_posities(self) -> dict:
        """Combineer open posities van alle agents voor dashboard."""
        posities = {}
        for agent in self.agents.values():
            posities.update(agent.open_posities)
        return posities

    def agent_stats(self) -> list[dict]:
        """Statistieken van alle sub-agents voor dashboard."""
        return [agent.prestatie_stats() for agent in self.agents.values()]
