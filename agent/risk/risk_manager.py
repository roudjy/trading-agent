"""
RISICO MANAGER
==============
Beschermt het kapitaal. Geen trade gaat door zonder goedkeuring.

Taken:
- Bepaal positiegrootte (Kelly Criterion aangepast)
- Controleer drawdown limieten
- Voorkom over-concentratie in één asset
- Stop agent bij catastrofaal verlies
"""

import logging
from dataclasses import dataclass
from typing import Tuple, Dict

log = logging.getLogger(__name__)


@dataclass
class TradeSignaal:
    """Een handelssignaal met alle benodigde informatie."""
    symbool: str
    richting: str           # 'long' of 'short'
    strategie_type: str     # 'momentum', 'mean_reversion', etc.
    verwacht_rendement: float
    win_kans: float         # Geschatte winkans 0.0 - 1.0
    stop_loss_pct: float    # Verliespercentage bij stop-loss
    take_profit_pct: float  # Winstpercentage bij target
    bron: str               # Waar komt dit signaal vandaan
    zekerheid: float        # Zekerheid van het signaal 0.0 - 1.0
    regime: str             # Huidig marktregime


@dataclass
class PositieGrootte:
    """Resultaat van positiegrootte berekening."""
    euro_bedrag: float
    percentage_van_kapitaal: float
    redenering: str


class RiskManager:
    """
    Beoordeelt elke potentiële trade op risico.
    Gebruikt aangepaste Kelly Criterion voor optimale positiegrootte.
    """

    def __init__(self, config: dict, geheugen):
        self.config = config
        self.geheugen = geheugen
        self.max_positie = config['kapitaal']['max_positie_grootte']
        self.drawdown_limiet = config['kapitaal']['drawdown_limiet']

    def beoordeel(self, signaal: TradeSignaal, open_posities: dict) -> Tuple[bool, str]:
        """
        Beoordeel of een trade mag worden uitgevoerd.
        Geeft (goedgekeurd: bool, reden: str) terug.
        """

        huidig_kapitaal = self.geheugen.huidig_kapitaal()

        # Check 1: Drawdown limiet
        drawdown = self.bereken_totale_drawdown()
        if drawdown >= self.drawdown_limiet:
            return False, f"Drawdown limiet bereikt: {drawdown:.1%}"

        # Check 2: Minimale signaalzekerheid
        if signaal.zekerheid < 0.55:
            return False, f"Signaal zekerheid te laag: {signaal.zekerheid:.2f}"

        # Check 3: Maximale concentratie per asset
        huidige_blootstelling = self._bereken_blootstelling(signaal.symbool, open_posities)
        if huidige_blootstelling > 0.30:  # Max 30% in één asset
            return False, f"Te veel blootstelling aan {signaal.symbool}: {huidige_blootstelling:.1%}"

        # Check 4: Maximaal aantal open posities
        if len(open_posities) >= 8:
            return False, "Maximaal aantal open posities bereikt (8)"

        # Check 5: Minimum kapitaal per trade (€10 minimum)
        positie = self.bereken_positie_grootte(signaal, huidig_kapitaal)
        if positie.euro_bedrag < 10:
            return False, f"Positiegrootte te klein: €{positie.euro_bedrag:.2f}"

        return True, "Goedgekeurd"

    def bereken_positie_grootte(self, signaal: TradeSignaal, kapitaal: float) -> PositieGrootte:
        """
        Berekent optimale positiegrootte met Fractional Kelly Criterion.

        Kelly formule: f* = (p*b - q) / b
        Fractional Kelly schaalt f* op basis van aantal historische trades:
        - <10 trades:    f_safe = f* * 0.25  (zeer voorzichtig, weinig data)
        - 10-50 trades:  f_safe = f* * 0.50  (half Kelly)
        - 50-200 trades: f_safe = f* * 0.75  (drie-kwart Kelly)
        - >200 trades:   f_safe = f* * (1 - 1/sqrt(trades))  (asymptotisch naar full Kelly)
        """
        import math

        p = signaal.win_kans
        q = 1 - p
        b = signaal.take_profit_pct / max(signaal.stop_loss_pct, 0.001)

        # Volledige Kelly fractie
        f_star = (p * b - q) / b

        # Bepaal fractional Kelly op basis van aantal trades
        trades = self._tel_gesloten_trades()
        if trades < 10:
            f_safe = f_star * 0.25
            schaal_reden = f"<10 trades ({trades}): schaal 0.25"
        elif trades < 50:
            f_safe = f_star * 0.50
            schaal_reden = f"10-50 trades ({trades}): schaal 0.50"
        elif trades < 200:
            f_safe = f_star * 0.75
            schaal_reden = f"50-200 trades ({trades}): schaal 0.75"
        else:
            schaal = 1 - 1 / math.sqrt(trades)
            f_safe = f_star * schaal
            schaal_reden = f">200 trades ({trades}): schaal {schaal:.3f}"

        # Aanpassen voor signaalzekerheid
        gecorrigeerde_kelly = f_safe * signaal.zekerheid

        # Nooit meer dan geconfigureerd maximum, nooit negatief
        gecorrigeerde_kelly = min(max(gecorrigeerde_kelly, 0), self.max_positie)

        euro_bedrag = kapitaal * gecorrigeerde_kelly

        return PositieGrootte(
            euro_bedrag=round(euro_bedrag, 2),
            percentage_van_kapitaal=gecorrigeerde_kelly,
            redenering=(
                f"Kelly f*: {f_star:.2%} | {schaal_reden} → "
                f"f_safe: {f_safe:.2%} | Zekerheid {signaal.zekerheid:.0%} → "
                f"{gecorrigeerde_kelly:.2%} = €{euro_bedrag:.2f}"
            )
        )

    def _tel_gesloten_trades(self) -> int:
        """Tel het aantal gesloten trades uit de database voor Kelly-schaling."""
        try:
            totaal = sum(
                v.get("totaal_trades", 0)
                for v in self.geheugen.analyseer_prestaties().get("per_strategie", {}).values()
            )
            return totaal
        except Exception:
            return 0

    def bereken_totale_drawdown(self) -> float:
        """Bereken huidig verlies t.o.v. piek kapitaal."""
        piek = self.geheugen.piek_kapitaal()
        huidig = self.geheugen.huidig_kapitaal()
        if piek == 0:
            return 0
        return max(0, (piek - huidig) / piek)

    def _bereken_blootstelling(self, symbool: str, open_posities: dict) -> float:
        """Bereken huidige blootstelling aan een specifiek symbool."""
        totaal_kapitaal = self.geheugen.huidig_kapitaal()
        if totaal_kapitaal == 0:
            return 0

        blootstelling = sum(
            p.waarde for p in open_posities.values()
            if p.symbool == symbool
        )
        return blootstelling / totaal_kapitaal
