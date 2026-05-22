from __future__ import annotations

import ast
import importlib.util
import subprocess
from pathlib import Path
from types import ModuleType

import packages.control_plane_qre_adapter_contract as canonical_contract
import reporting.control_plane_qre_adapter_contract as compatibility_contract
from packages.control_plane_qre_adapter_contract import describe_contract
from reporting.architecture_import_scan import (
    DOMAIN_ADAPTER_CONTRACT,
    DOMAIN_ADE,
    DOMAIN_CONTROL_PLANE,
    DOMAIN_QRE,
    classify_module,
    classify_path,
    report_to_summary_dict,
    scan_repo,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
BOUNDARY_PATH = REPO_ROOT / "apps" / "control-plane" / "read_only_adapter_boundary.py"
MIGRATION_DOC = (
    REPO_ROOT
    / "docs"
    / "architecture"
    / "PACKAGE-MIGRATION-003-control-plane-read-only-adapter-boundary.md"
)
FROZEN_CONTRACT_PATHS = {
    "research/research_latest.json",
    "strategy_matrix.csv",
}
PROTECTED_PATH_PREFIXES = (
    ".claude/",
    "agent/execution/",
    "agent/risk/",
    "automation/live_gate",
    "broker/",
    "execution/",
    "live/",
    "paper/",
    "risk/",
    "shadow/",
)
ALLOWED_CHANGED_PATH_PREFIXES = (
    "apps/control-plane/",
    "docs/architecture/",
    "tests/architecture/",
)
FORBIDDEN_IMPORT_PREFIXES = (
    "agent.execution",
    "agent.risk",
    "automation.live_gate",
    "broker",
    "dashboard",
    "execution",
    "flask",
    "live",
    "paper",
    "research",
    "risk",
    "shadow",
)
PUBLIC_CONTRACT_NAMES = (
    "AdapterContractDescription",
    "CONTRACT_NAME",
    "CONTRACT_VERSION",
    "ControlPlaneQREReadAdapter",
    "FORBIDDEN_CAPABILITIES",
    "READ_ONLY_METHODS",
    "ReadModelContract",
    "describe_contract",
)
FORBIDDEN_HTTP_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def test_package_migration_003_boundary_imports_canonical_contract() -> None:
    boundary = _load_boundary_module()

    assert boundary.describe_read_only_adapter_boundary() == describe_contract()
    assert classify_path(BOUNDARY_PATH.relative_to(REPO_ROOT)) == DOMAIN_CONTROL_PLANE
    assert (
        classify_module("packages.control_plane_qre_adapter_contract")
        == DOMAIN_ADAPTER_CONTRACT
    )
    assert classify_path("packages/ade_governance/README.md") == DOMAIN_ADE


def test_package_migration_003_compatibility_path_still_exposes_same_contract() -> None:
    assert canonical_contract.__all__ == list(PUBLIC_CONTRACT_NAMES)
    assert compatibility_contract.__all__ == list(PUBLIC_CONTRACT_NAMES)
    for name in PUBLIC_CONTRACT_NAMES:
        assert getattr(compatibility_contract, name) is getattr(
            canonical_contract,
            name,
        )


def test_package_migration_003_boundary_is_stdlib_plus_adapter_contract_only() -> None:
    imported_modules = _imported_modules(BOUNDARY_PATH)

    assert imported_modules == [
        "__future__",
        "packages.control_plane_qre_adapter_contract",
    ]
    assert not any(_has_forbidden_import_prefix(module) for module in imported_modules)


def test_package_migration_003_adds_no_dashboard_mutation_or_runtime_route() -> None:
    tree = ast.parse(BOUNDARY_PATH.read_text(encoding="utf-8"))
    route_decorators = [
        decorator
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        for decorator in node.decorator_list
        if isinstance(decorator, ast.Call)
        and isinstance(decorator.func, ast.Attribute)
        and decorator.func.attr == "route"
    ]
    string_constants = [
        node.value for node in ast.walk(tree) if isinstance(node, ast.Constant)
    ]

    assert route_decorators == []
    assert "flask" not in _imported_modules(BOUNDARY_PATH)
    assert "Flask" not in string_constants
    assert "Blueprint" not in string_constants
    assert not any(value in FORBIDDEN_HTTP_METHODS for value in string_constants)


def test_package_migration_003_scanner_has_no_forbidden_edges_and_keeps_legacy_visible() -> None:
    summary = report_to_summary_dict(scan_repo(REPO_ROOT))
    legacy_by_rule_and_domain = {
        (row["rule"], row["source_domain"], row["target_domain"]): row[
            "finding_count"
        ]
        for row in summary["legacy_finding_categories"]
    }

    assert summary["forbidden_edge_count"] == 0
    assert summary["legacy_edge_count"] > 0
    assert (
        legacy_by_rule_and_domain[
            ("control-plane-to-qre", DOMAIN_CONTROL_PLANE, DOMAIN_QRE)
        ]
        == 18
    )
    assert legacy_by_rule_and_domain[("ade-to-qre", DOMAIN_ADE, DOMAIN_QRE)] == 2
    assert legacy_by_rule_and_domain[
        ("mixed-domain", DOMAIN_CONTROL_PLANE, DOMAIN_ADAPTER_CONTRACT)
    ] == 1


def test_package_migration_003_changed_paths_stay_inside_bounded_slice() -> None:
    changed_paths = _changed_paths()

    assert changed_paths
    assert FROZEN_CONTRACT_PATHS.isdisjoint(changed_paths)
    assert not any(path.startswith(".claude/") for path in changed_paths)
    assert not any(
        path.startswith(prefix)
        for path in changed_paths
        for prefix in PROTECTED_PATH_PREFIXES
    )
    assert all(
        path.startswith(ALLOWED_CHANGED_PATH_PREFIXES)
        for path in changed_paths
    )


def test_package_migration_003_decision_doc_is_bounded_to_one_next_unit() -> None:
    text = MIGRATION_DOC.read_text(encoding="utf-8")

    assert "PACKAGE_MIGRATION_CONTINUES_WITH_BOUNDED_NEXT_UNIT" in text
    assert text.count("Exact next recommended unit:") == 1
    assert (
        "PACKAGE-MIGRATION-004 - Migrate QRE Diagnostics Read-Only Package Boundary"
        in text
    )
    assert "No frozen research outputs were changed." in text
    assert "No `.claude/**` files were changed." in text
    assert "No dashboard mutation routes were added." in text
    assert (
        "No live, paper, shadow, risk, broker, or execution behavior was changed."
        in text
    )


def _load_boundary_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "control_plane_read_only_adapter_boundary",
        BOUNDARY_PATH,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _imported_modules(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported_modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.append(node.module)
    return imported_modules


def _has_forbidden_import_prefix(module_name: str) -> bool:
    return any(
        module_name == prefix or module_name.startswith(prefix + ".")
        for prefix in FORBIDDEN_IMPORT_PREFIXES
    )


def _changed_paths() -> set[str]:
    paths: set[str] = set()
    for args in (
        ["diff", "--name-only", "main...HEAD"],
        ["diff", "--name-only", "origin/main...HEAD"],
        ["diff", "--name-only"],
        ["diff", "--name-only", "--cached"],
    ):
        result = subprocess.run(
            ["git", *args],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            continue
        paths.update(
            line.strip().replace("\\", "/")
            for line in result.stdout.splitlines()
            if line.strip()
        )
    return paths or _declared_migration_paths()


def _declared_migration_paths() -> set[str]:
    text = MIGRATION_DOC.read_text(encoding="utf-8")
    marker = "## Exact Files/Modules Migrated or Introduced"
    start = text.index(marker)
    next_section = text.index("\n## ", start + len(marker))
    section = text[start:next_section]
    return {
        line.strip().removeprefix("- `").removesuffix("`")
        for line in section.splitlines()
        if line.strip().startswith("- `")
    }
