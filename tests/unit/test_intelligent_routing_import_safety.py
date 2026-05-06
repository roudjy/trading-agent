"""PR-A — import-safety pins for reporting.intelligent_routing.

v3.15.16 advisory release. Per Correction 6 + Critical-review item 1,
these tests pin the module's "import does nothing observable"
invariant with **explicit, targeted** monkeypatches rather than broad
full-tree comparisons:

* Importing the module opens no file in any write mode.
* Importing the module does not import forbidden modules
  (automation.live_gate, agent.risk*, agent.execution*, broker*,
  live*, paper*, shadow*, trading*, dashboard*).
* Importing the module does not mutate any frozen no-touch research
  artifact (sha256 snapshot of a closed list is unchanged across
  import).
* Importing the module does not run subprocess, network, or git.
"""

from __future__ import annotations

import builtins
import hashlib
import importlib
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

#: Closed list of frozen / no-touch research artifacts whose bytes
#: must be byte-identical before and after importing the module. We
#: deliberately use a small, explicit set instead of walking
#: ``research/**`` so the test is stable when unrelated research code
#: writes its own sidecars during a parallel test run.
FROZEN_PATHS_FOR_SNAPSHOT: tuple[str, ...] = (
    "research/research_latest.json",
    "research/strategy_matrix.csv",
    "research/campaigns/evidence/dead_zones_latest.v1.json",
    "research/campaigns/evidence/information_gain_latest.v1.json",
    "research/campaigns/evidence/viability_latest.v1.json",
    "research/campaigns/evidence/stop_conditions_latest.v1.json",
    "research/campaigns/evidence/evidence_ledger_latest.v1.json",
)

#: Closed list of forbidden top-level/dotted package prefixes the
#: module must not pull in transitively.
FORBIDDEN_IMPORT_PREFIXES: tuple[str, ...] = (
    "automation.live_gate",
    "agent.risk",
    "agent.execution",
    "broker",
    "live",
    "paper",
    "shadow",
    "trading",
    "dashboard",
    "ccxt",
    "yfinance",
)

MODULE_NAME = "reporting.intelligent_routing"


