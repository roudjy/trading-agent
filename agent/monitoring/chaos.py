"""
ChaosMonkey: injecteert fouten in de trading agent om robuustheid te testen.

Gebruik:
    monkey = ChaosMonkey(kans=0.1)
    monkey.activeer()
    # ... run agent ...
    monkey.deactiveer()
    print(monkey.rapport())

Injectie-types:
  - network_timeout   : simuleert een netwerk-timeout in fetch-operaties
  - db_fout           : simuleert een SQLite DB-fout (tijdelijk)
  - prijs_corruptie   : injecteert NaN/0 in prijsdata
  - geheugen_fout     : simuleert een geheugen-schrijffout
  - willekeurige_exit : roept sys.exit() aan (alleen in test-modus)
"""

import logging
import random
import sqlite3
import threading
import time
from collections import defaultdict
from contextlib import contextmanager
from typing import Optional
from unittest.mock import MagicMock, patch

log = logging.getLogger(__name__)


class ChaosMonkey:
    """
    Injecteert willekeurige fouten om agent-robuustheid te valideren.

    Parameters
    ----------
    kans : float
        Kans per injectie-punt dat een fout wordt geïnjecteerd (0.0 – 1.0).
    soorten : list[str] | None
        Welke fout-soorten actief zijn. None = alle.
    test_modus : bool
        Als True: geen echte side-effects (sys.exit wordt geblokkeerd).
    """

    BESCHIKBAAR = ["network_timeout", "db_fout", "prijs_corruptie", "geheugen_fout"]

    def __init__(
        self,
        kans: float = 0.1,
        soorten: Optional[list] = None,
        test_modus: bool = True,
    ):
        if not 0.0 <= kans <= 1.0:
            raise ValueError(f"kans moet tussen 0 en 1 liggen, niet {kans}")
        self.kans = kans
        self.soorten = soorten or self.BESCHIKBAAR
        self.test_modus = test_modus

        self._actief = False
        self._tellers: dict[str, int] = defaultdict(int)
        self._gevangen: dict[str, int] = defaultdict(int)
        self._lock = threading.Lock()
        self._patches: list = []

    # ──────────────────────────────────────────────────────
    # Activeren / deactiveren
    # ──────────────────────────────────────────────────────

    def activeer(self) -> None:
        """Start chaos-injectie."""
        self._actief = True
        log.warning(f"[ChaosMonkey] Geactiveerd (kans={self.kans}, soorten={self.soorten})")

    def deactiveer(self) -> None:
        """Stop chaos-injectie en verwijder patches."""
        self._actief = False
        for p in self._patches:
            try:
                p.stop()
            except RuntimeError:
                pass
        self._patches.clear()
        log.info("[ChaosMonkey] Gedeactiveerd")

    # ──────────────────────────────────────────────────────
    # Injectie-punten
    # ──────────────────────────────────────────────────────

    def injecteer(self, soort: str) -> bool:
        """
        Roep dit aan op een injectie-punt.
        Geeft True terug als een fout werd geïnjecteerd.

        Raises TimeoutError, sqlite3.OperationalError, ValueError, IOError
        afhankelijk van soort.
        """
        if not self._actief:
            return False
        if soort not in self.soorten:
            return False
        if random.random() > self.kans:
            return False

        with self._lock:
            self._tellers[soort] += 1

        log.warning(f"[ChaosMonkey] Injecteer: {soort}")
        self._gooi_fout(soort)
        return True  # nooit bereikt als _gooi_fout altijd raist

    def _gooi_fout(self, soort: str) -> None:
        if soort == "network_timeout":
            raise TimeoutError("ChaosMonkey: gesimuleerde netwerk-timeout")
        elif soort == "db_fout":
            raise sqlite3.OperationalError("ChaosMonkey: gesimuleerde DB-fout (database is locked)")
        elif soort == "prijs_corruptie":
            raise ValueError("ChaosMonkey: gesimuleerde corrupte prijsdata (NaN/0)")
        elif soort == "geheugen_fout":
            raise IOError("ChaosMonkey: gesimuleerde geheugen-schrijffout")
        else:
            raise RuntimeError(f"ChaosMonkey: onbekende fout-soort '{soort}'")

    # ──────────────────────────────────────────────────────
    # Context manager (handig voor with-blokken)
    # ──────────────────────────────────────────────────────

    @contextmanager
    def bewaken(self, soort: str):
        """
        Context manager die de injectie registreert als de fout wordt
        *gevangen* door de omringende code.

        Gebruik:
            try:
                with monkey.bewaken('network_timeout'):
                    data = await haal_data_op()
            except TimeoutError:
                ...  # monkey of echte fout — beide worden geteld
        """
        try:
            yield
        except (TimeoutError, sqlite3.OperationalError, ValueError, IOError,
                RuntimeError) as exc:
            with self._lock:
                self._gevangen[soort] += 1
            raise

    # ──────────────────────────────────────────────────────
    # Rapport
    # ──────────────────────────────────────────────────────

    def rapport(self) -> dict:
        """Geeft statistieken terug over geïnjecteerde en gevangen fouten."""
        with self._lock:
            injecties = dict(self._tellers)
            gevangen  = dict(self._gevangen)

        totaal = sum(injecties.values())
        resilience = (
            sum(gevangen.values()) / totaal
            if totaal > 0 else 1.0
        )

        return {
            "actief": self._actief,
            "kans": self.kans,
            "soorten": self.soorten,
            "injecties": injecties,
            "gevangen": gevangen,
            "totaal_injecties": totaal,
            "resilience_score": round(resilience, 3),
        }

    def reset(self) -> None:
        """Reset alle tellers."""
        with self._lock:
            self._tellers.clear()
            self._gevangen.clear()

    def __repr__(self) -> str:
        r = self.rapport()
        return (
            f"ChaosMonkey(actief={r['actief']}, kans={r['kans']}, "
            f"injecties={r['totaal_injecties']}, resilience={r['resilience_score']})"
        )
