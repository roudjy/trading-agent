"""Static guarantee: research/diagnostics never imports decision modules.

This test parses every module in ``research/diagnostics/`` as TEXT
(no ``import``) and asserts that none of them contains an ``import``
or ``from ... import`` statement that pulls in a known runtime /
decision module.

Allowed imports:
* stdlib (anything builtin)
* ``research._sidecar_io`` (verified pure utility — no project deps)
* relative imports inside ``research.diagnostics``

Anything else is a hard fail. This test is the contractual guard
that the observability layer cannot accidentally drag in
campaign/sprint/strategy code.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

DIAGNOSTICS_DIR = (
    Path(__file__).resolve().parents[2] / "research" / "diagnostics"
)

# Modules / packages that are STRICTLY forbidden inside research.diagnostics.
FORBIDDEN_PREFIXES = (
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
    "research.screening_runtime",
    "research.screening_evidence",
    "research.screening_process",
    "research.run_research",
    "research.run_state",
    "research.observability",  # legacy module — pulls in research.run_state
    "research.candidate_lifecycle",
    "research.candidate_pipeline",
    "research.candidate_registry_v2",
    "research.candidate_resume",
    "research.candidate_returns_feed",
    "research.candidate_scoring",
    "research.candidate_sidecars",
    "research.engine",
    "research.presets",
    "research.public_artifact_status",
    "research.research_evidence_ledger",
    "research.funnel_spawn_proposer",
    "research.dead_zone_detection",
    "research.information_gain",
    "research.stop_condition_engine",
    "research.viability_metrics",
    "research.batch_execution",
    "research.batching",
    "research.strategy_hypothesis_catalog",
    "research.integrity",
    "research.integrity_reporting",
    "agent",
    "agent.",
    "strategies",
    "strategies.",
    "orchestration",
    "orchestration.",
    "execution",
    "execution.",
    "automation",
    "automation.",
    "state",
    "state.",
    "dashboard",
    "dashboard.",
)

# Modules from inside the project that ARE allowed. Tightly enumerated.
ALLOWED_PROJECT_IMPORTS = {
    "research._sidecar_io",
}


def _module_files() -> list[Path]:
    return sorted(p for p in DIAGNOSTICS_DIR.glob("*.py") if p.is_file())


def _is_forbidden(module_name: str) -> bool:
    for prefix in FORBIDDEN_PREFIXES:
        if module_name == prefix or module_name.startswith(prefix + "."):
            return True
    return False


def _imports_in(file_path: Path) -> list[tuple[str, int]]:
    tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
    imports: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append((alias.name, node.lineno))
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            # Relative imports (``from . import ...``) have level > 0
            # and are always allowed within the package.
            if node.level and not module:
                continue
            if node.level:
                # Relative ``from .x import y`` — translate to package path.
                # We require these to stay inside research.diagnostics.
                imports.append((f"<relative:{node.level}>:{module}", node.lineno))
                continue
            for alias in node.names:
                if alias.name and module == "":
                    imports.append((alias.name, node.lineno))
                else:
                    imports.append((module, node.lineno))
                    break  # one entry per ImportFrom is enough for the check
    return imports


def test_observability_modules_exist():
    files = _module_files()
    assert len(files) >= 4, f"expected at least 4 modules, got {[f.name for f in files]}"
    names = {f.stem for f in files}
    required = {
        "__init__",
        "paths",
        "clock",
        "io",
        "artifact_health",
        "failure_modes",
        "throughput",
        "system_integrity",
        "aggregator",
        "cli",
        "__main__",
    }
    missing = required - names
    assert not missing, f"observability package is missing modules: {missing}"


@pytest.mark.parametrize("module_path", _module_files(), ids=lambda p: p.name)
def test_no_forbidden_imports(module_path: Path):
    """Every module under research/diagnostics must not import any
    forbidden runtime/decision module."""
    imports = _imports_in(module_path)
    violations: list[tuple[str, int]] = []
    for name, lineno in imports:
        if name.startswith("<relative:"):
            continue  # internal relative imports are always allowed
        if _is_forbidden(name):
            violations.append((name, lineno))
    assert not violations, (
        f"{module_path.name} imports forbidden modules: {violations}"
    )


@pytest.mark.parametrize("module_path", _module_files(), ids=lambda p: p.name)
def test_only_whitelisted_project_imports(module_path: Path):
    """Project (non-stdlib) imports must come from the explicit allowlist.

    Heuristic: any top-level module whose name contains a dot AND whose
    leading segment matches one of {"agent", "strategies", "research",
    "orchestration", "execution", "automation", "state", "dashboard",
    "data", "reporting", "config", "ops"} is treated as project code.
    Allowed project imports are listed in ``ALLOWED_PROJECT_IMPORTS``.
    """
    project_roots = {
        "agent",
        "strategies",
        "research",
        "orchestration",
        "execution",
        "automation",
        "state",
        "dashboard",
        "data",
        "reporting",
        "config",
        "ops",
    }
    imports = _imports_in(module_path)
    project_imports = [
        (name, lineno)
        for name, lineno in imports
        if not name.startswith("<relative:")
        and name.split(".", 1)[0] in project_roots
    ]
    extras = [
        (name, lineno)
        for name, lineno in project_imports
        if name not in ALLOWED_PROJECT_IMPORTS
    ]
    assert not extras, (
        f"{module_path.name} imports non-whitelisted project modules: {extras}\n"
        f"Allowed: {sorted(ALLOWED_PROJECT_IMPORTS)}"
    )
