from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TOOL_PATH = REPO_ROOT / "tools" / "qre_funnel_architecture_audit.py"
SPEC = importlib.util.spec_from_file_location("qre_funnel_architecture_audit", TOOL_PATH)
assert SPEC is not None and SPEC.loader is not None
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _fixture_repo(root: Path) -> Path:
    _write(root / "research" / "qre_tiingo_candidate_research_loop.py", "DEFAULT='logs/qre_tiingo_candidate_research_loop/latest.json'\n")
    _write(root / "research" / "qre_tiingo_hypothesis_lifecycle.py", "REPORT_KIND='qre_tiingo_hypothesis_lifecycle'\n")
    _write(root / "research" / "qre_daily_status_digest.py", "INPUT='logs/qre_tiingo_candidate_research_loop/latest.json'\n")
    _write(root / "research" / "run_research.py", "OUT='research/research_latest.json'\n")
    _write(root / "registry.py", "REGISTRY={}\n")
    _write(root / "research" / "qre_campaign_memory.py", "CampaignSpec='x'; LessonMemory='y'\n")
    _write(root / "tests" / "unit" / "test_qre_tiingo_candidate_research_loop.py", "def test_fixture(): pass\n")
    _write(root / "docs" / "research" / "tiingo_candidate_research_loop.md", "Tiingo candidate research loop\n")
    _write(root / "research" / "research_latest.json", "{}\n")
    _write(root / "research" / "strategy_matrix.csv", "a,b\n")
    return root


def test_default_mode_prints_json_and_writes_nothing(tmp_path: Path) -> None:
    repo = _fixture_repo(tmp_path)

    result = subprocess.run(
        [sys.executable, str(TOOL_PATH), "--repo-root", str(repo)],
        check=True,
        text=True,
        capture_output=True,
    )

    payload = json.loads(result.stdout)
    assert payload["report_kind"] == "qre_funnel_architecture_audit"
    assert not (repo / "logs" / "qre_funnel_architecture_audit").exists()


def test_write_mode_writes_only_allowed_audit_dir(tmp_path: Path) -> None:
    repo = _fixture_repo(tmp_path)
    report = audit.build_report(repo)

    paths = audit.write_outputs(report, repo_root=repo)

    assert set(paths) == {
        "latest",
        "dependency_graph",
        "provider_leakage_report",
        "contract_map",
        "funnel_inventory",
        "operator_summary",
    }
    assert all(value.startswith("logs/qre_funnel_architecture_audit/") for value in paths.values())
    assert (repo / "logs" / "qre_funnel_architecture_audit" / "latest.json").is_file()


def test_report_kind_and_safety_flags(tmp_path: Path) -> None:
    report = audit.build_report(_fixture_repo(tmp_path))

    assert report["report_kind"] == "qre_funnel_architecture_audit"
    assert report["safety"]["audit_only"] is True
    assert report["safety"]["runtime_behavior_changed"] is False
    assert report["safety"]["created_candidates"] is False
    assert report["safety"]["trading_authority"] is False


def test_inventory_includes_tiingo_candidate_loop(tmp_path: Path) -> None:
    report = audit.build_report(_fixture_repo(tmp_path))
    ids = {row["funnel_id"] for row in report["funnel_inventory"]}
    assert "tiingo_hypothesis_candidate_research_mini_loop" in ids


def test_inventory_includes_daily_digest_observability(tmp_path: Path) -> None:
    report = audit.build_report(_fixture_repo(tmp_path))
    digest = next(
        row
        for row in report["funnel_inventory"]
        if row["funnel_id"] == "daily_status_digest_observability"
    )
    assert digest["canonicality"] == "observability_only"
    assert digest["status_recommendation"] == "OBSERVABILITY_ONLY"


def test_contract_map_includes_required_objects(tmp_path: Path) -> None:
    report = audit.build_report(_fixture_repo(tmp_path))
    for name in audit.CANONICAL_OBJECTS:
        assert name in report["contract_map"]


def test_provider_leakage_allows_adapter_and_provenance_references() -> None:
    assert audit.classify_provider_reference("research/qre_tiingo_hypothesis_generator_e2e.py", "source_snapshot_id='x'") in {
        "allowed_adapter_reference",
        "allowed_provenance_reference",
        "allowed_source_manifest_reference",
    }


def test_provider_leakage_flags_preset_campaign_semantics() -> None:
    assert audit.classify_provider_reference("research/preset_builder.py", "tiingo campaign admission policy") == "forbidden_provider_coupling"


def test_dependency_graph_has_nodes_and_edges(tmp_path: Path) -> None:
    report = audit.build_report(_fixture_repo(tmp_path))
    graph = report["dependency_graph"]
    assert graph["summary"]["nodes"] > 0
    assert graph["summary"]["edges"] > 0


def test_dependency_graph_classifies_observability_edges(tmp_path: Path) -> None:
    report = audit.build_report(_fixture_repo(tmp_path))
    assert any(edge["classification"] == "observability" for edge in report["dependency_graph"]["edges"])


def test_hardcoded_path_scanner_detects_log_path_coupling(tmp_path: Path) -> None:
    report = audit.build_report(_fixture_repo(tmp_path))
    findings = report["hardcoded_coupling_report"]["hardcoded_coupling_findings"]
    assert any(item["pattern"] == "hardcoded_artifact_path" for item in findings)


