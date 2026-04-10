"""
AGENT GEHEUGEN
==============
Slaat alle trades op en leert van het verleden.
De agent wordt elke dag slimmer door zijn eigen geschiedenis te analyseren.

Opgeslagen in een lokale SQLite database - geen cloud, alles bij jou.
"""

import sqlite3
import json
import time
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

log = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Database hulpfuncties
# ──────────────────────────────────────────────
def _db_connect(pad):
    """
    Open een SQLite connectie met:
    - WAL mode (concurrent lezen/schrijven)
    - busy_timeout 5s (SQLite-level wachten)
    - timeout 30s (connectie-level wachten)
    - check_same_thread=False (asyncio-safe)
    """
    conn = sqlite3.connect(
        str(pad),
        timeout=30,
        check_same_thread=False
    )
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def _db_uitvoeren(pad, sql, params=(), max_pogingen=5):
    """
    Voer een write-query uit met exponentieel backoff bij locking.
    Gebruikt voor INSERT/UPDATE/DELETE.
    """
    wacht = 0.2
    for poging in range(1, max_pogingen + 1):
        try:
            with _db_connect(pad) as conn:
                conn.execute(sql, params)
                conn.commit()
            return
        except sqlite3.OperationalError as e:
            if 'locked' in str(e).lower() and poging < max_pogingen:
                import logging
                logging.getLogger(__name__).warning(
                    f"DB locked, poging {poging}/{max_pogingen}, wacht {wacht:.1f}s"
                )
                time.sleep(wacht)
                wacht *= 2
            else:
                raise



@dataclass
class Trade:
    """Een uitgevoerde trade met alle details."""
    id: str
    symbool: str
    richting: str             # 'long' of 'short'
    strategie_type: str
    entry_prijs: float
    exit_prijs: Optional[float]
    hoeveelheid: float
    euro_bedrag: float
    pnl: Optional[float]      # Winst/verlies in euro
    pnl_pct: Optional[float]  # Winst/verlies in procent
    entry_tijdstip: datetime
    exit_tijdstip: Optional[datetime]
    reden_entry: str          # Waarom ingekocht
    reden_exit: str           # Waarom verkocht
    geleerd: str              # Wat de agent leerde van deze trade
    regime: str
    sentiment_score: float
    exchange: str
    stop_loss_pct: Optional[float] = None
    take_profit_pct: Optional[float] = None
    slippage_bps: Optional[float] = None

    def samenvatting(self) -> str:
        pnl_str = f"+€{self.pnl:.2f}" if self.pnl and self.pnl > 0 else f"€{self.pnl:.2f}" if self.pnl else "open"
        return f"{self.symbool} {self.richting} | {pnl_str} | {self.strategie_type}"

    def bereken_pnl_pct(self, huidige_prijs: float) -> float:
        if self.richting == 'long':
            return (huidige_prijs - self.entry_prijs) / self.entry_prijs
        else:
            return (self.entry_prijs - huidige_prijs) / self.entry_prijs

    @property
    def waarde(self) -> float:
        return self.euro_bedrag


