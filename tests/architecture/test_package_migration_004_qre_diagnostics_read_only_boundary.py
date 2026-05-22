from __future__ import annotations

import ast
import subprocess
from pathlib import Path

import packages.qre_diagnostics.paths as canonical_paths
import research.diagnostics.paths as compatibility_paths
from reporting.architecture_import_scan import (
    DOMAIN_ADE,
    DOMAIN_CONTROL_PLANE,
    DOMAIN_QRE,
    classify_module,
    classify_path,
    report_to_summary_dict,
    scan_repo,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
CANONICAL_PATH = REPO_ROOT / "packages" / "qre_diagnostics" / "paths.py"
COMPATIBILITY_PATH = REPO_ROOT / "research" / "diagnostics" / "paths.py"
MIGRATION_DOC = (
    REPO_ROOT
    / "docs"
    / "architecture"
    / "PACKAGE-MIGRATION-004-qre-diagnostics-read-only-boundary.md"
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
    "docs/architecture/",
    "packages/qre_diagnostics/",
    "research/diagnostics/paths.py",
    "tests/architecture/",
    "tests/unit/",
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
    "risk",
    "shadow",
)
FORBIDDEN_HTTP_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def test_package_migration_004_canonical_import_path_works() -> None:
    assert classify_path(CANONICAL_PATH.relative_to(REPO_ROOT)) == DOMAIN_QRE
    assert classify_module("packages.qre_diagnostics.paths") == DOMAIN_QRE
    assert str(canonical_paths.OBSERVABILITY_DIR).replace("\\", "/") == (
        "research/observability"
    )
    assert canonical_paths.OBSERVABILITY_SCHEMA_VERSION == "1.0"


def test_package_migration_004_compatibility_import_path_preserves_contract() -> None:
    assert compatibility_paths.__all__ == canonical_paths.__all__
    for name in canonical_paths.__all__:
        assert getattr(compatibility_paths, name) is getattr(canonical_paths, name)


def test_package_migration_004_canonical_module_is_stdlib_only() -> None:
    imported_modules = _imported_modules(CANONICAL_PATH)

    assert imported_modules == ["__future__", "pathlib"]
    assert not any(_has_forbidden_import_prefix(module) for module in imported_modules)


def test_package_migration_004_compatibility_shim_imports_only_canonical_contract() -> None:
    imported_modules = _imported_modules(COMPATIBILITY_PATH)

    assert imported_modules == ["__future__", "packages.qre_diagnostics.paths"]
    assert not any(_has_forbidden_import_prefix(module) for module in imported_modules)


def test_package_migration_004_adds_no_dashboard_mutation_or_runtime_route() -> None:
    for path in (CANONICAL_PATH, COMPATIBILITY_PATH):
        tree = ast.parse(path.read_text(encoding="utf-8"))
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
        assert "flask" not in _imported_modules(path)
        assert "Flask" not in string_constants
        assert "Blueprint" not in string_constants
        assert not any(value in FORBIDDEN_HTTP_METHODS for value in string_constants)


def test_package_migration_004_scanner_has_no_forbidden_edges_and_keeps_legacy_visible() -> None:
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


def test_package_migration_004_changed_paths_stay_inside_bounded_slice() -> None:
    changed_paths = _changed_paths()

    assert changed_paths
    assert FROZEN_CONTRACT_PATHS.isdisjoint(changed_paths)
    assert not any(path.startswith(".claude/") for path in changed_paths)
    assert not any(
        path.startswith(prefix)
        for path in changed_paths
        for prefix in PROTECTED_PATH_PREFIXES
    )
    assert all(path.startswith(ALLOWED_CHANGED_PATH_PREFIXES) for path in changed_paths)


def test_package_migration_004_decision_doc_is_bounded_to_one_next_unit() -> None:
    text = MIGRATION_DOC.read_text(encoding="utf-8")

    assert "PACKAGE_MIGRATION_CONTINUES_WITH_BOUNDED_NEXT_UNIT" in text
    assert text.count("Exact next recommended unit:") == 1
    assert (
        "PACKAGE-MIGRATION-005 - Migrate QRE Artifacts Read-Only Package Boundary"
        in text
    )
    assert "No frozen research outputs were changed." in text
    assert "No `.claude/**` files were changed." in text
    assert "No dashboard mutation routes were added." in text
    assert (
        "No live, paper, shadow, risk, broker, or execution behavior was changed."
        in text
    )
    assert "No dashboard runtime route wiring was changed." in text


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
    declared_paths = _declared_migration_paths()
    relevant_paths = paths & declared_paths
    return relevant_paths or declared_paths


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
