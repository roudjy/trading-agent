"""Tests for ADE-QRE-012 trusted-loop materialization."""

from __future__ import annotations

import json
from pathlib import Path

from reporting import trusted_loop_materialization as tlm


FROZEN = "2026-05-23T00:00:00Z"


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, indent=2), encoding="utf-8")


def _seed_operator_sources(tmp_path: Path) -> dict[str, Path]:
    screening = tmp_path / "research" / "screening_failure_attribution_latest.v1.json"
    failure_actions = tmp_path / "logs" / "failure_action_mapping_minimal" / "latest.json"
    data_manifest = tmp_path / "logs" / "qre_data_cache_manifest" / "latest.json"
    source_quality = tmp_path / "logs" / "qre_data_source_quality_readiness" / "latest.json"
    memory = tmp_path / "logs" / "qre_research_memory" / "latest.json"
    diagnostics = tmp_path / "logs" / "qre_research_diagnostics_loop" / "latest.json"
    queue = tmp_path / "docs" / "governance" / "queue.md"

    _write_json(
        screening,
        {
            "summary": {
                "observation_count": 2,
                "unknown_observation_count": 0,
                "primary_classification": "insufficient_trades",
            },
            "recommended_next_action": "increase_timeframe",
            "classifications": [
                {
                    "classification": "insufficient_trades",
                    "count": 2,
                    "sources": ["run_filter_summary"],
                    "raw_reasons": {"insufficient_trades": 2},
                    "action_hint": {"action": "increase_timeframe"},
                }
            ],
        },
    )
    _write_json(
        failure_actions,
        {
            "counts": {"total": 0, "actionable_recommendations": 0},
            "final_recommendation": "nothing_actionable",
        },
    )
    _write_json(data_manifest, {"summary": {"research_ready": True}})
    _write_json(source_quality, {"summary": {"research_ready": True}})
    _write_json(
        memory,
        {
            "summary": {"research_memory_ready": True, "entry_count": 1},
            "entries": [{"ontology_tags": ["failure"]}],
        },
    )
    _write_json(
        diagnostics,
        {
            "summary": {
                "status": "ready",
                "diagnostic_count": 1,
                "recommended_operator_step": "inspect_next_diagnostic",
                "blocking_reasons": [],
            }
        },
    )
    queue.parent.mkdir(parents=True, exist_ok=True)
    queue.write_text("- queue id: `ADE-QRE-008`\n- status: `done`\n", encoding="utf-8")
    return {
        "screening_failure_attribution_path": screening,
        "failure_action_mapping_path": failure_actions,
        "data_manifest_path": data_manifest,
        "source_quality_path": source_quality,
        "research_memory_path": memory,
        "research_diagnostics_loop_path": diagnostics,
        "ade_queue_doc_path": queue,
    }


def test_materialize_writes_empty_evidence_artifacts_without_reason_records(
    tmp_path: Path,
    monkeypatch,
) -> None:
    sources = _seed_operator_sources(tmp_path)
    monkeypatch.setattr(
        tlm._observability,
        "SCREENING_FAILURE_ATTRIBUTION_LATEST",
        sources["screening_failure_attribution_path"],
    )
    monkeypatch.setattr(
        tlm._observability,
        "FAILURE_ACTION_MAPPING_LATEST",
        sources["failure_action_mapping_path"],
    )
    monkeypatch.setattr(
        tlm._observability,
        "QRE_DATA_MANIFEST_LATEST",
        sources["data_manifest_path"],
    )
    monkeypatch.setattr(
        tlm._observability,
        "QRE_SOURCE_QUALITY_LATEST",
        sources["source_quality_path"],
    )
    monkeypatch.setattr(
        tlm._observability,
        "QRE_RESEARCH_MEMORY_LATEST",
        sources["research_memory_path"],
    )
    monkeypatch.setattr(
        tlm._observability,
        "QRE_RESEARCH_DIAGNOSTICS_LOOP_LATEST",
        sources["research_diagnostics_loop_path"],
    )
    monkeypatch.setattr(tlm._observability, "ADE_QUEUE_DOC", sources["ade_queue_doc_path"])

    rr_dir = tmp_path / "logs" / "reason_records"
    routing_dir = tmp_path / "logs" / "intelligent_routing_minimal"
    sampling_dir = tmp_path / "logs" / "sampling_intelligence_minimal"
    observability_dir = tmp_path / "logs" / "research_observability_minimal"
    materialization_dir = tmp_path / "logs" / "trusted_loop_materialization"

    snapshot = tlm.materialize(
        frozen_utc=FROZEN,
        reason_records_artifact_dir=rr_dir,
        routing_artifact_dir=routing_dir,
        sampling_artifact_dir=sampling_dir,
        observability_artifact_dir=observability_dir,
        artifact_dir=materialization_dir,
    )

    assert (rr_dir / "manifest.v1.json").is_file()
    assert not (rr_dir / "routing_v1.jsonl").exists()
    assert not (rr_dir / "sampling_v1.jsonl").exists()
    assert (routing_dir / "latest.json").is_file()
    assert (sampling_dir / "latest.json").is_file()
    assert (observability_dir / "latest.json").is_file()
    assert (materialization_dir / "latest.json").is_file()
    assert snapshot["materialized_artifacts"]["reason_records_manifest"]["total_records"] == 0
    assert snapshot["materialized_artifacts"]["routing_minimal_latest"]["total"] == 0
    assert snapshot["materialized_artifacts"]["sampling_minimal_latest"]["total"] == 0
    assert snapshot["failure_action_mapping"]["status"] == "not_ready"
    assert snapshot["failure_action_mapping"]["total_failures"] == 0
    assert snapshot["synthesis_remains_blocked"] is True


