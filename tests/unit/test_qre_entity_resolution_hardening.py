from __future__ import annotations

import json
from pathlib import Path

from research import qre_entity_resolution_hardening as entity_hardening


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def test_entity_resolution_hardening_blocks_cross_artifact_ambiguity(monkeypatch) -> None:
    monkeypatch.setattr(
        entity_hardening.memory_coverage,
        "build_research_memory_coverage",
        lambda **_: {
            "summary": {
                "final_recommendation": "research_memory_coverage_ready",
                "indexed_entry_count": 2,
                "indexed_candidate_count": 1,
            },
            "entries": [
                {
                    "artifact_id": "basket:cand-1",
                    "record_kind": "basket",
                    "subject_id": "cand-1",
                    "title": "BTC-USD basket",
                    "text_preview": "resolved asset context",
                    "metadata": {},
                    "resolved_entities": [
                        {
                            "entity_id": "asset:BTC-USD",
                            "entity_type": "asset",
                            "label": "BTC-USD",
                            "confidence": "HIGH",
                            "ambiguity_status": "resolved",
                            "evidence": ["matched_symbol:BTC-USD"],
                        }
                    ],
                },
                {
                    "artifact_id": "reason:cand-1",
                    "record_kind": "reason_record",
                    "subject_id": "cand-1",
                    "title": "BTCUSD reason",
                    "text_preview": "resolved asset context",
                    "metadata": {},
                    "resolved_entities": [
                        {
                            "entity_id": "asset:BTC-USD",
                            "entity_type": "asset",
                            "label": "BTCUSD",
                            "confidence": "HIGH",
                            "ambiguity_status": "resolved",
                            "evidence": ["matched_symbol:BTC-USD"],
                        }
                    ],
                },
            ],
        },
    )

    report = entity_hardening.build_entity_resolution_hardening()

    assert report["summary"]["graph_status"] == "partial"
    assert report["summary"]["blocked_entity_count"] == 1
    assert report["summary"]["cross_artifact_entity_count"] == 1
    entity = next(row for row in report["canonical_entities"] if row["entity_id"] == "asset:BTC-USD")
    assert entity["ambiguity_blocked"] is True
    assert "cross_artifact_label_conflict" in entity["blocking_reasons"]
    assert len(entity["source_artifact_ids"]) == 2


def test_entity_resolution_hardening_blocks_when_memory_surface_missing(monkeypatch) -> None:
    monkeypatch.setattr(
        entity_hardening.memory_coverage,
        "build_research_memory_coverage",
        lambda **_: {
            "summary": {"final_recommendation": "research_memory_coverage_missing"},
            "entries": [],
        },
    )

    report = entity_hardening.build_entity_resolution_hardening()

    assert report["summary"]["graph_status"] == "blocked"
    assert report["canonical_entities"] == []
    assert report["blocked_entities"] == []


def test_entity_resolution_hardening_writes_outputs(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        entity_hardening.memory_coverage,
        "build_research_memory_coverage",
        lambda **_: {
            "summary": {"final_recommendation": "research_memory_coverage_ready"},
            "entries": [
                {
                    "artifact_id": "basket:cand-1",
                    "record_kind": "basket",
                    "subject_id": "cand-1",
                    "title": "BTC-USD basket",
                    "text_preview": "resolved asset context",
                    "metadata": {},
                    "resolved_entities": [
                        {
                            "entity_id": "asset:BTC-USD",
                            "entity_type": "asset",
                            "label": "BTC-USD",
                            "confidence": "HIGH",
                            "ambiguity_status": "resolved",
                            "evidence": ["matched_symbol:BTC-USD"],
                        }
                    ],
                }
            ],
        },
    )

    report = entity_hardening.build_entity_resolution_hardening()
    paths = entity_hardening.write_outputs(report, repo_root=tmp_path)
    summary = (tmp_path / paths["operator_summary"]).read_text(encoding="utf-8")
    assert paths["latest"] == "logs/qre_entity_resolution_hardening/latest.json"
    assert "# QRE Entity Resolution Hardening" in summary
