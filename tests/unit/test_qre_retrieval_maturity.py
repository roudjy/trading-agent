from __future__ import annotations

import json
from pathlib import Path

from research import qre_retrieval_maturity as retrieval_maturity


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def test_retrieval_maturity_combines_keyword_metadata_and_graph_neighbors(monkeypatch) -> None:
    monkeypatch.setattr(
        retrieval_maturity.memory_coverage,
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
                    "title": "BTC policy action",
                    "text_preview": "keyword seed for retrieval",
                    "metadata": {"reason_codes": ["policy_action"], "source": "alpha"},
                    "ontology_classification": {"research_scope": "target_equity_research"},
                },
                {
                    "artifact_id": "failure:cand-1",
                    "record_kind": "failure_action",
                    "subject_id": "cand-1",
                    "title": "BTC blocker",
                    "text_preview": "blocked contradiction_detected review",
                    "metadata": {"blocker_code": "lineage_missing", "recommended_action": "review"},
                    "ontology_classification": {"research_scope": "target_equity_research"},
                },
                {
                    "artifact_id": "reason:cand-1",
                    "record_kind": "reason_record",
                    "subject_id": "cand-1",
                    "title": "reason cand-1",
                    "text_preview": "policy action context",
                    "metadata": {"reason_codes": ["policy_action"]},
                    "ontology_classification": {"research_scope": "target_equity_research"},
                },
            ],
        },
    )
    monkeypatch.setattr(
        retrieval_maturity.memory_graph,
        "build_research_memory_graph",
        lambda **_: {
            "summary": {"graph_status": "ready"},
            "nodes": [
                {"node_id": "memory::basket:cand-1", "node_type": "memory_entry", "subject_id": "cand-1"},
                {"node_id": "memory::failure:cand-1", "node_type": "memory_entry", "subject_id": "cand-1"},
                {"node_id": "memory::reason:cand-1", "node_type": "memory_entry", "subject_id": "cand-1"},
                {"node_id": "subject::cand-1", "node_type": "subject", "subject_id": "cand-1"},
                {"node_id": "retrieval::cand-1", "node_type": "retrieval_result", "subject_id": "cand-1"},
            ],
            "edges": [
                {
                    "source": "subject::cand-1",
                    "target": "memory::basket:cand-1",
                    "relation": "contains_entry",
                },
                {
                    "source": "subject::cand-1",
                    "target": "memory::failure:cand-1",
                    "relation": "contains_entry",
                },
                {
                    "source": "subject::cand-1",
                    "target": "memory::reason:cand-1",
                    "relation": "contains_entry",
                },
                {
                    "source": "memory::basket:cand-1",
                    "target": "memory::reason:cand-1",
                    "relation": "same_subject",
                },
                {
                    "source": "subject::cand-1",
                    "target": "retrieval::cand-1",
                    "relation": "retrieval_summary",
                },
                {
                    "source": "retrieval::cand-1",
                    "target": "memory::failure:cand-1",
                    "relation": "retrieval_similarity",
                },
            ],
        },
    )

    report = retrieval_maturity.build_retrieval_maturity(query="BTC policy action")

    assert report["summary"]["graph_status"] == "ready"
    assert report["summary"]["combined_result_count"] == 3
    assert report["keyword_surface"]
    assert report["metadata_surface"]
    assert report["graph_neighbor_surface"]
    top = report["combined_results"][0]
    assert top["artifact_id"] == "basket:cand-1"
    assert top["graph_neighbor_visible"] is True


def test_retrieval_maturity_blocks_when_memory_surface_missing(monkeypatch) -> None:
    monkeypatch.setattr(
        retrieval_maturity.memory_coverage,
        "build_research_memory_coverage",
        lambda **_: {
            "summary": {"final_recommendation": "research_memory_coverage_missing"},
            "entries": [],
        },
    )
    monkeypatch.setattr(
        retrieval_maturity.memory_graph,
        "build_research_memory_graph",
        lambda **_: {"summary": {"graph_status": "blocked"}, "nodes": [], "edges": []},
    )

    report = retrieval_maturity.build_retrieval_maturity(query="BTC policy action")

    assert report["summary"]["graph_status"] == "blocked"
    assert report["combined_results"] == []


def test_retrieval_maturity_writes_outputs(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        retrieval_maturity.memory_coverage,
        "build_research_memory_coverage",
        lambda **_: {
            "summary": {"final_recommendation": "research_memory_coverage_ready"},
            "entries": [
                {
                    "artifact_id": "basket:cand-1",
                    "record_kind": "basket",
                    "subject_id": "cand-1",
                    "title": "BTC policy action",
                    "text_preview": "keyword seed for retrieval",
                    "metadata": {"reason_codes": ["policy_action"], "source": "alpha"},
                    "ontology_classification": {"research_scope": "target_equity_research"},
                }
            ],
        },
    )
    monkeypatch.setattr(
        retrieval_maturity.memory_graph,
        "build_research_memory_graph",
        lambda **_: {
            "summary": {"graph_status": "ready"},
            "nodes": [{"node_id": "memory::basket:cand-1", "node_type": "memory_entry", "subject_id": "cand-1"}],
            "edges": [],
        },
    )

    report = retrieval_maturity.build_retrieval_maturity(query="BTC policy action")
    paths = retrieval_maturity.write_outputs(report, repo_root=tmp_path)
    summary = (tmp_path / paths["operator_summary"]).read_text(encoding="utf-8")
    assert paths["latest"] == "logs/qre_retrieval_maturity/latest.json"
    assert "# QRE Retrieval Maturity" in summary
