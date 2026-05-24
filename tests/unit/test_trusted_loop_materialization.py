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
    density = snapshot["routing_sampling_readiness_density"]
    assert density["overall_status"] == "fail_closed"
    assert density["values"]["routing_ready"]["status"] == "fail_closed"
    assert density["values"]["sampling_ready"]["status"] == "fail_closed"
    assert snapshot["synthesis_remains_blocked"] is True
    explanation_density = snapshot["synthesis_blocker_explanation_density"]
    assert explanation_density["overall_status"] == "blocked_explained"
    assert explanation_density["unexplained_blocker_count"] == 0
    assert (
        explanation_density["values"]["no_strategy_synthesis_scope_authorized"][
            "enables_strategy_synthesis"
        ]
        is False
    )


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
    assert kpis["values"]["OAB"]["status"] == "fail_closed"
    assert kpis["values"]["OAB"]["value"] is None
    assert kpis["values"]["OAB"]["fail_closed"] is True
    assert kpis["values"]["OAB"]["partial_evidence_count"] == 4
    assert kpis["values"]["TTFPRC"]["status"] == "fail_closed"
    assert kpis["values"]["TTFPRC"]["readiness_score"] == 0.0
    assert kpis["complete_value_count"] == 0
    assert kpis["partial_value_count"] == 1
    assert kpis["fail_closed_count"] == 7
    assert kpis["all_reported_kpis_numeric_or_fail_closed"] is True


def test_research_quality_kpis_are_ready_with_complete_numeric_evidence() -> None:
    evidence = {
        "TTFPRC": {"value": 12.0, "source": "fixture"},
        "OOS_DSR": {"value": 0.7, "source": "fixture"},
        "MASQ": {"value": 1.2, "source": "fixture"},
        "NMBR": {"value": 0.75, "source": "fixture"},
        "DZCR": {"value": 0.18, "source": "fixture"},
        "OAB": {
            "visible_surface_count": 4,
            "operator_decisions_per_week": 2,
            "source": "fixture",
        },
        "CRSR": {"value": 0.4, "source": "fixture"},
    }

    kpis = tlm._research_quality_kpi_readiness(
        {"research_quality_kpi_evidence": evidence}
    )

    assert kpis["complete_value_count"] == 7
    assert kpis["fail_closed_count"] == 0
    assert kpis["partial_value_count"] == 0
    assert kpis["all_reported_kpis_numeric_or_fail_closed"] is True
    assert kpis["values"]["OAB"]["value"] == 8
    assert all(row["status"] == "ready" for row in kpis["values"].values())
    assert all(row["readiness_score"] == 1.0 for row in kpis["values"].values())


def test_research_quality_kpis_fail_closed_on_missing_evidence() -> None:
    kpis = tlm._research_quality_kpi_readiness({})

    assert kpis["complete_value_count"] == 0
    assert kpis["partial_value_count"] == 0
    assert kpis["fail_closed_count"] == 7
    assert kpis["all_reported_kpis_numeric_or_fail_closed"] is True
    for row in kpis["values"].values():
        assert row["status"] == "fail_closed"
        assert row["value"] is None
        assert row["numeric_value_ready"] is False
        assert row["fail_closed"] is True
        assert row["readiness_score"] == 0.0
        assert row["missing_evidence"]


def test_research_quality_kpis_fail_closed_on_unknown_non_numeric_evidence() -> None:
    kpis = tlm._research_quality_kpi_readiness(
        {
            "research_quality_kpi_evidence": {
                "TTFPRC": {"value": "unknown", "source": "fixture"},
                "NMBR": {"value": None, "source": "fixture"},
            }
        }
    )

    assert kpis["complete_value_count"] == 0
    assert kpis["fail_closed_count"] == 7
    assert kpis["values"]["TTFPRC"]["status"] == "fail_closed"
    assert kpis["values"]["TTFPRC"]["source"] == "fixture"
    assert kpis["values"]["NMBR"]["status"] == "fail_closed"
    assert kpis["values"]["NMBR"]["source"] == "fixture"


