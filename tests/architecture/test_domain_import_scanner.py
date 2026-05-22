from __future__ import annotations

import json
import subprocess
from pathlib import Path

from reporting.architecture_import_scan import (
    DOMAIN_ADAPTER_CONTRACT,
    DOMAIN_ADE,
    DOMAIN_CONTROL_PLANE,
    DOMAIN_EXECUTION,
    DOMAIN_GOVERNANCE_TOOLING,
    DOMAIN_QRE,
    DOMAIN_TESTS,
    ImportEdge,
    classify_module,
    classify_path,
    evaluate_edges,
    legacy_edge_allowlist_entries,
    report_to_dict,
    report_to_summary_dict,
    report_to_text,
    scan_files,
    scan_repo,
    tracked_python_files,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_tracked_python_files_excludes_untracked_files(tmp_path: Path) -> None:
    _git(tmp_path, "init")
    tracked = tmp_path / "pkg" / "tracked.py"
    untracked = tmp_path / "pkg" / "untracked.py"
    tracked.parent.mkdir()
    tracked.write_text("import os\n", encoding="utf-8")
    untracked.write_text("import sys\n", encoding="utf-8")
    _git(tmp_path, "add", "pkg/tracked.py")
    _git(tmp_path, "commit", "-m", "add tracked file")

    assert tracked_python_files(tmp_path) == (Path("pkg/tracked.py"),)


def test_scanner_parses_imports_deterministically(tmp_path: Path) -> None:
    source = tmp_path / "dashboard" / "api.py"
    target = tmp_path / "research" / "campaigns.py"
    source.parent.mkdir()
    target.parent.mkdir()
    source.write_text(
        "\n".join(
            [
                "from research import campaigns",
                "import reporting.execution_authority",
                "import os",
                "",
            ]
        ),
        encoding="utf-8",
    )
    target.write_text("VALUE = 1\n", encoding="utf-8")

    first = scan_files(
        tmp_path,
        (Path("dashboard/api.py"), Path("research/campaigns.py")),
    )
    second = scan_files(
        tmp_path,
        (Path("research/campaigns.py"), Path("dashboard/api.py")),
    )

    assert first.edges == second.edges
    assert [
        (edge.source_module, edge.target_module, edge.source_path, edge.target_root)
        for edge in first.edges
    ] == [
        ("dashboard.api", "research.campaigns", "dashboard/api.py", "research"),
        (
            "dashboard.api",
            "reporting.execution_authority",
            "dashboard/api.py",
            "reporting",
        ),
        ("dashboard.api", "os", "dashboard/api.py", "os"),
    ]


def test_domain_classifier_assigns_expected_domains() -> None:
    assert classify_path("reporting/execution_authority.py") == DOMAIN_ADE
    assert classify_path("research/run_research.py") == DOMAIN_QRE
    assert classify_path("dashboard/api_campaigns.py") == DOMAIN_CONTROL_PLANE
    assert classify_path("execution/protocols.py") == DOMAIN_EXECUTION
    assert (
        classify_path("packages/control_plane_qre_adapter_contract/__init__.py")
        == DOMAIN_ADAPTER_CONTRACT
    )
    assert (
        classify_path("packages/ade_governance/architecture_import_contracts.py")
        == DOMAIN_ADE
    )
    assert (
        classify_path(
            "packages/ade_governance/import_contracts/architecture_import.py"
        )
        == DOMAIN_ADE
    )
    assert (
        classify_module("packages.control_plane_qre_adapter_contract")
        == DOMAIN_ADAPTER_CONTRACT
    )
    assert (
        classify_module("packages.ade_governance.architecture_import_contracts")
        == DOMAIN_ADE
    )
    assert (
        classify_module(
            "packages.ade_governance.import_contracts.architecture_import"
        )
        == DOMAIN_ADE
    )
    assert classify_path("tests/architecture/test_x.py") == DOMAIN_TESTS
    assert classify_path(".claude/hooks/deny_no_touch.py") == DOMAIN_GOVERNANCE_TOOLING
    assert classify_path("scripts/governance_lint.py") == DOMAIN_GOVERNANCE_TOOLING


def test_relative_imports_are_resolved(tmp_path: Path) -> None:
    init_file = tmp_path / "research" / "diagnostics" / "__init__.py"
    cli_file = tmp_path / "research" / "diagnostics" / "cli.py"
    io_file = tmp_path / "research" / "diagnostics" / "io.py"
    init_file.parent.mkdir(parents=True)
    init_file.write_text("", encoding="utf-8")
    cli_file.write_text("from . import io\n", encoding="utf-8")
    io_file.write_text("VALUE = 1\n", encoding="utf-8")

    report = scan_files(
        tmp_path,
        (
            Path("research/diagnostics/__init__.py"),
            Path("research/diagnostics/cli.py"),
            Path("research/diagnostics/io.py"),
        ),
    )

    targets = {
        edge.target_module
        for edge in report.edges
        if edge.source_module == "research.diagnostics.cli"
    }
    assert "research.diagnostics.io" in targets


def test_forbidden_edge_rules_fail_on_synthetic_closed_violations() -> None:
    edges = (
        ImportEdge(
            source_module="dashboard.api_new",
            target_module="research.campaign_policy",
            source_path="dashboard/api_new.py",
            source_domain=DOMAIN_CONTROL_PLANE,
            target_domain=DOMAIN_QRE,
            target_root="research",
            line=3,
            import_kind="from",
        ),
        ImportEdge(
            source_module="research.new_policy",
            target_module="execution.protocols",
            source_path="research/new_policy.py",
            source_domain=DOMAIN_QRE,
            target_domain=DOMAIN_EXECUTION,
            target_root="execution",
            line=7,
            import_kind="import",
        ),
    )

    report = evaluate_edges(edges)

    assert [finding.rule for finding in report.forbidden_edges] == [
        "control-plane-to-qre",
        "qre-to-execution",
    ]
    assert report.legacy_edges == ()


def test_known_legacy_edges_report_without_forbidden_failure() -> None:
    edge = ImportEdge(
        source_module="reporting.intelligent_routing",
        target_module="research.presets",
        source_path="reporting/intelligent_routing.py",
        source_domain=DOMAIN_ADE,
        target_domain=DOMAIN_QRE,
        target_root="research",
        line=10,
        import_kind="from",
    )

    report = evaluate_edges((edge,))

    assert report.forbidden_edges == ()
    assert len(report.legacy_edges) == 1
    assert report.legacy_edges[0].rule == "ade-to-qre"


def test_tests_classification_is_required_for_boundary_exemption() -> None:
    test_edge = ImportEdge(
        source_module="tests.unit.test_research",
        target_module="execution.protocols",
        source_path="tests/unit/test_research.py",
        source_domain=DOMAIN_TESTS,
        target_domain=DOMAIN_EXECUTION,
        target_root="execution",
        line=5,
        import_kind="import",
    )
    prod_edge = ImportEdge(
        source_module="research.test_named_helper",
        target_module="execution.protocols",
        source_path="research/test_named_helper.py",
        source_domain=DOMAIN_QRE,
        target_domain=DOMAIN_EXECUTION,
        target_root="execution",
        line=5,
        import_kind="import",
    )

    report = evaluate_edges((test_edge, prod_edge))

    assert [finding.source_module for finding in report.forbidden_edges] == [
        "research.test_named_helper"
    ]


def test_production_modules_must_not_import_test_modules() -> None:
    prod_edge = ImportEdge(
        source_module="research.new_policy",
        target_module="tests._harness_helpers",
        source_path="research/new_policy.py",
        source_domain=DOMAIN_QRE,
        target_domain=DOMAIN_TESTS,
        target_root="tests",
        line=6,
        import_kind="from",
    )
    test_edge = ImportEdge(
        source_module="tests.unit.test_new_policy",
        target_module="tests._harness_helpers",
        source_path="tests/unit/test_new_policy.py",
        source_domain=DOMAIN_TESTS,
        target_domain=DOMAIN_TESTS,
        target_root="tests",
        line=4,
        import_kind="from",
    )

    report = evaluate_edges((prod_edge, test_edge))

    assert [
        (finding.rule, finding.source_module) for finding in report.forbidden_edges
    ] == [("production-to-tests", "research.new_policy")]
    assert report.legacy_edges == ()


def test_control_plane_qre_allowlist_is_exact_current_report_only_boundary() -> None:
    report = scan_repo(REPO_ROOT)

    control_plane_qre_edges = {
        (finding.source_module, finding.target_module)
        for finding in report.legacy_edges
        if finding.rule == "control-plane-to-qre"
    }
    allowed_control_plane_qre_edges = {
        (entry.source_module, entry.target_module)
        for entry in legacy_edge_allowlist_entries("control-plane-to-qre")
    }

    assert control_plane_qre_edges == allowed_control_plane_qre_edges
    assert len(control_plane_qre_edges) == 18
    assert all(
        entry.status == "legacy/report-only" and entry.reason and entry.sunset
        for entry in legacy_edge_allowlist_entries("control-plane-to-qre")
    )


def test_control_plane_qre_allowlist_uses_exact_edges_without_wildcards() -> None:
    entries = legacy_edge_allowlist_entries()

    assert entries
    for entry in entries:
        assert "*" not in entry.source_module
        assert "*" not in entry.target_module
        assert entry.source_module
        assert entry.target_module
        assert entry.reason
        assert entry.sunset


def test_new_control_plane_qre_edge_fails_with_source_target_and_domain() -> None:
    edge = ImportEdge(
        source_module="dashboard.api_new_read_model",
        target_module="research.new_read_model",
        source_path="dashboard/api_new_read_model.py",
        source_domain=DOMAIN_CONTROL_PLANE,
        target_domain=DOMAIN_QRE,
        target_root="research",
        line=12,
        import_kind="from",
    )

    report = evaluate_edges((edge,))
    rendered = report_to_text(report)

    assert [
        (finding.rule, finding.source_module, finding.target_module)
        for finding in report.forbidden_edges
    ] == [
        (
            "control-plane-to-qre",
            "dashboard.api_new_read_model",
            "research.new_read_model",
        )
    ]
    assert "dashboard.api_new_read_model:12 -> research.new_read_model" in rendered
    assert "(control-plane -> QRE)" in rendered


def test_scanner_does_not_import_or_execute_target_modules(tmp_path: Path) -> None:
    _git(tmp_path, "init")
    source = tmp_path / "source.py"
    target = tmp_path / "target.py"
    sentinel = tmp_path / "executed.txt"
    source.write_text("import target\n", encoding="utf-8")
    target.write_text(
        f"from pathlib import Path\nPath({str(sentinel)!r}).write_text('executed')\n",
        encoding="utf-8",
    )
    _git(tmp_path, "add", "source.py", "target.py")
    _git(tmp_path, "commit", "-m", "add import graph")

    report = scan_repo(tmp_path)

    assert any(edge.target_module == "target" for edge in report.edges)
    assert not sentinel.exists()


def test_repo_scan_has_no_closed_forbidden_edges_and_reports_legacy() -> None:
    report = scan_repo(REPO_ROOT)

    assert report.forbidden_edges == ()
    assert report.legacy_edges


def test_arch_003_repo_scan_has_no_production_to_tests_imports() -> None:
    report = scan_repo(REPO_ROOT)

    production_to_tests = [
        finding
        for finding in report.forbidden_edges
        if finding.rule == "production-to-tests"
    ]
    assert production_to_tests == []


def test_report_surfaces_are_deterministic_json_and_text() -> None:
    edge = ImportEdge(
        source_module="dashboard.api",
        target_module="research.run_state",
        source_path="dashboard/api.py",
        source_domain=DOMAIN_CONTROL_PLANE,
        target_domain=DOMAIN_QRE,
        target_root="research",
        line=1,
        import_kind="from",
    )
    report = evaluate_edges((edge,))

    rendered_json = json.dumps(report_to_dict(report), indent=2, sort_keys=True)
    rendered_text = report_to_text(report)

    assert rendered_json == json.dumps(report_to_dict(report), indent=2, sort_keys=True)
    assert rendered_text == report_to_text(report)
    assert "ARCH-001 domain import scan" in rendered_text


def test_arch_002_summary_report_is_deterministic_and_compact() -> None:
    edges = (
        ImportEdge(
            source_module="dashboard.api",
            target_module="research.run_state",
            source_path="dashboard/api.py",
            source_domain=DOMAIN_CONTROL_PLANE,
            target_domain=DOMAIN_QRE,
            target_root="research",
            line=1,
            import_kind="from",
        ),
        ImportEdge(
            source_module="reporting.intelligent_routing",
            target_module="research.presets",
            source_path="reporting/intelligent_routing.py",
            source_domain=DOMAIN_ADE,
            target_domain=DOMAIN_QRE,
            target_root="research",
            line=955,
            import_kind="from",
        ),
    )
    first = report_to_summary_dict(evaluate_edges(edges))
    second = report_to_summary_dict(evaluate_edges(tuple(reversed(edges))))

    assert first == second
    assert "edges" not in first
    assert first["edge_count"] == 2
    assert first["forbidden_edge_count"] == 1
    assert first["legacy_edge_count"] == 1
    assert first["domain_edge_categories"] == [
        {
            "edge_count": 1,
            "source_domain": DOMAIN_ADE,
            "target_domain": DOMAIN_QRE,
        },
        {
            "edge_count": 1,
            "source_domain": DOMAIN_CONTROL_PLANE,
            "target_domain": DOMAIN_QRE,
        },
    ]


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(
        [
            "git",
            "-c",
            "user.email=architecture-tests@example.invalid",
            "-c",
            "user.name=Architecture Tests",
            *args,
        ],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )
