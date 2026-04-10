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
- Identieke logica als live; alleen de uitvoer verschilt
- Gebruik minimaal 4 weken paper trading voor je live gaat
"""

import logging
import uuid
from datetime import UTC, datetime
from typing import Optional

import ccxt.async_support as ccxt

from automation import live_gate
from agent.learning.memory import Trade
from agent.risk.risk_manager import TradeSignaal
from execution.paper.polymarket_sim import (
    MaxEntryPriceExceededError,
    NoLiquidityError,
    PolymarketPaperBroker,
)
from execution.protocols import BrokerProtocol, LiveGateClosedError, OrderIntent

log = logging.getLogger(__name__)


class PriceUnavailableError(RuntimeError):
    """Raised when no real market price is available for execution."""


class OrderExecutor:
    """
    Voert orders uit op geconfigureerde exchanges.
    Schakelt automatisch tussen paper en live modus.
    """

    def __init__(self, config: dict, polymarket_broker: Optional[BrokerProtocol] = None):
        self.config = config
        self.exchanges = {}
        self._initialiseer_exchanges()
        self.polymarket_broker = polymarket_broker or PolymarketPaperBroker()

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
            for exchange_naam in ['bitvavo', 'kraken']:
                if self.config['exchanges'].get(exchange_naam, {}).get('actief'):
                    live_gewenst = self.config['exchanges'][exchange_naam].get('paper_trading', True) is False
                    break
        elif any(c.isalpha() for c in symbool):
            live_gewenst = self.config['exchanges'].get('ibkr', {}).get('paper_trading', True) is False

        if live_gewenst:
            if live_gate.is_live_armed():
                return False
            log.error(f"Live trading geweigerd voor {symbool}: live gate niet gewapend")

        return True

    async def voer_uit(
        self,
        signaal: TradeSignaal,
        markt_data: dict = None,
        max_bedrag: float = None,
    ) -> Optional[Trade]:
        """
        Voer een trade uit op basis van een signaal.
        markt_data: verse marktdata van MarketDataFetcher voor echte prijzen.
        max_bedrag: maximaal te investeren bedrag (agent-kapitaalpool limiet).
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
        return await self._live_trade(signaal)

    async def _paper_trade(
        self,
        signaal: TradeSignaal,
        markt_data: dict = None,
        max_bedrag: float = None,
    ) -> Optional[Trade]:
        """Simuleer een trade in paper modus."""
        try:
            if self._is_polymarket_signaal(signaal):
                return self._paper_trade_polymarket(signaal, markt_data, max_bedrag)

            prijs = None
            if markt_data and signaal.symbool in markt_data:
                prijs = markt_data[signaal.symbool].get('prijs')
            if not prijs:
                prijs = self._haal_huidige_prijs(signaal.symbool)

            if max_bedrag is not None:
                bedrag = max_bedrag
            else:
                maximaal = self.paper_kapitaal * self.config['kapitaal']['max_positie_grootte']
                bedrag = min(maximaal, self.paper_kapitaal * 0.15)
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
                reden_entry=signaal.bron[:200],
                reden_exit='',
                geleerd='',
                regime=signaal.regime,
                sentiment_score=0.0,
                exchange='paper',
                stop_loss_pct=signaal.stop_loss_pct,
                take_profit_pct=signaal.take_profit_pct,
            )

            self.paper_kapitaal -= bedrag
            self.paper_posities[trade_id] = trade

            log.info(f"[PAPER] Trade geopend: {trade.samenvatting()} | Prijs: EUR {prijs:.2f}")
            return trade
        except (NoLiquidityError, MaxEntryPriceExceededError, LiveGateClosedError) as e:
            log.warning(f"[PAPER] Geen Polymarket trade geopend voor {signaal.symbool}: {e}")
            return None
        except PriceUnavailableError as e:
            log.error(f"Geen prijs beschikbaar voor {signaal.symbool}: {e}")
            return None
        except Exception as e:
            log.error(f"Paper trade mislukt: {e}")
            return None

    def _paper_trade_polymarket(
        self,
        signaal: TradeSignaal,
        markt_data: dict = None,
        max_bedrag: float = None,
    ) -> Optional[Trade]:
        snapshot = self._haal_polymarket_snapshot(signaal, markt_data)
        reference_price = self._polymarket_reference_price(signaal, snapshot)

        if max_bedrag is not None:
            bedrag = max_bedrag
        else:
            maximaal = self.paper_kapitaal * self.config['kapitaal']['max_positie_grootte']
            bedrag = min(maximaal, self.paper_kapitaal * 0.15)

        intent = OrderIntent(
            instrument_id=signaal.symbool,
            side='buy' if signaal.richting == 'long' else 'sell',
            size=bedrag / reference_price,
            limit_price=None,
            venue='polymarket',
            client_tag=signaal.strategie_type,
        )
        fill = self.polymarket_broker.place_paper_order(intent, snapshot)
        bedrag = fill.fill_price * fill.size

        trade_id = str(uuid.uuid4())[:8]
        trade = Trade(
            id=trade_id,
            symbool=signaal.symbool,
            richting=signaal.richting,
            strategie_type=signaal.strategie_type,
            entry_prijs=fill.fill_price,
            exit_prijs=None,
            hoeveelheid=fill.size,
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
            exchange='paper',
            stop_loss_pct=signaal.stop_loss_pct,
            take_profit_pct=signaal.take_profit_pct,
            slippage_bps=fill.slippage_bps,
        )

        self.paper_kapitaal -= bedrag
        self.paper_posities[trade_id] = trade

        log.info(
            f"[PAPER] Polymarket trade geopend: {trade.samenvatting()} | "
            f"Fill: {fill.fill_price:.4f} | Slippage: {fill.slippage_bps:.4f} bps"
        )
        log.info(
            f"[PAPER] Polymarket fee: {fill.fee_amount:.4f} {fill.fee_ccy} | "
            f"Intent: {intent.size:.4f} | Fill size: {fill.size:.4f}"
        )
        return trade

    async def _live_trade(self, signaal: TradeSignaal) -> Optional[Trade]:
        """Voer een echte trade uit op de exchange."""
        try:
            exchange = self._selecteer_exchange(signaal.symbool)
            if not exchange:
                log.error(f"Geen exchange beschikbaar voor {signaal.symbool}")
                return None

            ticker = await exchange.fetch_ticker(signaal.symbool)
            prijs = ticker['last']

            bedrag = self.config['kapitaal']['start'] * 0.15
            hoeveelheid = bedrag / prijs

            kant = 'buy' if signaal.richting == 'long' else 'sell'
            order = await exchange.create_order(
                symbol=signaal.symbool,
                type='market',
                side=kant,
                amount=hoeveelheid,
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
                exchange=type(exchange).__name__.lower(),
                stop_loss_pct=signaal.stop_loss_pct,
                take_profit_pct=signaal.take_profit_pct,
            )

            log.info(f"[LIVE] Trade geopend: {trade.samenvatting()}")
            return trade
        except Exception as e:
            log.error(f"Live trade mislukt voor {signaal.symbool}: {e}")
            return None

    async def sluit_positie(self, positie_id: str, huidige_prijs: float) -> Optional[Trade]:
        """Sluit een open positie."""
        if positie_id in self.paper_posities:
            trade = self.paper_posities[positie_id]
            trade.exit_prijs = huidige_prijs
            trade.exit_tijdstip = datetime.now()
            trade.pnl_pct = trade.bereken_pnl_pct(huidige_prijs)
            trade.pnl = trade.euro_bedrag * trade.pnl_pct

            self.paper_kapitaal += trade.euro_bedrag + trade.pnl
            trade.geleerd = self._leer_van_trade(trade)
            trade.reden_exit = self._bepaal_exit_reden(trade)

            del self.paper_posities[positie_id]
            log.info(
                f"[PAPER] Trade gesloten: {trade.samenvatting()} | "
                f"Duur: {(trade.exit_tijdstip - trade.entry_tijdstip).seconds // 60} min"
            )
            return trade

        return None

    def _haal_huidige_prijs(self, symbool: str) -> float:
        """
        Haal huidige prijs op vanuit bestaande realtime bronnen.
        Als er geen echte prijs beschikbaar is, moet de trade worden overgeslagen.
        """
        raise PriceUnavailableError(f"Geen realtime prijsbron beschikbaar voor {symbool}")

    @staticmethod
    def _is_polymarket_signaal(signaal: TradeSignaal) -> bool:
        strategie_type = (signaal.strategie_type or '').lower()
        return signaal.regime == 'polymarket' or strategie_type.startswith('polymarket_') or strategie_type in {
            'data_arbitrage',
            'bot_exploiter',
        }

    def _haal_polymarket_snapshot(self, signaal: TradeSignaal, markt_data: dict | None) -> dict:
        if not markt_data or signaal.symbool not in markt_data:
            raise PriceUnavailableError(f"Geen Polymarket markt_data beschikbaar voor {signaal.symbool}")

        data = dict(markt_data[signaal.symbool] or {})
        prijs = data.get('prijs')
        if prijs in (None, 0):
            raise PriceUnavailableError(f"Geen Polymarket prijs beschikbaar voor {signaal.symbool}")

        timestamp_utc = data.get('timestamp_utc') or datetime(1970, 1, 1, tzinfo=UTC)
        grootte = float(data.get('volume') or data.get('beschikbare_size') or 1.0)
        return {
            'market_id': data.get('market_id', signaal.symbool),
            'yes_bids': data.get('yes_bids') or [(prijs, grootte)],
            'yes_asks': data.get('yes_asks') or [(prijs, grootte)],
            'no_bids': data.get('no_bids') or [],
            'no_asks': data.get('no_asks') or [],
            'timestamp_utc': timestamp_utc,
            'book_side': data.get('book_side', 'yes'),
        }

    @staticmethod
    def _polymarket_reference_price(signaal: TradeSignaal, snapshot: dict) -> float:
        if signaal.richting == 'long':
            levels = snapshot.get('yes_asks') or snapshot.get('no_asks') or []
        else:
            levels = snapshot.get('yes_bids') or snapshot.get('no_bids') or []
        if not levels:
            raise NoLiquidityError(f"Geen Polymarket boekniveau beschikbaar voor {signaal.symbool}")
        return float(levels[0][0])

    def _selecteer_exchange(self, symbool: str):
        """Selecteer de juiste exchange voor een symbool."""
        if '/' in symbool:
            return self.exchanges.get('bitvavo') or self.exchanges.get('kraken')
        return None

    def _leer_van_trade(self, trade: Trade) -> str:
        """Genereer een leerles van een gesloten trade."""
        if trade.pnl is None:
            return ''

        if trade.pnl > 0:
            return (
                f"Winstgevende {trade.strategie_type} trade op {trade.symbool}. "
                f"Signaal was correct. Strategie weging verhogen."
            )

        pnl_pct = abs(trade.pnl_pct or 0)
        if pnl_pct > 0.05:
            return (
                f"Groot verlies op {trade.symbool} ({pnl_pct:.1%}). "
                f"Entry condities evalueren. Mogelijk te vroeg ingekocht."
            )
        return (
            f"Klein verlies op {trade.symbool}. "
            f"Stop-loss werkte correct. Geen aanpassing nodig."
        )

    def _bepaal_exit_reden(self, trade: Trade) -> str:
        """Beschrijf waarom de trade gesloten is."""
        if trade.pnl_pct is None:
            return 'Onbekend'

        if trade.pnl_pct >= self.config['strategie']['momentum'].get('take_profit', 0.06):
            return f"Take-profit bereikt ({trade.pnl_pct:.1%})"
        if trade.pnl_pct <= -self.config['strategie']['momentum'].get('stop_loss', 0.03):
            return f"Stop-loss geraakt ({trade.pnl_pct:.1%})"
        return f"Strategie exit signaal ({trade.pnl_pct:.1%})"
