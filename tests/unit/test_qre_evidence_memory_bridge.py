from __future__ import annotations

from pathlib import Path

import pytest

from packages.qre_research import canonical_contracts
from packages.qre_research.evidence_memory_bridge import (
    EvidenceMemoryBridgeError,
    disposition_from_evidence_pack,
    evidence_ledger_entry_from_screening_result,
    evidence_pack_from_screening_result,
    feedback_record_from_disposition,
    lesson_memory_from_feedback_records,
    research_memory_from_lessons,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def _screening(decision: str = "screening_fail") -> dict[str, object]:
    return {
        "screening_result_id": "screen_001",
        "campaign_run_id": "campaign_run_001",
        "candidate_id": "cand_001",
        "decision": decision,
        "metrics": {
            "candidate_total_return": -0.1,
            "benchmark_total_return": 0.02,
            "excess_return": -0.12,
            "candidate_sharpe_like": -0.4,
        },
        "null_control": {"beats_null_p50": False},
        "contradictions": ["benchmark_positive_candidate_negative"],
    }


def test_evidence_pack_from_fixture_campaign_result() -> None:
    pack = evidence_pack_from_screening_result(_screening())

    assert pack["canonical_name"] == "EvidencePack"
    assert str(pack["evidence_pack_id"]).startswith("epack_")
    assert pack["decision_basis"]["negative_result_preserved"] is True
    assert pack["decision_basis"]["contradictions"] == ["benchmark_positive_candidate_negative"]


def test_evidence_ledger_from_screening_result() -> None:
    ledger = evidence_ledger_entry_from_screening_result(_screening("null_not_beaten"))

    assert ledger["canonical_name"] == "EvidenceLedger"
    assert ledger["evidence_decision"] == "weak_research_evidence"
    assert ledger["audit_flags"]["trading_authority"] is False


def test_disposition_from_evidence() -> None:
    disposition = disposition_from_evidence_pack(evidence_pack_from_screening_result(_screening()))

    assert disposition["canonical_name"] == "Disposition"
    assert disposition["decision"] == "reject_for_now"
    assert disposition["reason_codes"] == ["screening_fail"]


def test_feedback_record_from_disposition() -> None:
    feedback = feedback_record_from_disposition(
        disposition_from_evidence_pack(evidence_pack_from_screening_result(_screening()))
    )

    assert feedback["canonical_name"] == "FeedbackRecord"
    assert feedback["feedback_decision"] == "reject_for_now"
    assert feedback["next_action"] == "suppress_matching_candidate_family"
    assert feedback["consumable_by_next_run"] is True


def test_lesson_memory_from_repeated_or_classified_failures() -> None:
    feedback = feedback_record_from_disposition(
        disposition_from_evidence_pack(evidence_pack_from_screening_result(_screening()))
    )

    lesson = lesson_memory_from_feedback_records([feedback, feedback])

    assert lesson["canonical_name"] == "LessonMemory"
    assert lesson["do_not_repeat"] == [feedback["feedback_id"], feedback["feedback_id"]]
    assert "preserve_negative_results" in lesson["generator_constraints"]


def test_research_memory_from_lessons() -> None:
    feedback = feedback_record_from_disposition(
        disposition_from_evidence_pack(evidence_pack_from_screening_result(_screening()))
    )
    lesson = lesson_memory_from_feedback_records([feedback])

    memory = research_memory_from_lessons([lesson])

    assert memory["canonical_name"] == "ResearchMemory"
    assert memory["lesson_refs"] == [lesson["lesson_id"]]
    assert memory["feedback_refs"] == [feedback["feedback_id"]]


def test_missing_evidence_fails_closed() -> None:
    bad = _screening()
    bad.pop("metrics")

    with pytest.raises(EvidenceMemoryBridgeError, match="missing_required_fields"):
        evidence_pack_from_screening_result(bad)


def test_provider_leakage_is_blocked() -> None:
    bad = _screening()
    bad["metrics"] = {"provider": "tiingo"}

    with pytest.raises(EvidenceMemoryBridgeError, match="provider_leakage"):
        evidence_pack_from_screening_result(bad)


def test_frozen_contracts_are_not_mutated() -> None:
    before = {path: (REPO_ROOT / path).read_bytes() for path in canonical_contracts.FROZEN_LEGACY_OUTPUTS}

    feedback = feedback_record_from_disposition(
        disposition_from_evidence_pack(evidence_pack_from_screening_result(_screening()))
    )
    lesson = lesson_memory_from_feedback_records([feedback])
    research_memory_from_lessons([lesson])

    after = {path: (REPO_ROOT / path).read_bytes() for path in canonical_contracts.FROZEN_LEGACY_OUTPUTS}
    assert after == before


def test_no_execution_or_promotion_authority() -> None:
    feedback = feedback_record_from_disposition(
        disposition_from_evidence_pack(evidence_pack_from_screening_result(_screening()))
    )
    lesson = lesson_memory_from_feedback_records([feedback])
    memory = research_memory_from_lessons([lesson])

    for payload in (feedback, lesson, memory):
        safety = payload["safety"]
        assert safety["runs_campaign"] is False
        assert safety["runs_screening"] is False
        assert safety["promotes_candidates"] is False
        assert safety["trading_authority"] is False
        assert safety["validation_authority"] is False
