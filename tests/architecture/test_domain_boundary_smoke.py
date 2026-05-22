"""ARCH-000 conservative architecture boundary smoke tests.

These tests are intentionally narrow. They pin boundaries the current
repository already satisfies and provide an executable foothold for the
larger ARCH-001 import scanner.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

EXECUTION_IMPORT_PREFIXES: tuple[str, ...] = (
    "agent.execution",
    "agent.risk",
    "automation.live_gate",
    "broker",
    "execution",
    "live",
    "paper",
    "shadow",
)

IMPLEMENTATION_AGENT_ALLOWED_ROOTS = {
    "dashboard/",
    "tests/",
    "frontend/",
    "docs/",
    "docs/adr/_drafts/",
}
IMPLEMENTATION_AGENT_REQUIRED_EXCLUDES = {
    "dashboard/api_observability.py",
    "docs/governance/",
    "docs/adr/ADR-*.md",
    "tests/regression/test_v3_*pin*.py",
    "tests/regression/test_v3_15_artifacts_deterministic.py",
    "tests/regression/test_authority_invariants.py",
    "tests/regression/test_v3_15_8_canonical_dump_and_digest.py",
}
DEPLOYMENT_IMPLEMENTATION_ALLOWED_ROOTS = {
    "scripts/deploy_vps_dashboard.sh",
    ".github/workflows/deploy-vps-dashboard.yml",
    "docs/governance/vps_deploy.md",
}


def _imports_in(file_path: Path) -> list[tuple[str, int]]:
    tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
    imports: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append((alias.name, node.lineno))
        elif isinstance(node, ast.ImportFrom) and node.module:
            if node.level:
                continue
            imports.append((node.module, node.lineno))
    return imports


def _is_forbidden_import(module_name: str) -> bool:
    return any(
        module_name == prefix or module_name.startswith(prefix + ".")
        for prefix in EXECUTION_IMPORT_PREFIXES
    )


def _frontmatter_list(text: str, key: str) -> list[str]:
    lines = text.splitlines()
    values: list[str] = []
    in_key = False
    for line in lines:
        if line == "---" and values:
            break
        if line.startswith(f"{key}:"):
            in_key = True
            continue
        if in_key:
            if line.startswith("  - "):
                values.append(line.removeprefix("  - ").strip())
                continue
            if line and not line.startswith(" "):
                break
    return values


def _frontmatter_scalar(text: str, key: str) -> str | None:
    for line in text.splitlines():
        if line.startswith(f"{key}:"):
            return line.split(":", 1)[1].strip()
    return None


@pytest.mark.parametrize(
    "module_path",
    sorted((REPO_ROOT / "reporting").glob("development*.py")),
    ids=lambda p: p.name,
)
def test_reporting_development_modules_do_not_import_execution_domains(
    module_path: Path,
) -> None:
    violations = [
        (name, lineno)
        for name, lineno in _imports_in(module_path)
        if _is_forbidden_import(name)
    ]
    assert violations == []


@pytest.mark.parametrize(
    "module_path",
    sorted((REPO_ROOT / "research" / "diagnostics").glob("*.py")),
    ids=lambda p: p.name,
)
def test_research_diagnostics_do_not_import_execution_domains(
    module_path: Path,
) -> None:
    violations = [
        (name, lineno)
        for name, lineno in _imports_in(module_path)
        if _is_forbidden_import(name)
    ]
    assert violations == []


def test_implementation_agent_scope_is_pinned_to_non_execution_roots() -> None:
    text = (REPO_ROOT / ".claude" / "agents" / "implementation-agent.md").read_text(
        encoding="utf-8"
    )
    allowed_roots = set(_frontmatter_list(text, "allowed_roots"))
    excludes = set(_frontmatter_list(text, "allowed_root_excludes"))
    max_autonomy_level = _frontmatter_scalar(text, "max_autonomy_level")

    assert allowed_roots == IMPLEMENTATION_AGENT_ALLOWED_ROOTS
    assert IMPLEMENTATION_AGENT_REQUIRED_EXCLUDES <= excludes
    assert max_autonomy_level == "3"
    assert not any(_root_is_execution_scoped(root) for root in allowed_roots)


def test_deployment_implementation_agent_scope_is_dashboard_deploy_only() -> None:
    text = (
        REPO_ROOT / ".claude" / "agents" / "deployment-implementation-agent.md"
    ).read_text(encoding="utf-8")
    allowed_roots = set(_frontmatter_list(text, "allowed_roots"))
    max_autonomy_level = _frontmatter_scalar(text, "max_autonomy_level")

    assert allowed_roots == DEPLOYMENT_IMPLEMENTATION_ALLOWED_ROOTS
    assert max_autonomy_level == "1"
    assert not any(_root_is_execution_scoped(root) for root in allowed_roots)


def _root_is_execution_scoped(root: str) -> bool:
    lowered = root.lower()
    execution_terms = (
        "agent/execution",
        "agent/risk",
        "broker",
        "execution/live",
        "live",
        "paper",
        "shadow",
        "risk",
    )
    return any(term in lowered for term in execution_terms)
