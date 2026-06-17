from __future__ import annotations

from datetime import datetime, timezone

from research.qre_hypothesis_model import (
    Hypothesis,
    compute_hypothesis_scope_hash,
    validate_hypothesis,
)


_T = datetime(2026, 6, 17, 12, 0, 0, tzinfo=timezone.utc)


def _hypothesis(**overrides: object) -> Hypothesis:
    base = {
        "hypothesis_id": "qre_hypothesis_v1",
        "behavior_id": "trend_continuation",
        "title": "Trend continuation hypothesis",
        "description": "A bounded continuation setup for research validation.",
        "universe_ref": "equity_us_largecap",
        "universe_description": "US large-cap equity universe",
        "symbols": ("AAPL", "NVDA"),
        "preset_id": "trend_pullback_continuation_daily_v1",
        "timeframe": "1d",
        "expected_mechanism": "Continuation after bounded pullback resolves.",
        "expected_observables": ("trend_alignment", "breakout_follow_through"),
        "falsification_criteria": ("Fails OOS on bounded holdout",),
        "required_evidence_types": ("screening", "lineage"),
        "required_data_capabilities": ("time_series_ohlcv", "cost_model"),
        "known_risks": ("late_entry",),
        "status": "draft",
        "created_at_utc": _T,
        "source": "unit-test",
        "reason_record_refs": ("rr-1",),
        "scope_hash": "",
    }
    base.update(overrides)
    return Hypothesis(**base)


def test_valid_draft_hypothesis_validates() -> None:
    hyp = _hypothesis()
    result = validate_hypothesis(hyp)
    assert result.valid is True
    assert result.status == "draft"
    assert result.strategy_authority is False
    assert result.candidate_authority is False
    assert result.deployment_authority is False


def test_research_ready_requires_falsification_criteria() -> None:
    hyp = _hypothesis(status="research_ready", falsification_criteria=())
    result = validate_hypothesis(hyp)
    assert result.valid is False
    assert "missing_falsification_criteria" in result.rejection_reasons


def test_evidence_complete_requires_accepted_evidence_refs() -> None:
    hyp = _hypothesis(status="evidence_complete", reason_record_refs=())
    result = validate_hypothesis(hyp)
    assert result.valid is False
    assert "missing_accepted_evidence_refs" in result.rejection_reasons


def test_scope_hash_is_deterministic() -> None:
    hyp_1 = _hypothesis()
    hyp_2 = _hypothesis()
    assert compute_hypothesis_scope_hash(hyp_1) == compute_hypothesis_scope_hash(hyp_2)
    assert validate_hypothesis(hyp_1).scope_hash == validate_hypothesis(hyp_2).scope_hash


def test_hypothesis_is_symbol_agnostic() -> None:
    hyp = _hypothesis(symbols=("AAPL", "NVDA"))
    result = validate_hypothesis(hyp)
    assert result.valid is True
    assert hyp.symbols == ("AAPL", "NVDA")
    assert hyp.behavior_id == "trend_continuation"


def test_unknown_behavior_id_fails_closed_by_default() -> None:
    hyp = _hypothesis(behavior_id="unknown_behavior")
    result = validate_hypothesis(hyp)
    assert result.valid is False
    assert "unknown_behavior_id" in result.rejection_reasons


def test_unknown_behavior_id_can_be_marked_provisional_without_authority() -> None:
    hyp = _hypothesis(
        behavior_id="provisional_behavior",
        status="draft",
        reason_record_refs=("rr-1",),
    )
    result = validate_hypothesis(hyp, provisional_behavior_ids=("provisional_behavior",))
    assert result.valid is True
    assert result.execution_authoritative is False
    assert result.strategy_authority is False
    assert result.candidate_authority is False
    assert result.deployment_authority is False


def test_hypothesis_does_not_authorize_strategy_candidate_or_deployment() -> None:
    hyp = _hypothesis(status="research_ready")
    result = validate_hypothesis(hyp)
    assert result.valid is True
    assert result.execution_authoritative is False
    assert result.strategy_authority is False
    assert result.candidate_authority is False
    assert result.deployment_authority is False