def test_collect_snapshot_surfaces_only_evidence_backed_numeric_values(
    tmp_path: Path,
    monkeypatch,
) -> None:
    sources = _seed_operator_sources(tmp_path)
    monkeypatch.setattr(
        tlm._observability,
        "SCREENING_FAILURE_ATTRIBUTION_LATEST",
        sources["screening_failure_attribution_path"],
    )
    monkeypatch.setattr(
        tlm._observability,
        "FAILURE_ACTION_MAPPING_LATEST",
        sources["failure_action_mapping_path"],
    )
    monkeypatch.setattr(
        tlm._observability,
        "QRE_DATA_MANIFEST_LATEST",
        sources["data_manifest_path"],
    )
    monkeypatch.setattr(
        tlm._observability,
        "QRE_SOURCE_QUALITY_LATEST",
        sources["source_quality_path"],
    )
    monkeypatch.setattr(
        tlm._observability,
        "QRE_RESEARCH_MEMORY_LATEST",
        sources["research_memory_path"],
    )
    monkeypatch.setattr(
        tlm._observability,
        "QRE_RESEARCH_DIAGNOSTICS_LOOP_LATEST",
        sources["research_diagnostics_loop_path"],
    )
    monkeypatch.setattr(tlm._observability, "ADE_QUEUE_DOC", sources["ade_queue_doc_path"])

    snapshot = tlm.collect_snapshot(
        frozen_utc=FROZEN,
        reason_records_artifact_dir=tmp_path / "logs" / "reason_records",
        routing_artifact_dir=tmp_path / "logs" / "intelligent_routing_minimal",
        sampling_artifact_dir=tmp_path / "logs" / "sampling_intelligence_minimal",
        observability_artifact_dir=tmp_path / "logs" / "research_observability_minimal",
    )
    metrics = snapshot["trusted_loop_metric_values"]
    assert metrics["unknown_failure_rate"]["ready"] is True
    assert metrics["unknown_failure_rate"]["value"] == 0.0
    assert metrics["attribution_depth_score"]["ready"] is True
    assert metrics["attribution_depth_score"]["value"] == 1.0
    assert metrics["actionable_failure_rate"]["ready"] is False
    assert metrics["actionable_failure_rate"]["value"] is None

    kpis = snapshot["research_quality_kpi_readiness"]
    assert kpis["values"]["OAB"]["status"] == "partial"
    assert kpis["values"]["TTFPRC"]["status"] == "not_ready"
    assert kpis["complete_value_count"] == 0


def test_write_outputs_refuses_outside_allowlist(tmp_path: Path) -> None:
    bad = tmp_path / "elsewhere" / "latest.json"
    bad.parent.mkdir(parents=True, exist_ok=True)
    try:
        tlm._validate_write_target(bad)
    except ValueError as exc:
        assert "outside allowlist" in str(exc)
    else:
        raise AssertionError("expected outside-allowlist refusal")
