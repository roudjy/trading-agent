from __future__ import annotations

import json
from pathlib import Path

from research import qre_research_memory_graph as memory_graph


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def test_memory_graph_surfaces_entries_similarity_and_contradictions(monkeypatch) -> None:
    monkeypatch.setattr(
        memory_graph.memory_coverage,
        "build_research_memory_coverage",
        lambda **_: {
            "summary": {
                "final_recommendation": "research_memory_coverage_ready",
                "indexed_entry_count": 3,
                "indexed_candidate_count": 1,
            },
            "entries": [
                {
                    "artifact_id": "basket:cand-1",
                    "record_kind": "basket",
                    "subject_id": "cand-1",
                    "title": "AAPL trend",
                    "text_preview": "diagnosable ready",
                    "metadata": {"reason_code": "source_and_cache_evidence_available"},
                    "ontology_classification": {"research_scope": "target_equity_research", "readiness_state": "ready", "asset_class": "fundamental_equity"},
                },
                {
                    "artifact_id": "failure:cand-1",
                    "record_kind": "failure_action",
                    "subject_id": "cand-1",
                    "title": "AAPL blocker",
                    "text_preview": "blocked contradiction_detected",
                    "metadata": {"blocker_code": "lineage_missing", "recommended_action": "review", "reason_codes": ["contradiction_detected"]},
                    "ontology_classification": {"research_scope": "target_equity_research", "readiness_state": "blocked", "asset_class": "fundamental_equity"},
                },
                {
                    "artifact_id": "reason:cand-1",
                    "record_kind": "reason_record",
                    "subject_id": "cand-1",
                    "title": "reason cand-1",
                    "text_preview": "contradiction_detected",
                    "metadata": {"reason_codes": ["contradiction_detected"], "evidence_ref_count": 1},
                    "ontology_classification": {"research_scope": "target_equity_research", "readiness_state": "blocked", "asset_class": "fundamental_equity"},
                },
            ],
        },
    )
    monkeypatch.setattr(
        memory_graph.memory_coverage,
        "build_failure_retrieval",
        lambda _memory, top_k=3: {
            "summary": {"failure_subject_count": 1, "retrievable_failure_subject_count": 1},
            "rows": [
                {
                    "subject_id": "cand-1",
                    "blocker_code": "lineage_missing",
                    "recommended_action": "review",
                    "similar_failures": [
                        {
                            "subject_id": "cand-1",
                            "artifact_id": "failure:cand-1",
                            "title": "AAPL blocker",
                            "score": 7,
                            "record_kind": "failure_action",
                            "blocker_code": "lineage_missing",
                            "recommended_action": "review",
                            "ontology_tags": ["failure"],
                            "ontology_classification": {},
                            "resolved_entities": [],
                            "metadata": {"blocker_code": "lineage_missing"},
                        }
                    ],
                }
            ],
        },
    )

    report = memory_graph.build_research_memory_graph()

    assert report["summary"]["graph_status"] == "partial"
    assert report["summary"]["contradiction_count"] == 2
    assert any(edge["relation"] == "contradiction_visible" for edge in report["edges"])
    assert any(edge["relation"] == "retrieval_similarity" for edge in report["edges"])
    assert any(edge["relation"] == "same_subject" for edge in report["edges"])


def test_memory_graph_blocks_when_memory_surface_missing(monkeypatch) -> None:
    monkeypatch.setattr(
        memory_graph.memory_coverage,
        "build_research_memory_coverage",
        lambda **_: {
            "summary": {"final_recommendation": "research_memory_coverage_missing"},
            "entries": [],
        },
    )
    monkeypatch.setattr(
        memory_graph.memory_coverage,
        "build_failure_retrieval",
        lambda _memory, top_k=3: {"summary": {"failure_subject_count": 0}, "rows": []},
    )

    report = memory_graph.build_research_memory_graph()
    assert report["summary"]["graph_status"] == "blocked"
    assert report["checks"]["orphan_nodes"] == []


def test_memory_graph_writes_outputs(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        memory_graph.memory_coverage,
        "build_research_memory_coverage",
        lambda **_: {
            "summary": {"final_recommendation": "research_memory_coverage_ready"},
            "entries": [
                {
                    "artifact_id": "basket:cand-1",
                    "record_kind": "basket",
                    "subject_id": "cand-1",
                    "title": "AAPL trend",
                    "text_preview": "diagnosable ready",
                    "metadata": {"reason_code": "source_and_cache_evidence_available"},
                    "ontology_classification": {"research_scope": "target_equity_research", "readiness_state": "ready", "asset_class": "fundamental_equity"},
                }
            ],
        },
    )
    monkeypatch.setattr(
        memory_graph.memory_coverage,
        "build_failure_retrieval",
        lambda _memory, top_k=3: {"summary": {"failure_subject_count": 0}, "rows": []},
    )

    report = memory_graph.build_research_memory_graph()
    paths = memory_graph.write_outputs(report, repo_root=tmp_path)
    summary = (tmp_path / paths["operator_summary"]).read_text(encoding="utf-8")
    assert paths["latest"] == "logs/qre_research_memory_graph/latest.json"
    assert "# QRE Research Memory Graph" in summary
