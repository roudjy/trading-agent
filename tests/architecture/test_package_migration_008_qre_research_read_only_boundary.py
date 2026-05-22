from __future__ import annotations

import ast
import subprocess
from pathlib import Path

import packages.qre_research.universe as canonical_universe
import research.universe as compatibility_universe
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
CANONICAL_PATH = REPO_ROOT / "packages" / "qre_research" / "universe.py"
COMPATIBILITY_PATH = REPO_ROOT / "research" / "universe.py"
MIGRATION_DOC = (
    REPO_ROOT
    / "docs"
    / "architecture"
    / "PACKAGE-MIGRATION-008-qre-research-read-only-boundary.md"
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
    "docs/architecture/",
    "packages/qre_research/",
    "research/universe.py",
    "tests/architecture/",
)
PUBLIC_CONTRACT_NAMES = (
    "ResearchAsset",
    "UniverseSnapshot",
    "BUILTIN_UNIVERSES",
    "DEFAULT_SOURCE",
    "DEFAULT_INTERVALS",
    "UniverseResolver",
    "BuiltinResolver",
    "StaticResolver",
    "resolve_universe",
    "resolve_as_of_utc",
    "build_research_universe",
    "build_research_universe_from_preset",
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
    "research.run_research",
    "research.campaign_launcher",
    "research.runtime",
    "research.screening_runtime",
    "research.candidate_pipeline",
    "research.authority_trace",
    "research.promotion",
    "research.campaign_policy",
    "research.campaign_funnel_policy",
    "research.falsification",
    "research.falsification_reporting",
    "research.candidate_lifecycle",
    "research.paper_readiness",
)
FORBIDDEN_IO_CALL_NAMES = frozenset(
    {
        "open",
        "read_text",
        "write",
        "write_text",
        "write_bytes",
        "write_json_atomic",
        "write_sidecar_atomic",
    }
)
FORBIDDEN_HTTP_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def test_package_migration_008_canonical_import_path_works() -> None:
    assert classify_path(CANONICAL_PATH.relative_to(REPO_ROOT)) == DOMAIN_QRE
    assert classify_module("packages.qre_research.universe") == DOMAIN_QRE

    assets, snapshot = canonical_universe.resolve_universe(
        {"universe": {"source": canonical_universe.DEFAULT_SOURCE}},
        "2026-04-13T10:00:00+00:00",
    )

    assert assets
    assert snapshot.source == canonical_universe.DEFAULT_SOURCE
    assert snapshot.resolver == "builtin"


def test_package_migration_008_compatibility_import_path_preserves_contract() -> None:
    for name in PUBLIC_CONTRACT_NAMES:
        assert getattr(compatibility_universe, name) is getattr(
            canonical_universe,
            name,
        )


def test_package_migration_008_universe_behavior_is_preserved() -> None:
    config = {"universe": {"source": "crypto_major", "exclude": ["BTC-USD"]}}
    assets, snapshot = compatibility_universe.resolve_universe(
        config,
        "2026-04-13T10:00:00+00:00",
    )

    assert "BTC-USD" not in [asset.symbol for asset in assets]
    assert "BTC-USD" in snapshot.excluded_symbols
    assert snapshot.to_dict()["version"] == "v1"


def test_package_migration_008_canonical_module_imports_only_stdlib_sources() -> None:
    imported_modules = _imported_modules(CANONICAL_PATH)

    assert imported_modules == ["dataclasses", "datetime", "typing"]
    assert not any(_has_forbidden_import_prefix(module) for module in imported_modules)


def test_package_migration_008_compatibility_imports_only_canonical_universe_contract() -> None:
    imported_modules = _imported_modules(COMPATIBILITY_PATH)

    assert imported_modules == ["__future__", "packages.qre_research.universe"]
    assert not any(_has_forbidden_import_prefix(module) for module in imported_modules)


def test_package_migration_008_adds_no_io_dashboard_mutation_or_runtime_route() -> None:
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


def test_package_migration_008_scanner_has_no_forbidden_edges_and_keeps_legacy_visible() -> None:
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


def test_package_migration_008_changed_paths_stay_inside_bounded_slice() -> None:
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


def test_package_migration_008_decision_doc_is_bounded_to_one_next_unit() -> None:
    text = MIGRATION_DOC.read_text(encoding="utf-8")

    assert "PACKAGE_MIGRATION_CONTINUES_WITH_BOUNDED_NEXT_UNIT" in text
    assert text.count("Exact next recommended unit:") == 1
    assert (
        "PACKAGE-MIGRATION-009 - Validate Execution-Sim Future-Only Package Guards"
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
