from __future__ import annotations

from scripts.ci_path_classifier import classify_paths


def test_docs_only_excludes_frontend_and_deploy_domains() -> None:
    result = classify_paths(["docs/research_quality_kpis.md", "CHANGELOG.md"])

    assert result["docs_only"] is True
    assert result["frontend"] is False
    assert result["dashboard_or_control_plane"] is False
    assert result["ci_or_governance"] is False
    assert result["run_frontend"] is False
    assert result["run_docker_build"] is False


def test_governance_docs_are_ci_or_governance_not_docs_only() -> None:
    result = classify_paths(["docs/governance/ci_path_aware_gates.md"])

    assert result["ci_or_governance"] is True
    assert result["docs_only"] is False
    assert result["run_frontend"] is True
    assert result["run_docker_build"] is True


def test_architecture_only_accepts_adr_and_architecture_tests() -> None:
    result = classify_paths(
        [
            "docs/adr/ADR-014-truth-authority-settlement.md",
            "tests/architecture/test_domain_boundary_smoke.py",
        ]
    )

    assert result["architecture_only"] is True
    assert result["tests"] is True
    assert result["run_frontend"] is False
    assert result["run_docker_build"] is False


def test_frontend_dashboard_packages_and_research_domains() -> None:
    result = classify_paths(
        [
            "frontend/src/App.test.tsx",
            "dashboard/api_agent_control.py",
            "packages/qre_control_plane_adapter/__init__.py",
            "research/run_research.py",
        ]
    )

    assert result["frontend"] is True
    assert result["dashboard_or_control_plane"] is True
    assert result["packages"] is True
    assert result["qre_research"] is True
    assert result["run_frontend"] is True
    assert result["run_docker_build"] is True


def test_ci_and_execution_sensitive_paths_are_explicit() -> None:
    result = classify_paths(
        [
            ".github/workflows/tests.yml",
            "scripts/governance_lint.py",
            "execution/protocols.py",
            "agent/risk/limits.py",
        ]
    )

    assert result["ci_or_governance"] is True
    assert result["execution_sensitive"] is True
    assert result["deployment_sensitive"] is False
    assert result["run_dashboard_deploy"] is True


def test_deployment_sensitive_runtime_files_trigger_build_and_deploy() -> None:
    result = classify_paths(["Dockerfile", "scripts/deploy_vps_dashboard.sh"])

    assert result["deployment_sensitive"] is True
    assert result["run_docker_build"] is True
    assert result["run_dashboard_deploy"] is True
