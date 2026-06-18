from __future__ import annotations

from pathlib import Path

from research.qre_controlled_validation_adapter import (
    build_controlled_validation_adapter_result,
    compute_adapter_hash,
    validate_adapter_result,
)


def _request(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "request_id": "req-controlled-validation-001",
        "symbols": ("AAA", "BBB"),
        "preset_id": "trend_pullback_continuation_daily_v1",
        "timeframe": "1d",
        "approval_ref": "approval/operator/bounded-validation-001",
        "required_artifact_types": ("structured_lineage", "structured_oos"),
        "allowed_output_paths": (
            "logs/qre_controlled_validation_adapter/latest.json",
            "artifacts/qre_controlled_validation/accepted.json",
        ),
        "forbidden_capabilities": (),
        "created_at_utc": "2026-06-18T00:00:00Z",
        "source": "unit-test",
    }
    payload.update(overrides)
    return payload


def _structured_source(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "source_type": "structured_controlled_validation",
        "source_authority": "structured_source",
        "source_ref": "artifacts/qre_controlled_validation/source-001.json",
        "lineage_records": (
            {
                "candidate_id": "cand-001",
                "campaign_id": "camp-001",
                "generation_run_id": "gen-001",
                "reason_record_refs": ("rr-lineage-001",),
            },
        ),
        "oos_records": (
            {
                "candidate_id": "cand-001",
                "oos_window": {"start": "2025-01-01", "end": "2025-06-30"},
                "oos_metric_fields": {"oos_trade_count": 24, "oos_return_pct": 3.1},
                "cost_slippage_assumption_refs": ("cost-model-001",),
                "reason_record_refs": ("rr-oos-001",),
            },
        ),
    }
    payload.update(overrides)
    return payload


def test_invalid_bounded_request_fails_closed() -> None:
    result = build_controlled_validation_adapter_result(
        _request(request_id=""),
        controlled_validation_source=_structured_source(),
    )
    assert result["adapter_status"] == "blocked_invalid_bounded_request"
    assert result["accepted_lineage_count"] == 0
    assert result["accepted_oos_count"] == 0
    assert result["can_clear_blockers"] is False


def test_missing_approval_ref_fails_closed() -> None:
    result = build_controlled_validation_adapter_result(
        _request(approval_ref=""),
        controlled_validation_source=_structured_source(),
    )
    assert result["adapter_status"] == "blocked_missing_approval_ref"
    assert result["rejected_reasons"] == ["missing_approval_ref"]


def test_forbidden_capabilities_fail_closed() -> None:
    result = build_controlled_validation_adapter_result(
        _request(forbidden_capabilities=("strategy_synthesis",)),
        controlled_validation_source=_structured_source(),
    )
    assert result["adapter_status"] == "blocked_forbidden_capability"
    assert result["can_clear_blockers"] is False


def test_disallowed_output_paths_fail_closed() -> None:
    result = build_controlled_validation_adapter_result(
        _request(allowed_output_paths=("/tmp/out.json",)),
        controlled_validation_source=_structured_source(),
    )
    assert result["adapter_status"] == "blocked_output_path_not_allowlisted"


def test_no_safe_controlled_validation_source_returns_no_accepted_evidence() -> None:
    result = build_controlled_validation_adapter_result(_request())
    assert result["adapter_status"] == "no_safe_controlled_validation_source"
    assert result["accepted_lineage_count"] == 0
    assert result["accepted_oos_count"] == 0
    assert result["can_clear_blockers"] is False


def test_stdout_only_source_rejected() -> None:
    result = build_controlled_validation_adapter_result(
        _request(),
        controlled_validation_source={"source_type": "stdout_only", "source_ref": "stdout"},
    )
    assert result["adapter_status"] == "rejected_stdout_only_source"


def test_context_only_source_rejected() -> None:
    result = build_controlled_validation_adapter_result(
        _request(),
        controlled_validation_source={"source_type": "context_only", "source_ref": "report"},
    )
    assert result["adapter_status"] == "rejected_context_only_source"


