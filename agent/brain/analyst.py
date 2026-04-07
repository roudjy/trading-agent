"""
CLAUDE ANALYST
==============
Twee lagen AI-analyse:

Layer 1 — Real-time filter (Claude Haiku):
  - Alleen voor Sentiment + Bot agent signalen
  - 5 seconden timeout, fallback = signaal doorlaten
  - 15-minuten cache per asset
  - Kost ~$0.05/dag
  - Retourneert: {beslissing: 'ga_door'/'blokkeer', reden: str, risico: 'laag'/'middel'/'hoog'}

Layer 2 — Dagelijkse evaluatie (Claude Sonnet):
  - Elke dag om 23:00 (aangeroepen door orchestrator)
  - Analyseert alle trades van de dag
  - Output naar logs/analyst_evaluatie.log
  - Kost ~$0.05/dag
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import anthropic

log = logging.getLogger(__name__)

HAIKU_MODEL = "claude-haiku-4-5-20251001"
SONNET_MODEL = "claude-sonnet-4-6"

LAYER1_PROMPT = """Je bent een real-time trading filter. Beoordeel dit signaal in max 3 zinnen.

Signaal:
- Asset: {symbool}
- Richting: {richting}
- Strategie: {strategie_type}
- Reden: {bron}
- Sentiment score: {sentiment_score}
- Zekerheid agent: {zekerheid:.0%}

Antwoord ALLEEN in dit JSON formaat:
{{"beslissing": "ga_door" of "blokkeer", "reden": "korte uitleg", "risico": "laag" of "middel" of "hoog"}}

