from __future__ import annotations

from pathlib import Path

from packages.qre_research import hypothesis_generator_governance as governance
from packages.qre_research import offline_research_dry_run as dry_run
from packages.qre_research import rejection_reasons as reasons
from packages.qre_research import research_throughput_controls as throughput

REPO_ROOT = Path(__file__).resolve().parents[2]
FROZEN_OUTPUTS = (
    "research/research_latest.json",
    "research/strategy_matrix.csv",
)


def _proposal(hypothesis_id: str, **kwargs: object) -> governance.HypothesisProposal:
    return governance.HypothesisProposal(
        hypothesis_id=hypothesis_id,
        mechanism="synthetic trend persistence",
        source_id="source_fixture",
        behavior_family="trend",
        expected_information_gain=50.0,
        **kwargs,
    )


def _candidate(hypothesis_id: str, **kwargs: object) -> throughput.ThroughputCandidate:
    return throughput.ThroughputCandidate(
        proposal=_proposal(hypothesis_id),
        timeframe="1h",
        **kwargs,
    )


def _budget() -> throughput.ThroughputBudget:
    return throughput.ThroughputBudget(
        candidate_budget=1,
        campaign_budget=1,
        per_source_budget=1,
        per_behavior_family_budget=1,
        per_timeframe_budget=1,
    )


def test_dry_run_follows_canonical_stage_order_and_records_every_stage() -> None:
    result = dry_run.run_offline_dry_run(_candidate("route_ok"), budget=_budget())

    assert tuple(record.stage for record in result.stage_records) == dry_run.DRY_RUN_STAGE_ORDER
    assert result.offline_only is True
    assert result.deterministic is True
    assert result.admitted is True


def test_dry_run_emits_disposition_and_memory_feedback() -> None:
    result = dry_run.run_offline_dry_run(_candidate("memory_ok"), budget=_budget())

    assert result.disposition["disposition"] == "accepted_for_research_memory"
    assert result.evidence_pack["artifact_kind"] == "offline_fixture_evidence_pack"
    assert result.evidence_pack["complete"] is True
    assert result.feedback_memory[0]["research_memory"]["canonical_reason_code"] == "offline_route_verified"


def test_dry_run_distinguishes_missing_from_negative_evidence() -> None:
    missing = reasons.make_reason_record(
        code="evidence_incomplete",
        stage="EvidencePack",
        object_id="blocked",
        explanation="Evidence is incomplete.",
        next_action="collect_missing_evidence",
    )
    negative = reasons.make_reason_record(
        code="data_quality_failed",
        stage="SourceSnapshot",
        object_id="blocked",
        explanation="Data quality failed.",
        next_action="repair_source_data_quality",
    )

    result = dry_run.run_offline_dry_run(
        _candidate("blocked"),
        budget=_budget(),
        rejection_records=(missing, negative),
    )

    assert result.admitted is False
    assert "evidence_incomplete" in result.evidence_pack["missing_evidence_reason_codes"]
    assert "data_quality_failed" in result.evidence_pack["negative_evidence_reason_codes"]


def test_dry_run_respects_throughput_architecture_and_maturity_blocks() -> None:
    result = dry_run.run_offline_dry_run(
        throughput.ThroughputCandidate(
            proposal=_proposal("gated"),
            timeframe="1h",
            architecture_gate_passed=False,
            maturity_gate_passed=False,
        ),
        budget=_budget(),
    )

    assert result.admitted is False
    assert result.disposition["disposition"] == "blocked_before_screening"
    assert set(result.disposition["reason_codes"]) == {
        "architecture_gate_failed",
        "maturity_gate_failed",
    }


def test_dry_run_does_not_mutate_frozen_outputs() -> None:
    before = {path: (REPO_ROOT / path).read_bytes() for path in FROZEN_OUTPUTS}

    dry_run.run_offline_dry_run(_candidate("frozen_safe"), budget=_budget())

    after = {path: (REPO_ROOT / path).read_bytes() for path in FROZEN_OUTPUTS}
    assert after == before


def test_dry_run_grants_no_execution_or_deployment_authority() -> None:
    result = dry_run.run_offline_dry_run(_candidate("authority_safe"), budget=_budget())

    assert result.safety["strategy_synthesis_authority"] is False
    assert result.safety["shadow_authority"] is False
    assert result.safety["paper_authority"] is False
    assert result.safety["live_authority"] is False
    assert result.safety["broker_authority"] is False
    assert result.safety["risk_authority"] is False
    assert result.safety["order_authority"] is False
    assert result.safety["capital_allocation_authority"] is False
