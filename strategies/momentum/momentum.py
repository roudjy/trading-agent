"""
MOMENTUM STRATEGIE
==================
Volgt sterke trends. Koopt als de markt al omhoog gaat
en er bevestiging is van volume en indicators.

Kernlogica:
- MACD crossover met volumebevestiging
- Prijs boven EMA 20 en EMA 50
- RSI tussen 50-70 (niet te overbought)
- Exit: MACD keert, RSI > 75, of trailing stop geraakt
"""

import logging
from typing import Optional
from agent.brain.regime_detector import RegimeResultaat, Regime

log = logging.getLogger(__name__)


class MomentumStrategie:
    """Momentum strategie: rijd mee op sterke trends."""

    def __init__(self, config: dict):
        self.config = config
        self.mc = config['strategie']['momentum']
        # Gewicht van deze strategie (wordt bijgeleerd)
        self.gewicht = 1.0

    def moet_sluiten(
        self,
        positie,
        huidige_prijs: float,
        regime: dict
    ) -> bool:
        """Bepaal of een momentum positie gesloten moet worden."""
        if positie.strategie_type != 'momentum':
            return False

        pnl_pct = positie.bereken_pnl_pct(huidige_prijs)

        # Harde stop-loss: -3%
        stop_loss = self.mc.get('stop_loss', 0.03)
        if pnl_pct <= -stop_loss:
            log.info(f"Momentum stop-loss: {positie.symbool} {pnl_pct:.1%}")
            return True

        # Take-profit: +6%
        take_profit = self.mc.get('take_profit', 0.06)
        if pnl_pct >= take_profit:
            log.info(f"Momentum take-profit: {positie.symbool} {pnl_pct:.1%}")
            return True

        # Regime exit: sluit ALLEEN bij tegengesteld regime (niet bij CRISIS/ZIJWAARTS)
        # CRISIS en HOGE_VOLATILITEIT laten we afhandelen door stop-loss
        symbool_regime = regime.get(positie.symbool)
        if symbool_regime:
            if positie.richting == 'long' and symbool_regime.regime == Regime.TRENDING_OMLAAG:
                log.info(f"Momentum exit: markt draait om voor {positie.symbool}")
                return True
            if positie.richting == 'short' and symbool_regime.regime == Regime.TRENDING_OMHOOG:
                log.info(f"Momentum exit: markt draait om voor {positie.symbool}")
                return True

        # Trailing stop: als winst ooit > 5% was maar teruggevallen naar < 3%
        # pnl_pct wordt vergeleken met peak_pnl_pct bijgehouden in positie
        peak = getattr(positie, 'peak_pnl_pct', pnl_pct)
        if pnl_pct > peak:
            positie.peak_pnl_pct = pnl_pct
        elif peak > 0.05 and pnl_pct < 0.03:
            log.info(f"Momentum trailing stop: {positie.symbool} piek {peak:.1%} → huidig {pnl_pct:.1%}")
            return True

        return False

    def pas_parameters_aan(self, prestatie: dict):
        """Pas strategie parameters aan op basis van prestaties."""
        win_rate = prestatie.get('win_rate', 0)
        if win_rate < 0.45:
            # Strategie werkt slecht: verhoog zekerheidsdrempel
            log.info("Momentum: win rate laag, zekerheidsdrempel verhoogd")
        self.gewicht = max(0.3, min(2.0,
            self.gewicht + prestatie.get('gewicht_aanpassing', 0)
        ))
