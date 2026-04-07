"""
DATA ARBITRAGE AGENT
====================
Kapitaal: €100 (voormalige reserve)
Edge: beantwoord Polymarket vragen met publieke databronnen

Werkwijze:
1. Scan open Polymarket markten elke 30 minuten
2. Filter vragen die te beantwoorden zijn met publieke data
3. Vergelijk marktprijs met eigen zekerheid
4. Als mispricing > 20% EN zekerheid >= 85%: neem positie

Kelly criterion: f* = (p - m) / (1 - m)
- p = eigen zekerheid
- m = marktprijs

Limieten:
- Geen stop-loss (binaire markten)
- Force exit bij 80% winst
- Max €10 per positie
- Max 5 gelijktijdige posities
- Instapprijs: 0.005 – 0.60 USDC
"""

import asyncio
import logging
import math
import aiohttp
from datetime import datetime
from pathlib import Path
from typing import Optional

from agent.agents.base_agent import BaseAgent
from agent.risk.risk_manager import TradeSignaal

log = logging.getLogger(__name__)

MAX_POSITIES = 5
MAX_INZET_EUR = 10.0
MIN_ZEKERHEID = 0.85
MIN_MISPRICING = 0.20
MAX_INSTAP = 0.60
MIN_INSTAP = 0.005
FORCE_EXIT_WINST = 0.80
SCAN_INTERVAL = 1800  # 30 minuten

LOG_PAD = Path('logs/data_arbitrage_agent.log')


