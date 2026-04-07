"""
MEAN REVERSION STRATEGIE
========================
Koopt overdreven gedaalde assets in de verwachting
dat ze terugkeren naar hun gemiddelde waarde.

Kernlogica:
- RSI < 30 (oversold)
- Prijs onder Bollinger onderband
- Volume niet extreem hoog (geen paniekverkoop)
- Exit: RSI > 55, prijs terug bij Bollinger middellijn
"""

import logging
from agent.brain.regime_detector import Regime

log = logging.getLogger(__name__)


class MeanReversionStrategie:
    """Mean reversion: koop oversold, verkoop overbought."""

    def __init__(self, config: dict):
        self.config = config
        self.mr = config['strategie']['mean_reversion']
        self.gewicht = 1.0

    def moet_sluiten(self, positie, huidige_prijs: float, regime: dict) -> bool:
        """Bepaal of een mean reversion positie gesloten moet worden."""
        if positie.strategie_type != 'mean_reversion':
            return False

        pnl_pct = positie.bereken_pnl_pct(huidige_prijs)

        # Stop-loss: -3% (strakker dan momentum, want dip kan doorzetten)
        if pnl_pct <= -0.03:
            log.info(f"Mean reversion stop-loss: {positie.symbool} {pnl_pct:.1%}")
            return True

        # Take-profit: +5% (iets conservatiever dan momentum)
        if pnl_pct >= 0.05:
            log.info(f"Mean reversion take-profit: {positie.symbool} {pnl_pct:.1%}")
            return True

        # Als markt trending wordt, sluit de mean reversion positie
        symbool_regime = regime.get(positie.symbool)
        if symbool_regime and symbool_regime.regime == Regime.TRENDING_OMLAAG:
            log.info(f"Mean reversion exit: downtrend op {positie.symbool}")
            return True

        return False

    def pas_parameters_aan(self, prestatie: dict):
        """Pas strategie parameters aan."""
        self.gewicht = max(0.3, min(2.0,
            self.gewicht + prestatie.get('gewicht_aanpassing', 0)
        ))
