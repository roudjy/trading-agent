"""
BOT EXPLOITER AGENT
===================
Kapitaal: €200
Assets: Polymarket prediction markets
Logica: Detecteer bot-patronen via BotDetector, trade tegenover of mee
Geen stop-loss (binaire markten: 0 of 1)
Exit: wanneer kans ≥ 0.90 of ≤ 0.10
Cooldown: 2 uur per markt
"""

import logging
from agent.agents.base_agent import BaseAgent
from agent.risk.risk_manager import TradeSignaal

log = logging.getLogger(__name__)


class BotAgent(BaseAgent):
    """Exploiteert bot-patronen op Polymarket."""

    naam = "bot"
    cooldown_uren = 2

    def _initieel_kapitaal(self) -> float:
        return 200.0

    def _clamp_stop_loss(self, stop_loss_pct: float) -> float:
        """Polymarket: binaire markten, geen stop-loss."""
        return 1.0  # Nooit stop-loss triggeren

    async def _genereer_signalen(self, markt_data, regime, sentiment, bot_patronen):
        signalen = []

        if not bot_patronen:
            return signalen

        for patroon in bot_patronen:
            # patroon heeft: symbool, richting, confidence, reden
            symbool = getattr(patroon, 'symbool', None)
            confidence = getattr(patroon, 'confidence', 0)
            richting = getattr(patroon, 'richting', None)
            reden = getattr(patroon, 'reden', 'bot_patroon')

            if not symbool or not richting:
                continue

            min_confidence = self.config.get('strategie', {}).get('adversarial', {}).get(
                'min_bot_confidence', 0.75
            )
            if confidence < min_confidence:
                continue

            signaal = TradeSignaal(
                symbool=symbool,
                richting=richting,
                strategie_type='bot_exploiter',
                verwacht_rendement=0.15,
                win_kans=confidence,
                stop_loss_pct=1.0,       # Geen stop-loss
                take_profit_pct=0.50,    # Exit bij 50% winst
                bron=f"bot_patroon: {reden}",
                zekerheid=confidence,
                regime='polymarket'
            )
            signalen.append(signaal)
            log.debug(f"[BOT] Signaal: {symbool} {richting} confidence={confidence:.0%}")

        return signalen

    def _moet_sluiten_strategie(self, positie, huidige_prijs, regime):
        """
        Polymarket: sluit als kans erg hoog of laag is.
        huidige_prijs is de USDC kans (0-1).
        """
        if positie.richting == 'long' and huidige_prijs >= 0.90:
            log.info(f"[BOT] Exit long: kans {huidige_prijs:.0%} >= 90%")
            return True
        if positie.richting == 'short' and huidige_prijs <= 0.10:
            log.info(f"[BOT] Exit short: kans {huidige_prijs:.0%} <= 10%")
            return True
        return False
