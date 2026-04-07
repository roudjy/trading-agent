"""
SENTIMENT AGENT
===============
Kapitaal: €100
Assets: BTC/EUR, ETH/EUR (crypto met hoog sentiment-effect)
Logica:
  - Sentiment > 0.75 → LONG
  - Sentiment < -0.75 → SHORT
  - RSI bevestiging: RSI tussen 35-65 (niet al overbought/oversold)
  - Max 1 open positie tegelijk
Cooldown: 6 uur
Stop-loss: 4%
Take-profit: 6%
"""

import logging
from agent.agents.base_agent import BaseAgent
from agent.risk.risk_manager import TradeSignaal
from agent.brain.regime_detector import Regime

log = logging.getLogger(__name__)

SENTIMENT_SYMBOLEN = ['BTC/EUR', 'ETH/EUR']
MAX_POSITIES = 1


class SentimentAgent(BaseAgent):
    """Handelt op extreme sentiment signalen met RSI-bevestiging."""

    naam = "sentiment"
    cooldown_uren = 6

    def _initieel_kapitaal(self) -> float:
        return 100.0

    async def _genereer_signalen(self, markt_data, regime, sentiment, bot_patronen):
        signalen = []

        # Max 1 positie tegelijk
        if len(self.open_posities) >= MAX_POSITIES:
            return signalen

        if sentiment is None:
            return signalen

        # Haal overall sentiment score
        if hasattr(sentiment, 'huidig_sentiment'):
            sentiment_data = sentiment.huidig_sentiment
        else:
            sentiment_data = sentiment

        overall_score = 0.0
        if isinstance(sentiment_data, dict):
            overall_score = sentiment_data.get('overall', 0.0)
        elif hasattr(sentiment_data, 'overall'):
            overall_score = sentiment_data.overall

        if abs(overall_score) < 0.75:
            return signalen

        richting_sentiment = 'long' if overall_score > 0 else 'short'

        for symbool in SENTIMENT_SYMBOLEN:
            data = markt_data.get(symbool)
            if not data:
                continue

            indicatoren = data.get('indicatoren', {})
            rsi = indicatoren.get('rsi')
            if rsi is None:
                continue

            # RSI bevestiging: tussen 35-65 (neutraal, niet al extremen)
            if not (35 <= rsi <= 65):
                log.debug(f"[SENTIMENT] Skip {symbool}: RSI={rsi:.1f} buiten 35-65")
                continue

            symbool_regime = regime.get(symbool)
            regime_type = symbool_regime.regime if symbool_regime else None

            if regime_type == Regime.CRISIS:
                continue

            zekerheid = min(0.85, abs(overall_score) * 0.9)

            signaal = TradeSignaal(
                symbool=symbool,
                richting=richting_sentiment,
                strategie_type='sentiment',
                verwacht_rendement=0.06,
                win_kans=zekerheid,
                stop_loss_pct=0.04,
                take_profit_pct=0.06,
                bron=f"sentiment={overall_score:.2f}, RSI={rsi:.1f}",
                zekerheid=zekerheid,
                regime=regime_type.value if regime_type else 'onbekend'
            )
            signalen.append(signaal)
            log.debug(f"[SENTIMENT] Signaal: {symbool} {richting_sentiment} (score={overall_score:.2f})")

            # Max 1 signaal per cyclus
            break

        return signalen