Blokkeer alleen bij duidelijke problemen (manipulatie, extreme risico's, tegenstrijdige signalen)."""

LAYER2_PROMPT = """Je bent een trading evaluator. Analyseer de trades van vandaag.

Datum: {datum}
Aantal trades: {aantal_trades}
Win rate: {win_rate:.0%}
Totale PnL: €{totaal_pnl:.2f}

Top 3 trades (beste/slechtste):
{trade_samenvatting}

Per agent statistieken:
{agent_stats}

Geef in max 200 woorden:
1. Wat werkte goed vandaag?
2. Wat werkte slecht?
3. Één concrete aanbeveling voor morgen."""


class ClaudeAnalyst:
    """Tweelags Claude AI analyse voor trading signalen."""

    def __init__(self, config: dict):
        self.config = config
        api_key = config.get('ai', {}).get('anthropic_api_key', '')
        self.client = anthropic.Anthropic(api_key=api_key) if api_key else None
        self._cache: dict[str, tuple[datetime, dict]] = {}  # symbool -> (tijd, resultaat)
        self.cache_ttl = timedelta(minutes=15)
        self.log_pad = Path('logs/analyst_evaluatie.log')
        self.log_pad.parent.mkdir(exist_ok=True)

    async def filter_signaal(self, signaal, sentiment_score: float = 0.0) -> dict:
        """
        Layer 1: Real-time filter voor sentiment + bot signalen.
        Returns: {beslissing: str, reden: str, risico: str}
        Timeout: 5 seconden. Bij timeout: signaal doorlaten.
        """
        if not self.client:
            return {'beslissing': 'ga_door', 'reden': 'geen API key', 'risico': 'onbekend'}

        # Cache check
        cache_key = f"{signaal.symbool}_{signaal.richting}"
        if cache_key in self._cache:
            cache_tijd, cache_result = self._cache[cache_key]
            if datetime.now() - cache_tijd < self.cache_ttl:
                log.debug(f"[ANALYST] Cache hit: {cache_key}")
                return cache_result

        prompt = LAYER1_PROMPT.format(
            symbool=signaal.symbool,
            richting=signaal.richting,
            strategie_type=signaal.strategie_type,
            bron=signaal.bron[:100],
            sentiment_score=sentiment_score,
            zekerheid=signaal.zekerheid
        )

        try:
            resultaat = await asyncio.wait_for(
                self._vraag_haiku(prompt),
                timeout=5.0
            )
            self._cache[cache_key] = (datetime.now(), resultaat)
            return resultaat
        except asyncio.TimeoutError:
            log.warning(f"[ANALYST] Layer 1 timeout voor {signaal.symbool} — signaal doorgelaten")
            return {'beslissing': 'ga_door', 'reden': 'timeout', 'risico': 'onbekend'}
        except Exception as e:
            log.error(f"[ANALYST] Layer 1 fout: {e}")
            return {'beslissing': 'ga_door', 'reden': f'fout: {e}', 'risico': 'onbekend'}

    async def _vraag_haiku(self, prompt: str) -> dict:
        """Vraag Claude Haiku en parse JSON antwoord."""
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: self.client.messages.create(
                model=HAIKU_MODEL,
                max_tokens=150,
                messages=[{'role': 'user', 'content': prompt}]
            )
        )
        tekst = response.content[0].text.strip()
        # Extraheer JSON
        start = tekst.find('{')
        einde = tekst.rfind('}') + 1
        if start >= 0 and einde > start:
            return json.loads(tekst[start:einde])
        return {'beslissing': 'ga_door', 'reden': 'ongeldig antwoord', 'risico': 'onbekend'}

    async def dagelijkse_evaluatie(self, trades: list, agent_stats: Optional[list] = None):
        """
        Layer 2: Dagelijkse evaluatie door Claude Sonnet.
        Schrijft resultaat naar logs/analyst_evaluatie.log.
        """
        if not self.client or not trades:
            return

        trades_met_pnl = [t for t in trades if t.pnl is not None]
        if not trades_met_pnl:
            return

        win_rate = len([t for t in trades_met_pnl if t.pnl > 0]) / len(trades_met_pnl)
        totaal_pnl = sum(t.pnl for t in trades_met_pnl)

        # Top 3 trades (gesorteerd op PnL)
        gesorteerd = sorted(trades_met_pnl, key=lambda t: t.pnl, reverse=True)
        top3_tekst = "\n".join([
            f"  {t.symbool} {t.richting}: €{t.pnl:.2f} ({t.pnl_pct:.1%}) — {t.reden_entry[:60]}"
            for t in (gesorteerd[:2] + gesorteerd[-1:])
        ])

        agent_stats_tekst = ""
        if agent_stats:
            for s in agent_stats:
                agent_stats_tekst += (
                    f"  {s['naam']}: {s['totaal_trades']} trades, "
                    f"win_rate={s['win_rate']:.0%}, "
                    f"kapitaal=€{s['kapitaal_pool']:.0f}\n"
                )

        prompt = LAYER2_PROMPT.format(
            datum=datetime.now().strftime('%Y-%m-%d'),
            aantal_trades=len(trades_met_pnl),
            win_rate=win_rate,
            totaal_pnl=totaal_pnl,
            trade_samenvatting=top3_tekst,
            agent_stats=agent_stats_tekst or "N/A"
        )

        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.client.messages.create(
                    model=SONNET_MODEL,
                    max_tokens=400,
                    messages=[{'role': 'user', 'content': prompt}]
                )
            )
            evaluatie = response.content[0].text.strip()

            # Schrijf naar log
            entry = {
                'datum': datetime.now().isoformat(),
                'trades': len(trades_met_pnl),
                'win_rate': win_rate,
                'totaal_pnl': totaal_pnl,
                'evaluatie': evaluatie
            }
            with open(self.log_pad, 'a', encoding='utf-8') as f:
                f.write(json.dumps(entry, ensure_ascii=False) + '\n')

            log.info(f"[ANALYST] Dagelijkse evaluatie geschreven: win={win_rate:.0%}, pnl=€{totaal_pnl:.2f}")

        except Exception as e:
            log.error(f"[ANALYST] Layer 2 fout: {e}")