class AgentMemory:
    """
    Persistent geheugen voor de trading agent.
    Slaat alles op in SQLite - snel, lokaal, betrouwbaar.
    """

    def __init__(self, config: dict):
        self.config = config
        self.db_pad = Path("logs/agent_geheugen.db")
        self.db_pad.parent.mkdir(exist_ok=True)
        self._initialiseer_database()

        # In-memory cache voor snelle toegang
        self._kapitaal_cache = float(config['kapitaal']['start'])
        self._piek_kapitaal = float(config['kapitaal']['start'])

    def _initialiseer_database(self):
        """Maak de database tabellen aan als ze nog niet bestaan."""
        with _db_connect(self.db_pad) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS trades (
                    id TEXT PRIMARY KEY,
                    symbool TEXT,
                    richting TEXT,
                    strategie_type TEXT,
                    entry_prijs REAL,
                    exit_prijs REAL,
                    hoeveelheid REAL,
                    euro_bedrag REAL,
                    pnl REAL,
                    pnl_pct REAL,
                    entry_tijdstip TEXT,
                    exit_tijdstip TEXT,
                    reden_entry TEXT,
                    reden_exit TEXT,
                    geleerd TEXT,
                    regime TEXT,
                    sentiment_score REAL,
                    exchange TEXT
                )
            """)
            self._migreer_trade_kolommen(conn)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS kapitaal_geschiedenis (
                    tijdstip TEXT,
                    bedrag REAL,
                    reden TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS strategie_prestaties (
                    datum TEXT,
                    strategie TEXT,
                    win_rate REAL,
                    gemiddeld_rendement REAL,
                    totaal_trades INTEGER,
                    aanbevolen_aanpassing TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sentiment_effectiviteit (
                    datum TEXT,
                    bron TEXT,
                    voorspelling_correct REAL,
                    weging_aanpassing REAL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cooldowns (
                    symbool TEXT NOT NULL,
                    agent_naam TEXT NOT NULL,
                    laatste_trade TEXT NOT NULL,
                    cooldown_uren REAL NOT NULL,
                    PRIMARY KEY (symbool, agent_naam)
                )
            """)
            conn.commit()

    @staticmethod
    def _migreer_trade_kolommen(conn) -> None:
        """Voeg backward-compatible kolommen toe voor persisted trade metadata."""
        bestaande_kolommen = {
            rij[1]
            for rij in conn.execute("PRAGMA table_info(trades)").fetchall()
        }
        if 'stop_loss_pct' not in bestaande_kolommen:
            conn.execute("ALTER TABLE trades ADD COLUMN stop_loss_pct REAL")
        if 'take_profit_pct' not in bestaande_kolommen:
            conn.execute("ALTER TABLE trades ADD COLUMN take_profit_pct REAL")
        if 'slippage_bps' not in bestaande_kolommen:
            conn.execute("ALTER TABLE trades ADD COLUMN slippage_bps REAL")

    @staticmethod
    def _fmt_dt(dt) -> str | None:
        """Converteer datetime naar ISO string, None als het None is."""
        if dt is None:
            return None
        if isinstance(dt, str):
            return dt if dt != 'None' else None
        return dt.isoformat(sep=' ', timespec='microseconds')

    @staticmethod
    def _parse_dt(value) -> datetime | None:
        """Converteer database timestamps terug naar datetime, tolerant voor legacy NULL/None."""
        if value in (None, '', 'None'):
            return None
        if isinstance(value, datetime):
            return value
        return datetime.fromisoformat(value)

    def sla_trade_op(self, trade: Trade):
        """Sla een nieuwe trade op in de database."""
        with _db_connect(self.db_pad) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO trades (
                    id, symbool, richting, strategie_type, entry_prijs, exit_prijs,
                    hoeveelheid, euro_bedrag, pnl, pnl_pct, entry_tijdstip,
                    exit_tijdstip, reden_entry, reden_exit, geleerd, regime,
                    sentiment_score, exchange, stop_loss_pct, take_profit_pct, slippage_bps
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                trade.id, trade.symbool, trade.richting, trade.strategie_type,
                trade.entry_prijs, trade.exit_prijs, trade.hoeveelheid,
                trade.euro_bedrag, trade.pnl, trade.pnl_pct,
                self._fmt_dt(trade.entry_tijdstip),
                self._fmt_dt(trade.exit_tijdstip),
                trade.reden_entry, trade.reden_exit, trade.geleerd,
                trade.regime, trade.sentiment_score, trade.exchange,
                trade.stop_loss_pct, trade.take_profit_pct, trade.slippage_bps
            ))
            conn.commit()

    def laad_trade(self, trade_id: str) -> Optional[Trade]:
        """Laad één trade uit de database, tolerant voor legacy NULL kolommen."""
        with _db_connect(self.db_pad) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM trades WHERE id = ?",
                (trade_id,),
            ).fetchone()
        if row is None:
            return None
        return self._row_naar_trade(row)

    def _row_naar_trade(self, row: sqlite3.Row) -> Trade:
        """Map een SQLite row naar het canonical Trade-object."""
        return Trade(
            id=row["id"],
            symbool=row["symbool"],
            richting=row["richting"],
            strategie_type=row["strategie_type"],
            entry_prijs=row["entry_prijs"],
            exit_prijs=row["exit_prijs"],
            hoeveelheid=row["hoeveelheid"],
            euro_bedrag=row["euro_bedrag"],
            pnl=row["pnl"],
            pnl_pct=row["pnl_pct"],
            entry_tijdstip=self._parse_dt(row["entry_tijdstip"]),
            exit_tijdstip=self._parse_dt(row["exit_tijdstip"]),
            reden_entry=row["reden_entry"],
            reden_exit=row["reden_exit"],
            geleerd=row["geleerd"],
            regime=row["regime"],
            sentiment_score=row["sentiment_score"],
            exchange=row["exchange"],
            stop_loss_pct=row["stop_loss_pct"] if "stop_loss_pct" in row.keys() else None,
            take_profit_pct=row["take_profit_pct"] if "take_profit_pct" in row.keys() else None,
            slippage_bps=row["slippage_bps"] if "slippage_bps" in row.keys() else None,
        )

    def sla_resultaat_op(self, trade: Trade):
        """Update een bestaande trade met het eindresultaat."""
        self.sla_trade_op(trade)

        # Update kapitaal (ook bij pnl=0.0)
        if trade.pnl is not None:
            self._kapitaal_cache += trade.pnl
            if self._kapitaal_cache > self._piek_kapitaal:
                self._piek_kapitaal = self._kapitaal_cache

            with _db_connect(self.db_pad) as conn:
                conn.execute("""
                    INSERT INTO kapitaal_geschiedenis VALUES (?, ?, ?)
                """, (str(datetime.now()), self._kapitaal_cache,
                      f"Trade gesloten: {trade.samenvatting()}"))
                conn.commit()

    def huidig_kapitaal(self) -> float:
        return self._kapitaal_cache

    def piek_kapitaal(self) -> float:
        return self._piek_kapitaal

    def dagstatistieken(self, dagelijkse_trades: list) -> dict:
        """Bereken statistieken voor het dagrapport."""
        gesloten = [t for t in dagelijkse_trades if t.pnl is not None]
        dag_pnl = sum(t.pnl for t in gesloten)
        winnaars = [t for t in gesloten if t.pnl > 0]
        verliezers = [t for t in gesloten if t.pnl <= 0]

        return {
            'datum': datetime.now().strftime("%Y-%m-%d"),
            'huidig_kapitaal': self._kapitaal_cache,
            'dag_pnl': dag_pnl,
            'trades_vandaag': len(gesloten),
            'winnende_trades': len(winnaars),
            'verliezende_trades': len(verliezers),
            'max_drawdown': self._bereken_max_drawdown(),
            'trade_details': [
                {
                    'symbool': t.symbool,
                    'richting': t.richting,
                    'pnl': t.pnl,
                    'strategie': t.strategie_type,
                    'uitleg': t.reden_exit,
                    'geleerd': t.geleerd
                } for t in gesloten
            ],
            'regimes': {}  # Gevuld door hoofd agent
        }

    def analyseer_prestaties(self) -> dict:
        """
        Analyseer de laatste 30 dagen en genereer leerinzichten.
        Dit is hoe de agent zichzelf verbetert.
        """
        with _db_connect(self.db_pad) as conn:
            # Prestaties per strategie
            cursor = conn.execute("""
                SELECT strategie_type,
                       COUNT(*) as totaal,
                       SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as winst,
                       AVG(pnl_pct) as gem_rendement,
                       SUM(pnl) as totaal_pnl
                FROM trades
                WHERE exit_tijdstip > datetime('now', '-30 days')
                AND pnl IS NOT NULL
                GROUP BY strategie_type
            """)
            per_strategie = {}
            for rij in cursor.fetchall():
                strategie, totaal, winst, gem_rendement, totaal_pnl = rij
                win_rate = winst / totaal if totaal > 0 else 0
                per_strategie[strategie] = {
                    'totaal_trades': totaal,
                    'win_rate': win_rate,
                    'gem_rendement': gem_rendement or 0,
                    'totaal_pnl': totaal_pnl or 0,
                    # Aanbeveling: boost goede strategieën, reduceer slechte
                    'gewicht_aanpassing': self._bereken_gewicht_aanpassing(win_rate, gem_rendement or 0)
                }

        beste_strategie = max(per_strategie.items(),
                              key=lambda x: x[1]['totaal_pnl'],
                              default=('onbekend', {}))

        return {
            'per_strategie': per_strategie,
            'beste_strategie': beste_strategie[0],
            'sentiment_effectiviteit': {},  # Uitgebreid in volgende versie
            'samenvatting': (
                f"Analyse 30 dagen: beste strategie is {beste_strategie[0]} "
                f"met €{beste_strategie[1].get('totaal_pnl', 0):.2f} winst"
            )
        }


    def sla_cooldown_op(self, symbool: str, agent_naam: str, cooldown_uren: float):
        """Schrijf cooldown timestamp naar database (persistent over herstarts)."""
        _db_uitvoeren(self.db_pad,
            """INSERT OR REPLACE INTO cooldowns (symbool, agent_naam, laatste_trade, cooldown_uren)
               VALUES (?, ?, ?, ?)""",
            (symbool, agent_naam, datetime.now().isoformat(sep=' ', timespec='seconds'), cooldown_uren)
        )

    def cooldown_actief(self, symbool: str, agent_naam: str, cooldown_uren: float) -> bool:
        """Check of cooldown nog actief is. True = nog wachten, False = mag handelen."""
        with _db_connect(self.db_pad) as conn:
            rij = conn.execute(
                "SELECT laatste_trade FROM cooldowns WHERE symbool=? AND agent_naam=?",
                (symbool, agent_naam)
            ).fetchone()
        if not rij:
            return False
        try:
            laatste = datetime.fromisoformat(rij[0])
        except (ValueError, TypeError):
            return False
        verstreken = (datetime.now() - laatste).total_seconds()
        return verstreken < cooldown_uren * 3600

    def verwijder_cooldown(self, symbool: str, agent_naam: str):
        """Verwijder cooldown (na force-exit)."""
        _db_uitvoeren(self.db_pad,
            "DELETE FROM cooldowns WHERE symbool=? AND agent_naam=?",
            (symbool, agent_naam)
        )

    def tel_open_posities(self, strategie_type: str | None = None) -> int:
        """Tel open posities in de DB. Optioneel gefilterd op strategie_type."""
        with _db_connect(self.db_pad) as conn:
            if strategie_type:
                rij = conn.execute(
                    "SELECT COUNT(*) FROM trades WHERE exit_tijdstip IS NULL AND strategie_type = ?",
                    (strategie_type,)
                ).fetchone()
            else:
                rij = conn.execute(
                    "SELECT COUNT(*) FROM trades WHERE exit_tijdstip IS NULL"
                ).fetchone()
        return rij[0] if rij else 0

    def heeft_open_positie_db(self, symbool: str) -> bool:
        """Check of er een open positie is voor dit symbool in de DB (persistent na herstart)."""
        with _db_connect(self.db_pad) as conn:
            rij = conn.execute(
                "SELECT 1 FROM trades WHERE symbool = ? AND exit_tijdstip IS NULL LIMIT 1",
                (symbool,)
            ).fetchone()
        return rij is not None

    def _bereken_max_drawdown(self) -> float:
        """Bereken maximale drawdown als percentage."""
        if self._piek_kapitaal == 0:
            return 0
        return max(0, (self._piek_kapitaal - self._kapitaal_cache) / self._piek_kapitaal * 100)

    def _bereken_gewicht_aanpassing(self, win_rate: float, gem_rendement: float) -> float:
        """
        Bereken hoeveel het gewicht van een strategie moet worden aangepast.
        Positief = meer gebruiken, negatief = minder gebruiken.
        """
        if win_rate > 0.60 and gem_rendement > 0.01:
            return +0.15   # Strategie werkt goed: 15% meer inzetten
        elif win_rate > 0.50 and gem_rendement > 0:
            return +0.05   # Kleine verbetering
        elif win_rate < 0.40 or gem_rendement < -0.01:
            return -0.20   # Strategie werkt slecht: 20% minder inzetten
        else:
            return 0       # Neutraal, geen aanpassing
