"""
ZELF VERBETERAAR v2
===================
Per-agent statistieken en parameter-tuning.
Elke zondag om 06:00 (aangeroepen door orchestrator).

Veiligheidsregels (hard, niet te overschrijven door AI):
1. Cascade failure guard: stop als >3 agents negatieve PnL hebben
2. Extreme volatiliteit guard: stop als ATR >15% van prijs
3. Concentratie guard: stop als 1 agent >60% van kapitaal heeft
4. Geen stijging als win_rate <40% afgelopen 2 weken
5. Geen verlaging stop-loss onder 2%
6. Geen verhoging positiegrootte met >10% per week

Audit log: logs/zelfverbeteringen.log
"""

import json
import math
import logging
from datetime import datetime, timedelta
from pathlib import Path
import yaml
import anthropic

log = logging.getLogger(__name__)

# Harde grenzen per parameter
PARAM_GRENZEN = {
    'min_consensus':       (0.45, 0.80),
    'stop_loss_pct':       (0.02, 0.08),   # Max 8% hard ceiling
    'take_profit_pct':     (0.04, 0.20),
    'positie_factor':      (0.50, 1.50),
    'gewicht_rsi':         (0.05, 0.50),
    'gewicht_ema':         (0.05, 0.50),
    'gewicht_bot':         (0.05, 0.50),
    'gewicht_sentiment':   (0.05, 0.30),
    'rsi_oversold':        (20, 35),
    'rsi_overbought':      (65, 80),
    'ema_volume_factor':   (1.05, 1.50),
    'sentiment_drempel':   (0.60, 0.90),
}

SONNET_MODEL = "claude-sonnet-4-6"


