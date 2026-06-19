from __future__ import annotations

from pathlib import Path

from research import qre_contradiction_staleness_intelligence as csi


def test_contradiction_staleness_intelligence_aggregates_visible_rows(monkeypatch) -> None:
    monkeypatch.setattr(
        csi.memory_retrieval,
        "build_research_memory_retrieval",
        lambda **_: {
            "summary": {"research_memory_ready": True},
            "queries": [
                {
                    "query_id": "contradictory_outcomes",
                    "rows": [{"scope_key": "preset_alpha", "dimension": "preset", "reason": "accepted_and_rejected_counts_visible_together"}],
                },
                {
                    "query_id": "stale_or_superseded_knowledge",
                    "rows": [{"artifact_path": "logs/missing/latest.json", "status": "missing"}],
                },
            ],
        },
    )
    monkeypatch.setattr(
        csi.memory_graph,
        "build_research_memory_graph",
        lambda **_: {
            "summary": {"graph_status": "partial"},
            "checks": {"contradictions": [{"subject_id": "cand-1", "reason": "contradictory_reason_code_visible"}]},
        },
    )
    monkeypatch.setattr(
        csi.lineage_graph,
        "build_qre_lineage_graph_v1",
        lambda **_: {
            "summary": {"graph_status": "ready"},
            "checks": {"contradictions": [{"campaign_id": "cmp-1", "kind": "missing_campaign_digest_root", "detail": "Campaign has no lineage-root digest evidence."}]},
        },
    )
    monkeypatch.setattr(
        csi.retrieval_maturity,
        "build_retrieval_maturity",
        lambda **_: {"summary": {"graph_status": "ready"}},
    )
    monkeypatch.setattr(
        csi.operational_controls,
        "build_trusted_loop_operational_controls",
        lambda **_: {
            "state_reconciliation": {"mismatches": ["latest_artifacts_superseded_by_history"]},
            "artifact_freshness": {"stale_reasons": ["run_id_mismatch"]},
        },
    )

    report = csi.build_contradiction_staleness_intelligence()

    assert report["summary"]["contradiction_staleness_ready"] is True
    assert report["summary"]["contradiction_count"] == 3
    assert report["summary"]["stale_or_superseded_count"] == 3
    assert report["summary"]["exact_next_action"] == "reconcile_stale_or_superseded_artifacts"


def test_contradiction_staleness_write_outputs_stays_in_allowlist(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        csi.memory_retrieval,
        "build_research_memory_retrieval",
        lambda **_: {"summary": {"research_memory_ready": True}, "queries": []},
    )
    monkeypatch.setattr(
        csi.memory_retrieval,
        "write_outputs",
        lambda report, **_: {"latest": "logs/qre_research_memory_retrieval/latest.json"},
    )
    monkeypatch.setattr(
        csi.memory_graph,
        "build_research_memory_graph",
        lambda **_: {"summary": {"graph_status": "ready"}, "checks": {"contradictions": []}},
    )
    monkeypatch.setattr(
        csi.memory_graph,
        "write_outputs",
        lambda report, **_: {"latest": "logs/qre_research_memory_graph/latest.json"},
    )
    monkeypatch.setattr(
        csi.lineage_graph,
        "build_qre_lineage_graph_v1",
        lambda **_: {"summary": {"graph_status": "ready"}, "checks": {"contradictions": []}},
    )
    monkeypatch.setattr(
        csi.lineage_graph,
        "write_outputs",
        lambda report, **_: {"latest": "logs/qre_lineage_graph_v1/latest.json"},
    )
    monkeypatch.setattr(
        csi.retrieval_maturity,
        "build_retrieval_maturity",
        lambda **_: {"summary": {"graph_status": "ready"}},
    )
    monkeypatch.setattr(
        csi.retrieval_maturity,
        "write_outputs",
        lambda report, **_: {"latest": "logs/qre_retrieval_maturity/latest.json"},
    )
    monkeypatch.setattr(
        csi.operational_controls,
        "build_trusted_loop_operational_controls",
        lambda **_: {"state_reconciliation": {"mismatches": []}, "artifact_freshness": {"stale_reasons": []}},
    )

    report = csi.build_contradiction_staleness_intelligence(repo_root=tmp_path)
    paths = csi.write_outputs(report, repo_root=tmp_path)

    assert paths["latest"] == "logs/qre_contradiction_staleness_intelligence/latest.json"
    assert (tmp_path / paths["latest"]).exists()
    assert (tmp_path / paths["operator_summary"]).exists()
