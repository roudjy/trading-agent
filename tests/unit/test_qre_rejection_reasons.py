from __future__ import annotations

import pytest

from packages.qre_research import rejection_reasons as reasons


def test_required_rejection_taxonomy_is_present() -> None:
    assert set(reasons.CANONICAL_REASON_CODES) >= {
        "insufficient_data",
        "insufficient_trades",
        "data_quality_failed",
        "source_identity_unresolved",
        "provider_scope_violation",
        "duplicate_hypothesis",
        "duplicate_active_research_path",
        "missing_falsification_criteria",
        "missing_expected_observables",
        "primitive_missing",
        "strategy_mapping_failed",
        "preset_bounds_invalid",
        "campaign_budget_exceeded",
        "null_model_not_beaten",
        "cost_model_failed",
        "oos_not_available",
        "screening_criteria_not_met",
        "evidence_incomplete",
        "maturity_gate_failed",
        "architecture_gate_failed",
        "operator_decision_required",
        "policy_denied",
    }
    assert reasons.validate_reason_taxonomy() == []


def test_reason_record_contains_required_machine_readable_fields() -> None:
    record = reasons.make_reason_record(
        code="missing_falsification_criteria",
        stage="Hypothesis",
        object_id="hyp_fixture",
        explanation="Falsification criteria are required before admission.",
        next_action="add_falsification_criteria",
    )

    assert record.as_dict() == {
        "code": "missing_falsification_criteria",
        "stage": "Hypothesis",
        "object_id": "hyp_fixture",
        "severity": "blocking",
        "explanation": "Falsification criteria are required before admission.",
        "next_action": "add_falsification_criteria",
        "evidence_polarity": "missing_evidence",
        "terminal": False,
    }


def test_reason_codes_are_provider_agnostic() -> None:
    with pytest.raises(ValueError, match="provider_specific_reason_leakage:tiingo"):
        reasons.make_reason_record(
            code="insufficient_data",
            stage="SourceSnapshot",
            object_id="source_fixture",
            explanation="Tiingo rows are missing.",
            next_action="collect_provider_neutral_source_coverage",
        )


def test_missing_evidence_is_distinguished_from_negative_evidence() -> None:
    assert reasons.reason_polarity("evidence_incomplete") == "missing_evidence"
    assert reasons.reason_polarity("null_model_not_beaten") == "negative_evidence"


def test_governance_gate_failures_are_visible_as_rejections() -> None:
    architecture = reasons.make_reason_record(
        code="architecture_gate_failed",
        stage="CandidateSpec",
        object_id="candidate_fixture",
        explanation="Closed-world audit rejected an unregistered producer.",
        next_action="register_or_remove_parallel_funnel",
        terminal=True,
    )
    maturity = reasons.make_reason_record(
        code="maturity_gate_failed",
        stage="EvidencePack",
        object_id="evidence_fixture",
        explanation="Operator-trusted claim lacks required lineage.",
        next_action="add_lineage_or_downgrade_claim",
    )

    assert architecture.evidence_polarity == "governance_rejection"
    assert maturity.evidence_polarity == "governance_rejection"
    assert architecture.terminal is True


def test_reason_records_feed_feedback_lesson_and_research_memory() -> None:
    record = reasons.make_reason_record(
        code="duplicate_active_research_path",
        stage="Hypothesis",
        object_id="hyp_duplicate",
        explanation="Equivalent active research path already exists.",
        next_action="wait_for_changed_condition",
        terminal=True,
    )

    payload = reasons.feedback_memory_payload(record)

    assert payload["feedback_record"]["code"] == "duplicate_active_research_path"
    assert payload["lesson_memory"]["failure_mode"] == "missing_evidence"
    assert payload["research_memory"]["requires_changed_condition"] is True
    assert payload["research_memory"]["suppress_if_unchanged"] is True


def test_invalid_reason_record_reports_all_required_field_errors() -> None:
    record = reasons.ReasonRecord(
        code="not_real",
        stage="",
        object_id="",
        severity="blocking",
        explanation="",
        next_action="",
        evidence_polarity="missing_evidence",
    )

    assert reasons.validate_reason_record(record) == [
        "unknown_reason_code:not_real",
        "missing_stage",
        "missing_object_id",
        "missing_explanation",
        "missing_next_action",
    ]
