from __future__ import annotations

from pathlib import Path

from reporting.architecture_import_scan import (
    DOMAIN_ADE,
    DOMAIN_CONTROL_PLANE,
    DOMAIN_EXECUTION,
    DOMAIN_QRE,
    classify_module,
    classify_path,
    legacy_edge_allowlist_entries,
    report_to_summary_dict,
    scan_repo,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_MIGRATION_DOC = (
    REPO_ROOT / "docs" / "architecture" / "PACKAGE-MIGRATION-001-target-layout-skeleton.md"
)

TARGET_READMES = (
    REPO_ROOT / "apps" / "control-plane" / "README.md",
    REPO_ROOT / "packages" / "ade_governance" / "README.md",
    REPO_ROOT / "packages" / "qre_research" / "README.md",
    REPO_ROOT / "packages" / "qre_data" / "README.md",
    REPO_ROOT / "packages" / "qre_artifacts" / "README.md",
    REPO_ROOT / "packages" / "qre_diagnostics" / "README.md",
    REPO_ROOT / "packages" / "qre_policy" / "README.md",
    REPO_ROOT / "packages" / "qre_execution_sim" / "README.md",
    REPO_ROOT / "packages" / "qre_shadow" / "README.md",
    REPO_ROOT / "packages" / "qre_paper" / "README.md",
    REPO_ROOT / "packages" / "qre_live" / "README.md",
)

README_REQUIRED_SECTIONS = (
    "## Purpose",
    "## Current Status",
    "## Source of Truth / Authority Boundary",
    "## Allowed Future Contents",
    "## Forbidden Contents",
    "## Migration Preconditions",
    "## Current Compatibility Policy",
    "## Activation Status",
)

SCAFFOLD_ONLY_TARGETS = (
    REPO_ROOT / "packages" / "qre_execution_sim",
    REPO_ROOT / "packages" / "qre_shadow",
    REPO_ROOT / "packages" / "qre_paper",
    REPO_ROOT / "packages" / "qre_live",
)


def test_package_migration_001_target_skeleton_readmes_exist() -> None:
    for readme in TARGET_READMES:
        assert readme.exists(), readme
        assert readme.parent.is_dir(), readme.parent


def test_package_migration_001_readmes_define_required_governance_sections() -> None:
    for readme in TARGET_READMES:
        text = readme.read_text(encoding="utf-8")
        for section in README_REQUIRED_SECTIONS:
            assert section in text, f"{readme} missing {section}"
        assert "Forbidden Contents" in text
        assert "Status:" in text


def test_package_migration_001_future_and_disabled_packages_stay_inactive() -> None:
    qre_shadow = (REPO_ROOT / "packages" / "qre_shadow" / "README.md").read_text(
        encoding="utf-8"
    )
    qre_paper = (REPO_ROOT / "packages" / "qre_paper" / "README.md").read_text(
        encoding="utf-8"
    )
    qre_live = (REPO_ROOT / "packages" / "qre_live" / "README.md").read_text(
        encoding="utf-8"
    )

    assert "future-only and inactive until Roadmap v4.x" in qre_shadow
    assert "future-only and inactive until Roadmap v5.x" in qre_paper
    assert "hard-disabled until Roadmap v6.x and explicit operator approval" in qre_live
    assert "No live order\nplacement, broker mutation, capital allocation, or live risk behavior is\nauthorized by this scaffold." in qre_live


def test_package_migration_001_scaffold_targets_do_not_contain_runtime_modules() -> None:
    for target in SCAFFOLD_ONLY_TARGETS:
        files = sorted(
            path.relative_to(target).as_posix()
            for path in target.rglob("*")
            if path.is_file() and "__pycache__" not in path.parts
        )
        assert files == ["README.md"], target


def test_package_migration_001_qre_diagnostics_has_only_bounded_read_only_seed() -> None:
    target = REPO_ROOT / "packages" / "qre_diagnostics"
    files = sorted(
        path.relative_to(target).as_posix()
        for path in target.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    )

    assert files == [
        "README.md",
        "__init__.py",
        "paths.py",
        "research_diagnostics_loop.py",
    ], target


def test_package_migration_001_qre_artifacts_has_only_bounded_read_only_seed() -> None:
    target = REPO_ROOT / "packages" / "qre_artifacts"
    files = sorted(
        path.relative_to(target).as_posix()
        for path in target.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    )

    assert files == ["README.md", "__init__.py", "public_outputs.py"], target


def test_package_migration_001_qre_policy_has_only_bounded_read_only_seed() -> None:
    target = REPO_ROOT / "packages" / "qre_policy"
    files = sorted(
        path.relative_to(target).as_posix()
        for path in target.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    )

    assert files == ["README.md", "__init__.py", "authority_views.py"], target


def test_package_migration_001_qre_data_has_only_bounded_read_only_seed() -> None:
    target = REPO_ROOT / "packages" / "qre_data"
    files = sorted(
        path.relative_to(target).as_posix()
        for path in target.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    )

    assert files == [
        "README.md",
        "__init__.py",
        "bar_integrity.py",
        "cache_manifest.py",
        "contracts.py",
        "dataset_catalog.py",
        "historical_accounting.py",
        "source_lifecycle.py",
        "source_quality_readiness.py",
        "symbology_resolver.py",
    ], target


def test_package_migration_001_qre_research_has_only_bounded_read_only_seed() -> None:
    target = REPO_ROOT / "packages" / "qre_research"
    files = sorted(
        path.relative_to(target).as_posix()
        for path in target.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    )

    assert files == [
        "README.md",
        "__init__.py",
        "alpha_discovery/__init__.py",
        "alpha_discovery/acquisition.py",
        "alpha_discovery/capability_loop.py",
        "alpha_discovery/contracts.py",
        "alpha_discovery/data_planner.py",
        "alpha_discovery/evaluation.py",
        "alpha_discovery/experiment_compiler.py",
        "alpha_discovery/firewall.py",
        "alpha_discovery/learning.py",
        "alpha_discovery/observations.py",
        "alpha_discovery/providers.py",
        "alpha_discovery/runner.py",
        "alpha_discovery/snapshot_lineage.py",
        "alpha_discovery/source_qualification.py",
        "alpha_discovery/source_resolution.py",
        "alpha_discovery/strategy_compiler.py",
        "alpha_discovery/strategy_ir.py",
        "alpha_discovery/universe_planner.py",
        "architecture_registry.py",
        "automated_campaign_readiness.py",
        "automated_data_window_capacity.py",
        "automated_hypothesis_generation.py",
        "automated_primitive_expansion.py",
        "automated_strategy_generation.py",
        "autonomous_opportunity_loop.py",
        "autonomous_orchestration.py",
        "autonomous_readiness_closure.py",
        "bounded_strategy_synthesis.py",
        "candidate_planning_bridge.py",
        "canonical_contracts.py",
        "canonical_funnel_verification.py",
        "decision_calibration.py",
        "empirical_evidence_pack.py",
        "empirical_research_flywheel.py",
        "evidence_memory_accumulation.py",
        "evidence_memory_bridge.py",
        "funnel_classification.py",
        "generated_hypothesis_paths.py",
        "generated_primitive_paths.py",
        "generated_strategy_paths.py",
        "governed_candidate_batch.py",
        "hypothesis_generator_governance.py",
        "hypothesis_lifecycle.py",
        "maturity_gate.py",
        "memory_aware_hypothesis_generation.py",
        "offline_research_dry_run.py",
        "operator_trust_multirun_report.py",
        "opportunity_value.py",
        "rejection_reasons.py",
        "research_memory.py",
        "research_throughput_controls.py",
        "retrieval_coverage.py",
        "second_preregistered_campaign.py",
        "tiingo_canonical_bridge.py",
        "universe.py",
    ], target


def test_package_migration_001_scanner_classifies_target_paths() -> None:
    assert classify_path("apps/control-plane/README.md") == DOMAIN_CONTROL_PLANE
    assert classify_path("packages/ade_governance/README.md") == DOMAIN_ADE
    assert classify_path("packages/qre_research/README.md") == DOMAIN_QRE
    assert classify_path("packages/qre_research/opportunity_value.py") == DOMAIN_QRE
    assert classify_path("packages/qre_research/canonical_contracts.py") == DOMAIN_QRE
    assert classify_path("packages/qre_research/candidate_planning_bridge.py") == DOMAIN_QRE
    assert classify_path("packages/qre_research/memory_aware_hypothesis_generation.py") == DOMAIN_QRE
    assert classify_path("packages/qre_research/research_memory.py") == DOMAIN_QRE
    assert classify_path("packages/qre_research/evidence_memory_bridge.py") == DOMAIN_QRE
    assert classify_path("packages/qre_research/funnel_classification.py") == DOMAIN_QRE
    assert classify_path("packages/qre_research/tiingo_canonical_bridge.py") == DOMAIN_QRE
    assert classify_path("packages/qre_research/retrieval_coverage.py") == DOMAIN_QRE
    assert classify_path("packages/qre_research/universe.py") == DOMAIN_QRE
    assert classify_path("packages/qre_data/README.md") == DOMAIN_QRE
    assert classify_path("packages/qre_data/cache_manifest.py") == DOMAIN_QRE
    assert classify_path("packages/qre_data/contracts.py") == DOMAIN_QRE
    assert classify_path("packages/qre_data/dataset_catalog.py") == DOMAIN_QRE
    assert classify_path("packages/qre_data/historical_accounting.py") == DOMAIN_QRE
    assert classify_path("packages/qre_data/symbology_resolver.py") == DOMAIN_QRE
    assert classify_path("packages/qre_data/source_lifecycle.py") == DOMAIN_QRE
    assert classify_path("packages/qre_data/source_quality_readiness.py") == DOMAIN_QRE
    assert classify_path("packages/qre_artifacts/README.md") == DOMAIN_QRE
    assert classify_path("packages/qre_artifacts/public_outputs.py") == DOMAIN_QRE
    assert classify_path("packages/qre_diagnostics/README.md") == DOMAIN_QRE
    assert classify_path("packages/qre_diagnostics/research_diagnostics_loop.py") == DOMAIN_QRE
    assert classify_path("packages/qre_policy/README.md") == DOMAIN_QRE
    assert classify_path("packages/qre_policy/authority_views.py") == DOMAIN_QRE
    assert classify_path("packages/qre_execution_sim/README.md") == DOMAIN_EXECUTION
    assert classify_path("packages/qre_shadow/README.md") == DOMAIN_EXECUTION
    assert classify_path("packages/qre_paper/README.md") == DOMAIN_EXECUTION
    assert classify_path("packages/qre_live/README.md") == DOMAIN_EXECUTION

    assert classify_module("packages.qre_research.opportunity_value") == DOMAIN_QRE
    assert classify_module("packages.qre_research.canonical_contracts") == DOMAIN_QRE
    assert classify_module("packages.qre_research.candidate_planning_bridge") == DOMAIN_QRE
    assert classify_module("packages.qre_research.memory_aware_hypothesis_generation") == DOMAIN_QRE
    assert classify_module("packages.qre_research.research_memory") == DOMAIN_QRE
    assert classify_module("packages.qre_research.evidence_memory_bridge") == DOMAIN_QRE
    assert classify_module("packages.qre_research.funnel_classification") == DOMAIN_QRE
    assert classify_module("packages.qre_research.tiingo_canonical_bridge") == DOMAIN_QRE
    assert classify_module("packages.qre_research.universe") == DOMAIN_QRE
    assert classify_module("packages.qre_data.cache_manifest") == DOMAIN_QRE
    assert classify_module("packages.qre_data.contracts") == DOMAIN_QRE
    assert classify_module("packages.qre_data.dataset_catalog") == DOMAIN_QRE
    assert classify_module("packages.qre_data.historical_accounting") == DOMAIN_QRE
    assert classify_module("packages.qre_data.symbology_resolver") == DOMAIN_QRE
    assert classify_module("packages.qre_data.source_lifecycle") == DOMAIN_QRE
    assert classify_module("packages.qre_data.source_quality_readiness") == DOMAIN_QRE
    assert classify_module("packages.qre_artifacts.public_outputs") == DOMAIN_QRE
    assert classify_module("packages.qre_diagnostics.research_diagnostics_loop") == DOMAIN_QRE
    assert classify_module("packages.qre_policy.authority_views") == DOMAIN_QRE
    assert classify_module("packages.qre_live.contracts") == DOMAIN_EXECUTION


def test_package_migration_001_scanner_keeps_legacy_visible_without_failures() -> None:
    summary = report_to_summary_dict(scan_repo(REPO_ROOT))
    legacy_by_rule_and_domain = {
        (row["rule"], row["source_domain"], row["target_domain"]): row[
            "finding_count"
        ]
        for row in summary["legacy_finding_categories"]
    }

    assert summary["forbidden_edge_count"] == 0
    assert summary["legacy_edge_count"] >= 74
    assert legacy_by_rule_and_domain[
        ("control-plane-to-qre", DOMAIN_CONTROL_PLANE, DOMAIN_QRE)
    ] == 18
    assert legacy_by_rule_and_domain[("ade-to-qre", DOMAIN_ADE, DOMAIN_QRE)] == 2


def test_package_migration_001_has_no_wildcard_legacy_allowlists() -> None:
    for entry in legacy_edge_allowlist_entries():
        assert "*" not in entry.source_module
        assert "*" not in entry.target_module


def test_package_migration_001_decision_doc_is_bounded_to_one_next_unit() -> None:
    text = PACKAGE_MIGRATION_DOC.read_text(encoding="utf-8")

    assert "PACKAGE_MIGRATION_CONTINUES_WITH_BOUNDED_NEXT_UNIT" in text
    assert text.count("Exact next recommended unit:") == 1
    assert (
        "PACKAGE-MIGRATION-002 - Migrate ADE Governance Read-Only Contracts"
        in text
    )
    assert "No additional package-migration sequence is authorized" in text
    assert "No frozen research outputs were changed." in text
    assert "No `.claude/**` files were changed." in text
    assert "No dashboard mutation routes were added." in text
