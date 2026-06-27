from __future__ import annotations

import json
from pathlib import Path

import pytest

from reporting import qre_evidence_decay as decay


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _lineage_payload() -> dict:
    return {
        "report_kind": "qre_contradiction_hypothesis_lineage",
        "rows": [
            {
                "thesis_id": "qbt_test_001",
                "source_hypothesis_id": "hypothesis_001",
                "title": "Trend Continuation: test",
                "behavior_family": "trend_continuation",
                "lineage_complete": False,
                "missing_lineage_fields": [
                    "campaign_identity",
                    "data_snapshot_identity",
                    "source_identity",
                ],
                "graph_nodes": {
                    "source": [],
                    "data_snapshot": [],
                    "campaign": [],
                },
                "contradiction_rows": [],
                "contradicting_evidence_refs": [],
                "unresolved_evidence_refs": [
                    "state:regime_context:blocked:pending",
                    "state:oos_plan:blocked:oos:pending",
                ],
                "provenance_refs": [
                    "logs/qre_research_memory_retrieval/latest.json",
                    "logs/qre_lineage_graph_v1/latest.json",
                ],
            }
        ],
    }


def _contradiction_payload() -> dict:
    return {
        "report_kind": "qre_contradiction_staleness_intelligence",
        "stale_or_superseded": [
            {
                "artifact_path": "logs/qre_research_memory_retrieval/latest.json",
                "detail": "stale_artifact",
            }
        ],
    }


def test_decay_flags_incomplete_lineage_and_missing_oos_renewal(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "logs" / "qre_contradiction_hypothesis_lineage" / "latest.json",
        _lineage_payload(),
    )
    _write_json(
        tmp_path / "logs" / "qre_contradiction_staleness_intelligence" / "latest.json",
        _contradiction_payload(),
    )

    report = decay.build_evidence_decay(repo_root=tmp_path)

    row = report["rows"][0]
    assert row["decay_blocks_readiness"] is True
    assert row["dimension_statuses"]["incomplete_lineage"] == "lineage_incomplete"
    assert row["dimension_statuses"]["missing_oos_renewal"] == "missing_oos_plan_or_renewal"
    assert row["dimension_statuses"]["source_freshness"] == "missing_source_identity"
    assert "lineage_incomplete" in row["blocking_reasons"]
    assert report["summary"]["final_recommendation"] == "evidence_decay_visible_fail_closed"


def test_decay_uses_validation_and_visible_contradictions(tmp_path: Path) -> None:
    lineage = _lineage_payload()
    lineage["rows"][0]["lineage_complete"] = True
    lineage["rows"][0]["missing_lineage_fields"] = []
    lineage["rows"][0]["graph_nodes"] = {
        "source": ["evidence::source_a"],
        "data_snapshot": ["evidence::snapshot_a"],
        "campaign": ["campaign::001"],
    }
    lineage["rows"][0]["contradiction_rows"] = [{"scope_key": "hypothesis_001"}]
    lineage["rows"][0]["unresolved_evidence_refs"] = []
    lineage["rows"][0]["contradicting_evidence_refs"] = ["fixture#contradiction"]
    _write_json(
        tmp_path / "logs" / "qre_contradiction_hypothesis_lineage" / "latest.json",
        lineage,
    )
    _write_json(
        tmp_path / "logs" / "qre_contradiction_staleness_intelligence" / "latest.json",
        {"report_kind": "qre_contradiction_staleness_intelligence", "stale_or_superseded": []},
    )
    _write_json(
        tmp_path / "logs" / "qre_hypothesis_validation_results" / "latest.json",
        {
            "report_kind": "qre_hypothesis_validation_results",
            "validation_results": [{"hypothesis_id": "hypothesis_001", "status": "failed"}],
        },
    )

    report = decay.build_evidence_decay(repo_root=tmp_path)

    row = report["rows"][0]
    assert row["validation_result_count"] == 1
    assert row["dimension_statuses"]["reproducibility"] == "validation_result_present"
    assert row["dimension_statuses"]["contradiction_state"] == "contradicting_evidence_visible"
    assert "contradicting_evidence_visible" in row["blocking_reasons"]


def test_write_outputs_and_status_round_trip(tmp_path: Path) -> None:
    report = decay.build_evidence_decay(
        lineage_report={"report_kind": "qre_contradiction_hypothesis_lineage", "rows": []}
    )
    paths = decay.write_outputs(report, repo_root=tmp_path)

    assert paths["latest"] == "logs/qre_evidence_decay/latest.json"
    assert paths["doc"] == "docs/governance/qre_evidence_decay.md"
    assert decay.read_status(repo_root=tmp_path) == {
        "status": "missing_lineage_inputs_fail_closed",
        "path": "logs/qre_evidence_decay/latest.json",
    }


def test_write_outputs_refuses_outside_allowlist(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        decay._validate_write_target(tmp_path / "outside.json")
