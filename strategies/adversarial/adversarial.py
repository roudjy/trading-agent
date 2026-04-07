"""
ADVERSARIAL STRATEGIE
=====================
Exploiteert het voorspelbare gedrag van andere bots.

Dit is onze geheime wapen: terwijl andere bots blindeling
hun algoritme uitvoeren, leren wij hun patronen kennen
en positioneren we ons vóór hun verwachte actie.

Voorbeelden:
1. Polymarket arbitrage bots kopen altijd bij opening
   → Wij bieden liquiditeit op hun target prijs
   → Zij kopen van ons, wij pakken de spread

2. Crypto grid bots kopen op vaste levels
   → Wij kopen net erboven als support
   → Grid bot ondersteunt de prijs, wij profiteren

3. MEV bots front-runnen grote orders
   → Wij detecteren grote orders vroeg
   → Wij positioneren ons vóór de MEV bot

De agent leert continu nieuwe bot-patronen herkennen.
"""

import logging
from typing import List, Optional
from data.botdetection.detector import BotPatroon

log = logging.getLogger(__name__)


class AdversarialStrategie:
    """Exploiteert bot-gedrag voor winst."""

    def __init__(self, config: dict):
        self.config = config
        self.adv_config = config['strategie']['adversarial']
        self.gewicht = 1.0

        # Bijgehouden bot patronen en hun winstgevendheid
        self.patroon_prestaties = {}

    def moet_sluiten(self, positie, huidige_prijs: float, regime: dict) -> bool:
        """Adversarial posities hebben korte doorlooptijd."""
        if positie.strategie_type != 'adversarial':
            return False

        pnl_pct = positie.bereken_pnl_pct(huidige_prijs)

        # Snelle exit: adversarial trades zijn kort
        if pnl_pct <= -0.02:  # -2% stop (strak)
            return True
        if pnl_pct >= 0.03:   # +3% target (snel pakken)
            return True

        # Tijdslimiet: adversarial trades sluiten na 30 minuten
        from datetime import datetime
        if positie.entry_tijdstip:
            doorlooptijd = (datetime.now() - positie.entry_tijdstip).seconds
            if doorlooptijd > 1800:  # 30 minuten
                return True

        return False

    def genereer_counter_strategie(self, patroon: BotPatroon) -> Optional[dict]:
        """
        Genereer een counter-strategie voor een herkend bot-patroon.
        """
        if patroon.kans_op_winst < self.adv_config['min_bot_confidence']:
            return None

        if patroon.patroon_type == 'open_markt_arbitrage':
            return self._counter_arbitrage_bot(patroon)
        elif patroon.patroon_type == 'grid_bot':
            return self._counter_grid_bot(patroon)
        elif patroon.patroon_type == 'scalping_bot':
            return self._counter_scalping_bot(patroon)

        return None

    def _counter_arbitrage_bot(self, patroon: BotPatroon) -> dict:
        """
        Counter voor Polymarket arbitrage bots.
        Bot koopt beide kanten bij opening → wij bieden liquiditeit.
        """
        return {
            'actie': 'bied_liquiditeit',
            'timing': 'voor_markt_opening',
            'prijs_niveau': 0.47,  # Net boven bot target van 0.46
            'verwachte_winst_per_contract': 0.01,
            'uitleg': (
                "Arbitrage bot koopt bij opening op ~$0.46. "
                "Wij plaatsen sell order op $0.47. "
                "Bot koopt van ons → wij verdienen $0.01 per contract."
            )
        }

    def _counter_grid_bot(self, patroon: BotPatroon) -> dict:
        """
        Counter voor crypto grid bots.
        Grid bot koopt op vaste levels → wij kopen net erboven.
        """
        return {
            'actie': 'koop_net_boven_support',
            'timing': 'bij_nadering_grid_level',
            'stop_loss_pct': 0.015,  # 1.5% stop (grid bot support)
            'take_profit_pct': 0.025,  # 2.5% target
            'uitleg': (
                "Grid bot ondersteunt prijs op ~€" +
                str(patroon.markt) +
                ". Wij kopen net erboven met grid bot als stop."
            )
        }

    def _counter_scalping_bot(self, patroon: BotPatroon) -> dict:
        """Counter voor scalping bots."""
        return {
            'actie': 'vermijd_markt',
            'uitleg': "Scalping bot actief - spread te hoog, vermijden."
        }

    def registreer_resultaat(self, patroon_type: str, winstgevend: bool):
        """Registreer resultaat van een adversarial trade voor leren."""
        if patroon_type not in self.patroon_prestaties:
            self.patroon_prestaties[patroon_type] = {'wins': 0, 'losses': 0}

        if winstgevend:
            self.patroon_prestaties[patroon_type]['wins'] += 1
        else:
            self.patroon_prestaties[patroon_type]['losses'] += 1

        # Log win rate per patroon
        prestatie = self.patroon_prestaties[patroon_type]
        totaal = prestatie['wins'] + prestatie['losses']
        win_rate = prestatie['wins'] / totaal if totaal > 0 else 0
        log.info(f"Adversarial {patroon_type} win rate: {win_rate:.0%} ({totaal} trades)")

    def pas_parameters_aan(self, prestatie: dict):
        """Pas strategie parameters aan."""
        self.gewicht = max(0.3, min(2.0,
            self.gewicht + prestatie.get('gewicht_aanpassing', 0)
        ))