def test_reconciliation_plan_contains_decision_categories(tmp_path: Path) -> None:
    report = audit.build_report(_fixture_repo(tmp_path))
    decisions = {row["decision"] for row in report["reconciliation_plan"]}
    assert "KEEP_AS_PROVIDER_ADAPTER" in decisions
    assert "OBSERVABILITY_ONLY" in decisions
    assert decisions & {"BRIDGE_TO_CANONICAL", "UNKNOWN_REQUIRES_OPERATOR_DECISION"}


def test_visual_docs_contain_required_diagram_headings() -> None:
    text = (REPO_ROOT / "docs" / "architecture" / "qre_funnel_visual_maps.md").read_text(encoding="utf-8")
    for heading in (
        "C4 Context",
        "Current Detected Funnels",
        "Target Canonical Data-Flow",
        "Integration/Dependency",
        "Sequence",
        "Provider Leakage Boundary",
    ):
        assert heading in text


def test_audit_does_not_mutate_protected_outputs(tmp_path: Path) -> None:
    repo = _fixture_repo(tmp_path)
    latest = repo / "research" / "research_latest.json"
    matrix = repo / "research" / "strategy_matrix.csv"
    before_latest = latest.read_bytes()
    before_matrix = matrix.read_bytes()

    audit.build_report(repo)

    assert latest.read_bytes() == before_latest
    assert matrix.read_bytes() == before_matrix


def test_audit_does_not_create_candidate_loop_logs(tmp_path: Path) -> None:
    repo = _fixture_repo(tmp_path)
    audit.build_report(repo)
    assert not (repo / "logs" / "qre_tiingo_candidate_research_loop").exists()


def test_audit_does_not_create_campaign_screening_validation_artifacts(tmp_path: Path) -> None:
    repo = _fixture_repo(tmp_path)
    audit.build_report(repo)
    assert not (repo / "logs" / "qre_validation").exists()
    assert not (repo / "logs" / "qre_campaign").exists()
    assert not (repo / "logs" / "qre_tiingo_candidate_research_loop" / "screening_results.jsonl").exists()


def test_audit_runs_from_repo_root_on_windows_paths() -> None:
    report = audit.build_report(REPO_ROOT)
    assert report["summary"]["audit_verdict"] in {
        "pass_inventory_complete_with_reconciliation_needed",
        "partial_inventory_manual_review_required",
    }


def test_operator_summary_contains_required_sections(tmp_path: Path) -> None:
    report = audit.build_report(_fixture_repo(tmp_path))
    summary = audit.render_operator_summary(report)
    for heading in (
        "## Verdict",
        "## Funnels detected",
        "## Provider leakage",
        "## Funnel classification",
        "## Reconciliation decisions",
        "## Safety confirmation",
    ):
        assert heading in summary


def test_output_dir_rejects_non_audit_path(tmp_path: Path) -> None:
    repo = _fixture_repo(tmp_path)
    report = audit.build_report(repo)
    try:
        audit.write_outputs(report, repo_root=repo, output_dir=repo / "logs" / "other")
    except ValueError as exc:
        assert "output_dir_must_be_logs_qre_funnel_architecture_audit" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected output dir rejection")


def test_contract_answers_include_core_questions(tmp_path: Path) -> None:
    report = audit.build_report(_fixture_repo(tmp_path))
    answers = report["contract_map"]["_canonical_answers"]
    assert "Hypothesis" in answers
    assert "CandidateSpec" in answers
    assert "StrategySpec_or_StrategyIR" in answers
    assert "EvidencePack_or_EvidenceLedger" in answers


def test_operator_summary_bluntly_reports_parallel_funnels(tmp_path: Path) -> None:
    report = audit.build_report(_fixture_repo(tmp_path))
    summary = audit.render_operator_summary(report)
    assert "multiple partial funnels exist" in summary.lower()


def test_audit_includes_funnel_classification_registry(tmp_path: Path) -> None:
    report = audit.build_report(_fixture_repo(tmp_path))
    classification = report["funnel_classification"]

    assert classification["summary"]["canonical_contract_loop"] == "canonical_provider_agnostic_contract_bridge_loop"
    assert classification["summary"]["duplicate_canonical_claims"] is False
    assert classification["classifications"]["tiingo_hypothesis_candidate_research_mini_loop"]["classification"] == "provider_adapter"
    assert classification["classifications"]["daily_status_digest_observability"]["classification"] == "observability_only"


def test_audit_includes_closed_world_registry_gate(tmp_path: Path) -> None:
    report = audit.build_report(_fixture_repo(tmp_path))
    closed_world = report["closed_world_audit"]

    assert closed_world["verdict"] == "pass"
    assert closed_world["failures"] == []
    assert closed_world["enforcement_scope"]["runtime_behavior_changed"] is False


def test_audit_does_not_claim_runtime_loop_is_closed(tmp_path: Path) -> None:
    report = audit.build_report(_fixture_repo(tmp_path))
    assessment = report["canonicality_assessment"]

    assert assessment["canonical_contract_bridge_loop_classified"] is True
    assert assessment["full_provider_agnostic_loop_exists"] is False
