"""
POLYMARKET STRATEGIE
====================
Handelt op Polymarket prediction markets.

Drie sub-strategieën:
1. Kansschatting met Claude AI: analyse van marktjaar
2. Adversarial: liquiditeit bieden aan arbitrage bots
3. Informatievoorsprong: nieuws verwerken voor de markt

Polymarket werkt in USDC op Polygon blockchain.
Alle transacties zijn on-chain.
"""

import logging
from typing import Optional, List
from datetime import datetime

log = logging.getLogger(__name__)


class PolymarketStrategie:
    """Strategie voor Polymarket prediction markets."""

    def __init__(self, config: dict):
        self.config = config
        self.poly_config = config['assets']['polymarket']
        self.gewicht = 1.0

        # Minimum markt liquiditeit (USDC)
        self.min_liquiditeit = self.poly_config.get('min_liquiditeit', 1000)
        # Max blootstelling per markt
        self.max_blootstelling = self.poly_config.get('max_markt_blootstelling', 0.05)

    def moet_sluiten(self, positie, huidige_prijs: float, regime: dict) -> bool:
        """Bepaal of een Polymarket positie gesloten moet worden."""
        if positie.strategie_type != 'polymarket':
            return False

        pnl_pct = positie.bereken_pnl_pct(huidige_prijs)

        # Stop-loss: -8% (Polymarket is binair, meer ruimte nodig)
        if pnl_pct <= -0.08:
            return True

        # Take-profit: +15% (Polymarket kan grote moves maken)
        if pnl_pct >= 0.15:
            return True

        # Sluit als markt bijna expireert (> 90% kans richting)
        if huidige_prijs > 0.92 or huidige_prijs < 0.08:
            return True

        return False

    def beoordeel_markt(self, markt: dict) -> Optional[dict]:
        """
        Beoordeel of een Polymarket markt handelsbaar is.

        Args:
            markt: Polymarket markt data

        Returns:
            dict met aanbeveling of None als niet interessant
        """
        # Controleer minimale liquiditeit
        if markt.get('liquiditeit', 0) < self.min_liquiditeit:
            return None

        # Controleer of markt nog niet te dicht bij expiry is
        # (Binnen 1 uur voor expiry: te riskant)
        if markt.get('uren_tot_expiry', 24) < 1:
            return None

        # Kijk of er een kans-mismatch is (onze schatting vs marktprijs)
        markt_prijs = markt.get('ja_prijs', 0.5)
        onze_schatting = markt.get('ai_schatting', 0.5)

        verschil = abs(onze_schatting - markt_prijs)

        if verschil < 0.08:  # Minder dan 8% verschil: niet de moeite
            return None

        richting = 'long' if onze_schatting > markt_prijs else 'short'

        return {
            'markt_id': markt.get('id'),
            'richting': richting,
            'markt_prijs': markt_prijs,
            'onze_schatting': onze_schatting,
            'verwacht_rendement': verschil,
            'uitleg': (
                f"Marktprijs: {markt_prijs:.0%}, "
                f"AI schatting: {onze_schatting:.0%}, "
                f"Edge: {verschil:.0%}"
            )
        }

    def pas_parameters_aan(self, prestatie: dict):
        """Pas strategie parameters aan."""
        self.gewicht = max(0.3, min(2.0,
            self.gewicht + prestatie.get('gewicht_aanpassing', 0)
        ))
