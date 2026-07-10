from __future__ import annotations

from packages.qre_research import hypothesis_generator_governance as governance
from packages.qre_research import rejection_reasons as reasons


def _proposal(
    hypothesis_id: str,
    *,
    gain: float = 50.0,
    **kwargs: object,
) -> governance.HypothesisProposal:
    return governance.HypothesisProposal(
        hypothesis_id=hypothesis_id,
        mechanism="synthetic trend persistence",
        source_id="source_fixture",
        behavior_family="trend",
        expected_information_gain=gain,
        **kwargs,
    )


def test_prioritization_prefers_explainable_eligible_hypotheses() -> None:
    records = governance.prioritize_hypotheses(
        (_proposal("low", gain=10), _proposal("high", gain=90)),
        candidate_budget=2,
    )

    assert [record.hypothesis_id for record in records] == ["high", "low"]
    assert all(record.decision == "prioritize" for record in records)
    assert records[0].rationale.startswith("eligible:")


def test_duplicate_rejected_idea_requires_changed_condition() -> None:
    duplicate = reasons.make_reason_record(
        code="duplicate_hypothesis",
        stage="Hypothesis",
        object_id="dup",
        explanation="Equivalent rejected hypothesis already exists.",
        next_action="wait_for_changed_condition",
        terminal=True,
    )

    record = governance.prioritize_hypotheses(
        (_proposal("dup"),),
        rejection_records=(duplicate,),
        candidate_budget=1,
    )[0]

    assert record.decision == "blocked"
    assert record.reason_codes == ("duplicate_hypothesis",)
    assert record.next_action == "wait_for_changed_condition"


def test_data_quality_and_source_identity_blocks_are_not_promoted() -> None:
    records = governance.prioritize_hypotheses(
        (
            _proposal("bad_data", data_quality_ready=False),
            _proposal("bad_identity", source_identity_resolved=False),
        ),
        candidate_budget=2,
    )

    assert [record.decision for record in records] == ["blocked", "blocked"]
    assert records[0].reason_codes == ("data_quality_failed",)
    assert records[1].reason_codes == ("source_identity_unresolved",)


def test_operator_architecture_and_maturity_blocks_are_visible() -> None:
    records = governance.prioritize_hypotheses(
        (
            _proposal("operator", operator_decision_required=True),
            _proposal("architecture", architecture_gate_passed=False),
            _proposal("maturity", maturity_gate_passed=False),
        ),
        candidate_budget=3,
    )
    by_id = {record.hypothesis_id: record for record in records}

    assert by_id["operator"].reason_codes == ("operator_decision_required",)
    assert by_id["architecture"].reason_codes == ("architecture_gate_failed",)
    assert by_id["maturity"].reason_codes == ("maturity_gate_failed",)
    assert all(record.decision == "blocked" for record in records)


def test_budget_constraints_block_without_increasing_throughput() -> None:
    records = governance.prioritize_hypotheses(
        (
            _proposal("first", gain=100, budget_cost=1),
            _proposal("second", gain=90, budget_cost=1),
        ),
        candidate_budget=1,
    )

    assert records[0].decision == "prioritize"
    assert records[1].decision == "blocked"
    assert records[1].reason_codes == ("campaign_budget_exceeded",)


def test_rejection_reasons_downgrade_repeated_failure_modes() -> None:
    missing_oos = reasons.make_reason_record(
        code="oos_not_available",
        stage="EvidencePack",
        object_id="repeat",
        explanation="OOS evidence is not available.",
        next_action="collect_oos_evidence",
    )

    record = governance.prioritize_hypotheses(
        (_proposal("repeat", gain=50),),
        rejection_records=(missing_oos,),
        candidate_budget=1,
    )[0]

    assert record.decision == "prioritize"
    assert record.priority_score == 40.0
    assert record.next_action == "collect_missing_evidence_or_update_memory"


def test_prioritization_report_is_auditable_and_does_not_increase_throughput() -> None:
    report = governance.prioritization_report(
        (_proposal("eligible"), _proposal("blocked", data_quality_ready=False)),
        candidate_budget=1,
    )

    assert report["report_kind"] == "qre_hypothesis_generator_governance"
    assert report["summary"] == {"prioritized": 1, "blocked": 1}
    assert report["safety"]["throughput_increased"] is False
    assert report["safety"]["strategy_synthesis_authority"] is False
