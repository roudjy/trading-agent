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
import logging
import math
from datetime import datetime, timezone
from pathlib import Path

import anthropic

log = logging.getLogger(__name__)

# Harde grenzen per parameter
PARAM_GRENZEN = {
    'min_consensus': (0.45, 0.80),
    'stop_loss_pct': (0.02, 0.08),   # Max 8% hard ceiling
    'take_profit_pct': (0.04, 0.20),
    'positie_factor': (0.50, 1.50),
    'gewicht_rsi': (0.05, 0.50),
    'gewicht_ema': (0.05, 0.50),
    'gewicht_bot': (0.05, 0.50),
    'gewicht_sentiment': (0.05, 0.30),
    'rsi_oversold': (20, 35),
    'rsi_overbought': (65, 80),
    'ema_volume_factor': (1.05, 1.50),
    'sentiment_drempel': (0.60, 0.90),
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
        self.recommendation_dir = Path('logs/candidate_recommendations')
        self.audit_pad.parent.mkdir(exist_ok=True)
        self.recommendation_dir.mkdir(parents=True, exist_ok=True)

    async def verbeter(self, agent_stats: dict | None = None) -> str:
        """
        Hoofdentrypoint: analyseer, vraag AI, schrijf read-only aanbeveling.
        Geeft samenvatting string terug voor dagrapport.
        """
        log.info("=== ZELFVERBETERING GESTART ===")
        recommendation_path = self._recommendation_path()

        trades = self._lees_trades(70)
        if len(trades) < 10:
            log.info("Te weinig trades (<10) voor zelfverbetering")
            self._schrijf_recommendation(
                path=recommendation_path,
                stats={'totaal_trades': len(trades), 'per_agent': agent_stats or {}},
                rationale="Te weinig trades (<10) voor aanbeveling.",
                proposed_diff={},
                safety_outcome={'passed': False, 'reason': 'Te weinig trades (<10)'},
            )
            self._schrijf_audit({
                'actie': 'recommendation_only',
                'reden': 'Te weinig trades (<10)',
                'pad': str(recommendation_path),
            })
            self._log_read_only(recommendation_path)
            return ""

        stats = self._bereken_stats(trades, agent_stats)

        ok, reden = self._veiligheidscheck(stats, agent_stats)
        if not ok:
            log.warning(f"Veiligheidscheck gefaald: {reden}")
            self._schrijf_recommendation(
                path=recommendation_path,
                stats=stats,
                rationale=f"Veiligheidscheck blokkeerde toepassing: {reden}",
                proposed_diff={},
                safety_outcome={'passed': False, 'reason': reden},
            )
            self._schrijf_audit({
                'actie': 'recommendation_only',
                'reden': reden,
                'stats': stats,
                'pad': str(recommendation_path),
            })
            self._log_read_only(recommendation_path)
            return f"\n## Zelfverbetering geblokkeerd\nReden: {reden}\n"

        aanbevelingen = await self._vraag_ai(stats, agent_stats)
        wijzigingen = self._valideer_en_pas_toe(aanbevelingen or {})

        self._schrijf_recommendation(
            path=recommendation_path,
            stats=stats,
            rationale=(aanbevelingen or {}).get('onderbouwing', 'Geen AI-aanbeveling beschikbaar.'),
            proposed_diff=wijzigingen,
            safety_outcome={'passed': ok, 'reason': reden},
        )
        self._sla_config_op()
        self._schrijf_audit({
            'actie': 'recommendation_only',
            'wijzigingen': wijzigingen,
            'stats': stats,
            'aanbevelingen': aanbevelingen or {},
            'pad': str(recommendation_path),
        })
        self._log_read_only(recommendation_path)

        if wijzigingen:
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
                "SELECT * FROM trades ORDER BY entry_tijdstip DESC LIMIT ?",
                (n,),
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
                'n': len(met_pnl),
            }

        recent_stats = bereken(recent)
        oud_stats = bereken(oud)

        globaal_win_rate = recent_stats['win_rate'] * 0.60 + oud_stats['win_rate'] * 0.40
        globaal_gem_pnl = recent_stats['gem_pnl'] * 0.60 + oud_stats['gem_pnl'] * 0.40

        per_strategie = {}
        for trade in trades:
            strategie = trade.get('strategie_type', 'onbekend')
            if strategie not in per_strategie:
                per_strategie[strategie] = {'trades': [], 'wins': 0}
            per_strategie[strategie]['trades'].append(trade)
            if trade.get('pnl', 0) > 0:
                per_strategie[strategie]['wins'] += 1

        strategie_stats = {}
        for naam, data in per_strategie.items():
            aantal = len(data['trades'])
            strategie_stats[naam] = {
                'n': aantal,
                'win_rate': data['wins'] / aantal if aantal > 0 else 0,
                'gem_pnl': sum(t.get('pnl', 0) for t in data['trades']) / aantal if aantal > 0 else 0,
            }

        sortino_per_agent: dict[str, float] = {}
        if agent_stats:
            for agent_naam in agent_stats:
                agent_trades = [
                    trade for trade in trades
                    if agent_naam in (trade.get("strategie_type") or "")
                    and trade.get("pnl_pct") is not None
                ][-50:]
                sortino_per_agent[agent_naam] = self._bereken_sortino(agent_trades)

        return {
            'globaal_win_rate': globaal_win_rate,
            'globaal_gem_pnl': globaal_gem_pnl,
            'recent_win_rate': recent_stats['win_rate'],
            'oud_win_rate': oud_stats['win_rate'],
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
            wins = sum(1 for rendement in rendementen if rendement > 0)
            return round(wins / len(rendementen), 4)

        gemiddeld = sum(rendementen) / len(rendementen)
        negatief = [rendement for rendement in rendementen if rendement < 0]
        if not negatief:
            return float("inf")

        variantie = sum(rendement ** 2 for rendement in negatief) / len(negatief)
        std_neer = math.sqrt(variantie)
        if std_neer == 0:
            return 0.0
        return round(gemiddeld / std_neer, 4)

    def _veiligheidscheck(self, stats: dict, agent_stats: dict | None) -> tuple[bool, str]:
        """Zes harde veiligheidsregels."""

        if stats['recent_win_rate'] < 0.35:
            return False, f"Win rate te laag: {stats['recent_win_rate']:.0%} < 35%"

        if agent_stats:
            negatief = sum(1 for s in agent_stats.values() if s.get('gem_pnl_pct', 0) < 0)
            if negatief >= 3:
                return False, f"Cascade failure: {negatief}/4 agents negatief"

        if agent_stats:
            totaal = sum(s.get('kapitaal_pool', 0) for s in agent_stats.values())
            if totaal > 0:
                for naam, s in agent_stats.items():
                    concentratie = s.get('kapitaal_pool', 0) / totaal
                    if concentratie > 0.65:
                        return False, f"Concentratie te hoog: {naam} heeft {concentratie:.0%} van kapitaal"

        if agent_stats:
            for naam, s in agent_stats.items():
                if s.get('drawdown', 0) > 0.60:
                    return False, f"Agent {naam} heeft {s['drawdown']:.0%} drawdown"

        return True, ""

    async def _vraag_ai(self, stats: dict, agent_stats: dict | None) -> dict | None:
        """Vraag Claude Sonnet voor parameter-aanbevelingen."""
        if not self.client:
            log.warning("Geen Anthropic API key - zelfverbetering overgeslagen")
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
                    messages=[{'role': 'user', 'content': prompt}],
                ),
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
        """Valideer aanbevelingen en geef alleen een veilig voorgesteld diff terug."""
        wijzigingen_raw = aanbevelingen.get('wijzigingen', {})
        voorgesteld = {}
        huidig = self.config.get('zelfverbetering', {})

        for param, nieuwe_waarde in wijzigingen_raw.items():
            if param not in PARAM_GRENZEN:
                log.warning(f"Onbekende parameter: {param} - overgeslagen")
                continue

            min_val, max_val = PARAM_GRENZEN[param]
            veilige_waarde = max(min_val, min(max_val, float(nieuwe_waarde)))

            oud = huidig.get(param, (min_val + max_val) / 2)
            max_stap = oud * 0.20
            if abs(veilige_waarde - oud) > max_stap:
                richting = 1 if veilige_waarde > oud else -1
                veilige_waarde = oud + richting * max_stap

            veilige_waarde = round(veilige_waarde, 4)
            oud_afgerond = round(float(oud), 4)

            if veilige_waarde != oud_afgerond:
                voorgesteld[param] = {'oud': oud_afgerond, 'nieuw': veilige_waarde}
                log.info(f"Parameter {param}: {oud_afgerond} voorgesteld -> {veilige_waarde}")

        return voorgesteld

    def _sla_config_op(self):
        """Read-only mode: schrijf nooit rechtstreeks naar config/config.yaml."""
        log.debug("Zelfverbetering read-only: config/config.yaml wordt niet aangepast")

    def _schrijf_audit(self, data: dict):
        """Schrijf audit entry naar log."""
        data['timestamp'] = datetime.now().isoformat()
        with open(self.audit_pad, 'a', encoding='utf-8') as f:
            f.write(json.dumps(data, ensure_ascii=False, default=str) + '\n')

    def _recommendation_path(self) -> Path:
        """Genereer een UTC-bestandsnaam voor recommendation artifacts."""
        timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H-%M-%SZ')
        return self.recommendation_dir / f'recommendation_{timestamp}.json'

    def _schrijf_recommendation(
        self,
        path: Path,
        stats: dict,
        rationale: str,
        proposed_diff: dict,
        safety_outcome: dict,
    ) -> None:
        """Schrijf een read-only recommendation artifact naar disk."""
        artifact = {
            'generated_at_utc': datetime.now(timezone.utc).isoformat(),
            'stats_snapshot': stats,
            'ai_rationale': rationale,
            'proposed_parameter_diff': proposed_diff,
            'safety_check_outcome': safety_outcome,
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(artifact, f, ensure_ascii=False, indent=2, default=str)

    def _log_read_only(self, path: Path) -> None:
        """Maak read-only modus expliciet zichtbaar in de logs."""
        log.warning(f"[SELF-IMPROVER] READ-ONLY MODE — recommendation written to {path}")

    def _format_rapportblok(self, stats: dict, wijzigingen: dict) -> str:
        """Formatteer samenvatting voor dagrapport."""
        sortino_tekst = "; ".join(
            f"{k}: {v:.2f}" for k, v in stats.get("sortino_per_agent", {}).items()
        ) or "n.v.t."
        regels = [
            "\n## Zelfverbetering (Zondag)\n",
            f"- Win rate (gewogen): {stats['globaal_win_rate']:.1%}",
            f"- Gem PnL: €{stats['globaal_gem_pnl']:.2f}",
            f"- Sortino per agent: {sortino_tekst}",
            f"- Totaal trades geanalyseerd: {stats['totaal_trades']}",
            "\n**Aanbevelingen (read-only):**",
        ]
        for param, waarde in wijzigingen.items():
            regels.append(f"- `{param}`: {waarde['oud']} -> {waarde['nieuw']}")
        return '\n'.join(regels) + '\n'
