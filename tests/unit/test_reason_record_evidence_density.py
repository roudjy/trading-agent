"""Tests for ADE-QRE-014B reason-record evidence density."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from reporting import failure_action_mapping_minimal as fam
from reporting import intelligent_routing_minimal as routing
from reporting import reason_record_evidence_density as density
from reporting import sampling_intelligence_minimal as sampling


FROZEN = "2026-05-24T00:00:00Z"


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, indent=2), encoding="utf-8")


def test_density_counts_sidecar_evidence_refs(tmp_path: Path) -> None:
    routing_dir = tmp_path / "logs" / "intelligent_routing_minimal"
    sampling_dir = tmp_path / "logs" / "sampling_intelligence_minimal"
    failure_dir = tmp_path / "logs" / "failure_action_mapping_minimal"

    routing_snap = routing.collect_snapshot(
        [
            {
                "campaign_id": "c1",
                "info_gain_estimate": 0.8,
                "dead_zone_dwell": 0,
                "dependency_unmet": False,
                "multiplicity_budget_remaining": 2,
            }
        ],
        frozen_utc=FROZEN,
        emit_reason_records=False,
    )
    sampling_snap = sampling.collect_snapshot(
        [
            {
                "stratum_id": "s1",
                "coverage_actual": 0.1,
                "coverage_target": 0.4,
                "regime_match": True,
                "null_baseline_required": False,
                "multiplicity_budget_remaining": 2,
            }
        ],
        frozen_utc=FROZEN,
        emit_reason_records=False,
    )
    failure_snap = fam.collect_snapshot(
        [
            {
                "subject_id": "screening:missing_metric_field",
                "failure_code": "technical_failure",
                "severity": "medium",
                "evidence_count": 4,
            }
        ],
        frozen_utc=FROZEN,
    )
    routing.write_outputs(routing_snap, artifact_dir=routing_dir)
    sampling.write_outputs(sampling_snap, artifact_dir=sampling_dir)
    fam.write_outputs(failure_snap, artifact_dir=failure_dir)

    snapshot = density.collect_snapshot(
        frozen_utc=FROZEN,
        reason_records_artifact_dir=tmp_path / "logs" / "reason_records",
        routing_minimal_path=routing_dir / "latest.json",
        sampling_minimal_path=sampling_dir / "latest.json",
        failure_action_mapping_path=failure_dir / "latest.json",
        synthesis_gate_path=tmp_path / "missing_synthesis.json",
    )

    metrics = snapshot["metrics"]
    assert metrics["record_count"] == 3
    assert metrics["records_with_reason_codes"] == 3
    assert metrics["records_with_reason_text"] == 3
    assert metrics["records_with_evidence_refs"] == 3
    assert metrics["records_missing_evidence_refs"] == 0
    assert snapshot["final_recommendation"] == "evidence_density_ready"
    assert "routing_sidecar" in metrics["by_family"]


def test_missing_evidence_refs_fail_closed(tmp_path: Path) -> None:
    routing_path = tmp_path / "logs" / "intelligent_routing_minimal" / "latest.json"
    _write_json(
        routing_path,
        {
            "items": [
                {
                    "campaign_id": "thin",
                    "record_id": "rr_thin",
                    "reason_codes": ["info_gain_high"],
                    "reason_text": "thin record",
                }
            ]
        },
    )

    snapshot = density.collect_snapshot(
        frozen_utc=FROZEN,
        reason_records_artifact_dir=tmp_path / "logs" / "reason_records",
        routing_minimal_path=routing_path,
        sampling_minimal_path=tmp_path / "missing_sampling.json",
        failure_action_mapping_path=tmp_path / "missing_failure.json",
        synthesis_gate_path=tmp_path / "missing_synthesis.json",
    )

    assert snapshot["final_recommendation"] == "not_ready_missing_evidence_refs"
    assert snapshot["metrics"]["thin_records_top"][0]["missing_fields"] == [
        "evidence_refs"
    ]


def test_sidecar_refs_join_to_jsonl_reason_records(tmp_path: Path) -> None:
    rr_dir = tmp_path / "logs" / "reason_records"
    routing_dir = tmp_path / "logs" / "intelligent_routing_minimal"
    routing_snap = routing.collect_snapshot(
        [
            {
                "campaign_id": "joined",
                "info_gain_estimate": 0.8,
                "dead_zone_dwell": 0,
                "dependency_unmet": False,
                "multiplicity_budget_remaining": 2,
            }
        ],
        frozen_utc=FROZEN,
        artifact_dir_for_reasons=rr_dir,
    )
    routing.write_outputs(routing_snap, artifact_dir=routing_dir)

    snapshot = density.collect_snapshot(
        frozen_utc=FROZEN,
        reason_records_artifact_dir=rr_dir,
        routing_minimal_path=routing_dir / "latest.json",
        sampling_minimal_path=tmp_path / "missing_sampling.json",
        failure_action_mapping_path=tmp_path / "missing_failure.json",
        synthesis_gate_path=tmp_path / "missing_synthesis.json",
    )

    assert snapshot["baseline_without_sidecars"]["records_missing_evidence_refs"] == 1
    assert snapshot["after_with_sidecars"]["record_count"] == 1
    assert snapshot["after_with_sidecars"]["records_with_evidence_refs"] == 1
    assert snapshot["final_recommendation"] == "evidence_density_ready"


def test_synthesis_gate_is_read_as_reference_only_sidecar(tmp_path: Path) -> None:
    synthesis_path = tmp_path / "research" / "synthesis_gate_latest.v1.json"
    _write_json(
        synthesis_path,
        {
            "synthesis_gate_state": "blocked_missing_market_context",
            "reason_codes": ["missing_linked_market_context_insight"],
            "required_missing_evidence": ["linked_market_context_insight"],
            "supporting_evidence": {
                "artifact_inputs": {
                    "research_state": {
                        "path": "research/research_state_latest.v1.json",
                        "status": "missing",
                    }
                }
            },
        },
    )

    snapshot = density.collect_snapshot(
        frozen_utc=FROZEN,
        reason_records_artifact_dir=tmp_path / "logs" / "reason_records",
        routing_minimal_path=tmp_path / "missing_routing.json",
        sampling_minimal_path=tmp_path / "missing_sampling.json",
        failure_action_mapping_path=tmp_path / "missing_failure.json",
        synthesis_gate_path=synthesis_path,
    )

    assert snapshot["metrics"]["record_count"] == 1
    assert snapshot["metrics"]["records_with_evidence_refs"] == 1
    assert snapshot["safety_invariants"]["strategy_synthesis_enabled"] is False


def test_write_outputs_refuses_outside_allowlist(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="outside allowlist"):
        density._validate_write_target(tmp_path / "elsewhere" / "latest.json")