class DataArbitrageAgent(BaseAgent):
    """
    Exploiteert Polymarket vragen die beantwoord kunnen worden
    met publieke, gratis databronnen.
    """

    naam = "data_arbitrage"
    cooldown_uren = 2

    def __init__(self, config, executor, geheugen):
        """Initialiseer met cache voor Polymarket prijzen."""
        super().__init__(config, executor, geheugen)
        self._polymarket_prijzen: dict = {}
        self._laatste_scan: Optional[datetime] = None

    def _initieel_kapitaal(self) -> float:
        return 100.0

    def _clamp_stop_loss(self, stop_loss_pct: float) -> float:
        """Binaire markten: geen stop-loss."""
        return 1.0

    async def _genereer_signalen(self, markt_data, regime, sentiment, bot_patronen):
        """Scan Polymarket elke 30 minuten, genereer signalen bij mispricing."""
        signalen = []

        if len(self.open_posities) >= MAX_POSITIES:
            log.debug(f"[DATA_ARB] Max posities ({MAX_POSITIES}) bereikt")
            return signalen

        # Throttle: scan maximaal elke 30 minuten
        nu = datetime.now()
        if self._laatste_scan and (nu - self._laatste_scan).total_seconds() < SCAN_INTERVAL:
            return signalen
        self._laatste_scan = nu
        log.info(f"[DATA_ARB] Scan start: {nu:%H:%M}")

        kansen = await self._scan_polymarket()
        for kans in kansen:
            signaal = self._evalueer_kans(kans)
            if signaal:
                # Cache de marktprijs zodat executor de juiste entry prijs kan gebruiken
                self._polymarket_prijzen[kans['markt_id']] = kans['markt_prijs']
                signalen.append(signaal)
                self._log_kans(kans, signaal)

        return signalen

    async def run_cyclus(self, markt_data: dict, regime: dict, sentiment, bot_patronen):
        """Override om Polymarket prijzen in markt_data te injecteren voor paper trading."""
        # Injecteer gecachede Polymarket prijzen in markt_data formaat
        verrijkt = dict(markt_data) if markt_data else {}
        for markt_id, prijs in self._polymarket_prijzen.items():
            verrijkt[markt_id] = {'prijs': prijs, 'volume': 1.0, 'gem_volume': 1.0}
        await super().run_cyclus(verrijkt, regime, sentiment, bot_patronen)

    async def _scan_polymarket(self) -> list[dict]:
        """
        Haal open Polymarket markten op via Gamma API.
        Filter: sluit binnen 48u, volume >$1000, prijs 0.05-0.60.
        """
        from datetime import timezone, timedelta as _td
        kansen = []
        nu_utc = datetime.now(timezone.utc)
        deadline_max = nu_utc + _td(hours=48)

        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as ses:
                async with ses.get(
                    'https://gamma-api.polymarket.com/markets',
                    params={
                        'active': 'true',
                        'closed': 'false',
                        'limit': '100',
                        'volume_num_min': '1000',
                    }
                ) as resp:
                    if resp.status != 200:
                        log.warning(f"[DATA_ARB] Gamma API status {resp.status}")
                        return []
                    markten = await resp.json()

            if not isinstance(markten, list):
                markten = markten.get('data', [])

            gefilterd = 0
            for markt in markten:
                # Filter: sluit binnen 48 uur
                eind = markt.get('endDate') or markt.get('end_date') or ''
                if eind:
                    try:
                        if eind.endswith('Z'):
                            eind = eind[:-1] + '+00:00'
                        eind_dt = datetime.fromisoformat(eind)
                        if eind_dt.tzinfo is None:
                            eind_dt = eind_dt.replace(tzinfo=timezone.utc)
                        if eind_dt > deadline_max:
                            gefilterd += 1
                            continue
                    except (ValueError, TypeError):
                        pass

                analyse = await self._analyseer_markt(markt)
                if analyse:
                    kansen.append(analyse)

            log.info(
                f"[DATA_ARB] Scan klaar: {len(markten)} markten, "
                f"{gefilterd} >48u gefilterd, {len(kansen)} kansen"
            )

        except asyncio.TimeoutError:
            log.warning("[DATA_ARB] Polymarket scan timeout")
        except Exception as e:
            log.error(f"[DATA_ARB] Scan fout: {e}", exc_info=True)

        return kansen

    async def _analyseer_markt(self, markt: dict) -> Optional[dict]:
        """
        Analyseer één markt: kan ik dit beantwoorden?
        Retourneert kans-dict of None.
        """
        vraag = markt.get('question', '')
        tokens = markt.get('tokens', [])
        if not tokens or not vraag:
            return None

        # Haal Ja-token prijs op
        ja_token = next((t for t in tokens if t.get('outcome', '').upper() in ('YES', 'JA')), None)
        if not ja_token:
            return None

        try:
            markt_prijs = float(ja_token.get('price', 0))
        except (ValueError, TypeError):
            return None

        # Filter op instapprijs bereik
        if not (MIN_INSTAP <= markt_prijs <= MAX_INSTAP):
            return None

        # Probeer antwoord te vinden via databronnen
        databron_resultaat = await self._zoek_antwoord(vraag)
        if not databron_resultaat:
            return None

        zekerheid = databron_resultaat['zekerheid']
        antwoord = databron_resultaat['antwoord']  # True/False
        databron = databron_resultaat['bron']

        if zekerheid < MIN_ZEKERHEID:
            return None

        # Bereken mispricing
        verwacht = zekerheid if antwoord else (1 - zekerheid)
        mispricing = abs(verwacht - markt_prijs)

        if mispricing < MIN_MISPRICING:
            return None

        # Fractional Kelly inzet
        inzet = self._bereken_kelly_inzet(
            zekerheid if antwoord else (1 - zekerheid),
            markt_prijs
        )

        return {
            'markt_id': markt.get('condition_id', markt.get('id', 'onbekend')),
            'vraag': vraag[:120],
            'databron': databron,
            'antwoord': antwoord,
            'zekerheid': zekerheid,
            'markt_prijs': markt_prijs,
            'mispricing': mispricing,
            'richting': 'long' if antwoord else 'short',
            'kelly_inzet': round(inzet, 2),
        }

    async def _zoek_antwoord(self, vraag: str) -> Optional[dict]:
        """
        Probeer de Polymarket vraag te beantwoorden via publieke databronnen.
        Retourneert {antwoord: bool, zekerheid: float, bron: str} of None.
        """
        vraag_lower = vraag.lower()

        # ── Crypto prijs vragen ───────────────────────────────────────────
        if any(c in vraag_lower for c in ['bitcoin', 'btc', 'ethereum', 'eth']):
            return await self._check_crypto_prijs(vraag)

        # ── Aardbeving vragen ─────────────────────────────────────────────
        if any(w in vraag_lower for w in ['earthquake', 'seismic', 'aardbeving', 'magnitude']):
            return await self._check_aardbeving(vraag)

        # ── Weer vragen ───────────────────────────────────────────────────
        if any(w in vraag_lower for w in ['temperature', 'rainfall', 'storm', 'hurricane',
                                           'celsius', 'fahrenheit', 'degrees']):
            return await self._check_weer(vraag)

        # ── Sport vragen (al gespeeld) ────────────────────────────────────
        if any(w in vraag_lower for w in ['win', 'beat', 'defeat', 'champion', 'score']):
            # Alleen als het om een reeds gespeelde wedstrijd gaat
            return await self._check_sport(vraag)

        return None

    async def _check_crypto_prijs(self, vraag: str) -> Optional[dict]:
        """Beantwoord crypto prijs vragen via CoinGecko."""
        import re
        vraag_lower = vraag.lower()

        # Herken patroon: "Will BTC be above $X by [date]?"
        prijs_match = re.search(r'\$?([\d,]+)', vraag)
        if not prijs_match:
            return None

        try:
            drempel = float(prijs_match.group(1).replace(',', ''))
        except ValueError:
            return None

        symbool = 'bitcoin' if 'btc' in vraag_lower or 'bitcoin' in vraag_lower else 'ethereum'
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as ses:
                async with ses.get(
                    f'https://api.coingecko.com/api/v3/simple/price',
                    params={'ids': symbool, 'vs_currencies': 'usd'}
                ) as resp:
                    data = await resp.json()
            huidige_prijs = data[symbool]['usd']
        except Exception:
            return None

        boven = huidige_prijs > drempel
        # Hoe ver van drempel = meer zekerheid
        afstand_pct = abs(huidige_prijs - drempel) / drempel
        zekerheid = min(0.97, 0.85 + afstand_pct * 2)

        return {
            'antwoord': boven,
            'zekerheid': zekerheid,
            'bron': f'coingecko: {symbool}=${huidige_prijs:.0f} vs drempel ${drempel:.0f}'
        }

    async def _check_aardbeving(self, vraag: str) -> Optional[dict]:
        """Beantwoord aardbeving vragen via USGS."""
        import re
        import urllib.parse
        from datetime import timedelta

        # Haal recente aardbevingen op (afgelopen 7 dagen, M4+)
        try:
            eind = datetime.utcnow()
            begin = eind - timedelta(days=7)
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as ses:
                async with ses.get(
                    'https://earthquake.usgs.gov/fdsnws/event/1/query',
                    params={
                        'format': 'geojson',
                        'starttime': begin.strftime('%Y-%m-%d'),
                        'endtime': eind.strftime('%Y-%m-%d'),
                        'minmagnitude': '4.0',
                        'limit': '50'
                    }
                ) as resp:
                    data = await resp.json()
        except Exception:
            return None

        events = data.get('features', [])
        vraag_lower = vraag.lower()

        # Zoek naar magnitude drempel in vraag
        mag_match = re.search(r'magnitude\s+([\d.]+)', vraag_lower)
        if not mag_match:
            return None

        try:
            drempel_mag = float(mag_match.group(1))
        except ValueError:
            return None

        # Is er een aardbeving geweest boven de drempel?
        gevonden = any(
            e['properties']['mag'] >= drempel_mag
            for e in events
            if e['properties'].get('mag') is not None
        )

        return {
            'antwoord': gevonden,
            'zekerheid': 0.95,  # USGS data is zeer betrouwbaar
            'bron': f'usgs: {len(events)} events M4+ afgelopen 7d, gevonden M{drempel_mag}+: {gevonden}'
        }

    async def _check_weer(self, vraag: str) -> Optional[dict]:
        """Beantwoord weervragen via Open-Meteo (gratis, geen API key)."""
        # Vereenvoudigd: alleen temperatuur vragen voor Amsterdam (uitbreidbaar)
        import re
        vraag_lower = vraag.lower()

        temp_match = re.search(r'(\d+)\s*(?:degrees|°|celsius|fahrenheit)', vraag_lower)
        if not temp_match:
            return None

        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as ses:
                async with ses.get(
                    'https://api.open-meteo.com/v1/forecast',
                    params={
                        'latitude': '52.37',
                        'longitude': '4.90',
                        'current_weather': 'true',
                        'temperature_unit': 'celsius'
                    }
                ) as resp:
                    data = await resp.json()
            huidige_temp = data['current_weather']['temperature']
        except Exception:
            return None

        try:
            drempel = float(temp_match.group(1))
            if 'fahrenheit' in vraag_lower:
                drempel = (drempel - 32) * 5 / 9
        except ValueError:
            return None

        boven = huidige_temp > drempel
        afstand = abs(huidige_temp - drempel)
        zekerheid = min(0.95, 0.85 + afstand / 20)

        return {
            'antwoord': boven,
            'zekerheid': zekerheid,
            'bron': f'open-meteo: AMS temp={huidige_temp:.1f}°C vs drempel={drempel:.1f}°C'
        }

    async def _check_sport(self, vraag: str) -> Optional[dict]:
        """
        Beantwoord sport vragen via ESPN public API.
        Werkt voor NBA, NFL, en soccer. Alleen al gespeelde wedstrijden.
        """
        import re
        vraag_lower = vraag.lower()

        # Detecteer sport
        espn_endpoints = []
        if any(t in vraag_lower for t in ['nba', 'lakers', 'celtics', 'bucks', 'warriors']):
            espn_endpoints.append(
                'https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard'
            )
        if any(t in vraag_lower for t in ['nfl', 'chiefs', 'eagles', 'cowboys', 'patriots']):
            espn_endpoints.append(
                'https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard'
            )
        if any(t in vraag_lower for t in
               ['premier league', 'la liga', 'bundesliga', 'serie a',
                'champions league', 'uefa', 'fifa']):
            espn_endpoints.append(
                'https://site.api.espn.com/apis/site/v2/sports/soccer/uefa.champions/scoreboard'
            )

        if not espn_endpoints:
            return None

        # Zoek teamnamen in vraag (woorden met hoofdletter)
        teams_in_vraag = re.findall(r'[A-Z][a-zA-Z]+', vraag)

        for endpoint in espn_endpoints:
            try:
                async with aiohttp.ClientSession(
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as ses:
                    async with ses.get(endpoint) as resp:
                        if resp.status != 200:
                            continue
                        data = await resp.json()

                events = data.get('events', [])
                for event in events:
                    status = event.get('status', {}).get('type', {})
                    if not status.get('completed', False):
                        continue  # Alleen gespeelde wedstrijden

                    # Controleer of teams uit de vraag in dit event zitten
                    naam = event.get('name', '').lower()
                    gevonden_teams = sum(
                        1 for t in teams_in_vraag if t.lower() in naam
                    )
                    if gevonden_teams < 1:
                        continue

                    # Haal winnaar op
                    competities = event.get('competitions', [{}])
                    concurrenten = competities[0].get('competitors', []) if competities else []
                    winnaar = next(
                        (c['team']['displayName'] for c in concurrenten
                         if c.get('winner', False)),
                        None
                    )
                    if not winnaar:
                        continue

                    # Bepaal of vraag winnaar overeenkomt
                    winnaar_lower = winnaar.lower()
                    antwoord = any(t.lower() in winnaar_lower for t in teams_in_vraag)

                    return {
                        'antwoord': antwoord,
                        'zekerheid': 0.97,  # ESPN score is definitief
                        'bron': f'espn: winnaar={winnaar} | event={event.get("name","?")}'
                    }

            except Exception as e:
                log.debug(f"[DATA_ARB] ESPN {endpoint} fout: {e}")

        return None

    def _bereken_kelly_inzet(self, p: float, m: float) -> float:
        """
        Fractional Kelly inzet in euros.
        Schaling: <10 trades→0.25, <50→0.50, anders→0.75.

        f* = (p - m) / (1 - m)
        """
        if m >= 1.0:
            return 1.0

        f_star = (p - m) / (1 - m)
        if f_star <= 0:
            return 0.0

        try:
            prestaties = self.geheugen.analyseer_prestaties()
            agent_stats = prestaties.get("per_strategie", {}).get(self.naam, {})
            trades = int(agent_stats.get("totaal_trades", 0))
        except Exception:
            trades = 0

        if trades < 10:
            schaal = 0.25
        elif trades < 50:
            schaal = 0.50
        else:
            schaal = 0.75

        f_safe = f_star * schaal
        inzet = f_safe * self.kapitaal_pool
        return round(max(1.0, min(MAX_INZET_EUR, inzet)), 2)

    @staticmethod
    def _kelly(p: float, m: float) -> float:
        """
        Kelly criterion: f* = (p - m) / (1 - m)
        p = eigen zekerheid (kans op juist antwoord)
        m = marktprijs (implied kans)
        """
        if m >= 1.0:
            return 0.0
        kelly = (p - m) / (1 - m)
        return max(0.0, min(kelly, 0.25))  # Max 25% van kapitaal per trade

    def _evalueer_kans(self, kans: dict) -> Optional[TradeSignaal]:
        """Maak TradeSignaal van een gevalideerde kans."""
        return TradeSignaal(
            symbool=kans['markt_id'],
            richting=kans['richting'],
            strategie_type='data_arbitrage',
            verwacht_rendement=kans['mispricing'],
            win_kans=kans['zekerheid'],
            stop_loss_pct=1.0,          # Geen stop-loss
            take_profit_pct=FORCE_EXIT_WINST,
            bron=f"{kans['databron']} | mispricing={kans['mispricing']:.0%}",
            zekerheid=kans['zekerheid'],
            regime='polymarket'
        )

    def _moet_sluiten_strategie(self, positie, huidige_prijs: float, regime: dict) -> bool:
        """Sluit bij 80% winst (binaire markt nadert resolutie)."""
        try:
            pnl_pct = float(positie.bereken_pnl_pct(huidige_prijs))
        except Exception:
            return False
        if pnl_pct >= FORCE_EXIT_WINST:
            log.info(f"[DATA_ARB] Force exit: {positie.symbool} winst={pnl_pct:.0%}")
            return True
        return False

    def _log_kans(self, kans: dict, signaal: Optional[TradeSignaal]):
        """Schrijf gedetailleerde log naar data_arbitrage_agent.log."""
        LOG_PAD.parent.mkdir(exist_ok=True)
        beslissing = 'TRADE' if signaal else 'SKIP'
        kelly_inzet = kans.get('kelly_inzet', 0)
        entry = (
            f"[{datetime.now():%Y-%m-%d %H:%M}] {beslissing}\n"
            f"  Vraag:    {kans['vraag']}\n"
            f"  Databron: {kans['databron']}\n"
            f"  Antwoord: {'JA' if kans['antwoord'] else 'NEE'} | "
            f"zekerheid={kans['zekerheid']:.0%}\n"
            f"  Markt:    {kans['markt_prijs']:.3f} | "
            f"mispricing={kans['mispricing']:.0%}\n"
            f"  Kelly:    €{kelly_inzet:.2f}\n"
            f"  Richting: {kans['richting']}\n\n"
        )
        with open(LOG_PAD, 'a', encoding='utf-8') as f:
            f.write(entry)
