from __future__ import annotations

import ast
import subprocess
from pathlib import Path

import packages.ade_governance as package_exports
import packages.ade_governance.architecture_import_contracts as legacy_contracts
import packages.ade_governance.import_contracts as import_contracts
import packages.ade_governance.import_contracts.architecture_import as canonical_contracts
import reporting.architecture_import_scan as scanner_compatibility
from reporting.architecture_import_scan import (
    DOMAIN_ADE,
    DOMAIN_CONTROL_PLANE,
    DOMAIN_EXECUTION,
    DOMAIN_QRE,
    classify_module,
    classify_path,
    report_to_summary_dict,
    scan_repo,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATION_DOC = (
    REPO_ROOT
    / "docs"
    / "architecture"
    / "PACKAGE-MIGRATION-002-ade-governance-read-only-contracts.md"
)
CANONICAL_CONTRACT_PATH = (
    REPO_ROOT
    / "packages"
    / "ade_governance"
    / "import_contracts"
    / "architecture_import.py"
)
LEGACY_CONTRACT_PATH = (
    REPO_ROOT / "packages" / "ade_governance" / "architecture_import_contracts.py"
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
RUNTIME_ROUTE_PATH_PREFIXES = (
    "dashboard/",
    "frontend/",
    "apps/control-plane/",
)
PUBLIC_CONTRACT_NAMES = (
    "BoundaryFinding",
    "BoundaryReport",
    "DOMAIN_ADAPTER_CONTRACT",
    "DOMAIN_ADE",
    "DOMAIN_CONTROL_PLANE",
    "DOMAIN_EXECUTION",
    "DOMAIN_GOVERNANCE_TOOLING",
    "DOMAIN_QRE",
    "DOMAIN_TESTS",
    "DOMAIN_UNKNOWN",
    "EXECUTION_PATH_ROOTS",
    "ImportEdge",
    "LegacyEdgeAllowlistEntry",
)


def test_package_migration_002_canonical_namespace_imports() -> None:
    assert canonical_contracts.__all__ == list(PUBLIC_CONTRACT_NAMES)
    assert import_contracts.ImportEdge is canonical_contracts.ImportEdge
    assert package_exports.ImportEdge is canonical_contracts.ImportEdge
    assert (
        classify_module("packages.ade_governance.import_contracts")
        == DOMAIN_ADE
    )
    assert (
        classify_module("packages.ade_governance.import_contracts.architecture_import")
        == DOMAIN_ADE
    )
    assert classify_path(CANONICAL_CONTRACT_PATH.relative_to(REPO_ROOT)) == DOMAIN_ADE


def test_package_migration_002_compatibility_imports_are_preserved() -> None:
    for name in PUBLIC_CONTRACT_NAMES:
        canonical_object = getattr(canonical_contracts, name)
        assert getattr(legacy_contracts, name) is canonical_object
        assert getattr(scanner_compatibility, name) is canonical_object


def test_package_migration_002_contract_modules_are_stdlib_only() -> None:
    assert _imported_modules(CANONICAL_CONTRACT_PATH) == [
        "__future__",
        "dataclasses",
    ]
    legacy_imports = _imported_modules(LEGACY_CONTRACT_PATH)
    assert legacy_imports == [
        "__future__",
        "packages.ade_governance.import_contracts.architecture_import",
    ]

    for module in _imported_modules(CANONICAL_CONTRACT_PATH) + legacy_imports:
        assert not _has_forbidden_import_prefix(module)


def test_package_migration_002_scanner_has_no_forbidden_edges_and_keeps_legacy_visible() -> None:
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
        ("mixed-domain", DOMAIN_QRE, DOMAIN_EXECUTION)
    ] == 11


def test_package_migration_002_changed_paths_stay_inside_bounded_slice() -> None:
    changed_paths = _changed_paths()

    assert changed_paths
    assert FROZEN_CONTRACT_PATHS.isdisjoint(changed_paths)
    assert not any(path.startswith(".claude/") for path in changed_paths)
    assert not any(
        path.startswith(prefix)
        for path in changed_paths
        for prefix in PROTECTED_PATH_PREFIXES
    )
    assert not any(
        path.startswith(prefix)
        for path in changed_paths
        for prefix in RUNTIME_ROUTE_PATH_PREFIXES
    )
    assert all(
        path.startswith(
            (
                "docs/architecture/",
                "packages/ade_governance/",
                "reporting/architecture_import_scan.py",
                "tests/architecture/",
            )
        )
        for path in changed_paths
    )


def test_package_migration_002_decision_doc_is_bounded_to_one_next_unit() -> None:
    text = MIGRATION_DOC.read_text(encoding="utf-8")

    assert "PACKAGE_MIGRATION_CONTINUES_WITH_BOUNDED_NEXT_UNIT" in text
    assert text.count("Exact next recommended unit:") == 1
    assert (
        "PACKAGE-MIGRATION-003 - Migrate Control-Plane Read-Only Adapter Consumer "
        "or Package Boundary"
    ) in text
    assert "No dashboard mutation routes were added." in text
    assert (
        "No live, paper, shadow, risk, broker, or execution behavior was changed."
        in text
    )
    assert "No frozen research outputs were changed." in text
    assert "No `.claude/**` files were changed." in text


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
    marker = "## Files Changed"
    start = text.index(marker)
    next_section = text.index("\n## ", start + len(marker))
    section = text[start:next_section]
    return {
        line.strip().removeprefix("- `").removesuffix("`")
        for line in section.splitlines()
        if line.strip().startswith("- `")
    }
