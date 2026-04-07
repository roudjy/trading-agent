"""
SIGNAAL AGGREGATOR
==================
Combineert signalen uit meerdere bronnen tot handelsbeslissingen.

Bronnen (gewichten):
- Technisch   (0.35): RSI, MACD, Bollinger Bands, EMA
- Regime      (0.25): Marktregime detectie
- Sentiment   (0.20): Reddit, nieuws, social media
- Adversarial (0.15): Bot patronen en kansen
- Geheugen    (0.05): Historische win rate per strategie

Een TradeSignaal wordt alleen aangemaakt als de gecombineerde
zekerheid de min_consensus drempel (default 0.58) overschrijdt
én het regime het signaal bevestigt.
"""

import logging
from dataclasses import dataclass
from typing import List, Optional, Dict, Tuple

from agent.risk.risk_manager import TradeSignaal
from agent.brain.regime_detector import Regime, RegimeResultaat

log = logging.getLogger(__name__)


@dataclass
class BronSignaal:
    bron: str
    symbool: str
    richting: str
    sterkte: float
    zekerheid: float
    uitleg: str


class SignalAggregator:

    def __init__(self, config: dict):
        self.config = config
        # Gebruik zelfverbeterde gewichten als die beschikbaar zijn
        zv = config.get("zelfverbetering", {})
        self.gewichten = dict(zv.get("strategie_gewichten", {
            "technisch":   0.35,
            "regime":      0.25,
            "sentiment":   0.20,
            "adversarial": 0.15,
            "geheugen":    0.05,
        }))
        self.min_consensus = float(zv.get("min_consensus", 0.55))

    # ------------------------------------------------------------------
    # Hoofdmethode
    # ------------------------------------------------------------------

    async def aggregeer(
        self,
        markt_data: dict,
        regime: dict,
        sentiment: dict,
        bot_patronen: list,
        nieuws: list,
        geheugen,
    ) -> List[TradeSignaal]:
        """
        Verwerk alle databronnen en geef een lijst van TradeSignalen terug.
        Elke aanroep verwerkt elk symbool in markt_data onafhankelijk.
        """
        signalen: List[TradeSignaal] = []

        for symbool, data in (markt_data or {}).items():
            if not data or not isinstance(data, dict):
                continue
            ind = data.get('indicatoren') or {}
            if not ind or not data.get('prijs'):
                continue

            # 1. Technisch signaal — de kern van de beslissing
            tech = self._technisch_signaal(symbool, data, ind)
            if tech is None:
                continue
            richting, tech_zekerheid, strategie_type = tech

            # 2. Regime — bevestigt of blokkeert het signaal
            regime_result: Optional[RegimeResultaat] = (regime or {}).get(symbool)
            regime_zekerheid, regime_ok = self._regime_check(
                richting, strategie_type, regime_result
            )
            if not regime_ok:
                log.debug(
                    f"Signaal {symbool} {richting} geblokkeerd door regime "
                    f"{regime_result.regime.value if regime_result else 'onbekend'}"
                )
                continue

            # 3. Sentiment bijdrage
            sent_score = self._sentiment_score(symbool, sentiment or {})

            # 4. Adversarial kansen
            adv_score = self._adversarial_score(symbool, richting, bot_patronen or [])

            # 5. Historische prestaties
            mem_score = self._geheugen_score(symbool, strategie_type, geheugen)

            # 6. Gewogen zekerheid
            zekerheid = round(min(0.99, max(0.0,
                tech_zekerheid   * self.gewichten["technisch"]   +
                regime_zekerheid * self.gewichten["regime"]      +
                sent_score       * self.gewichten["sentiment"]   +
                adv_score        * self.gewichten["adversarial"] +
                mem_score        * self.gewichten["geheugen"]
            )), 3)

            if zekerheid < self.min_consensus:
                log.debug(
                    f"{symbool} {richting} zekerheid {zekerheid:.3f} "
                    f"< drempel {self.min_consensus}"
                )
                continue

            # 7. Exit niveaus
            stop_loss, take_profit = self._bereken_exit_niveaus(
                strategie_type, data, ind, regime_result
            )

            # 8. Verwacht rendement
            win_kans = round(min(0.85, 0.45 + zekerheid * 0.45), 3)
            verwacht = round(take_profit * win_kans - stop_loss * (1 - win_kans), 4)

            regime_naam = (
                regime_result.regime.value if regime_result else "onbekend"
            )

            signaal = TradeSignaal(
                symbool=symbool,
                richting=richting,
                strategie_type=strategie_type,
                verwacht_rendement=verwacht,
                win_kans=win_kans,
                stop_loss_pct=stop_loss,
                take_profit_pct=take_profit,
                bron=(
                    f"tech={tech_zekerheid:.2f} "
                    f"reg={regime_zekerheid:.2f} "
                    f"sent={sent_score:.2f} "
                    f"adv={adv_score:.2f}"
                ),
                zekerheid=zekerheid,
                regime=regime_naam,
            )
            signalen.append(signaal)

            log.info(
                f"Signaal: {symbool} {richting.upper()} | "
                f"strategie={strategie_type} zekerheid={zekerheid:.2f} | "
                f"stop={stop_loss:.1%} target={take_profit:.1%} | "
                f"verwacht rendement={verwacht:.2%}"
            )

        return signalen

    # ------------------------------------------------------------------
    # Technische analyse
    # ------------------------------------------------------------------

    def _technisch_signaal(
        self,
        symbool: str,
        data: dict,
        ind: dict,
    ) -> Optional[Tuple[str, float, str]]:
        """
        Analyseer technische indicatoren.
        Geeft (richting, zekerheid, strategie_type) of None als onduidelijk.
        """
        prijs    = data.get('prijs', 0)
        volume   = data.get('volume', 0)
        gem_vol  = data.get('gem_volume', 0)

        rsi       = ind.get('rsi')
        macd      = ind.get('macd')
        macd_sig  = ind.get('macd_signaal')
        bb_boven  = ind.get('bb_boven')
        bb_midden = ind.get('bb_midden')
        bb_onder  = ind.get('bb_onder')
        ema_20    = ind.get('ema_20')
        ema_50    = ind.get('ema_50')

        # Verzamel signalen per richting: (zekerheid, strategie_naam)
        longs:  List[Tuple[float, str]] = []
        shorts: List[Tuple[float, str]] = []

        # --- RSI oversold / overbought ---
        if rsi is not None:
            if rsi < 30:
                z = min(0.90, 0.56 + (30 - rsi) / 30 * 0.34)
                longs.append((z, 'mean_reversion'))
                log.debug(f"{symbool} RSI oversold {rsi:.1f} → long z={z:.2f}")
            elif rsi > 70:
                z = min(0.90, 0.56 + (rsi - 70) / 30 * 0.34)
                shorts.append((z, 'mean_reversion'))
                log.debug(f"{symbool} RSI overbought {rsi:.1f} → short z={z:.2f}")

        # --- Bollinger Bands ---
        if bb_boven and bb_onder and prijs > 0:
            breedte = bb_boven - bb_onder
            if breedte > 0:
                if prijs < bb_onder:
                    buiten = (bb_onder - prijs) / breedte
                    z = min(0.88, 0.57 + buiten * 0.31)
                    longs.append((z, 'mean_reversion'))
                    log.debug(f"{symbool} prijs onder BB → long z={z:.2f}")
                elif prijs > bb_boven:
                    buiten = (prijs - bb_boven) / breedte
                    z = min(0.88, 0.57 + buiten * 0.31)
                    shorts.append((z, 'mean_reversion'))
                    log.debug(f"{symbool} prijs boven BB → short z={z:.2f}")

        # --- MACD crossover ---
        if macd is not None and macd_sig is not None:
            diff = macd - macd_sig
            if diff != 0:
                norm = min(1.0, abs(diff) / (abs(macd_sig) + 1e-9))
                z = round(0.53 + norm * 0.27, 3)
                if diff > 0:
                    longs.append((z, 'momentum'))
                else:
                    shorts.append((z, 'momentum'))

        # --- EMA trend (met divergentie-magnitude bonus) ---
        if ema_20 and prijs > 0:
            pct = (prijs - ema_20) / ema_20  # positief = boven EMA, negatief = eronder
            if prijs > ema_20 * 1.005:
                # Hoe verder boven EMA, hoe sterker het signaal
                z_base = 0.60 if (ema_50 and prijs > ema_50 * 1.005) else 0.55
                z = min(0.90, z_base + pct * 2.0)
                longs.append((z, 'momentum'))
            elif prijs < ema_20 * 0.995:
                z_base = 0.60 if (ema_50 and prijs < ema_50 * 0.995) else 0.54
                z = min(0.90, z_base + abs(pct) * 2.0)
                shorts.append((z, 'momentum'))

        if not longs and not shorts:
            return None

        # Volume bonus (hoog volume bevestigt signaal)
        vol_bonus = 0.04 if (gem_vol > 0 and volume > gem_vol * 1.5) else 0.0

        best_long  = max(longs,  key=lambda x: x[0]) if longs  else (0.0, '')
        best_short = max(shorts, key=lambda x: x[0]) if shorts else (0.0, '')

        # Een richting moet minimaal 0.05 punt sterker zijn dan de andere
        marge = 0.05
        if best_long[0] > best_short[0] + marge:
            return ('long',  min(0.95, best_long[0]  + vol_bonus), best_long[1])
        elif best_short[0] > best_long[0] + marge:
            return ('short', min(0.95, best_short[0] + vol_bonus), best_short[1])

        return None  # Conflicterende signalen: wachten

    # ------------------------------------------------------------------
    # Regime check
    # ------------------------------------------------------------------

    def _regime_check(
        self,
        richting: str,
        strategie_type: str,
        regime_result: Optional[RegimeResultaat],
    ) -> Tuple[float, bool]:
        """
        Geeft (regime_zekerheid 0..1, mag_handelen bool).
        Blokkeert signalen die tegen het marktregime ingaan.
        """
        if regime_result is None:
            return 0.50, True  # Geen data: neutraal, sta toe

        regime = regime_result.regime

        if regime == Regime.CRISIS:
            # Niet volledig blokkeren: sterke technische signalen mogen door
            # maar de lage regime-bijdrage zorgt dat alleen de sterkste signalen
            # de totale zekerheidsdrempel halen.
            if strategie_type == 'mean_reversion' and richting == 'long':
                return 0.45, True   # Oversold kopen in crisis: klassieke strategie
            return 0.35, True       # Alle andere signalen: laag vertrouwen

        if regime == Regime.HOGE_VOLATILITEIT:
            if strategie_type == 'mean_reversion':
                return 0.65, True
            if richting == 'long' and strategie_type == 'momentum':
                return 0.50, True   # Momentum toegestaan maar voorzichtig
            return 0.40, True       # Overige: laag vertrouwen

        if regime == Regime.TRENDING_OMHOOG:
            if richting == 'long' and strategie_type == 'momentum':
                return regime_result.zekerheid, True
            if richting == 'long':
                return 0.55, True
            if richting == 'short':
                return 0.15, False  # Short in uptrend: nee

        if regime == Regime.TRENDING_OMLAAG:
            if richting == 'long':
                return 0.15, False  # Long in downtrend: nee
            if richting == 'short':
                return regime_result.zekerheid, True

        if regime == Regime.ZIJWAARTS:
            if strategie_type == 'mean_reversion':
                return regime_result.zekerheid, True
            return 0.38, True   # Zwak momentum signaal in zijwaartse markt

        return 0.50, True

    # ------------------------------------------------------------------
    # Sentiment
    # ------------------------------------------------------------------

    def _sentiment_score(self, symbool: str, sentiment: dict) -> float:
        """
        Vertaal sentiment (-1..+1) naar bijdrage (0..1).
        0.5 = neutraal, >0.5 = bullish, <0.5 = bearish.
        """
        if not sentiment:
            return 0.50
        # "BTC/EUR" → "btc", "NVDA" → "nvda"
        sleutel = symbool.split('/')[0].lower()
        score = sentiment.get(sleutel, sentiment.get('algemeen', 0.0))
        return round(max(0.0, min(1.0, 0.50 + float(score) * 0.40)), 3)

    # ------------------------------------------------------------------
    # Adversarial
    # ------------------------------------------------------------------

    def _adversarial_score(self, symbool: str, richting: str, bot_patronen: list) -> float:
        """
        Geeft hogere score als er een actief bot-patroon is
        dat handelen in deze richting beloont.
        """
        if not bot_patronen:
            return 0.50
        for patroon in bot_patronen:
            markt = getattr(patroon, 'markt', '')
            if symbool not in markt and markt not in symbool:
                continue
            kans = getattr(patroon, 'kans_op_winst', 0.0)
            if kans > 0.65:
                return min(0.90, 0.55 + kans * 0.35)
        return 0.50

    # ------------------------------------------------------------------
    # Geheugen
    # ------------------------------------------------------------------

    def _geheugen_score(self, symbool: str, strategie_type: str, geheugen) -> float:
        """
        Historische win rate voor deze strategie als tiebreaker.
        """
        if geheugen is None:
            return 0.50
        try:
            inzichten = geheugen.analyseer_prestaties()
            prestatie = inzichten.get('per_strategie', {}).get(strategie_type, {})
            win_rate = prestatie.get('win_rate', 0.50)
            return round(max(0.10, min(0.90, float(win_rate))), 3)
        except Exception:
            return 0.50

    # ------------------------------------------------------------------
    # Exit niveaus
    # ------------------------------------------------------------------

    def _bereken_exit_niveaus(
        self,
        strategie_type: str,
        data: dict,
        ind: dict,
        regime_result: Optional[RegimeResultaat],
    ) -> Tuple[float, float]:
        """
        Bereken stop-loss en take-profit percentages.
        Basis per strategie, aangepast op ATR-volatiliteit en regime.
        """
        if strategie_type == 'momentum':
            stop_loss, take_profit = 0.040, 0.080
        elif strategie_type == 'mean_reversion':
            stop_loss, take_profit = 0.030, 0.055
        else:  # adversarial, polymarket, overig
            stop_loss, take_profit = 0.025, 0.045

        # ATR-gebaseerde aanpassing
        prijs = data.get('prijs', 0)
        atr   = ind.get('atr')
        if atr and prijs > 0:
            atr_pct = atr / prijs
            if atr_pct > 0.025:      # Hoge volatiliteit: ruimere marges
                stop_loss   = min(0.06, stop_loss   * 1.40)
                take_profit = min(0.12, take_profit * 1.40)
            elif atr_pct < 0.005:    # Lage volatiliteit: strakker
                stop_loss   = max(0.015, stop_loss   * 0.80)
                take_profit = max(0.025, take_profit * 0.80)

        # Risicovolle regimes: strakker stop
        if regime_result and regime_result.positie_grootte_factor < 0.5:
            stop_loss = round(stop_loss * 0.75, 3)

        return round(stop_loss, 3), round(take_profit, 3)

    # ------------------------------------------------------------------
    # Gewichten aanpassen (leren)
    # ------------------------------------------------------------------

    def pas_gewichten_aan(self, prestatie_per_bron: dict):
        """
        Pas signaalgewichten aan op basis van historische accuraatheid per bron.
        Wordt wekelijks aangeroepen vanuit de leer-loop.
        """
        for bron, prestatie in (prestatie_per_bron or {}).items():
            if bron not in self.gewichten:
                continue
            acc = prestatie.get('accuraatheid', 0.50)
            if acc > 0.60:
                self.gewichten[bron] = min(0.50, self.gewichten[bron] * 1.10)
            elif acc < 0.40:
                self.gewichten[bron] = max(0.05, self.gewichten[bron] * 0.90)

        # Normaliseer naar 1.0
        totaal = sum(self.gewichten.values())
        if totaal > 0:
            self.gewichten = {
                k: round(v / totaal, 3) for k, v in self.gewichten.items()
            }
        log.info(f"Signaalgewichten bijgewerkt: {self.gewichten}")
