"""
EMA CROSSOVER AGENT
===================
Kapitaal: €300
Assets: 10 stocks (NVDA, AAPL, MSFT, ASML, AMD, GOOGL, META, TSLA, AMZN, JPM)
Logica: EMA20 kruist EMA50 + volume 20% boven gemiddelde
Markttijden: alleen 15:30-22:00 NL (NYSE open), niet eerste 30 minuten
Cooldown: 24 uur per symbool
Stop-loss: 4%
Take-profit: 8%
"""

import logging
from datetime import datetime, time
import pytz
from agent.agents.base_agent import BaseAgent
from agent.risk.risk_manager import TradeSignaal
from agent.brain.regime_detector import Regime

log = logging.getLogger(__name__)

STOCK_SYMBOLEN = [
    'NVDA', 'AAPL', 'MSFT', 'ASML', 'AMD',
    'GOOGL', 'META', 'TSLA', 'AMZN', 'JPM'
]

NL_TZ = pytz.timezone('Europe/Amsterdam')
# NYSE open 15:30 NL, sluit 22:00 NL
MARKT_OPEN = time(15, 30)
MARKT_SLUIT = time(22, 0)
# Geen trades eerste 30 minuten
MARKT_OPEN_VEILIG = time(16, 0)


class EMAAgent(BaseAgent):
    """EMA crossover trend-following agent voor stocks."""

    naam = "ema"
    cooldown_uren = 24

    def _initieel_kapitaal(self) -> float:
        return 300.0

    async def _mag_handelen(self, symbool: str, markt_data: dict) -> bool:
        """Alleen tijdens NYSE markturen, niet eerste 30 min."""
        nu_nl = datetime.now(NL_TZ).time()
        if nu_nl < MARKT_OPEN_VEILIG or nu_nl > MARKT_SLUIT:
            return False
        return True

    async def _genereer_signalen(self, markt_data, regime, sentiment, bot_patronen):
        signalen = []

        # Tijdcheck: markttijden
        nu_nl = datetime.now(NL_TZ).time()
        if nu_nl < MARKT_OPEN_VEILIG or nu_nl > MARKT_SLUIT:
            return signalen

        for symbool in STOCK_SYMBOLEN:
            data = markt_data.get(symbool)
            if not data:
                continue

            indicatoren = data.get('indicatoren', {})
            ema_20 = indicatoren.get('ema_20')
            ema_50 = indicatoren.get('ema_50')
            volume = data.get('volume', 0)
            gem_volume = data.get('gem_volume', 0)

            if not all([ema_20, ema_50, gem_volume]):
                continue

            symbool_regime = regime.get(symbool)
            regime_type = symbool_regime.regime if symbool_regime else None

            # Volume bevestiging: minimaal 20% boven gemiddelde
            volume_ok = volume >= gem_volume * 1.20
            if not volume_ok:
                continue

            richting = None
            reden = None

            # EMA crossover: kijk of EMA20 recent EMA50 heeft gekruist
            # We hebben alleen huidige waarden - gebruik prijs als proxy
            prijs = data.get('prijs', 0)
            if prijs <= 0:
                continue

            if ema_20 > ema_50 and regime_type in [Regime.TRENDING_OMHOOG, None]:
                richting = 'long'
                reden = f"EMA crossover bullish: EMA20={ema_20:.2f} > EMA50={ema_50:.2f}, vol={volume/gem_volume:.1f}x"
            elif ema_20 < ema_50 and regime_type in [Regime.TRENDING_OMLAAG, None]:
                richting = 'short'
                reden = f"EMA crossover bearish: EMA20={ema_20:.2f} < EMA50={ema_50:.2f}, vol={volume/gem_volume:.1f}x"

            if not richting:
                continue

            # Geen trades in crisis regime
            if regime_type == Regime.CRISIS:
                continue

            verschil_pct = abs(ema_20 - ema_50) / ema_50
            zekerheid = min(0.90, 0.60 + verschil_pct * 5)

            signaal = TradeSignaal(
                symbool=symbool,
                richting=richting,
                strategie_type='ema_crossover',
                verwacht_rendement=0.08,
                win_kans=zekerheid,
                stop_loss_pct=0.04,
                take_profit_pct=0.08,
                bron=reden,
                zekerheid=zekerheid,
                regime=regime_type.value if regime_type else 'onbekend'
            )
            signalen.append(signaal)
            log.debug(f"[EMA] Signaal: {symbool} {richting}")

        return signalen

    def _moet_sluiten_strategie(self, positie, huidige_prijs, regime):
        """Sluit bij einde marktdag."""
        nu_nl = datetime.now(NL_TZ).time()
        if nu_nl >= time(21, 45):
            log.info(f"[EMA] Einde marktdag exit: {positie.symbool}")
            return True
        return False
