from __future__ import annotations

import ast
from pathlib import Path

import packages.ade_governance.architecture_import_contracts as legacy_contracts
import packages.ade_governance.import_contracts.architecture_import as canonical_contracts
import reporting.architecture_import_scan as compatibility_scanner
from reporting.architecture_import_scan import (
    DOMAIN_ADE,
    DOMAIN_CONTROL_PLANE,
    DOMAIN_EXECUTION,
    DOMAIN_QRE,
    BoundaryReport,
    ImportEdge,
    classify_module,
    classify_path,
    report_to_summary_dict,
    scan_repo,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
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


def test_architecture_import_contracts_have_canonical_package_path() -> None:
    edge = ImportEdge(
        source_module="reporting.future_architecture_tool",
        target_module="packages.ade_governance.import_contracts.architecture_import",
        source_path="reporting/future_architecture_tool.py",
        source_domain=DOMAIN_ADE,
        target_domain=DOMAIN_ADE,
        target_root="packages",
        line=3,
        import_kind="from",
    )

    report = BoundaryReport(edges=(edge,), forbidden_edges=(), legacy_edges=())

    assert classify_path(CANONICAL_CONTRACT_PATH.relative_to(REPO_ROOT)) == DOMAIN_ADE
    assert (
        classify_module("packages.ade_governance.import_contracts.architecture_import")
        == DOMAIN_ADE
    )
    assert classify_path(LEGACY_CONTRACT_PATH.relative_to(REPO_ROOT)) == DOMAIN_ADE
    assert (
        classify_module("packages.ade_governance.architecture_import_contracts")
        == DOMAIN_ADE
    )
    assert report_to_summary_dict(report)["forbidden_edge_count"] == 0


def test_legacy_and_reporting_paths_reexport_same_public_contract_objects() -> None:
    assert canonical_contracts.__all__ == list(PUBLIC_CONTRACT_NAMES)
    assert legacy_contracts.__all__ == list(PUBLIC_CONTRACT_NAMES)
    for name in PUBLIC_CONTRACT_NAMES:
        assert getattr(legacy_contracts, name) is getattr(
            canonical_contracts,
            name,
        )
        assert getattr(compatibility_scanner, name) is getattr(
            canonical_contracts,
            name,
        )


def test_architecture_import_contracts_are_stdlib_only() -> None:
    imported_modules = _imported_modules(CANONICAL_CONTRACT_PATH)
    violations = [
        module
        for module in imported_modules
        if any(
            module == prefix or module.startswith(prefix + ".")
            for prefix in FORBIDDEN_IMPORT_PREFIXES
        )
    ]

    assert violations == []
    assert imported_modules == ["__future__", "dataclasses"]


def test_architecture_import_contracts_introduce_no_runtime_or_dashboard_edges() -> None:
    report = scan_repo(REPO_ROOT)
    contract_edges = [
        edge
        for edge in report.edges
        if edge.source_module
        == "packages.ade_governance.import_contracts.architecture_import"
    ]
    contract_forbidden = [
        finding
        for finding in report.forbidden_edges
        if finding.source_module
        == "packages.ade_governance.import_contracts.architecture_import"
    ]
    contract_legacy = [
        finding
        for finding in report.legacy_edges
        if finding.source_module
        == "packages.ade_governance.import_contracts.architecture_import"
    ]

    assert [(edge.target_module, edge.target_domain) for edge in contract_edges] == [
        ("__future__", "unknown"),
        ("dataclasses", "unknown"),
    ]
    assert contract_forbidden == []
    assert contract_legacy == []


def test_scanner_summary_still_reports_legacy_without_hard_failures() -> None:
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
    assert legacy_by_rule_and_domain[
        ("mixed-domain", DOMAIN_QRE, DOMAIN_EXECUTION)
    ] == 11


def _imported_modules(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported_modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.append(node.module)
    return imported_modules
