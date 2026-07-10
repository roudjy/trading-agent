from __future__ import annotations

from packages.qre_research import governed_candidate_batch as batch
from packages.qre_research import hypothesis_generator_governance as governance
from packages.qre_research import rejection_reasons as reasons
from packages.qre_research import research_throughput_controls as throughput


def _proposal(
    hypothesis_id: str,
    *,
    gain: float = 50.0,
    source_id: str = "source_a",
    behavior_family: str = "trend",
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


def _candidate(hypothesis_id: str, **kwargs: object) -> throughput.ThroughputCandidate:
    return throughput.ThroughputCandidate(
        proposal=_proposal(hypothesis_id, **kwargs),
        timeframe="1h",
    )


def _budget(**kwargs: int) -> throughput.ThroughputBudget:
    values = {
        "candidate_budget": 3,
        "campaign_budget": 3,
        "per_source_budget": 3,
        "per_behavior_family_budget": 3,
        "per_timeframe_budget": 3,
    }
    values.update(kwargs)
    return throughput.ThroughputBudget(**values)


def test_batch_produces_plan_admitted_blocked_and_dry_run_results() -> None:
    result = batch.run_governed_candidate_batch(
        "batch-1",
        (
            _candidate("eligible", gain=90),
            throughput.ThroughputCandidate(
                proposal=_proposal("blocked", gain=80),
                timeframe="1h",
                duplicate_active_path=True,
            ),
        ),
        budget=_budget(),
    )

    assert len(result.plan) == 2
    assert result.admitted_candidates == ("eligible",)
    assert result.blocked_candidates[0]["hypothesis_id"] == "blocked"
    assert result.dry_run_results[0].hypothesis_id == "eligible"
    assert result.evidence_summaries[0]["complete"] is True
    assert result.next_action_queue[0]["next_action"] == "wait_for_active_path_disposition"


def test_batch_enforces_budget_and_quality_gates() -> None:
    result = batch.run_governed_candidate_batch(
        "batch-budget",
        (
            _candidate("first", gain=100),
            throughput.ThroughputCandidate(
                proposal=_proposal("bad_data", gain=90),
                timeframe="4h",
                data_quality_admitted=False,
            ),
            _candidate("over_budget", gain=80),
        ),
        budget=_budget(candidate_budget=1, campaign_budget=1),
    )

    by_id = {record.hypothesis_id: record for record in result.plan}

    assert by_id["first"].decision == "admit"
    assert set(by_id["bad_data"].reason_codes) == {
        "campaign_budget_exceeded",
        "data_quality_failed",
    }
    assert by_id["over_budget"].reason_codes == ("campaign_budget_exceeded",)
    assert result.admitted_candidates == ("first",)


def test_batch_carries_rejection_memory_and_feedback_records() -> None:
    duplicate = reasons.make_reason_record(
        code="duplicate_hypothesis",
        stage="Hypothesis",
        object_id="dup",
        explanation="Equivalent rejected hypothesis already exists.",
        next_action="wait_for_changed_condition",
        terminal=True,
    )

    result = batch.run_governed_candidate_batch(
        "batch-memory",
        (_candidate("dup"), _candidate("fresh")),
        budget=_budget(),
        rejection_records=(duplicate,),
    )

    assert result.admitted_candidates == ("fresh",)
    assert result.blocked_candidates[0]["reason_codes"] == ["duplicate_hypothesis"]
    assert result.memory_feedback_records[0]["research_memory"]["canonical_reason_code"] == "offline_route_verified"


def test_batch_grants_no_execution_or_deployment_authority() -> None:
    result = batch.run_governed_candidate_batch(
        "batch-authority",
        (_candidate("eligible"),),
        budget=_budget(),
    )

    assert result.safety["research_execution"] is False
    assert result.safety["created_production_artifacts"] is False
    assert result.safety["strategy_synthesis_authority"] is False
    assert result.safety["shadow_authority"] is False
    assert result.safety["paper_authority"] is False
    assert result.safety["live_authority"] is False
    assert result.safety["broker_authority"] is False
    assert result.safety["risk_authority"] is False
    assert result.safety["order_authority"] is False
    assert result.safety["capital_allocation_authority"] is False