def test_routing_sampling_readiness_density_ready_with_existing_ready_artifacts(
    tmp_path: Path,
) -> None:
    routing_path = tmp_path / "logs" / "intelligent_routing_minimal" / "latest.json"
    sampling_path = tmp_path / "logs" / "sampling_intelligence_minimal" / "latest.json"
    routing_snapshot = tlm._routing.collect_snapshot(
        [
            {
                "campaign_id": "c1",
                "info_gain_estimate": 0.8,
                "dead_zone_dwell": 0,
                "dependency_unmet": False,
                "multiplicity_budget_remaining": 1,
            }
        ],
        frozen_utc=FROZEN,
        emit_reason_records=False,
    )
    sampling_snapshot = tlm._sampling.collect_snapshot(
        [
            {
                "stratum_id": "s1",
                "coverage_actual": 0.1,
                "coverage_target": 0.3,
                "regime_match": True,
                "null_baseline_required": False,
                "multiplicity_budget_remaining": 1,
            }
        ],
        frozen_utc=FROZEN,
        emit_reason_records=False,
    )
    _write_json(routing_path, routing_snapshot)
    _write_json(sampling_path, sampling_snapshot)

    density = tlm._routing_sampling_readiness_density(
        routing_snapshot=routing_snapshot,
        sampling_snapshot=sampling_snapshot,
        routing_artifact_path=routing_path,
        sampling_artifact_path=sampling_path,
    )

    assert density["overall_status"] == "ready"
    assert density["ready_count"] == 2
    assert density["fail_closed_count"] == 0
    assert density["overall_evidence_density_score"] == 1.0
    assert density["values"]["routing_ready"]["status"] == "ready"
    assert density["values"]["routing_ready"]["prioritize_count"] == 1
    assert density["values"]["sampling_ready"]["status"] == "ready"
    assert density["values"]["sampling_ready"]["actionable_count"] == 1


def test_routing_sampling_readiness_density_fails_closed_on_empty_artifacts(
    tmp_path: Path,
) -> None:
    routing_path = tmp_path / "logs" / "intelligent_routing_minimal" / "latest.json"
    sampling_path = tmp_path / "logs" / "sampling_intelligence_minimal" / "latest.json"
    routing_snapshot = tlm._routing.collect_snapshot(
        [],
        frozen_utc=FROZEN,
        emit_reason_records=False,
    )
    sampling_snapshot = tlm._sampling.collect_snapshot(
        [],
        frozen_utc=FROZEN,
        emit_reason_records=False,
    )
    _write_json(routing_path, routing_snapshot)
    _write_json(sampling_path, sampling_snapshot)

    density = tlm._routing_sampling_readiness_density(
        routing_snapshot=routing_snapshot,
        sampling_snapshot=sampling_snapshot,
        routing_artifact_path=routing_path,
        sampling_artifact_path=sampling_path,
    )

    assert density["overall_status"] == "fail_closed"
    assert density["ready_count"] == 0
    assert density["fail_closed_count"] == 2
    assert density["missing_evidence_count"] == 6
    assert density["values"]["routing_ready"]["missing_evidence"] == [
        "final_recommendation_ready",
        "total_count_positive",
        "prioritize_count_positive",
    ]
    assert density["values"]["sampling_ready"]["missing_evidence"] == [
        "final_recommendation_ready",
        "total_count_positive",
        "actionable_count_positive",
    ]


