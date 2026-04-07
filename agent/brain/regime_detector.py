"""
REGIME DETECTOR
===============
Detecteert in welk marktregime we zitten per asset class.
Dit bepaalt welke strategie de agent inzet.

Regimes:
- TRENDING_OMHOOG   → Momentum strategie
- TRENDING_OMLAAG   → Short momentum of defensief
- ZIJWAARTS         → Mean reversion strategie
- HOGE_VOLATILITEIT → Kleinere posities, voorzichtiger
- CRISIS            → Minimale exposure, cash beschermen
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass
from enum import Enum
from typing import Dict


class Regime(Enum):
    TRENDING_OMHOOG = "trending_omhoog"
    TRENDING_OMLAAG = "trending_omlaag"
    ZIJWAARTS = "zijwaarts"
    HOGE_VOLATILITEIT = "hoge_volatiliteit"
    CRISIS = "crisis"


@dataclass
class RegimeResultaat:
    regime: Regime
    zekerheid: float          # 0.0 tot 1.0
    aanbevolen_strategie: str
    positie_grootte_factor: float  # Vermenigvuldiger voor positiegrootte
    uitleg: str


class RegimeDetector:
    """
    Analyseert prijsdata en bepaalt het marktregime.
    Gebruikt meerdere indicatoren voor robuustheid.
    """

    def __init__(self, config: dict):
        self.config = config
        lookback = config['strategie']['regime_detectie']['lookback_periode']
        self.lookback = lookback
        self.vol_drempel = config['strategie']['regime_detectie']['volatiliteit_drempel']

    async def detecteer(self, markt_data: dict) -> Dict[str, RegimeResultaat]:
        """
        Detecteer regime voor elke asset class.
        Geeft een dict terug: symbool -> RegimeResultaat
        """
        resultaten = {}

        for symbool, data in markt_data.items():
            if 'prijzen' not in data or len(data['prijzen']) < self.lookback:
                continue

            prijzen = np.array(data['prijzen'])
            resultaten[symbool] = self._analyseer(symbool, prijzen, data)

        return resultaten

    def _analyseer(self, symbool: str, prijzen: np.ndarray, data: dict) -> RegimeResultaat:
        """Analyseer één symbool en bepaal het regime."""

        # Bereken rendement
        rendementen = np.diff(np.log(prijzen))
        recent = rendementen[-self.lookback:]

        # 1. Volatiliteit (hoe wild zijn de koersbewegingen?)
        volatiliteit = np.std(recent) * np.sqrt(252)  # Geannualiseerd

        # 2. Trend richting en sterkte
        # Gebruik lineaire regressie over de periode
        x = np.arange(len(recent))
        helling = np.polyfit(x, recent.cumsum(), 1)[0]
        trend_sterkte = abs(helling) / (volatiliteit + 1e-8)

        # 3. ADX-achtige meting (hoe sterk is de trend?)
        kortetermijn_ma = np.mean(prijzen[-5:])
        langetermijn_ma = np.mean(prijzen[-self.lookback:])
        ma_verhouding = (kortetermijn_ma - langetermijn_ma) / langetermijn_ma

        # 4. Determineer regime
        if volatiliteit > self.vol_drempel * 3:
            # Extreem hoge volatiliteit = crisis modus
            return RegimeResultaat(
                regime=Regime.CRISIS,
                zekerheid=0.90,
                aanbevolen_strategie="defensief",
                positie_grootte_factor=0.25,  # Slechts 25% van normale grootte
                uitleg=f"Crisis gedetecteerd op {symbool}. "
                       f"Volatiliteit {volatiliteit:.1%} is extreem hoog. "
                       f"Positiegrootte gereduceerd tot 25%."
            )

        elif volatiliteit > self.vol_drempel * 1.5:
            # Hoge volatiliteit maar geen crisis
            return RegimeResultaat(
                regime=Regime.HOGE_VOLATILITEIT,
                zekerheid=0.80,
                aanbevolen_strategie="mean_reversion",
                positie_grootte_factor=0.50,
                uitleg=f"Hoge volatiliteit op {symbool} ({volatiliteit:.1%}). "
                       f"Mean reversion kansen, kleinere posities."
            )

        elif ma_verhouding > 0.02 and trend_sterkte > 0.5:
            # Opwaartse trend
            zekerheid = min(0.95, 0.60 + trend_sterkte * 0.2)
            return RegimeResultaat(
                regime=Regime.TRENDING_OMHOOG,
                zekerheid=zekerheid,
                aanbevolen_strategie="momentum",
                positie_grootte_factor=1.0,
                uitleg=f"Opwaartse trend op {symbool}. "
                       f"MA verhouding: {ma_verhouding:.2%}. "
                       f"Momentum strategie actief."
            )

        elif ma_verhouding < -0.02 and trend_sterkte > 0.5:
            # Neerwaartse trend
            zekerheid = min(0.95, 0.60 + trend_sterkte * 0.2)
            return RegimeResultaat(
                regime=Regime.TRENDING_OMLAAG,
                zekerheid=zekerheid,
                aanbevolen_strategie="defensief",
                positie_grootte_factor=0.30,
                uitleg=f"Neerwaartse trend op {symbool}. "
                       f"Minimale exposure. Wachten op omkering."
            )

        else:
            # Zijwaarts - mean reversion
            return RegimeResultaat(
                regime=Regime.ZIJWAARTS,
                zekerheid=0.70,
                aanbevolen_strategie="mean_reversion",
                positie_grootte_factor=0.75,
                uitleg=f"Zijwaartse markt op {symbool}. "
                       f"Mean reversion strategie: koop oversold, verkoop overbought."
            )
