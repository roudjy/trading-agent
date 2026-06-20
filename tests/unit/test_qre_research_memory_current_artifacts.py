from __future__ import annotations

from pathlib import Path

from research import qre_research_memory_current_artifacts as current_artifacts


def test_current_artifacts_report_summarizes_package_and_qre_memory(monkeypatch) -> None:
    monkeypatch.setattr(
        current_artifacts.research_memory,
        "read_research_memory_status",
        lambda **_: {
            "status": "ready",
            "research_memory_ready": True,
            "path": "logs/qre_research_memory/latest.json",
            "fails_closed": False,
            "schema_version": "1.0",
        },
    )
    monkeypatch.setattr(
        current_artifacts.memory_coverage,
        "build_research_memory_coverage",
        lambda **_: {
            "summary": {
                "indexed_entry_count": 12,
                "indexed_candidate_count": 4,
                "final_recommendation": "research_memory_coverage_ready",
            }
        },
    )
    monkeypatch.setattr(
        current_artifacts.memory_coverage,
        "build_failure_retrieval",
        lambda _memory: {
            "summary": {
                "retrievable_failure_subject_count": 3,
                "final_recommendation": "failure_retrieval_ready",
            }
        },
    )
    monkeypatch.setattr(
        current_artifacts.artifact_continuity,
        "build_read_only_artifact_continuity",
        lambda **_: {
            "summary": {
                "artifact_continuity_ready": True,
                "materializable_target_count": 0,
            }
        },
    )
    monkeypatch.setattr(
        current_artifacts.contradiction_staleness,
        "build_contradiction_staleness_intelligence",
        lambda **_: {
            "summary": {
                "contradiction_staleness_ready": True,
                "contradiction_count": 0,
                "stale_or_superseded_count": 0,
            }
        },
    )
    monkeypatch.setattr(
        current_artifacts.throughput_bottlenecks,
        "build_campaign_throughput_bottleneck_intelligence",
        lambda **_: {
            "summary": {
                "campaign_throughput_bottleneck_intelligence_ready": True,
                "bottleneck_count": 0,
            }
        },
    )
    monkeypatch.setattr(
        current_artifacts.novelty_enforcement,
        "build_experiment_dedup_novelty_enforcement",
        lambda **_: {
            "summary": {
                "experiment_dedup_novelty_enforcement_ready": True,
                "duplicate_pressure_count": 0,
            }
        },
    )
    monkeypatch.setattr(
        current_artifacts.sequential_retrieval,
        "build_research_state_sequential_retrieval",
        lambda **_: {
            "summary": {
                "research_state_sequential_retrieval_ready": True,
                "visible_sequence_row_count": 4,
                "exact_next_action": "preserve_research_state_sequence_visibility",
            }
        },
    )
    monkeypatch.setattr(
        current_artifacts.remediation_planning,
        "build_incomplete_artifact_remediation_planning",
        lambda **_: {
            "summary": {
                "remediation_planning_ready": True,
                "remediation_count": 2,
                "exact_next_action": "preserve_current_read_only_artifact_visibility",
            }
        },
    )

    report = current_artifacts.build_research_memory_current_artifacts()

    assert report["summary"]["package_research_memory_ready"] is True
    assert report["summary"]["coverage_ready"] is True
    assert report["summary"]["retrieval_ready"] is True
    assert report["summary"]["artifact_continuity_ready"] is True
    assert report["summary"]["contradiction_staleness_ready"] is True
    assert report["summary"]["campaign_throughput_bottleneck_intelligence_ready"] is True
    assert report["summary"]["experiment_dedup_novelty_enforcement_ready"] is True
    assert report["summary"]["research_state_sequential_retrieval_ready"] is True
    assert report["summary"]["incomplete_artifact_remediation_planning_ready"] is True
    assert report["summary"]["final_recommendation"] == "research_memory_current_artifacts_ready"


