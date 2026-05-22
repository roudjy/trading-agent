from __future__ import annotations

import ast
import subprocess
from dataclasses import FrozenInstanceError, asdict
from datetime import UTC, datetime
from pathlib import Path

import pytest

import data.contracts as compatibility_contracts
import packages.qre_data.contracts as canonical_contracts
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
CANONICAL_PATH = REPO_ROOT / "packages" / "qre_data" / "contracts.py"
COMPATIBILITY_PATH = REPO_ROOT / "data" / "contracts.py"
MIGRATION_DOC = (
    REPO_ROOT
    / "docs"
    / "architecture"
    / "PACKAGE-MIGRATION-007-qre-data-read-only-boundary.md"
)
FROZEN_CONTRACT_PATHS = {
    "research/research_latest.json",
    "research/strategy_matrix.csv",
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
    "data/contracts.py",
    "docs/architecture/",
    "packages/qre_data/",
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
    "risk",
    "shadow",
    "data.repository",
    "data.adapters",
    "pandas",
)
FORBIDDEN_IO_CALL_NAMES = frozenset(
    {
        "open",
        "read_parquet",
        "to_parquet",
        "write",
        "write_text",
        "write_bytes",
    }
)
FORBIDDEN_HTTP_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def test_package_migration_007_canonical_import_path_works() -> None:
    assert classify_path(CANONICAL_PATH.relative_to(REPO_ROOT)) == DOMAIN_QRE
    assert classify_module("packages.qre_data.contracts") == DOMAIN_QRE

    instrument = canonical_contracts.Instrument(
        id="btc-usd",
        asset_class="crypto",
        venue="yahoo",
        native_symbol="BTC-USD",
        quote_ccy="USD",
    )

    assert instrument.native_symbol == "BTC-USD"


def test_package_migration_007_compatibility_import_path_preserves_contract() -> None:
    assert compatibility_contracts.__all__ == canonical_contracts.__all__
    for name in canonical_contracts.__all__:
        assert getattr(compatibility_contracts, name) is getattr(
            canonical_contracts,
            name,
        )


def test_package_migration_007_dataclass_behavior_is_preserved() -> None:
    provenance = compatibility_contracts.Provenance(
        adapter="fixture",
        fetched_at_utc=datetime(2026, 4, 10, 10, 0, tzinfo=UTC),
        config_hash="cfg-1",
        source_version="1.0",
        cache_hit=False,
    )
    instrument = compatibility_contracts.Instrument(
        id="btc-usd",
        asset_class="crypto",
        venue="yahoo",
        native_symbol="BTC-USD",
        quote_ccy="USD",
    )
    bar = compatibility_contracts.CanonicalBar(
        instrument=instrument,
        interval="1h",
        timestamp_utc=datetime(2026, 4, 10, 9, 0, tzinfo=UTC),
        open=1.0,
        high=2.0,
        low=0.5,
        close=1.5,
        volume=100.0,
        provenance=provenance,
    )

    assert asdict(provenance)["adapter"] == "fixture"
    assert bar.provenance is provenance
    with pytest.raises(FrozenInstanceError):
        provenance.adapter = "changed"


def test_package_migration_007_canonical_module_is_stdlib_only() -> None:
    imported_modules = _imported_modules(CANONICAL_PATH)

    assert imported_modules == ["__future__", "dataclasses", "datetime", "typing"]
    assert not any(_has_forbidden_import_prefix(module) for module in imported_modules)


def test_package_migration_007_compatibility_imports_only_canonical_data_contract() -> None:
    imported_modules = _imported_modules(COMPATIBILITY_PATH)

    assert imported_modules == ["__future__", "packages.qre_data.contracts"]
    assert not any(_has_forbidden_import_prefix(module) for module in imported_modules)


def test_package_migration_007_adds_no_io_dashboard_mutation_or_runtime_route() -> None:
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
        called = _called_functions(tree)

        assert route_decorators == []
        assert called & FORBIDDEN_IO_CALL_NAMES == set()
        assert "flask" not in _imported_modules(path)
        assert "Flask" not in string_constants
        assert "Blueprint" not in string_constants
        assert not any(value in FORBIDDEN_HTTP_METHODS for value in string_constants)


def test_package_migration_007_scanner_has_no_forbidden_edges_and_keeps_legacy_visible() -> None:
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


def test_package_migration_007_changed_paths_stay_inside_bounded_slice() -> None:
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


def test_package_migration_007_decision_doc_is_bounded_to_one_next_unit() -> None:
    text = MIGRATION_DOC.read_text(encoding="utf-8")

    assert "PACKAGE_MIGRATION_CONTINUES_WITH_BOUNDED_NEXT_UNIT" in text
    assert text.count("Exact next recommended unit:") == 1
    assert (
        "PACKAGE-MIGRATION-008 - Migrate QRE Research Read-Only Package Boundary"
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


def _called_functions(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                names.add(func.id)
            elif isinstance(func, ast.Attribute):
                names.add(func.attr)
    return names


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
