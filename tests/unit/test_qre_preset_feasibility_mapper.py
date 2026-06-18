from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from research.qre_preset_feasibility_mapper import (
    compute_feasibility_hash,
    evaluate_preset_feasibility_for_hypothesis,
    list_feasible_presets_for_behavior,
    validate_feasibility_result,
)


_T = datetime(2026, 6, 18, 8, 0, 0, tzinfo=timezone.utc)


def _hypothesis(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "hypothesis_id": "hyp-trend-001",
        "behavior_id": "trend_continuation",
        "title": "Trend continuation feasibility check",
        "description": "Context-only feasibility mapping for a continuation hypothesis.",
        "timeframe": "1d",
        "expected_mechanism": "Trend resumes after bounded consolidation.",
        "falsification_criteria": ("Fails bounded OOS holdout",),
        "required_data_capabilities": ("time_series_ohlcv", "regime_context", "cost_model"),
        "required_evidence_types": ("screening_evidence", "oos_evidence", "lineage_evidence"),
        "status": "research_ready",
        "created_at_utc": _T,
        "source": "unit-test",
        "reason_record_refs": (),
        "symbols": ("AAA", "BBB"),
    }
    payload.update(overrides)
    return payload


def test_known_behavior_maps_to_expected_generic_presets() -> None:
    result = list_feasible_presets_for_behavior("trend_continuation")
    preset_timeframes = [(item["preset_id"], item["timeframe"]) for item in result["feasible_mappings"]]
    assert preset_timeframes == [
        ("trend_continuation_daily_v1", "1d"),
        ("trend_pullback_continuation_daily_v1", "1d"),
    ]
    assert result["blocked_mappings"] == []


def test_unknown_behavior_fails_closed() -> None:
    result = list_feasible_presets_for_behavior("unknown_behavior")
    assert result["feasible_mappings"] == []
    assert result["blocked_mappings"][0]["feasibility_status"] == "blocked_unknown_behavior"
    assert result["blocker_reasons"] == ["unknown_behavior_id"]


def test_mapper_output_is_deterministic() -> None:
    result_1 = list_feasible_presets_for_behavior("relative_strength")
    result_2 = list_feasible_presets_for_behavior("relative_strength")
    assert result_1 == result_2
    assert compute_feasibility_hash(result_1) == compute_feasibility_hash(result_2)


def test_mapper_output_is_non_authoritative() -> None:
    result = list_feasible_presets_for_behavior("relative_strength")
    assert result["non_authoritative"] is True
    assert result["evidence_authority"] == "context_only"


def test_mapper_cannot_authorize_execution_or_clear_or_promote() -> None:
    result = list_feasible_presets_for_behavior("post_shock_stabilization")
    assert result["can_authorize_execution"] is False
    assert result["can_clear_evidence_blockers"] is False
    assert result["can_promote_candidate"] is False
    for item in result["feasible_mappings"]:
        assert item["can_authorize_execution"] is False
        assert item["can_clear_evidence_blockers"] is False
        assert item["can_promote_candidate"] is False


def test_mapper_is_symbol_agnostic() -> None:
    result_1 = evaluate_preset_feasibility_for_hypothesis(_hypothesis(symbols=("AAA", "BBB")))
    result_2 = evaluate_preset_feasibility_for_hypothesis(_hypothesis(symbols=("CCC", "DDD")))
    assert result_1 == result_2


def test_core_mapper_logic_has_no_aapl_or_nvda_hardcoding() -> None:
    source = Path("research/qre_preset_feasibility_mapper.py").read_text(encoding="utf-8")
    assert "AAPL" not in source
    assert "NVDA" not in source


def test_hypothesis_with_missing_required_fields_fails_closed() -> None:
    result = evaluate_preset_feasibility_for_hypothesis(
        _hypothesis(title="", falsification_criteria=())
    )
    assert result["feasible_mappings"] == []
    assert result["blocked_mappings"][0]["feasibility_status"] == "blocked_missing_hypothesis_fields"
    assert "missing_hypothesis_field:title" in result["blocker_reasons"]
    assert "missing_hypothesis_field:falsification_criteria" in result["blocker_reasons"]


def test_valid_hypothesis_produces_feasible_mapping() -> None:
    result = evaluate_preset_feasibility_for_hypothesis(_hypothesis())
    statuses = {item["feasibility_status"] for item in result["feasible_mappings"]}
    assert statuses == {"feasible"}
    assert result["blocked_mappings"] == []


def test_blocked_statuses_preserve_reason_codes() -> None:
    result = evaluate_preset_feasibility_for_hypothesis(
        _hypothesis(required_data_capabilities=("time_series_ohlcv",))
    )
    assert result["feasible_mappings"] == []
    assert {
        item["feasibility_status"] for item in result["blocked_mappings"]
    } == {"blocked_missing_data_capability"}
    assert "missing_data_capability:regime_context" in result["blocker_reasons"]
    assert "missing_data_capability:cost_model" in result["blocker_reasons"]


def test_evidence_complete_hypothesis_is_blocked_not_evidence_authoritative() -> None:
    result = evaluate_preset_feasibility_for_hypothesis(
        _hypothesis(status="evidence_complete", reason_record_refs=("rr-1",))
    )
    assert result["feasible_mappings"] == []
    assert {
        item["feasibility_status"] for item in result["blocked_mappings"]
    } == {"blocked_not_evidence_authoritative"}
    assert "not_evidence_authoritative" in result["blocker_reasons"]


def test_validate_feasibility_result_accepts_valid_payload() -> None:
    result = evaluate_preset_feasibility_for_hypothesis(_hypothesis())
    validation = validate_feasibility_result(result)
    assert validation["valid"] is True
    assert validation["rejection_reasons"] == []


def test_validate_feasibility_result_rejects_authoritative_claims() -> None:
    result = evaluate_preset_feasibility_for_hypothesis(_hypothesis())
    result["can_authorize_execution"] = True
    validation = validate_feasibility_result(result)
    assert validation["valid"] is False
    assert "can_authorize_execution_must_be_false" in validation["rejection_reasons"]
