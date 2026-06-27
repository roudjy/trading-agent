from __future__ import annotations

import ast
import json
from pathlib import Path

from reporting import qre_contradiction_hypothesis_lineage as lineage


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _seed_reports(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "logs" / "qre_behavior_thesis_registry" / "latest.json",
        {
            "rows": [
                {
                    "thesis_id": "thesis-a",
                    "source_hypothesis_id": "hyp_a",
                    "behavior_family": "trend_continuation",
                    "title": "A",
                    "provenance_refs": ["registry:a"],
                },
                {
                    "thesis_id": "thesis-b",
                    "source_hypothesis_id": "hyp_b",
                    "behavior_family": "mean_reversion",
                    "title": "B",
                    "provenance_refs": ["registry:b"],
                },
            ]
        },
    )
    _write_json(
        tmp_path / "logs" / "qre_behavior_thesis_evidence" / "latest.json",
        {
            "rows": [
                {
                    "thesis_id": "thesis-a",
                    "source_hypothesis_id": "hyp_a",
                    "provenance_refs": ["evidence:a"],
                    "evidence_items": [
                        {"stance": "supporting", "evidence_ref": "support:a"},
                        {"stance": "contradicting", "evidence_ref": "contra:a"},
                        {"stance": "unresolved", "evidence_ref": "unresolved:a"},
                    ],
                },
                {
                    "thesis_id": "thesis-b",
                    "source_hypothesis_id": "hyp_b",
                    "provenance_refs": ["evidence:b"],
                    "evidence_items": [
                        {"stance": "supporting", "evidence_ref": "support:b"},
                    ],
                },
            ]
        },
    )
    _write_json(
        tmp_path / "logs" / "qre_lineage_graph_v1" / "latest.json",
        {
            "summary": {"graph_status": "partial"},
            "checks": {
                "orphan_nodes": [
                    {
                        "node_id": "hypothesis::hyp_b",
                        "reason": "hypothesis_has_no_campaign_reference",
                    }
                ]
            },
            "nodes": [
                {"node_id": "hypothesis::hyp_a", "node_type": "hypothesis"},
                {"node_id": "hypothesis::hyp_b", "node_type": "hypothesis"},
                {"node_id": "campaign::cmp-a", "node_type": "campaign", "outcome": "completed_no_survivor"},
            ],
            "edges": [
                {
                    "source": "hypothesis::hyp_a",
                    "target": "campaign::cmp-a",
                    "relation": "registry_reference",
                },
                {
                    "source": "campaign::cmp-a",
                    "target": "evidence::source_quality_readiness",
                    "relation": "documented_by",
                },
                {
                    "source": "campaign::cmp-a",
                    "target": "evidence::historical_accounting_foundation",
                    "relation": "documented_by",
                },
            ],
        },
    )
    _write_json(
        tmp_path / "logs" / "qre_contradiction_staleness_intelligence" / "latest.json",
        {
            "summary": {"exact_next_action": "review_visible_contradictions_before_new_research"},
            "contradictions": [{"scope_key": "hyp_a", "detail": "visible_contradiction"}],
            "stale_or_superseded": [{"artifact_path": "logs/stale/latest.json"}],
        },
    )


def test_build_binds_thesis_to_visible_lineage_and_explicit_gaps(tmp_path: Path) -> None:
    _seed_reports(tmp_path)

    report = lineage.build_contradiction_hypothesis_lineage(
        repo_root=tmp_path,
        thesis_registry_report=json.loads(
            (tmp_path / "logs" / "qre_behavior_thesis_registry" / "latest.json").read_text(encoding="utf-8")
        ),
        thesis_evidence_report=json.loads(
            (tmp_path / "logs" / "qre_behavior_thesis_evidence" / "latest.json").read_text(encoding="utf-8")
        ),
        lineage_graph_report=json.loads(
            (tmp_path / "logs" / "qre_lineage_graph_v1" / "latest.json").read_text(encoding="utf-8")
        ),
        contradiction_report=json.loads(
            (tmp_path / "logs" / "qre_contradiction_staleness_intelligence" / "latest.json").read_text(encoding="utf-8")
        ),
    )

    assert report["report_kind"] == "qre_contradiction_hypothesis_lineage"
    assert report["summary"]["thesis_count"] == 2
    assert report["summary"]["orphan_thesis_count"] == 1
    assert report["summary"]["complete_lineage_count"] == 1
    row_a = next(row for row in report["rows"] if row["thesis_id"] == "thesis-a")
    row_b = next(row for row in report["rows"] if row["thesis_id"] == "thesis-b")
    assert row_a["lineage_complete"] is True
    assert row_a["graph_nodes"]["campaign"] == ["campaign::cmp-a"]
    assert row_a["graph_nodes"]["next_action"] == "review_visible_contradictions_before_new_research"
    assert row_b["orphan_status"]["is_orphan"] is True
    assert "campaign_identity" in row_b["missing_lineage_fields"]
    assert "data_snapshot_identity" in row_b["missing_lineage_fields"]


def test_missing_campaign_lineage_fails_closed_without_inventing_links(tmp_path: Path) -> None:
    _seed_reports(tmp_path)
    payload = json.loads((tmp_path / "logs" / "qre_lineage_graph_v1" / "latest.json").read_text(encoding="utf-8"))
    payload["edges"] = []
    (tmp_path / "logs" / "qre_lineage_graph_v1" / "latest.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )

    report = lineage.build_contradiction_hypothesis_lineage(
        repo_root=tmp_path,
        thesis_registry_report=json.loads(
            (tmp_path / "logs" / "qre_behavior_thesis_registry" / "latest.json").read_text(encoding="utf-8")
        ),
        thesis_evidence_report=json.loads(
            (tmp_path / "logs" / "qre_behavior_thesis_evidence" / "latest.json").read_text(encoding="utf-8")
        ),
        lineage_graph_report=payload,
        contradiction_report=json.loads(
            (tmp_path / "logs" / "qre_contradiction_staleness_intelligence" / "latest.json").read_text(encoding="utf-8")
        ),
    )

    assert report["summary"]["complete_lineage_count"] == 0
    for row in report["rows"]:
        assert row["graph_nodes"]["campaign"] == []
        assert row["graph_nodes"]["policy_decision"] == "blocked_missing_campaign_lineage"


def test_write_outputs_and_status_round_trip(tmp_path: Path) -> None:
    _seed_reports(tmp_path)
    report = lineage.build_contradiction_hypothesis_lineage(repo_root=tmp_path)

    paths = lineage.write_outputs(report, repo_root=tmp_path)

    assert paths == {
        "latest": "logs/qre_contradiction_hypothesis_lineage/latest.json",
        "doc": "docs/governance/qre_contradiction_hypothesis_lineage.md",
    }
    assert "QRE Contradiction Hypothesis Lineage" in (tmp_path / paths["doc"]).read_text(encoding="utf-8")
    assert lineage.read_status(repo_root=tmp_path) == {
        "status": "ready",
        "path": "logs/qre_contradiction_hypothesis_lineage/latest.json",
        "fails_closed": False,
        "schema_version": "1.0",
    }


def test_source_is_read_only_and_preserves_frozen_contracts() -> None:
    source = Path(lineage.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])

    assert imported.isdisjoint({"requests", "socket", "httpx", "urllib", "subprocess"})
    assert "research/research_latest.json" not in source
    assert "research/strategy_matrix.csv" not in source
    assert "\"can_launch_campaign\": False" in source
