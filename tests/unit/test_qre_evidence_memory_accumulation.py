from __future__ import annotations

from packages.qre_research import evidence_memory_accumulation as accumulation
from packages.qre_research import governed_candidate_batch as batch
from packages.qre_research import hypothesis_generator_governance as governance
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
    return throughput.ThroughputCandidate(
        proposal=_proposal(hypothesis_id),
        timeframe="1h",
        **kwargs,
    )


def _budget() -> throughput.ThroughputBudget:
    return throughput.ThroughputBudget(3, 3, 3, 3, 3)


def test_accumulation_combines_batch_outcomes_and_lineage() -> None:
    first = batch.run_governed_candidate_batch("batch-1", (_candidate("a"),), budget=_budget())
    second = batch.run_governed_candidate_batch("batch-2", (_candidate("b"),), budget=_budget())

    result = accumulation.accumulate_evidence_memory((first, second))

    assert result.run_count == 2
    assert result.tested_hypotheses == ("a", "b")
    assert result.lineage == {"a": ("batch-1",), "b": ("batch-2",)}
    assert result.disposition_trends == {"accepted_for_research_memory": 2}


def test_accumulation_preserves_missing_vs_negative_evidence() -> None:
    missing = reasons.make_reason_record(
        code="evidence_incomplete",
        stage="EvidencePack",
        object_id="x",
        explanation="Evidence incomplete.",
        next_action="collect_missing_evidence",
    )
    negative = reasons.make_reason_record(
        code="data_quality_failed",
        stage="SourceSnapshot",
        object_id="y",
        explanation="Data quality failed.",
        next_action="repair_source_data_quality",
    )
    run = batch.run_governed_candidate_batch(
        "batch-reasons",
        (_candidate("x"), _candidate("y")),
        budget=_budget(),
        rejection_records=(missing, negative),
    )

    result = accumulation.accumulate_evidence_memory((run,))

    assert "evidence_incomplete" in result.missing_evidence_reasons
    assert "data_quality_failed" in result.negative_evidence_reasons


def test_accumulation_tracks_repeated_failures_and_suppression() -> None:
    duplicate = reasons.make_reason_record(
        code="duplicate_hypothesis",
        stage="Hypothesis",
        object_id="dup",
        explanation="Duplicate hypothesis.",
        next_action="wait_for_changed_condition",
        terminal=True,
    )
    first = batch.run_governed_candidate_batch("batch-1", (_candidate("dup"),), budget=_budget(), rejection_records=(duplicate,))
    second = batch.run_governed_candidate_batch("batch-2", (_candidate("dup"),), budget=_budget(), rejection_records=(duplicate,))

    result = accumulation.accumulate_evidence_memory((first, second))

    assert result.reason_distribution["duplicate_hypothesis"] == 2
    assert result.repeated_failure_modes == ("duplicate_hypothesis",)
    assert result.suppress_retest == ("dup", "dup")
    assert result.next_action_queue[0]["next_action"] == "wait_for_changed_condition"


def test_accumulation_grants_no_execution_or_deployment_authority() -> None:
    run = batch.run_governed_candidate_batch("batch-safe", (_candidate("safe"),), budget=_budget())
    result = accumulation.accumulate_evidence_memory((run,))

    assert result.safety["created_production_artifacts"] is False
    assert result.safety["strategy_synthesis_authority"] is False
    assert result.safety["shadow_authority"] is False
    assert result.safety["paper_authority"] is False
    assert result.safety["live_authority"] is False
    assert result.safety["broker_authority"] is False
    assert result.safety["risk_authority"] is False
    assert result.safety["order_authority"] is False
    assert result.safety["capital_allocation_authority"] is False
