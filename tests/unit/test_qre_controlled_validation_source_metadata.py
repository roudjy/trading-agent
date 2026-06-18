from __future__ import annotations

import json
from pathlib import Path

from research import qre_bounded_generation_artifact_acceptance_verifier as verifier
from research import qre_controlled_validation_adapter as adapter
from research import qre_controlled_validation_adapter_result_materialization as materializer
from research import qre_controlled_validation_source_metadata as metadata


def _source(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "source_type": "structured_controlled_validation",
        "source_authority": "structured_source",
        "source_ref": "artifacts/qre_controlled_validation/source-001.json",
        "lineage_records": [
            {
                "candidate_id": "cand-001",
                "campaign_id": "camp-001",
                "generation_run_id": "gen-001",
                "validation_status": "accepted",
                "reason_record_refs": ["rr-lineage-001"],
            }
        ],
        "oos_records": [
            {
                "candidate_id": "cand-001",
                "oos_window": {"start": "2025-01-01", "end": "2025-06-30"},
                "oos_metric_fields": {"oos_trade_count": 24, "oos_return_pct": 3.1},
                "cost_slippage_assumption_refs": ["cost-model-001"],
                "validation_status": "accepted",
                "reason_record_refs": ["rr-oos-001"],
            }
        ],
    }
    payload.update(overrides)
    return payload


def _request() -> dict[str, object]:
    return {
        "request_id": "req-metadata-001",
        "symbols": ["AAPL", "NVDA"],
        "preset_id": "trend_pullback_continuation_daily_v1",
        "timeframe": "daily_v1",
        "approval_ref": "approval-001",
        "required_artifact_types": [
            "generation_manifest",
            "structured_lineage_artifact",
            "structured_oos_artifact",
        ],
        "allowed_output_paths": ["logs/qre_controlled_validation_adapter_results/"],
        "forbidden_capabilities": [],
        "created_at_utc": "2026-06-18T00:00:00Z",
        "source": "operator_approval_manifest",
    }


def test_complete_metadata_passes() -> None:
    report = metadata.build_controlled_validation_source_metadata(_source())
    validation = metadata.validate_source_metadata(report)

    assert report["metadata_status"] == "metadata_complete"
    assert validation["valid"] is True


def test_each_missing_field_produces_explicit_reason() -> None:
    report = metadata.build_controlled_validation_source_metadata(
        _source(
            source_ref="",
            lineage_records=[{"candidate_id": "", "campaign_id": "", "generation_run_id": "", "reason_record_refs": []}],
            oos_records=[{"candidate_id": "", "oos_window": {}, "oos_metric_fields": {}, "cost_slippage_assumption_refs": [], "reason_record_refs": [], "validation_status": ""}],
        )
    )

    assert "missing_candidate_id" in report["reasons"]
    assert "missing_campaign_or_generation_id" in report["reasons"]
    assert "missing_source_artifact_ref" in report["reasons"]
    assert "missing_oos_window" in report["reasons"]
    assert "missing_oos_metrics" in report["reasons"]
    assert "missing_cost_slippage_refs" in report["reasons"]
    assert "missing_validation_status" in report["reasons"]
    assert "missing_reason_records" in report["reasons"]


def test_context_stdout_and_legacy_sources_are_unrecoverable() -> None:
    assert metadata.build_controlled_validation_source_metadata(
        _source(source_type="context_only")
    )["metadata_status"] == "unrecoverable_context_only_source"
    assert metadata.build_controlled_validation_source_metadata(
        _source(source_type="stdout_only")
    )["metadata_status"] == "unrecoverable_stdout_only_source"
    assert metadata.build_controlled_validation_source_metadata(
        _source(source_type="legacy_alias_only")
    )["metadata_status"] == "unrecoverable_legacy_alias_only_source"


def test_metadata_repair_never_invents_fields() -> None:
    report = metadata.build_controlled_validation_source_metadata(
        _source(lineage_records=[{"candidate_id": "", "campaign_id": "", "generation_run_id": ""}])
    )
    assert report["metadata_status"] == "missing_candidate_id"


def test_metadata_output_is_deterministic() -> None:
    first = metadata.build_controlled_validation_source_metadata(_source())
    second = metadata.build_controlled_validation_source_metadata(_source())
    assert first == second
    assert first["hash"] == metadata.compute_source_metadata_hash(first)


def test_verifier_uses_metadata_status_when_integrated(tmp_path: Path) -> None:
    adapter_result = adapter.build_controlled_validation_adapter_result(
        _request(),
        controlled_validation_source=_source(),
    )
    adapter_result["source_metadata_status"] = "missing_cost_slippage_refs"
    adapter_result["source_metadata_reasons"] = ["missing_cost_slippage_refs"]
    materialized = materializer.build_controlled_validation_adapter_result_materialization(adapter_result)
    target = tmp_path / "logs" / "qre_controlled_validation_adapter_results" / "latest.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(materialized, indent=2) + "\n", encoding="utf-8")

    report = verifier.build_bounded_generation_artifact_acceptance_verifier(repo_root=tmp_path)
    row = report["rows"][0]
    assert row["classification"] == "rejected_materialized_missing_required_fields"
    assert "missing_cost_slippage_refs" in row["rejection_reasons"]


def test_core_metadata_logic_has_no_aapl_or_nvda_hardcoding() -> None:
    source = Path("research/qre_controlled_validation_source_metadata.py").read_text(encoding="utf-8")
    assert "AAPL" not in source
    assert "NVDA" not in source
