from __future__ import annotations

from packages.qre_research import evidence_memory_accumulation as accumulation
from packages.qre_research import governed_candidate_batch as batch
from packages.qre_research import hypothesis_generator_governance as governance
from packages.qre_research import operator_trust_multirun_report as report
from packages.qre_research import rejection_reasons as reasons
from packages.qre_research import research_throughput_controls as throughput


def _proposal(hypothesis_id: str, gain: float = 50.0) -> governance.HypothesisProposal:
    return governance.HypothesisProposal(
        hypothesis_id=hypothesis_id,
        mechanism="synthetic trend persistence",
        source_id="source_fixture",
        behavior_family="trend",
        expected_information_gain=gain,
    )


def _candidate(hypothesis_id: str, **kwargs: object) -> throughput.ThroughputCandidate:
    return throughput.ThroughputCandidate(proposal=_proposal(hypothesis_id), timeframe="1h", **kwargs)


def _budget() -> throughput.ThroughputBudget:
    return throughput.ThroughputBudget(3, 3, 3, 3, 3)


def _sample_report() -> report.OperatorTrustMultirunReport:
    duplicate = reasons.make_reason_record(
        code="duplicate_hypothesis",
        stage="Hypothesis",
        object_id="dup",
        explanation="Duplicate hypothesis.",
        next_action="wait_for_changed_condition",
        terminal=True,
    )
    gated = batch.run_governed_candidate_batch(
        "batch-1",
        (
            _candidate("admitted"),
            _candidate("dup"),
            throughput.ThroughputCandidate(
                proposal=_proposal("operator"),
                timeframe="1h",
                operator_decision_required=True,
            ),
        ),
        budget=_budget(),
        rejection_records=(duplicate,),
    )
    accumulated = accumulation.accumulate_evidence_memory((gated,))
    return report.build_operator_trust_multirun_report(accumulated)


def test_report_answers_what_was_tested_and_what_failed() -> None:
    result = _sample_report()

    assert result.tested_hypotheses == ("admitted", "dup", "operator")
    assert result.admitted_count == 1
    assert result.blocked_count == 2
    assert result.rejection_reason_distribution["duplicate_hypothesis"] == 1
    assert result.operator_decision_blockers == 1


def test_report_explains_missing_negative_memory_and_retest_guidance() -> None:
    result = _sample_report()

    assert result.memory_feedback_summary["offline_route_verified"] == 1
    assert result.do_not_retest == ("dup",)
    assert "admitted" in result.worth_testing_next
    assert result.next_action_queue[0]["next_action"] == "wait_for_changed_condition"


def test_report_surfaces_gate_blockers_and_next_actions() -> None:
    result = _sample_report()

    assert result.gate_blockers == {"operator_decision_required": 1}
    assert result.evidence_completeness == {"complete": 1, "incomplete_or_blocked": 2}
    assert result.missing_vs_negative_evidence["missing"] == ("duplicate_hypothesis",)


def test_report_makes_no_readiness_or_execution_authority_claims() -> None:
    result = _sample_report()

    assert result.authority_statement["strategy_synthesis_execution_authority"] is False
    assert result.authority_statement["shadow_authority"] is False
    assert result.authority_statement["paper_authority"] is False
    assert result.authority_statement["live_authority"] is False
    assert result.authority_statement["broker_authority"] is False
    assert result.authority_statement["risk_authority"] is False
    assert result.authority_statement["order_authority"] is False
    assert result.authority_statement["capital_allocation_authority"] is False
    assert result.authority_statement["paper_ready_claim"] is False
    assert result.authority_statement["shadow_ready_claim"] is False
    assert result.authority_statement["live_ready_claim"] is False
