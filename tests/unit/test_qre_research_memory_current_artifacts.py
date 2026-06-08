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

    report = current_artifacts.build_research_memory_current_artifacts()

    assert report["summary"]["package_research_memory_ready"] is True
    assert report["summary"]["coverage_ready"] is True
    assert report["summary"]["retrieval_ready"] is True
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

    report = current_artifacts.build_research_memory_current_artifacts(repo_root=tmp_path)
    paths = current_artifacts.write_outputs(report, repo_root=tmp_path)

    markdown = (tmp_path / paths["operator_summary"]).read_text(encoding="utf-8")
    assert paths["latest"] == "logs/qre_research_memory_current_artifacts/latest.json"
    assert "# QRE Research Memory Current Artifacts" in markdown
