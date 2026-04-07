"""
DAGELIJKS RAPPORT GENERATOR
============================
Schrijft elke ochtend om 07:00 een Nederlandstalig rapport.
Geen alarmen - alleen informatie over wat er goed ging,
wat er mis ging, en wat de agent heeft geleerd en aangepast.

Rapport formaat:
- Financieel overzicht (P&L, kapitaal, posities)
- Wat ging goed (met uitleg)
- Wat ging mis (met eerlijke analyse)
- Wat de agent heeft geleerd
- Wat de agent morgen anders doet
- Marktregime verwachting voor komende dag
"""

import logging
import json
from datetime import datetime
from pathlib import Path
from typing import List
from anthropic import Anthropic

log = logging.getLogger(__name__)


class DagelijksRapport:
    """Genereert het dagelijkse Nederlandstalige rapport."""

    def __init__(self, config: dict, geheugen):
        self.config = config
        self.geheugen = geheugen
        self.rapport_map = Path("reports")
        self.rapport_map.mkdir(exist_ok=True)

        # Claude API voor intelligente rapportage
        api_key = config['ai']['anthropic_api_key']
        if api_key:
            self.claude = Anthropic(api_key=api_key)
        else:
            self.claude = None
            log.warning("Geen Anthropic API key - rapport zonder AI analyse")

    async def schrijf_dagrapport(self, dagelijkse_trades: list):
        """Schrijf het dagelijkse rapport naar een bestand en log het."""

        datum = datetime.now().strftime("%Y-%m-%d")
        statistieken = self.geheugen.dagstatistieken(dagelijkse_trades)

        # Genereer rapport tekst
        rapport_tekst = await self._genereer_rapport_tekst(statistieken, dagelijkse_trades)

        # Sla op als tekstbestand
        bestandsnaam = self.rapport_map / f"rapport_{datum}.md"
        with open(bestandsnaam, 'w', encoding='utf-8') as f:
            f.write(rapport_tekst)

        # Log de samenvatting
        log.info(f"\n{'='*60}\n{rapport_tekst[:500]}\n{'='*60}")

        # Sla ook op als JSON voor het dashboard
        json_bestand = self.rapport_map / f"rapport_{datum}.json"
        with open(json_bestand, 'w', encoding='utf-8') as f:
            json.dump(statistieken, f, ensure_ascii=False, indent=2, default=str)

        return bestandsnaam

    async def _genereer_rapport_tekst(self, statistieken: dict, trades: list) -> str:
        """Genereer de volledige rapporttekst met AI."""

        datum = datetime.now().strftime("%d %B %Y")

        # Basis statistieken (altijd beschikbaar, ook zonder AI)
        basis_rapport = self._basis_rapport(datum, statistieken)

        # AI-gegenereerde analyse (als API key beschikbaar)
        if self.claude and statistieken.get('trades_vandaag', 0) > 0:
            ai_analyse = await self._ai_analyse(statistieken, trades)
            return basis_rapport + "\n\n" + ai_analyse

        return basis_rapport

    def _basis_rapport(self, datum: str, stats: dict) -> str:
        """Genereer basis rapport zonder AI."""

        kapitaal = stats.get('huidig_kapitaal', 0)
        start_kapitaal = self.config['kapitaal']['start']
        totaal_rendement = ((kapitaal - start_kapitaal) / start_kapitaal) * 100

        dagwinst = stats.get('dag_pnl', 0)
        dag_pnl_kleur = "+" if dagwinst >= 0 else ""

        win_trades = stats.get('winnende_trades', 0)
        verlies_trades = stats.get('verliezende_trades', 0)
        totaal_trades = win_trades + verlies_trades
        win_rate = (win_trades / totaal_trades * 100) if totaal_trades > 0 else 0

        rapport = f"""# Dagrapport Trading Agent — {datum}

## Financieel overzicht

| | |
|---|---|
| Huidig kapitaal | €{kapitaal:,.2f} |
| Dag P&L | {dag_pnl_kleur}€{dagwinst:,.2f} |
| Totaal rendement | {totaal_rendement:+.1f}% |
| Drawdown (max) | {stats.get('max_drawdown', 0):.1f}% |
| Win rate (vandaag) | {win_rate:.0f}% ({win_trades}W / {verlies_trades}V) |

## Trades vandaag ({totaal_trades} totaal)
"""
        # Voeg individuele trades toe
        for trade in stats.get('trade_details', []):
            pnl = trade.get('pnl', 0)
            teken = "+" if pnl >= 0 else ""
            rapport += (
                f"- **{trade.get('symbool', '?')}** | "
                f"{trade.get('richting', '?')} | "
                f"{teken}€{pnl:.2f} | "
                f"{trade.get('strategie', '?')} | "
                f"{trade.get('uitleg', '')}\n"
            )

        rapport += f"\n## Marktregimes vandaag\n"
        for asset, regime in stats.get('regimes', {}).items():
            rapport += f"- **{asset}**: {regime}\n"

        return rapport

    async def _ai_analyse(self, statistieken: dict, trades: list) -> str:
        """
        Gebruik Claude om een intelligente analyse te schrijven.
        Dit is de 'stem' van de agent die uitlegt wat er is gebeurd.
        """
        if not self.claude:
            return ""

        # Bouw context voor Claude
        trade_samenvatting = []
        for t in trades[:20]:  # Max 20 trades meegeven
            trade_samenvatting.append({
                'symbool': getattr(t, 'symbool', '?'),
                'pnl': getattr(t, 'pnl', 0),
                'strategie': getattr(t, 'strategie_type', '?'),
                'reden_entry': getattr(t, 'reden_entry', ''),
                'reden_exit': getattr(t, 'reden_exit', ''),
                'geleerd': getattr(t, 'geleerd', '')
            })

        prompt = f"""Je bent een autonome trading agent die dagelijks verslag uitbrengt 
aan zijn eigenaar Joery. Schrijf een eerlijk, informatief Nederlandstalig rapport 
over de afgelopen handelsdag.

STATISTIEKEN:
{json.dumps(statistieken, ensure_ascii=False, default=str, indent=2)}

TRADES:
{json.dumps(trade_samenvatting, ensure_ascii=False, indent=2)}

Schrijf het rapport in de volgende secties:
1. **Wat ging goed** - Wees specifiek over welke trades/signalen werkten en waarom
2. **Wat ging mis** - Eerlijke analyse, geen excuses, gewoon wat er fout ging
3. **Wat ik heb geleerd** - Concrete lessen uit de dag
4. **Wat ik morgen anders doe** - Specifieke aanpassingen aan de strategie
5. **Marktvisie voor morgen** - Verwacht regime per asset class

Toon: direct, feitelijk, geen emotie. Jij bent de expert, Joery leest mee.
Maximaal 400 woorden. Gebruik geen clichés."""

        try:
            response = self.claude.messages.create(
                model=self.config['ai']['model'],
                max_tokens=600,
                messages=[{"role": "user", "content": prompt}]
            )
            return response.content[0].text
        except Exception as e:
            log.error(f"AI rapport generatie mislukt: {e}")
            return "*(AI analyse tijdelijk niet beschikbaar)*"

    async def schrijf_noodrapport(self, drawdown: float):
        """Schrijf een rapport als de drawdown limiet bereikt is."""
        datum = datetime.now().strftime("%Y-%m-%d %H:%M")
        rapport = f"""# NOODRAPPORT — {datum}

## Agent gepauzeerd

De drawdown limiet van {self.config['kapitaal']['drawdown_limiet']:.0%} is bereikt.
Huidige drawdown: **{drawdown:.1%}**

De agent heeft zichzelf gestopt om verder kapitaalverlies te voorkomen.

## Wat nu?

1. Bekijk het dashboard voor de volledige analyse
2. Review de recente trades in het logboek
3. Als je wil dat de agent herstart: pas de config aan en herstart handmatig
4. Aanbeveling: wacht minimaal 24 uur en analyseer wat er mis ging

## Open posities

Alle open posities zijn gesloten of worden gemonitored.
Controleer je exchanges voor de actuele status.
"""
        bestand = self.rapport_map / f"NOODRAPPORT_{datum.replace(':', '-')}.md"
        with open(bestand, 'w', encoding='utf-8') as f:
            f.write(rapport)

        log.warning(f"Noodrapport geschreven: {bestand}")