def test_routing_sampling_readiness_density_fails_closed_on_missing_or_unknown(
    tmp_path: Path,
) -> None:
    density = tlm._routing_sampling_readiness_density(
        routing_snapshot={"counts": {"total": "unknown"}},
        sampling_snapshot={"counts": {"total": None, "actionable": "unknown"}},
        routing_artifact_path=(
            tmp_path / "logs" / "intelligent_routing_minimal" / "latest.json"
        ),
        sampling_artifact_path=(
            tmp_path / "logs" / "sampling_intelligence_minimal" / "latest.json"
        ),
    )

    assert density["overall_status"] == "fail_closed"
    assert density["fail_closed_count"] == 2
    assert density["values"]["routing_ready"]["final_recommendation"] == "unknown"
    assert density["values"]["sampling_ready"]["final_recommendation"] == "unknown"
    assert "latest_artifact_present" in density["values"]["routing_ready"][
        "missing_evidence"
    ]
    assert "latest_artifact_present" in density["values"]["sampling_ready"][
        "missing_evidence"
    ]


def test_synthesis_blocker_explanation_density_explains_current_blockers() -> None:
    kpis = tlm._research_quality_kpi_readiness({})
    routing_sampling = {
        "values": {
            "routing_ready": {
                "status": "fail_closed",
                "final_recommendation": "nothing_ready",
                "total": 0,
                "prioritize_count": 0,
                "evidence_density_score": 0.25,
                "missing_evidence": [
                    "final_recommendation_ready",
                    "total_count_positive",
                    "prioritize_count_positive",
                ],
            },
            "sampling_ready": {
                "status": "fail_closed",
                "final_recommendation": "nothing_ready",
                "total": 0,
                "actionable_count": 0,
                "evidence_density_score": 0.25,
                "missing_evidence": [
                    "final_recommendation_ready",
                    "total_count_positive",
                    "actionable_count_positive",
                ],
            },
        }
    }
    density = tlm._synthesis_blocker_explanation_density(
        block_reasons=[
            "failure_action_mapping_not_ready_when_total_failures_zero",
            "no_complete_research_quality_kpi_values",
            "no_strategy_synthesis_scope_authorized",
            "reason_record_evidence_density_not_ready",
            "routing_ready_evidence_missing_or_not_ready",
            "sampling_ready_evidence_missing_or_not_ready",
        ],
        failure_action_mapping={
            "status": "not_ready",
            "total_failures": 0,
            "actionable_failure_count": 0,
        },
        kpi_readiness=kpis,
        routing_sampling_readiness=routing_sampling,
        reason_density={
            "final_recommendation": "not_ready_no_reason_records",
            "metrics": {
                "record_count": 0,
                "records_with_evidence_refs": 0,
            },
        },
    )

    assert density["overall_status"] == "blocked_explained"
    assert density["active_blocker_count"] == 6
    assert density["explained_blocker_count"] == 6
    assert density["unexplained_blocker_count"] == 0
    assert density["synthesis_remains_blocked"] is True
    assert density["values"]["no_complete_research_quality_kpi_values"][
        "missing_evidence"
    ] == ["complete_numeric_research_quality_kpis"]
    assert density["values"]["reason_record_evidence_density_not_ready"][
        "readiness_score"
    ] == 0.0
    assert all(row["read_only"] is True for row in density["values"].values())
    assert all(
        row["enables_strategy_synthesis"] is False
        for row in density["values"].values()
    )


def test_synthesis_blocker_explanation_density_fails_closed_on_unknown_reason() -> None:
    density = tlm._synthesis_blocker_explanation_density(
        block_reasons=["unknown_future_blocker"],
        failure_action_mapping={},
        kpi_readiness={},
        routing_sampling_readiness={},
        reason_density={},
    )

    assert density["overall_status"] == "fail_closed"
    assert density["active_blocker_count"] == 1
    assert density["explained_blocker_count"] == 0
    assert density["unexplained_blocker_count"] == 1
    assert density["unexplained_block_reasons"] == ["unknown_future_blocker"]
    assert density["synthesis_remains_blocked"] is True


def test_write_outputs_refuses_outside_allowlist(tmp_path: Path) -> None:
    bad = tmp_path / "elsewhere" / "latest.json"
    bad.parent.mkdir(parents=True, exist_ok=True)
    try:
        tlm._validate_write_target(bad)
    except ValueError as exc:
        assert "outside allowlist" in str(exc)
    else:
        raise AssertionError("expected outside-allowlist refusal")
