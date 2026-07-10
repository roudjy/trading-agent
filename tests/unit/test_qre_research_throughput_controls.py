from __future__ import annotations

from packages.qre_research import hypothesis_generator_governance as governance
from packages.qre_research import rejection_reasons as reasons
from packages.qre_research import research_throughput_controls as throughput


def _proposal(
    hypothesis_id: str,
    *,
    source_id: str = "source_a",
    behavior_family: str = "trend",
    gain: float = 50.0,
    **kwargs: object,
) -> governance.HypothesisProposal:
    return governance.HypothesisProposal(
        hypothesis_id=hypothesis_id,
        mechanism="synthetic trend persistence",
        source_id=source_id,
        behavior_family=behavior_family,
        expected_information_gain=gain,
        **kwargs,
    )


def _candidate(
    hypothesis_id: str,
    *,
    timeframe: str = "1h",
    **kwargs: object,
) -> throughput.ThroughputCandidate:
    return throughput.ThroughputCandidate(
        proposal=_proposal(hypothesis_id, **kwargs),
        timeframe=timeframe,
    )


def _budget(**kwargs: int) -> throughput.ThroughputBudget:
    values = {
        "candidate_budget": 10,
        "campaign_budget": 10,
        "per_source_budget": 10,
        "per_behavior_family_budget": 10,
        "per_timeframe_budget": 10,
    }
    values.update(kwargs)
    return throughput.ThroughputBudget(**values)


def test_admits_only_within_explicit_candidate_and_campaign_budgets() -> None:
    records = throughput.plan_research_throughput(
        (
            _candidate("first", gain=100),
            _candidate("second", gain=90),
        ),
        budget=_budget(candidate_budget=1, campaign_budget=1),
    )

    assert records[0].decision == "admit"
    assert records[1].decision == "blocked"
    assert records[1].reason_codes == ("campaign_budget_exceeded",)
    assert records[1].next_action == "reduce_scope_or_wait_for_budget"


def test_per_source_behavior_family_and_timeframe_budgets_are_enforced() -> None:
    records = throughput.plan_research_throughput(
        (
            _candidate("source_one", gain=100, source_id="same", behavior_family="trend"),
            _candidate("source_two", gain=90, source_id="same", behavior_family="trend"),
            _candidate("timeframe_two", gain=80, source_id="other", behavior_family="carry"),
        ),
        budget=_budget(per_source_budget=1, per_behavior_family_budget=1, per_timeframe_budget=1),
    )

    by_id = {record.hypothesis_id: record for record in records}

    assert by_id["source_one"].decision == "admit"
    assert by_id["source_two"].decision == "blocked"
    assert by_id["source_two"].reason_codes == ("campaign_budget_exceeded",)
    assert by_id["timeframe_two"].decision == "blocked"
    assert by_id["timeframe_two"].reason_codes == ("campaign_budget_exceeded",)


def test_duplicate_and_failure_mode_suppression_blocks_admission() -> None:
    records = throughput.plan_research_throughput(
        (
            throughput.ThroughputCandidate(
                proposal=_proposal("duplicate_active"),
                timeframe="1h",
                duplicate_active_path=True,
            ),
            throughput.ThroughputCandidate(
                proposal=_proposal("repeated_failure"),
                timeframe="4h",
                repeated_failure_mode=True,
            ),
        ),
        budget=_budget(),
    )

    by_id = {record.hypothesis_id: record for record in records}

    assert by_id["duplicate_active"].decision == "blocked"
    assert by_id["duplicate_active"].reason_codes == ("duplicate_active_research_path",)
    assert by_id["duplicate_active"].next_action == "wait_for_active_path_disposition"
    assert by_id["repeated_failure"].decision == "blocked"
    assert by_id["repeated_failure"].reason_codes == ("duplicate_hypothesis",)
    assert by_id["repeated_failure"].next_action == "wait_for_changed_condition"


def test_quality_operator_architecture_and_maturity_blocks_remain_visible() -> None:
    records = throughput.plan_research_throughput(
        (
            throughput.ThroughputCandidate(
                proposal=_proposal("bad_data"),
                timeframe="1h",
                data_quality_admitted=False,
            ),
            throughput.ThroughputCandidate(
                proposal=_proposal("operator", operator_decision_required=True),
                timeframe="4h",
                operator_decision_required=True,
            ),
            throughput.ThroughputCandidate(
                proposal=_proposal("architecture", architecture_gate_passed=False),
                timeframe="1d",
                architecture_gate_passed=False,
            ),
            throughput.ThroughputCandidate(
                proposal=_proposal("maturity", maturity_gate_passed=False),
                timeframe="1w",
                maturity_gate_passed=False,
            ),
        ),
        budget=_budget(),
    )
    by_id = {record.hypothesis_id: record for record in records}

    assert by_id["bad_data"].reason_codes == ("data_quality_failed",)
    assert by_id["operator"].reason_codes == ("operator_decision_required",)
    assert by_id["architecture"].reason_codes == ("architecture_gate_failed",)
    assert by_id["maturity"].reason_codes == ("maturity_gate_failed",)
    assert all(record.decision == "blocked" for record in records)


def test_rejection_memory_blocks_unchanged_terminal_duplicate() -> None:
    duplicate = reasons.make_reason_record(
        code="duplicate_hypothesis",
        stage="Hypothesis",
        object_id="dup",
        explanation="Equivalent rejected hypothesis already exists.",
        next_action="wait_for_changed_condition",
        terminal=True,
    )

    record = throughput.plan_research_throughput(
        (_candidate("dup"),),
        budget=_budget(),
        rejection_records=(duplicate,),
    )[0]

    assert record.decision == "blocked"
    assert record.reason_codes == ("duplicate_hypothesis",)


def test_report_is_read_only_and_authority_free() -> None:
    report = throughput.throughput_report(
        (
            _candidate("eligible"),
            throughput.ThroughputCandidate(
                proposal=_proposal("blocked"),
                timeframe="1h",
                duplicate_active_path=True,
            ),
        ),
        budget=_budget(),
    )

    assert report["report_kind"] == "qre_governed_research_throughput"
    assert report["summary"] == {"admitted": 1, "blocked": 1}
    assert len(report["next_action_queue"]) == 1
    assert report["safety"]["research_execution"] is False
    assert report["safety"]["created_candidates"] is False
    assert report["safety"]["strategy_synthesis_authority"] is False
    assert report["safety"]["shadow_authority"] is False
    assert report["safety"]["paper_authority"] is False
    assert report["safety"]["live_authority"] is False
    assert report["safety"]["broker_authority"] is False
    assert report["safety"]["risk_authority"] is False
    assert report["safety"]["order_authority"] is False
    assert report["safety"]["capital_allocation_authority"] is False