def test_legacy_alias_only_source_rejected() -> None:
    result = build_controlled_validation_adapter_result(
        _request(),
        controlled_validation_source={"source_type": "legacy_alias_only", "source_ref": "alias"},
    )
    assert result["adapter_status"] == "rejected_legacy_alias_only_source"


def test_missing_candidate_or_campaign_generation_ids_rejected_for_lineage_acceptance() -> None:
    result = build_controlled_validation_adapter_result(
        _request(),
        controlled_validation_source=_structured_source(
            lineage_records=(
                {
                    "candidate_id": "",
                    "campaign_id": "",
                    "generation_run_id": "",
                },
            )
        ),
    )
    assert result["adapter_status"] == "blocked_missing_candidate_id"
    assert "missing_candidate_id" in result["rejected_reasons"]
    assert "missing_campaign_or_generation_id" in result["rejected_reasons"]
    assert result["accepted_lineage_count"] == 0


def test_missing_oos_window_metrics_or_cost_refs_rejected_for_oos_acceptance() -> None:
    result = build_controlled_validation_adapter_result(
        _request(),
        controlled_validation_source=_structured_source(
            oos_records=(
                {
                    "candidate_id": "cand-001",
                    "oos_window": {},
                    "oos_metric_fields": {},
                    "cost_slippage_assumption_refs": (),
                },
            )
        ),
    )
    assert result["adapter_status"] == "blocked_missing_oos_window"
    assert "missing_oos_window" in result["rejected_reasons"]
    assert "missing_oos_metrics" in result["rejected_reasons"]
    assert "missing_cost_slippage_refs" in result["rejected_reasons"]
    assert result["accepted_oos_count"] == 0


def test_accepted_structured_source_can_produce_accepted_candidate_artifacts() -> None:
    result = build_controlled_validation_adapter_result(
        _request(),
        controlled_validation_source=_structured_source(),
    )
    assert result["adapter_status"] == "accepted_structured_evidence"
    assert result["accepted_lineage_count"] == 1
    assert result["accepted_oos_count"] == 1
    assert result["lineage_candidate_refs"] == [
        "artifacts/qre_controlled_validation/source-001.json#lineage:cand-001"
    ]
    assert result["oos_candidate_refs"] == [
        "artifacts/qre_controlled_validation/source-001.json#oos:cand-001"
    ]
    assert result["can_clear_blockers"] is True


def test_adapter_never_invents_ids() -> None:
    result = build_controlled_validation_adapter_result(
        _request(),
        controlled_validation_source=_structured_source(
            lineage_records=({"candidate_id": "", "campaign_id": "", "generation_run_id": ""},),
            oos_records=(
                {
                    "candidate_id": "",
                    "oos_window": {"start": "2025-01-01", "end": "2025-06-30"},
                    "oos_metric_fields": {"oos_trade_count": 1},
                    "cost_slippage_assumption_refs": ("cost",),
                },
            ),
        ),
    )
    assert result["lineage_candidates"][0]["candidate_id"] == ""
    assert result["lineage_candidates"][0]["campaign_id"] == ""
    assert result["lineage_candidates"][0]["generation_id"] == ""
    assert result["oos_candidates"][0]["candidate_id"] == ""


def test_adapter_output_deterministic() -> None:
    result_1 = build_controlled_validation_adapter_result(
        _request(),
        controlled_validation_source=_structured_source(),
    )
    result_2 = build_controlled_validation_adapter_result(
        _request(),
        controlled_validation_source=_structured_source(),
    )
    assert result_1 == result_2
    assert compute_adapter_hash(result_1) == compute_adapter_hash(result_2)


def test_adapter_cannot_authorize_strategy_candidate_or_deployment() -> None:
    result = build_controlled_validation_adapter_result(
        _request(),
        controlled_validation_source=_structured_source(),
    )
    assert result["non_authoritative"] is True
    assert result["can_authorize_execution"] is False
    assert result["can_promote_candidate"] is False
    validation = validate_adapter_result(result)
    assert validation["valid"] is True


def test_core_adapter_logic_has_no_aapl_or_nvda_hardcoding() -> None:
    source = Path("research/qre_controlled_validation_adapter.py").read_text(encoding="utf-8")
    assert "AAPL" not in source
    assert "NVDA" not in source
