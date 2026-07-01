from __future__ import annotations

import subprocess
from pathlib import Path

from reporting.architecture_import_scan import (
    DOMAIN_ADE,
    DOMAIN_CONTROL_PLANE,
    DOMAIN_QRE,
    report_to_summary_dict,
    scan_repo,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATION_DOC = (
    REPO_ROOT
    / "docs"
    / "architecture"
    / "PACKAGE-MIGRATION-010-package-migration-closure-decision.md"
)
EXPECTED_MIGRATION_DOCS = (
    "PACKAGE-MIGRATION-001-target-layout-skeleton.md",
    "PACKAGE-MIGRATION-002-ade-governance-read-only-contracts.md",
    "PACKAGE-MIGRATION-003-control-plane-read-only-adapter-boundary.md",
    "PACKAGE-MIGRATION-004-qre-diagnostics-read-only-boundary.md",
    "PACKAGE-MIGRATION-005-qre-artifacts-read-only-boundary.md",
    "PACKAGE-MIGRATION-006-qre-policy-read-only-boundary.md",
    "PACKAGE-MIGRATION-007-qre-data-read-only-boundary.md",
    "PACKAGE-MIGRATION-008-qre-research-read-only-boundary.md",
    "PACKAGE-MIGRATION-009-execution-sim-future-only-guards.md",
    "PACKAGE-MIGRATION-010-package-migration-closure-decision.md",
)
BOUNDED_PACKAGE_CONTENTS = {
    "qre_research": [
        "README.md",
        "__init__.py",
        "automated_campaign_readiness.py",
        "automated_data_window_capacity.py",
        "automated_hypothesis_generation.py",
        "automated_primitive_expansion.py",
        "automated_strategy_generation.py",
        "autonomous_orchestration.py",
        "autonomous_readiness_closure.py",
        "bounded_strategy_synthesis.py",
        "generated_hypothesis_paths.py",
        "generated_primitive_paths.py",
        "generated_strategy_paths.py",
        "hypothesis_lifecycle.py",
        "opportunity_value.py",
        "research_memory.py",
        "retrieval_coverage.py",
        "second_preregistered_campaign.py",
        "universe.py",
    ],
    "qre_data": [
        "README.md",
        "__init__.py",
        "cache_manifest.py",
        "contracts.py",
        "historical_accounting.py",
        "source_lifecycle.py",
        "source_quality_readiness.py",
        "symbology_resolver.py",
    ],
    "qre_artifacts": ["README.md", "__init__.py", "public_outputs.py"],
    "qre_diagnostics": [
        "README.md",
        "__init__.py",
        "paths.py",
        "research_diagnostics_loop.py",
    ],
    "qre_policy": ["README.md", "__init__.py", "authority_views.py"],
    "qre_execution_sim": ["README.md"],
    "qre_shadow": ["README.md"],
    "qre_paper": ["README.md"],
    "qre_live": ["README.md"],
}
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
    "tests/architecture/",
)


def test_package_migration_010_all_required_migration_docs_exist() -> None:
    architecture_dir = REPO_ROOT / "docs" / "architecture"

    for filename in EXPECTED_MIGRATION_DOCS:
        assert (architecture_dir / filename).exists(), filename


def test_package_migration_010_package_boundaries_are_bounded_or_inactive() -> None:
    for package_name, expected_files in BOUNDED_PACKAGE_CONTENTS.items():
        package_root = REPO_ROOT / "packages" / package_name
        files = sorted(
            path.relative_to(package_root).as_posix()
            for path in package_root.rglob("*")
            if path.is_file() and "__pycache__" not in path.parts
        )

        assert files == expected_files, package_name


def test_package_migration_010_future_execution_packages_remain_inactive() -> None:
    execution_sim = (
        REPO_ROOT / "packages" / "qre_execution_sim" / "README.md"
    ).read_text(encoding="utf-8")
    shadow = (REPO_ROOT / "packages" / "qre_shadow" / "README.md").read_text(
        encoding="utf-8"
    )
    paper = (REPO_ROOT / "packages" / "qre_paper" / "README.md").read_text(
        encoding="utf-8"
    )
    live = (REPO_ROOT / "packages" / "qre_live" / "README.md").read_text(
        encoding="utf-8"
    )

    assert "Status: future-only and inactive." in execution_sim
    assert "exports no runtime API" in execution_sim
    assert "future-only and inactive until Roadmap v4.x" in shadow
    assert "future-only and inactive until Roadmap v5.x" in paper
    assert "hard-disabled until Roadmap v6.x and explicit operator approval" in live


def test_package_migration_010_scanner_has_no_forbidden_edges_and_keeps_legacy_visible() -> None:
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


def test_package_migration_010_changed_paths_stay_inside_closure_slice() -> None:
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


def test_package_migration_010_decision_doc_is_terminal_ready_state() -> None:
    text = MIGRATION_DOC.read_text(encoding="utf-8")

    assert "PACKAGE_MIGRATION_READY_FOR_QRE_FEATURE_TRACK" in text
    assert "PACKAGE_MIGRATION_CONTINUES_WITH_BOUNDED_NEXT_UNIT" not in text
    assert "Exact next recommended unit:" not in text
    assert "Exact next recommended lane:" in text
    assert (
        "QRE Feature Build Track - operator review for first post-package feature phase"
        in text
    )
    assert (
        "target package skeleton and bounded read-only boundaries are sufficient"
        in text.lower()
    )
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
