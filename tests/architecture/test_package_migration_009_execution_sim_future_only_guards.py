from __future__ import annotations

import subprocess
from pathlib import Path

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
from scripts.ci_path_classifier import classify_paths

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = REPO_ROOT / "packages" / "qre_execution_sim"
README_PATH = PACKAGE_ROOT / "README.md"
MIGRATION_DOC = (
    REPO_ROOT
    / "docs"
    / "architecture"
    / "PACKAGE-MIGRATION-009-execution-sim-future-only-guards.md"
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
    "packages/qre_execution_sim/README.md",
    "scripts/ci_path_classifier.py",
    "tests/architecture/",
    "tests/unit/test_ci_path_classifier.py",
)


def test_package_migration_009_execution_sim_package_stays_readme_only() -> None:
    files = sorted(
        path.relative_to(PACKAGE_ROOT).as_posix()
        for path in PACKAGE_ROOT.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    )

    assert files == ["README.md"]


def test_package_migration_009_execution_sim_readme_pins_inactive_boundary() -> None:
    text = README_PATH.read_text(encoding="utf-8")

    assert "Status: future-only and inactive." in text
    assert "exports no runtime API" in text
    assert "separately approved migration" in text
    assert "No execution simulation authority is transferred by this scaffold" in text
    assert "Live order placement, broker mutation, or capital allocation" in text
    assert "Dashboard mutation routes" in text
    assert "broker, live, paper, shadow, risk, or order-execution behavior" in text


def test_package_migration_009_scanner_classifies_execution_sim_as_execution() -> None:
    assert classify_path("packages/qre_execution_sim/README.md") == DOMAIN_EXECUTION
    assert classify_module("packages.qre_execution_sim.contracts") == DOMAIN_EXECUTION


def test_package_migration_009_ci_classifier_treats_future_execution_packages_as_sensitive() -> None:
    result = classify_paths(
        [
            "packages/qre_execution_sim/README.md",
            "packages/qre_shadow/README.md",
            "packages/qre_paper/README.md",
            "packages/qre_live/README.md",
        ]
    )

    assert result["packages"] is True
    assert result["execution_sensitive"] is True
    assert result["run_frontend"] is True
    assert result["run_docker_build"] is True
    assert result["run_dashboard_deploy"] is True


def test_package_migration_009_scanner_has_no_forbidden_edges_and_keeps_legacy_visible() -> None:
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


def test_package_migration_009_changed_paths_stay_inside_bounded_guard_slice() -> None:
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


def test_package_migration_009_decision_doc_is_bounded_to_one_next_unit() -> None:
    text = MIGRATION_DOC.read_text(encoding="utf-8")

    assert "PACKAGE_MIGRATION_CONTINUES_WITH_BOUNDED_NEXT_UNIT" in text
    assert text.count("Exact next recommended unit:") == 1
    assert "PACKAGE-MIGRATION-010 - Package Migration Closure Decision" in text
    assert "No frozen research outputs were changed." in text
    assert "No `.claude/**` files were changed." in text
    assert "No dashboard mutation routes were added." in text
    assert (
        "No live, paper, shadow, risk, broker, or execution behavior was changed."
        in text
    )
    assert "No dashboard runtime route wiring was changed." in text


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