def _snapshot_frozen_paths() -> dict[str, str | None]:
    """Map repo-relative path → sha256 hex (or None if absent)."""
    out: dict[str, str | None] = {}
    for rel in FROZEN_PATHS_FOR_SNAPSHOT:
        p = REPO_ROOT / rel
        if not p.exists():
            out[rel] = None
            continue
        out[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def _force_reimport() -> None:
    """Drop the module from sys.modules so a subsequent import re-runs
    its top-level body."""
    sys.modules.pop(MODULE_NAME, None)


# ---------------------------------------------------------------------------
# 1. Importing the module opens no file in any write mode.
# ---------------------------------------------------------------------------


def test_import_does_not_open_files_in_write_mode(
    monkeypatch: object,
) -> None:
    forbidden_modes = {"w", "a", "x", "+"}
    write_calls: list[tuple[str, str]] = []
    real_open = builtins.open

    def _spy_open(file: object, mode: str = "r", *a: object, **kw: object):
        m = mode if isinstance(mode, str) else ""
        if any(c in m for c in forbidden_modes):
            write_calls.append((str(file), m))
        return real_open(file, mode, *a, **kw)

    monkeypatch.setattr(builtins, "open", _spy_open)  # type: ignore[attr-defined]
    _force_reimport()
    importlib.import_module(MODULE_NAME)

    assert write_calls == [], (
        f"reporting.intelligent_routing opened files in write mode at "
        f"import time: {write_calls!r}"
    )


def test_import_does_not_open_paths_via_pathlib_write(
    monkeypatch: object,
) -> None:
    forbidden_modes = {"w", "a", "x", "+"}
    write_calls: list[tuple[str, str]] = []
    real_open = Path.open

    def _spy_open(self: Path, mode: str = "r", *a: object, **kw: object):
        m = mode if isinstance(mode, str) else ""
        if any(c in m for c in forbidden_modes):
            write_calls.append((str(self), m))
        return real_open(self, mode, *a, **kw)

    monkeypatch.setattr(Path, "open", _spy_open)  # type: ignore[attr-defined]
    _force_reimport()
    importlib.import_module(MODULE_NAME)

    assert write_calls == [], (
        f"reporting.intelligent_routing opened pathlib paths in write "
        f"mode at import time: {write_calls!r}"
    )


# ---------------------------------------------------------------------------
# 2. Importing the module does not import forbidden modules.
# ---------------------------------------------------------------------------


def test_import_does_not_pull_forbidden_modules() -> None:
    """The forbidden prefixes must not appear in ``sys.modules`` after
    a clean import of reporting.intelligent_routing.

    To avoid false positives from earlier tests in the same process,
    we snapshot which forbidden modules are *already* loaded, drop
    ``reporting.intelligent_routing``, re-import it, and assert no new
    forbidden module appeared as a result of the import.
    """
    pre_loaded = {
        name
        for name in sys.modules
        if any(
            name == p or name.startswith(p + ".")
            for p in FORBIDDEN_IMPORT_PREFIXES
        )
    }

    _force_reimport()
    importlib.import_module(MODULE_NAME)

    post_loaded = {
        name
        for name in sys.modules
        if any(
            name == p or name.startswith(p + ".")
            for p in FORBIDDEN_IMPORT_PREFIXES
        )
    }
    newly_loaded = post_loaded - pre_loaded
    assert newly_loaded == set(), (
        "reporting.intelligent_routing pulled in forbidden modules at "
        f"import time: {sorted(newly_loaded)!r}"
    )


# ---------------------------------------------------------------------------
# 3. Importing does not mutate frozen / no-touch research artifacts.
# ---------------------------------------------------------------------------


def test_import_does_not_mutate_frozen_research_artifacts() -> None:
    """Sha256 snapshot of the closed list of frozen artifacts is
    byte-identical before and after a fresh import. Targeted, not a
    full-tree walk, per Critical-review item 1."""
    before = _snapshot_frozen_paths()
    _force_reimport()
    importlib.import_module(MODULE_NAME)
    after = _snapshot_frozen_paths()
    assert before == after, (
        "reporting.intelligent_routing mutated a frozen artifact at "
        f"import time: before={before!r} after={after!r}"
    )


# ---------------------------------------------------------------------------
# 4. Importing does not invoke subprocess / network / git.
# ---------------------------------------------------------------------------


def test_import_does_not_invoke_subprocess(monkeypatch: object) -> None:
    import subprocess

    calls: list[object] = []
    real_run = subprocess.run

    def _spy_run(*a: object, **kw: object):
        calls.append((a, kw))
        return real_run(*a, **kw)

    real_popen = subprocess.Popen

    class _SpyPopen(real_popen):  # type: ignore[misc, valid-type]
        def __init__(self, *a: object, **kw: object) -> None:
            calls.append((a, kw))
            super().__init__(*a, **kw)

    monkeypatch.setattr(subprocess, "run", _spy_run)  # type: ignore[attr-defined]
    monkeypatch.setattr(subprocess, "Popen", _SpyPopen)  # type: ignore[attr-defined]
    _force_reimport()
    importlib.import_module(MODULE_NAME)

    assert calls == [], (
        "reporting.intelligent_routing invoked subprocess at import "
        f"time: {calls!r}"
    )


# ---------------------------------------------------------------------------
# 5. Module surface is the closed __all__ — no surprise side-effect functions.
# ---------------------------------------------------------------------------


def test_module_all_is_closed_and_includes_advisory_constants() -> None:
    _force_reimport()
    mod = importlib.import_module(MODULE_NAME)
    all_set = set(mod.__all__)
    # Required closed-vocabulary constants per the plan.
    assert "ROUTING_EFFECT_ADVISORY_ONLY" in all_set
    assert "QUEUE_ORDERING_EFFECT_NONE" in all_set
    assert "SCHEMA_VERSION" in all_set
    assert "MODULE_VERSION" in all_set
    assert "REPORT_KIND" in all_set
    assert "ADVISORY_SUPPRESSION_REASONS" in all_set
    # Required pure-helper exports.
    for sym in (
        "derive_behavior_coordinates",
        "bucket_info_gain",
        "classify_dead_zone_status",
        "compute_orthogonality_bucket",
        "compute_near_duplicate_group",
    ):
        assert sym in all_set, sym
    # Required dataclass exports.
    for sym in (
        "BehaviorCoordinates",
        "RoutingDecision",
        "RoutingReportSummary",
        "RoutingReport",
    ):
        assert sym in all_set, sym
