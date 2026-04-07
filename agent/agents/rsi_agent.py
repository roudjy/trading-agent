"""
RSI MEAN REVERSION AGENT
========================
Kapitaal: €300
Assets: 8 crypto paren (BTC/EUR, ETH/EUR, SOL/EUR, BNB/EUR, ADA/EUR, DOT/EUR, AVAX/EUR, MATIC/EUR)
Logica: RSI(14) op 1-uur kaarsen
  - RSI < 28 → LONG (oversold)
  - RSI > 72 → SHORT (overbought)
Cooldown: 4 uur per symbool
Stop-loss: 5%
Take-profit: 8%
"""

import logging
from agent.agents.base_agent import BaseAgent
from agent.risk.risk_manager import TradeSignaal
from agent.brain.regime_detector import Regime

log = logging.getLogger(__name__)

CRYPTO_SYMBOLEN = [
    'BTC/EUR', 'ETH/EUR', 'SOL/EUR', 'BNB/EUR',
    'ADA/EUR', 'DOT/EUR', 'AVAX/EUR', 'MATIC/EUR'
]


class RSIAgent(BaseAgent):
    """Mean reversion agent op basis van RSI oversold/overbought."""

    naam = "rsi"
    cooldown_uren = 4

    def _initieel_kapitaal(self) -> float:
        return 300.0

    async def _genereer_signalen(self, markt_data, regime, sentiment, bot_patronen):
        signalen = []

        for symbool in CRYPTO_SYMBOLEN:
            data = markt_data.get(symbool)
            if not data:
                continue

            indicatoren = data.get('indicatoren', {})
            rsi = indicatoren.get('rsi')
            if rsi is None:
                continue

            symbool_regime = regime.get(symbool)
            regime_type = symbool_regime.regime if symbool_regime else None

            # Geen trades in crisis regime
            if regime_type == Regime.CRISIS:
                continue

            richting = None
            reden = None

            if rsi < 28:
                richting = 'long'
                reden = f"RSI oversold: {rsi:.1f} < 28"
            elif rsi > 72:
                richting = 'short'
                reden = f"RSI overbought: {rsi:.1f} > 72"

            if not richting:
                continue

            # Zekerheid: hoe extremer RSI, hoe zekerder
            if richting == 'long':
                zekerheid = min(1.0, (28 - rsi) / 10 + 0.6)
            else:
                zekerheid = min(1.0, (rsi - 72) / 10 + 0.6)

            signaal = TradeSignaal(
                symbool=symbool,
                richting=richting,
                strategie_type='rsi_mean_reversion',
                verwacht_rendement=0.08,
                win_kans=zekerheid,
                stop_loss_pct=0.05,
                take_profit_pct=0.08,
                bron=reden,
                zekerheid=zekerheid,
                regime=regime_type.value if regime_type else 'onbekend'
            )
            signalen.append(signaal)
            log.debug(f"[RSI] Signaal: {symbool} {richting} (RSI={rsi:.1f})")

        return signalen

    def _moet_sluiten_strategie(self, positie, huidige_prijs, regime):
        """Sluit als RSI terugkeert naar neutraal (wordt bijgehouden via take/stop)."""
        return False
