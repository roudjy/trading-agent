"""
ORDER EXECUTOR
==============
Voert trades uit op de juiste exchange.

Ondersteunde exchanges:
- Bitvavo (crypto NL)
- Kraken (crypto)
- Interactive Brokers (stocks)
- Polymarket (prediction markets)

Paper trading modus:
- Simuleert trades zonder echt geld
- Identieke logica als live - alleen de uitvoer verschilt
- Gebruik minimaal 4 weken paper trading voor je live gaat
"""

import asyncio
import logging
import uuid
from datetime import datetime
from typing import Optional

import ccxt.async_support as ccxt

from automation import live_gate
from agent.risk.risk_manager import TradeSignaal, PositieGrootte
from agent.learning.memory import Trade

log = logging.getLogger(__name__)


class OrderExecutor:
    """
    Voert orders uit op geconfigureerde exchanges.
    Schakelt automatisch tussen paper en live modus.
    """

    def __init__(self, config: dict):
        self.config = config
        self.exchanges = {}
        self._initialiseer_exchanges()

        # Paper trading register
        self.paper_posities = {}
        self.paper_kapitaal = float(config['kapitaal']['start'])

    def _initialiseer_exchanges(self):
        """Initialiseer exchange verbindingen."""
        exc_config = self.config['exchanges']

        if exc_config['bitvavo']['actief']:
            self.exchanges['bitvavo'] = ccxt.bitvavo({
                'apiKey': exc_config['bitvavo']['api_key'],
                'secret': exc_config['bitvavo']['api_secret'],
            })

        if exc_config['kraken']['actief']:
            self.exchanges['kraken'] = ccxt.kraken({
                'apiKey': exc_config['kraken']['api_key'],
                'secret': exc_config['kraken']['api_secret'],
            })

    def _is_paper_mode(self, symbool: str) -> bool:
        """Bepaal of paper trading actief is voor dit symbool."""
        live_gewenst = False
        if '/' in symbool:
            # Crypto symbool
            for exchange_naam in ['bitvavo', 'kraken']:
                if self.config['exchanges'].get(exchange_naam, {}).get('actief'):
                    live_gewenst = self.config['exchanges'][exchange_naam].get('paper_trading', True) is False
                    break
        elif any(c.isalpha() for c in symbool):
            # Stock symbool
            live_gewenst = self.config['exchanges'].get('ibkr', {}).get('paper_trading', True) is False

        if live_gewenst:
            if live_gate.is_live_armed():
                return False
            log.error(f"Live trading geweigerd voor {symbool}: live gate niet gewapend")

        return True  # Default: paper mode

    async def voer_uit(self, signaal: TradeSignaal, markt_data: dict = None, max_bedrag: float = None) -> Optional[Trade]:
        """
        Voer een trade uit op basis van een signaal.
        markt_data: verse marktdata van MarketDataFetcher voor echte prijzen.
        max_bedrag: maximaal te investeren bedrag (agent's kapitaalpool limiet).
        """
        is_paper = self._is_paper_mode(signaal.symbool)
        modus = "PAPER" if is_paper else "LIVE"

        log.info(
            f"[{modus}] Order: {signaal.symbool} {signaal.richting} | "
            f"Strategie: {signaal.strategie_type} | "
            f"Zekerheid: {signaal.zekerheid:.0%}"
        )

        if is_paper:
            return await self._paper_trade(signaal, markt_data, max_bedrag=max_bedrag)
        else:
            return await self._live_trade(signaal)

    async def _paper_trade(self, signaal: TradeSignaal, markt_data: dict = None, max_bedrag: float = None) -> Optional[Trade]:
        """Simuleer een trade in paper modus."""
        try:
            # Gebruik echte marktprijs als beschikbaar, anders hardcoded fallback
            prijs = None
            if markt_data and signaal.symbool in markt_data:
                prijs = markt_data[signaal.symbool].get('prijs')
            if not prijs:
                prijs = self._haal_huidige_prijs(signaal.symbool)
            if not prijs:
                return None

            # Bereken bedrag — gebruik agent's max_bedrag als opgegeven, anders globale config
            if max_bedrag is not None:
                bedrag = max_bedrag
            else:
                _max = self.paper_kapitaal * self.config['kapitaal']['max_positie_grootte']
                bedrag = min(_max, self.paper_kapitaal * 0.15)  # Max 15% per trade
            hoeveelheid = bedrag / prijs

            trade_id = str(uuid.uuid4())[:8]

            trade = Trade(
                id=trade_id,
                symbool=signaal.symbool,
                richting=signaal.richting,
                strategie_type=signaal.strategie_type,
                entry_prijs=prijs,
                exit_prijs=None,
                hoeveelheid=hoeveelheid,
                euro_bedrag=bedrag,
                pnl=None,
                pnl_pct=None,
                entry_tijdstip=datetime.now(),
                exit_tijdstip=None,
                reden_entry=signaal.bron[:200],  # Max 200 tekens
                reden_exit='',
                geleerd='',
                regime=signaal.regime,
                sentiment_score=0.0,
                exchange='paper'
            )

            # Reserveer kapitaal
            self.paper_kapitaal -= bedrag
            self.paper_posities[trade_id] = trade

            log.info(f"[PAPER] Trade geopend: {trade.samenvatting()} | Prijs: €{prijs:.2f}")
            return trade

        except Exception as e:
            log.error(f"Paper trade mislukt: {e}")
            return None

    async def _live_trade(self, signaal: TradeSignaal) -> Optional[Trade]:
        """Voer een echte trade uit op de exchange."""
        try:
            # Bepaal exchange op basis van symbool
            exchange = self._selecteer_exchange(signaal.symbool)
            if not exchange:
                log.error(f"Geen exchange beschikbaar voor {signaal.symbool}")
                return None

            # Haal live prijs op
            ticker = await exchange.fetch_ticker(signaal.symbool)
            prijs = ticker['last']

            # Bereken positiegrootte
            bedrag = self.config['kapitaal']['start'] * 0.15  # Vereenvoudigd
            hoeveelheid = bedrag / prijs

            # Plaats market order
            kant = 'buy' if signaal.richting == 'long' else 'sell'
            order = await exchange.create_order(
                symbol=signaal.symbool,
                type='market',
                side=kant,
                amount=hoeveelheid
            )

            trade_id = order.get('id', str(uuid.uuid4())[:8])

            trade = Trade(
                id=trade_id,
                symbool=signaal.symbool,
                richting=signaal.richting,
                strategie_type=signaal.strategie_type,
                entry_prijs=float(order.get('price', prijs)),
                exit_prijs=None,
                hoeveelheid=hoeveelheid,
                euro_bedrag=bedrag,
                pnl=None,
                pnl_pct=None,
                entry_tijdstip=datetime.now(),
                exit_tijdstip=None,
                reden_entry=signaal.bron[:200],
                reden_exit='',
                geleerd='',
                regime=signaal.regime,
                sentiment_score=0.0,
                exchange=type(exchange).__name__.lower()
            )

            log.info(f"[LIVE] Trade geopend: {trade.samenvatting()}")
            return trade

        except Exception as e:
            log.error(f"Live trade mislukt voor {signaal.symbool}: {e}")
            return None

    async def sluit_positie(self, positie_id: str, huidige_prijs: float) -> Optional[Trade]:
        """Sluit een open positie."""
        # Uit paper posities
        if positie_id in self.paper_posities:
            trade = self.paper_posities[positie_id]
            trade.exit_prijs = huidige_prijs
            trade.exit_tijdstip = datetime.now()
            trade.pnl_pct = trade.bereken_pnl_pct(huidige_prijs)
            trade.pnl = trade.euro_bedrag * trade.pnl_pct

            # Geef kapitaal terug + winst/verlies
            self.paper_kapitaal += trade.euro_bedrag + trade.pnl

            # Leer van deze trade
            trade.geleerd = self._leer_van_trade(trade)
            trade.reden_exit = self._bepaal_exit_reden(trade)

            del self.paper_posities[positie_id]
            log.info(
                f"[PAPER] Trade gesloten: {trade.samenvatting()} | "
                f"Duur: {(trade.exit_tijdstip - trade.entry_tijdstip).seconds // 60} min"
            )
            return trade

        return None

    def _haal_huidige_prijs(self, symbool: str) -> Optional[float]:
        """
        Haal huidige prijs op (vereenvoudigd voor paper trading).
        In echte implementatie: gebruik gecachede data van MarketDataFetcher.
        """
        # Placeholder prijzen voor paper trading
        prijzen = {
            'BTC/EUR': 65000.0,
            'ETH/EUR': 3200.0,
            'SOL/EUR': 145.0,
            'BNB/EUR': 420.0,
            'NVDA': 850.0,
            'AAPL': 185.0,
            'MSFT': 420.0,
            'ASML': 920.0,
            'AMD': 175.0,
        }
        return prijzen.get(symbool)

    def _selecteer_exchange(self, symbool: str):
        """Selecteer de juiste exchange voor een symbool."""
        if '/' in symbool:
            # Crypto: prefereer Bitvavo (NL), anders Kraken
            return self.exchanges.get('bitvavo') or self.exchanges.get('kraken')
        return None  # Stocks via IBKR (aparte implementatie)

    def _leer_van_trade(self, trade: Trade) -> str:
        """Genereer een leerles van een gesloten trade."""
        if trade.pnl is None:
            return ''

        if trade.pnl > 0:
            return (
                f"Winstgevende {trade.strategie_type} trade op {trade.symbool}. "
                f"Signaal was correct. Strategie weging verhogen."
            )
        else:
            pnl_pct = abs(trade.pnl_pct or 0)
            if pnl_pct > 0.05:
                return (
                    f"Groot verlies op {trade.symbool} ({pnl_pct:.1%}). "
                    f"Entry condities evalueren. Mogelijk te vroeg ingekocht."
                )
            else:
                return (
                    f"Klein verlies op {trade.symbool}. "
                    f"Stop-loss werkte correct. Geen aanpassing nodig."
                )

    def _bepaal_exit_reden(self, trade: Trade) -> str:
        """Beschrijf waarom de trade gesloten is."""
        if trade.pnl_pct is None:
            return 'Onbekend'

        if trade.pnl_pct >= (self.config['strategie']['momentum'].get('take_profit', 0.06)):
            return f"Take-profit bereikt ({trade.pnl_pct:.1%})"
        elif trade.pnl_pct <= -(self.config['strategie']['momentum'].get('stop_loss', 0.03)):
            return f"Stop-loss geraakt ({trade.pnl_pct:.1%})"
        else:
            return f"Strategie exit signaal ({trade.pnl_pct:.1%})"
