"""Static guarantee: tests/functional/ never imports forbidden modules.

Parses every ``.py`` file under ``tests/functional/`` (excluding this
test itself) AS TEXT — no ``import`` of the file under inspection —
and asserts every import lands in the allowlist:

* Python stdlib (``sys.stdlib_module_names``)
* ``pytest``
* ``research._sidecar_io`` (verified pure)
* ``research.diagnostics`` and submodules
* Relative imports inside ``tests.functional``

Anything else is a hard fail. This is the contractual guard that
the harness cannot accidentally drag in
campaign/sprint/strategy/runtime code.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

FUNCTIONAL_DIR = Path(__file__).resolve().parent
SELF_FILENAME = Path(__file__).name


# Modules / packages STRICTLY forbidden inside tests/functional/.
FORBIDDEN_PREFIXES: tuple[str, ...] = (
    # Funnel / runtime decision modules — explicitly listed in the
    # v3.15.15.5 brief.
    "research.campaign_policy",
    "research.campaign_launcher",
    "research.campaign_queue",
    "research.campaign_lease",
    "research.campaign_registry",
    "research.campaign_digest",
    "research.campaign_budget",
    "research.campaign_templates",
    "research.campaign_evidence_ledger",
    "research.campaign_followup",
    "research.campaign_funnel_policy",
    "research.campaign_invariants",
    "research.campaign_os_artifacts",
    "research.campaign_preset_policy",
    "research.campaign_family_policy",
    "research.campaigns",
    "research.discovery_sprint",
    "research.candidate_pipeline",
    "research.candidate_lifecycle",
    "research.candidate_registry_v2",
    "research.candidate_resume",
    "research.candidate_returns_feed",
    "research.candidate_scoring",
    "research.candidate_sidecars",
    "research.paper_readiness",
    "research.paper_validation_sidecars",
    "research.promotion",
    "research.run_research",
    "research.run_state",
    "research.observability",  # legacy ProgressTracker — pulls research.run_state
    "research.screening_runtime",
    "research.screening_evidence",
    "research.screening_process",
    "research.batch_execution",
    "research.batching",
    "research.engine",
    "research.presets",
    "research.public_artifact_status",
    "research.research_evidence_ledger",
    "research.funnel_spawn_proposer",
    "research.dead_zone_detection",
    "research.information_gain",
    "research.stop_condition_engine",
    "research.viability_metrics",
    "research.strategy_hypothesis_catalog",
    "research.integrity",
    "research.integrity_reporting",
    # Forbidden subsystems.
    "agent",
    "execution",
    "orchestration",
    "automation",
    "state",
    "dashboard",
    # Network / external clients.
    "yfinance",
    "ccxt",
    "requests",
    "urllib.request",
    "urllib3",
    "httpx",
)

# Project-rooted imports allowed by exact name (not prefix-matched).
ALLOWED_PROJECT_IMPORTS: frozenset[str] = frozenset(
    {
        "research._sidecar_io",
    }
)

# Project package roots used in heuristic detection of "is this a
# project import we need to gate?".
PROJECT_ROOTS: frozenset[str] = frozenset(
    {
        "agent",
        "strategies",
        "research",
        "orchestration",
        "execution",
        "automation",
        "state",
        "data",
        "reporting",
        "config",
        "ops",
        "dashboard",
    }
)


def _module_files() -> list[Path]:
    return sorted(
        p
        for p in FUNCTIONAL_DIR.glob("*.py")
        if p.is_file() and p.name != SELF_FILENAME
    )


def _is_forbidden(module_name: str) -> bool:
    for prefix in FORBIDDEN_PREFIXES:
        if module_name == prefix or module_name.startswith(prefix + "."):
            return True
    return False


def _imports_in(file_path: Path) -> list[tuple[str, int]]:
    tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
    out: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                out.append((alias.name, node.lineno))
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                # Relative imports inside tests.functional are always allowed;
                # we only record them so the test reports them in failures.
                out.append((f"<relative:{node.level}>:{node.module or ''}", node.lineno))
                continue
            if node.module:
                out.append((node.module, node.lineno))
    return out


def _is_stdlib(module_name: str) -> bool:
    """Best-effort stdlib detection.

    ``sys.stdlib_module_names`` (Python 3.10+) is authoritative for
    top-level stdlib package names. We strip submodule path so e.g.
    ``"datetime"``, ``"pathlib.Path"``, ``"json"`` are all matched.
    """
    top = module_name.split(".", 1)[0]
    return top in sys.stdlib_module_names


def test_module_files_present():
    """Sanity: the harness contains the expected scaffolding."""
    names = {f.name for f in _module_files()}
    required = {
        "__init__.py",
        "conftest.py",
        "_funnel_artifact_builders.py",
        "test_a_degenerate_no_survivor.py",
        "test_b_technical_failure.py",
        "test_f_observability_lite.py",
    }
    missing = required - names
    assert not missing, f"missing harness modules: {missing}"


@pytest.mark.parametrize("module_path", _module_files(), ids=lambda p: p.name)
def test_no_forbidden_imports(module_path: Path):
    """Every module under tests/functional/ refuses any forbidden import."""
    imports = _imports_in(module_path)
    violations: list[tuple[str, int]] = []
    for name, lineno in imports:
        if name.startswith("<relative:"):
            continue  # always allowed
        if _is_forbidden(name):
            violations.append((name, lineno))
    assert not violations, (
        f"{module_path.name} imports forbidden modules: {violations}"
    )


@pytest.mark.parametrize("module_path", _module_files(), ids=lambda p: p.name)
def test_only_allowlist_project_imports(module_path: Path):
    """Project (non-stdlib, non-pytest) imports must be allowlisted."""
    imports = _imports_in(module_path)
    extras: list[tuple[str, int]] = []
    for name, lineno in imports:
        if name.startswith("<relative:"):
            continue
        if name == "pytest" or _is_stdlib(name):
            continue
        # research.diagnostics + submodules are allowed.
        if name == "research.diagnostics" or name.startswith("research.diagnostics."):
            continue
        # Whitelisted exact names.
        if name in ALLOWED_PROJECT_IMPORTS:
            continue
        # Anything left that hits a project root is a violation.
        top = name.split(".", 1)[0]
        if top in PROJECT_ROOTS:
            extras.append((name, lineno))
    assert not extras, (
        f"{module_path.name} imports non-allowlisted project modules: {extras}\n"
        f"Allowed project imports: research._sidecar_io, research.diagnostics.*"
    )
