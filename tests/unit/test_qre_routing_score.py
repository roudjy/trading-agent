from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from research.qre_preset_feasibility_mapper import (
    evaluate_preset_feasibility_for_hypothesis,
)
from research.qre_routing_score import (
    SCORE_COMPONENT_NAMES,
    compute_routing_hash,
    evaluate_routing_score,
    validate_routing_result,
)


_T = datetime(2026, 6, 18, 8, 0, 0, tzinfo=timezone.utc)


def _hypothesis(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "hypothesis_id": "hyp-route-001",
        "behavior_id": "trend_continuation",
        "title": "Trend continuation routing check",
        "description": "Context-only routing scaffold for a continuation hypothesis.",
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


def _context() -> dict[str, object]:
    return {
        "evidence_gap_information": {"missing_evidence_count": 3, "visible_gap_count": 1},
        "blocker_severity": {"max_severity": "high"},
        "source_cache_readiness": {"ready_count": 3, "blocked_count": 1},
        "prior_failure_density": 0.2,
        "expected_information_gain_proxy": 0.8,
        "compute_budget_proxy": 0.3,
        "behavior_diversity_proxy": 0.6,
        "provisional_evidence_visibility_context": {
            "provisional_artifacts_visible": False,
        },
    }


def _routing_result(**overrides: object) -> dict[str, object]:
    hypothesis = _hypothesis()
    feasibility = evaluate_preset_feasibility_for_hypothesis(hypothesis)
    payload: dict[str, object] = {
        "behavior_id": "trend_continuation",
        "hypothesis": hypothesis,
        "preset_feasibility_result": feasibility,
    }
    payload.update(_context())
    payload.update(overrides)
    return evaluate_routing_score(**payload)  # type: ignore[arg-type]


def test_deterministic_scoring() -> None:
    result_1 = _routing_result()
    result_2 = _routing_result()
    assert result_1 == result_2
    assert compute_routing_hash(result_1) == compute_routing_hash(result_2)


def test_unknown_behavior_fails_closed() -> None:
    result = _routing_result(behavior_id="unknown_behavior")
    assert result["routing_status"] == "blocked_unknown_behavior"
    assert result["routing_score"] == 0.0
    assert result["blocked_reasons"] == ["unknown_behavior_id"]


def test_missing_feasibility_fails_closed() -> None:
    result = evaluate_routing_score(
        behavior_id="trend_continuation",
        hypothesis=_hypothesis(),
        preset_feasibility_result=None,
        **_context(),
    )
    assert result["routing_status"] == "blocked_missing_feasibility"
    assert result["recommended_next_action"] == "evaluate_preset_feasibility"
    assert result["blocked_reasons"] == ["missing_preset_feasibility_result"]


def test_missing_hypothesis_fails_closed() -> None:
    result = evaluate_routing_score(
        behavior_id="trend_continuation",
        hypothesis=None,
        hypothesis_ref=None,
        preset_feasibility_result={},
        **_context(),
    )
    assert result["routing_status"] == "blocked_missing_hypothesis"
    assert result["blocked_reasons"] == ["missing_hypothesis_or_ref"]


def test_missing_required_context_fails_closed() -> None:
    hypothesis = _hypothesis()
    feasibility = evaluate_preset_feasibility_for_hypothesis(hypothesis)
    result = evaluate_routing_score(
        behavior_id="trend_continuation",
        hypothesis=hypothesis,
        preset_feasibility_result=feasibility,
    )
    assert result["routing_status"] == "blocked_missing_required_context"
    assert "missing_required_context:evidence_gap_information" in result["blocked_reasons"]


def test_routing_is_non_authoritative() -> None:
    result = _routing_result()
    assert result["non_authoritative"] is True
    assert result["evidence_authority"] == "context_only"


def test_routing_cannot_authorize_execution_clear_or_promote() -> None:
    result = _routing_result()
    assert result["can_authorize_execution"] is False
    assert result["can_clear_evidence_blockers"] is False
    assert result["can_promote_candidate"] is False


def test_core_routing_logic_has_no_aapl_or_nvda_hardcoding() -> None:
    source = Path("research/qre_routing_score.py").read_text(encoding="utf-8")
    assert "AAPL" not in source
    assert "NVDA" not in source


def test_score_components_are_visible_and_stable() -> None:
    result = _routing_result()
    assert tuple(result["score_components"].keys()) == SCORE_COMPONENT_NAMES
    assert result["score_components"] == {
        "evidence_gap_reduction_score": 0.75,
        "source_cache_readiness_score": 0.75,
        "blocker_severity_score": 0.75,
        "information_gain_proxy_score": 0.8,
        "prior_failure_penalty": 0.2,
        "compute_cost_penalty": 0.3,
        "behavior_diversity_score": 0.6,
        "feasibility_score": 1.0,
    }
    assert result["routing_score"] == 0.525


def test_blocked_statuses_preserve_reason_codes() -> None:
    hypothesis = _hypothesis(required_data_capabilities=("time_series_ohlcv",))
    feasibility = evaluate_preset_feasibility_for_hypothesis(hypothesis)
    result = _routing_result(hypothesis=hypothesis, preset_feasibility_result=feasibility)
    assert result["routing_status"] == "blocked_missing_feasibility"
    assert "missing_data_capability:regime_context" in result["blocked_reasons"]
    assert "missing_data_capability:cost_model" in result["blocked_reasons"]


def test_provisional_visibility_context_marks_result_provisional() -> None:
    context = _context()
    context["provisional_evidence_visibility_context"] = {
        "provisional_artifacts_visible": True,
    }
    result = _routing_result(**context)
    assert result["routing_status"] == "provisional"
    assert "provisional_artifacts_visible_context_only" in result["blocked_reasons"]


def test_validate_routing_result_accepts_valid_payload() -> None:
    result = _routing_result()
    validation = validate_routing_result(result)
    assert validation["valid"] is True
    assert validation["rejection_reasons"] == []


def test_validate_routing_result_rejects_authoritative_claims() -> None:
    result = _routing_result()
    result["can_promote_candidate"] = True
    validation = validate_routing_result(result)
    assert validation["valid"] is False
    assert "can_promote_candidate_must_be_false" in validation["rejection_reasons"]