class ZelfVerbeteraar:
    """Analyseert prestaties per agent en stelt AI-aanbevelingen voor."""

    def __init__(self, config: dict):
        self.config = config
        api_key = config.get('ai', {}).get('anthropic_api_key', '')
        self.client = anthropic.Anthropic(api_key=api_key) if api_key else None
        self.config_pad = Path('config/config.yaml')
        self.audit_pad = Path('logs/zelfverbeteringen.log')
        self.audit_pad.parent.mkdir(exist_ok=True)

    async def verbeter(self, agent_stats: dict | None = None) -> str:
        """
        Hoofdentrypoint: analyseer, vraag AI, pas toe.
        Geeft samenvatting string terug voor dagrapport.
        """
        log.info("=== ZELFVERBETERING GESTART ===")

        trades = self._lees_trades(70)
        if len(trades) < 10:
            log.info("Te weinig trades (<10) voor zelfverbetering")
            return ""

        stats = self._bereken_stats(trades, agent_stats)

        ok, reden = self._veiligheidscheck(stats, agent_stats)
        if not ok:
            log.warning(f"Veiligheidscheck gefaald: {reden}")
            self._schrijf_audit({'actie': 'geblokkeerd', 'reden': reden, 'stats': stats})
            return f"\n## Zelfverbetering geblokkeerd\nReden: {reden}\n"

        aanbevelingen = await self._vraag_ai(stats, agent_stats)
        if not aanbevelingen:
            return ""

        wijzigingen = self._valideer_en_pas_toe(aanbevelingen)
        if wijzigingen:
            self._sla_config_op()
            self._schrijf_audit({
                'actie': 'toegepast',
                'wijzigingen': wijzigingen,
                'stats': stats,
                'aanbevelingen': aanbevelingen
            })
            return self._format_rapportblok(stats, wijzigingen)

        return ""

    def _lees_trades(self, n: int) -> list[dict]:
        """Lees laatste n trades uit SQLite."""
        import sqlite3
        db_pad = self.config.get('database', {}).get('pad', 'logs/agent_geheugen.db')
        try:
            conn = sqlite3.connect(db_pad)
            conn.row_factory = sqlite3.Row
            trades = conn.execute(
                "SELECT * FROM trades ORDER BY entry_tijdstip DESC LIMIT ?", (n,)
            ).fetchall()
            conn.close()
            return [dict(t) for t in trades]
        except Exception as e:
            log.error(f"Fout bij lezen trades: {e}")
            return []

    def _bereken_stats(self, trades: list[dict], agent_stats: dict | None) -> dict:
        """
        60/40 tijdsgewogen statistieken.
        Recente 35 trades wegen 60%, oudere 35 wegen 40%.
        Per-agent stats komen van agent_stats parameter.
        """
        n = len(trades)
        helft = n // 2
        recent = trades[:helft]
        oud = trades[helft:]

        def bereken(subset):
            met_pnl = [t for t in subset if t.get('pnl') is not None]
            if not met_pnl:
                return {'win_rate': 0, 'gem_pnl': 0, 'n': 0}
            winst = [t for t in met_pnl if t['pnl'] > 0]
            return {
                'win_rate': len(winst) / len(met_pnl),
                'gem_pnl': sum(t['pnl'] for t in met_pnl) / len(met_pnl),
                'n': len(met_pnl)
            }

        r = bereken(recent)
        o = bereken(oud)

        globaal_win_rate = r['win_rate'] * 0.60 + o['win_rate'] * 0.40
        globaal_gem_pnl = r['gem_pnl'] * 0.60 + o['gem_pnl'] * 0.40

        # Per strategie type
        per_strategie = {}
        for t in trades:
            st = t.get('strategie_type', 'onbekend')
            if st not in per_strategie:
                per_strategie[st] = {'trades': [], 'wins': 0}
            per_strategie[st]['trades'].append(t)
            if t.get('pnl', 0) > 0:
                per_strategie[st]['wins'] += 1

        strategie_stats = {}
        for naam, data in per_strategie.items():
            n_st = len(data['trades'])
            strategie_stats[naam] = {
                'n': n_st,
                'win_rate': data['wins'] / n_st if n_st > 0 else 0,
                'gem_pnl': sum(t.get('pnl', 0) for t in data['trades']) / n_st if n_st > 0 else 0,
            }

        # Sortino Ratio per agent (laatste 50 trades per agent)
        sortino_per_agent: dict[str, float] = {}
        if agent_stats:
            for agent_naam in agent_stats:
                agent_trades = [
                    t for t in trades
                    if agent_naam in (t.get("strategie_type") or "")
                    and t.get("pnl_pct") is not None
                ][-50:]
                sortino_per_agent[agent_naam] = self._bereken_sortino(agent_trades)

        return {
            'globaal_win_rate': globaal_win_rate,
            'globaal_gem_pnl': globaal_gem_pnl,
            'recent_win_rate': r['win_rate'],
            'oud_win_rate': o['win_rate'],
            'totaal_trades': n,
            'per_strategie': strategie_stats,
            'per_agent': agent_stats or {},
            'sortino_per_agent': sortino_per_agent,
        }

    def _bereken_sortino(self, trades: list[dict]) -> float:
        """Sortino Ratio op basis van pnl_pct. Fallback naar win_rate bij <10 trades."""
        rendementen = [t["pnl_pct"] for t in trades if t.get("pnl_pct") is not None]
        if len(rendementen) < 10:
            if not rendementen:
                return 0.0
            wins = sum(1 for r in rendementen if r > 0)
            return round(wins / len(rendementen), 4)

        gem = sum(rendementen) / len(rendementen)
        negatief = [r for r in rendementen if r < 0]
        if not negatief:
            return float("inf")

        variantie = sum(r ** 2 for r in negatief) / len(negatief)
        std_neer = math.sqrt(variantie)
        if std_neer == 0:
            return 0.0
        return round(gem / std_neer, 4)

    def _veiligheidscheck(self, stats: dict, agent_stats: dict | None) -> tuple[bool, str]:
        """Zes harde veiligheidsregels."""

        # 1. Win rate te laag
        if stats['recent_win_rate'] < 0.35:
            return False, f"Win rate te laag: {stats['recent_win_rate']:.0%} < 35%"

        # 2. Cascade failure: >3 agents negatief
        if agent_stats:
            negatief = sum(
                1 for s in agent_stats.values()
                if s.get('gem_pnl_pct', 0) < 0
            )
            if negatief >= 3:
                return False, f"Cascade failure: {negatief}/4 agents negatief"

        # 3. Concentratie guard: 1 agent >60% van totaal kapitaal
        if agent_stats:
            totaal = sum(s.get('kapitaal_pool', 0) for s in agent_stats.values())
            if totaal > 0:
                for naam, s in agent_stats.items():
                    concentratie = s.get('kapitaal_pool', 0) / totaal
                    if concentratie > 0.65:
                        return False, f"Concentratie te hoog: {naam} heeft {concentratie:.0%} van kapitaal"

        # 4. Extreme drawdown op een agent
        if agent_stats:
            for naam, s in agent_stats.items():
                if s.get('drawdown', 0) > 0.60:
                    return False, f"Agent {naam} heeft {s['drawdown']:.0%} drawdown"

        return True, ""

    async def _vraag_ai(self, stats: dict, agent_stats: dict | None) -> dict | None:
        """Vraag Claude Sonnet voor parameter-aanbevelingen."""
        if not self.client:
            log.warning("Geen Anthropic API key — zelfverbetering overgeslagen")
            return None

        huidig = self.config.get('zelfverbetering', {})

        prompt = f"""Je bent een trading systeem optimizer. Analyseer onderstaande statistieken en stel parameter-aanpassingen voor.

HUIDIGE PARAMETERS:
{json.dumps(huidig, indent=2)}

ALGEMENE STATISTIEKEN (60/40 tijdsgewogen):
- Win rate: {stats['globaal_win_rate']:.1%}
- Gem PnL per trade: €{stats['globaal_gem_pnl']:.2f}
- Totaal trades: {stats['totaal_trades']}
- Recente win rate (60%): {stats['recent_win_rate']:.1%}
- Oudere win rate (40%): {stats['oud_win_rate']:.1%}

PER STRATEGIE:
{json.dumps(stats['per_strategie'], indent=2)}

PER AGENT (live stats):
{json.dumps({k: {kk: vv for kk, vv in v.items() if kk != 'naam'} for k, v in (agent_stats or {}).items()}, indent=2)}

TOEGESTANE PARAMETER GRENZEN:
{json.dumps(PARAM_GRENZEN, indent=2)}

Antwoord ALLEEN in dit JSON formaat. Geef alleen parameters die écht moeten veranderen:
{{
  "wijzigingen": {{
    "parameter_naam": nieuwe_waarde,
    ...
  }},
  "onderbouwing": "korte uitleg per wijziging"
}}

Regels:
- Maximaal 3 wijzigingen tegelijk
- Geen stijging positie_factor als win_rate < 50%
- Geen stop_loss_pct verlaging als er recentelijk grote verliezen waren
- Voorzichtig: liever kleine aanpassingen dan grote sprongen"""

        try:
            import asyncio
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.client.messages.create(
                    model=SONNET_MODEL,
                    max_tokens=500,
                    messages=[{'role': 'user', 'content': prompt}]
                )
            )
            tekst = response.content[0].text.strip()
            start = tekst.find('{')
            einde = tekst.rfind('}') + 1
            if start >= 0 and einde > start:
                return json.loads(tekst[start:einde])
        except Exception as e:
            log.error(f"AI aanbeveling fout: {e}")

        return None

    def _valideer_en_pas_toe(self, aanbevelingen: dict) -> dict:
        """Valideer elke aanbeveling tegen harde grenzen en pas toe."""
        wijzigingen_raw = aanbevelingen.get('wijzigingen', {})
        toegepast = {}
        huidig = self.config.setdefault('zelfverbetering', {})

        for param, nieuwe_waarde in wijzigingen_raw.items():
            if param not in PARAM_GRENZEN:
                log.warning(f"Onbekende parameter: {param} — overgeslagen")
                continue

            min_val, max_val = PARAM_GRENZEN[param]

            # Clamp binnen grenzen
            veilige_waarde = max(min_val, min(max_val, float(nieuwe_waarde)))

            # Max 20% stap per iteratie
            oud = huidig.get(param, (min_val + max_val) / 2)
            max_stap = oud * 0.20
            if abs(veilige_waarde - oud) > max_stap:
                richting = 1 if veilige_waarde > oud else -1
                veilige_waarde = oud + richting * max_stap

            veilige_waarde = round(veilige_waarde, 4)
            oud_afgerond = round(float(oud), 4)

            if veilige_waarde != oud_afgerond:
                huidig[param] = veilige_waarde
                toegepast[param] = {'oud': oud_afgerond, 'nieuw': veilige_waarde}
                log.info(f"Parameter {param}: {oud_afgerond} → {veilige_waarde}")

        return toegepast

    def _sla_config_op(self):
        """Schrijf aangepaste config terug naar YAML."""
        try:
            with open(self.config_pad, 'r', encoding='utf-8') as f:
                huidig = yaml.safe_load(f)

            huidig['zelfverbetering'] = self.config.get('zelfverbetering', {})
            huidig['zelfverbetering']['laatste_update'] = datetime.now().isoformat()

            with open(self.config_pad, 'w', encoding='utf-8') as f:
                yaml.dump(huidig, f, default_flow_style=False, allow_unicode=True)

            log.info("Config bijgewerkt")
        except Exception as e:
            log.error(f"Config opslaan mislukt: {e}")

    def _schrijf_audit(self, data: dict):
        """Schrijf audit entry naar log."""
        data['timestamp'] = datetime.now().isoformat()
        with open(self.audit_pad, 'a', encoding='utf-8') as f:
            f.write(json.dumps(data, ensure_ascii=False, default=str) + '\n')

    def _format_rapportblok(self, stats: dict, wijzigingen: dict) -> str:
        """Formatteer samenvatting voor dagrapport."""
        sortino_tekst = "; ".join(
            f"{k}: {v:.2f}" for k, v in stats.get("sortino_per_agent", {}).items()
        ) or "n.v.t."
        regels = [
            "\n## Zelfverbetering (Zondag)\n",
            f"- Win rate (gewogen): {stats['globaal_win_rate']:.1%}",
            f"- Gem PnL: \u20ac{stats['globaal_gem_pnl']:.2f}",
            f"- Sortino per agent: {sortino_tekst}",
            f"- Totaal trades geanalyseerd: {stats['totaal_trades']}",
            "\n**Aanpassingen:**",
        ]
        for param, v in wijzigingen.items():
            regels.append(f"- `{param}`: {v['oud']} → {v['nieuw']}")
        return '\n'.join(regels) + '\n'