def test_current_artifacts_write_outputs_also_materializes_coverage_and_retrieval(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        current_artifacts.research_memory,
        "read_research_memory_status",
        lambda **_: {
            "status": "missing_research_memory",
            "research_memory_ready": False,
            "path": "logs/qre_research_memory/latest.json",
            "fails_closed": True,
        },
    )
    monkeypatch.setattr(
        current_artifacts.memory_coverage,
        "build_research_memory_coverage",
        lambda **_: {
            "summary": {
                "indexed_entry_count": 0,
                "indexed_candidate_count": 0,
                "final_recommendation": "research_memory_coverage_missing",
            }
        },
    )
    monkeypatch.setattr(
        current_artifacts.memory_coverage,
        "build_failure_retrieval",
        lambda _memory: {
            "summary": {
                "retrievable_failure_subject_count": 0,
                "final_recommendation": "failure_retrieval_not_ready",
            }
        },
    )
    monkeypatch.setattr(
        current_artifacts.memory_coverage,
        "write_outputs",
        lambda memory, retrieval, repo_root: {
            "memory_latest": "logs/qre_research_memory_coverage/latest.json",
            "failure_latest": "logs/qre_failure_retrieval/latest.json",
        },
    )
    monkeypatch.setattr(
        current_artifacts.artifact_continuity,
        "build_read_only_artifact_continuity",
        lambda **_: {
            "summary": {
                "artifact_continuity_ready": False,
                "materializable_target_count": 3,
            }
        },
    )
    monkeypatch.setattr(
        current_artifacts.artifact_continuity,
        "write_outputs",
        lambda report, repo_root: {
            "latest": "logs/qre_read_only_artifact_continuity/latest.json",
            "operator_summary": "logs/qre_read_only_artifact_continuity/operator_summary.md",
        },
    )
    monkeypatch.setattr(
        current_artifacts.contradiction_staleness,
        "build_contradiction_staleness_intelligence",
        lambda **_: {
            "summary": {
                "contradiction_staleness_ready": False,
                "contradiction_count": 2,
                "stale_or_superseded_count": 1,
            }
        },
    )
    monkeypatch.setattr(
        current_artifacts.throughput_bottlenecks,
        "build_campaign_throughput_bottleneck_intelligence",
        lambda **_: {
            "summary": {
                "campaign_throughput_bottleneck_intelligence_ready": False,
                "bottleneck_count": 3,
            }
        },
    )
    monkeypatch.setattr(
        current_artifacts.novelty_enforcement,
        "build_experiment_dedup_novelty_enforcement",
        lambda **_: {
            "summary": {
                "experiment_dedup_novelty_enforcement_ready": False,
                "duplicate_pressure_count": 4,
            }
        },
    )
    monkeypatch.setattr(
        current_artifacts.sequential_retrieval,
        "build_research_state_sequential_retrieval",
        lambda **_: {
            "summary": {
                "research_state_sequential_retrieval_ready": False,
                "visible_sequence_row_count": 0,
                "exact_next_action": "restore_current_run_artifacts",
            }
        },
    )
    monkeypatch.setattr(
        current_artifacts.remediation_planning,
        "build_incomplete_artifact_remediation_planning",
        lambda **_: {
            "summary": {
                "remediation_planning_ready": False,
                "remediation_count": 4,
                "exact_next_action": "restore_inputs",
            }
        },
    )
    monkeypatch.setattr(
        current_artifacts.contradiction_staleness,
        "write_outputs",
        lambda report, repo_root: {
            "latest": "logs/qre_contradiction_staleness_intelligence/latest.json",
            "operator_summary": "logs/qre_contradiction_staleness_intelligence/operator_summary.md",
        },
    )
    monkeypatch.setattr(
        current_artifacts.throughput_bottlenecks,
        "write_outputs",
        lambda report, repo_root: {
            "latest": "logs/qre_campaign_throughput_bottleneck_intelligence/latest.json",
            "operator_summary": "logs/qre_campaign_throughput_bottleneck_intelligence/operator_summary.md",
        },
    )
    monkeypatch.setattr(
        current_artifacts.novelty_enforcement,
        "write_outputs",
        lambda report, repo_root: {
            "latest": "logs/qre_experiment_dedup_novelty_enforcement/latest.json",
            "operator_summary": "logs/qre_experiment_dedup_novelty_enforcement/operator_summary.md",
        },
    )
    monkeypatch.setattr(
        current_artifacts.sequential_retrieval,
        "write_outputs",
        lambda report, repo_root: {
            "latest": "logs/qre_research_state_sequential_retrieval/latest.json",
            "operator_summary": "logs/qre_research_state_sequential_retrieval/operator_summary.md",
        },
    )
    monkeypatch.setattr(
        current_artifacts.remediation_planning,
        "write_outputs",
        lambda report, repo_root: {
            "latest": "logs/qre_incomplete_artifact_remediation_planning/latest.json",
            "operator_summary": "logs/qre_incomplete_artifact_remediation_planning/operator_summary.md",
        },
    )

    report = current_artifacts.build_research_memory_current_artifacts(repo_root=tmp_path)
    paths = current_artifacts.write_outputs(report, repo_root=tmp_path)

    markdown = (tmp_path / paths["operator_summary"]).read_text(encoding="utf-8")
    assert paths["latest"] == "logs/qre_research_memory_current_artifacts/latest.json"
    assert paths["artifact_continuity_latest"] == "logs/qre_read_only_artifact_continuity/latest.json"
    assert paths["contradiction_staleness_latest"] == "logs/qre_contradiction_staleness_intelligence/latest.json"
    assert paths["campaign_throughput_bottleneck_latest"] == "logs/qre_campaign_throughput_bottleneck_intelligence/latest.json"
    assert paths["experiment_dedup_novelty_latest"] == "logs/qre_experiment_dedup_novelty_enforcement/latest.json"
    assert paths["research_state_sequential_retrieval_latest"] == "logs/qre_research_state_sequential_retrieval/latest.json"
    assert paths["incomplete_artifact_remediation_planning_latest"] == "logs/qre_incomplete_artifact_remediation_planning/latest.json"
    assert "# QRE Research Memory Current Artifacts" in markdown

def test_memory_coverage_entries_include_resolved_entities():
    from pathlib import Path

    from research import qre_research_memory_coverage as coverage

    report = coverage.build_research_memory_coverage(repo_root=Path("."), max_candidates=3)
    entries = report["entries"]

    assert entries
    assert all("resolved_entities" in entry for entry in entries)
    assert all(isinstance(entry["resolved_entities"], list) for entry in entries)

def test_failure_retrieval_matches_include_context_fields():
    from pathlib import Path

    from research import qre_research_memory_coverage as coverage

    memory = coverage.build_research_memory_coverage(repo_root=Path("."), max_candidates=15)
    retrieval = coverage.build_failure_retrieval(memory)

    assert "summary" in retrieval
    assert "matched_failure_subject_count" in retrieval["summary"]
    assert "unmatched_failure_subject_count" in retrieval["summary"]

    rows = retrieval.get("rows") or []
    for row in rows:
        for match in row.get("similar_failures") or []:
            assert "ontology_tags" in match
            assert "ontology_classification" in match
            assert "resolved_entities" in match
            assert "metadata" in match
