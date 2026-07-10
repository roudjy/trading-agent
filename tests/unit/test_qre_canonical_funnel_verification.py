from __future__ import annotations

from dataclasses import replace

from packages.qre_research import canonical_funnel_verification as verification


def test_canonical_funnel_order_matches_required_route() -> None:
    assert verification.canonical_funnel_order() == (
        "Hypothesis",
        "ResearchInputContract",
        "CandidateSpec",
        "StrategySpec",
        "StrategyIR",
        "PresetSpec",
        "CampaignSpec",
        "CampaignRun",
        "ScreeningResult",
        "EvidencePack",
        "EvidenceLedger",
        "Disposition",
        "FeedbackRecord",
        "LessonMemory",
        "ResearchMemory",
        "NextHypothesisBatch",
    )


def test_current_canonical_funnel_verification_passes() -> None:
    assert verification.verify_canonical_funnel() == []


def test_each_stage_consumes_only_prior_stage_output() -> None:
    stages = list(verification.CANONICAL_FUNNEL_RULES)
    stages[2] = replace(stages[2], consumes="Hypothesis")

    assert "stage_order_break:candidate_materialization:strategy_specification" in verification.verify_stage_order(tuple(stages))


def test_each_stage_emits_only_declared_next_object() -> None:
    stages = list(verification.CANONICAL_FUNNEL_RULES)
    stages[1] = replace(stages[1], emits="EvidencePack")

    errors = verification.verify_stage_order(tuple(stages))

    assert "stage_order_break:candidate_materialization:strategy_specification" in errors


def test_provider_specific_details_do_not_leak_into_canonical_objects() -> None:
    trace = list(verification.synthetic_fixture_trace())
    candidate_index = verification.canonical_funnel_order().index("CandidateSpec")
    trace[candidate_index] = replace(
        trace[candidate_index],
        fields={**trace[candidate_index].fields, "provider_id": "tiingo"},
    )

    assert "provider_leakage:CandidateSpec:provider_id" in verification.verify_fixture_trace(tuple(trace))


def test_fixture_objects_remain_fixture_only() -> None:
    trace = list(verification.synthetic_fixture_trace())
    trace[0] = replace(trace[0], fixture_only=False)

    assert (
        f"fixture_claims_empirical_evidence:Hypothesis:{trace[0].object_id}"
        in verification.verify_fixture_trace(tuple(trace))
    )


def test_next_hypothesis_batch_is_read_model_not_canonical_owner() -> None:
    final_stage = verification.CANONICAL_FUNNEL_RULES[-1]

    assert final_stage.stage_id == "next_hypothesis_batch"
    assert final_stage.consumes == "ResearchMemory"
    assert final_stage.emits == "NextHypothesisBatch"
    assert final_stage.output_kind == "read_model"


def test_architecture_boundaries_remain_enforced() -> None:
    assert verification.verify_architecture_boundaries() == []
