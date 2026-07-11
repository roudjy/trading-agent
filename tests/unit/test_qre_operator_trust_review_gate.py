from __future__ import annotations

from pathlib import Path

from packages.qre_research import hypothesis_generator_governance as governance
from packages.qre_research import multiwindow_evidence_closure as closure
from packages.qre_research import operator_trust_review_gate as review
from packages.qre_research import research_memory_feedback_loop as feedback
from packages.qre_research import single_dataset_offline_replay as replay


def _proposal(hypothesis_id: str) -> governance.HypothesisProposal:
    return governance.HypothesisProposal(
        hypothesis_id=hypothesis_id,
        mechanism="operator review",
        source_id="offline-source-review",
        behavior_family="trend",
        expected_information_gain=20.0,
    )


def _closure(tmp_path: Path, hypothesis_id: str, statuses: dict[closure.WindowName, closure.WindowStatus]) -> closure.MultiwindowEvidenceClosure:
    dataset = replay.OfflineDatasetBoundary(
        dataset_id=f"dataset-{hypothesis_id}",
        source_id="offline-source-review",
        source_mode="offline_cached",
        dataset_fingerprint=f"offline_cached:{hypothesis_id}:sha256:abc",
        source_provenance="approved_offline_cache_manifest",
        data_provenance="offline_cached_sample",
    )
    replay_result = replay.run_single_dataset_offline_replay(
        replay_id=f"replay-{hypothesis_id}",
        dataset=dataset,
        candidate=replay.synthetic_replay_candidate(hypothesis_id),
        budget=replay.default_replay_budget(),
        artifact_dir=tmp_path,
        created_at_utc="2026-01-01T00:00:00Z",
    )
    return closure.run_multiwindow_evidence_closure(
        closure_id=f"closure-{hypothesis_id}",
        replay_result=replay_result,
        window_statuses=statuses,
        artifact_dir=tmp_path,
    )


def _review(tmp_path: Path, hypothesis_id: str, statuses: dict[closure.WindowName, closure.WindowStatus]) -> review.OperatorTrustReview:
    window_statuses = {name: "passed" for name in closure.REQUIRED_WINDOWS}
    window_statuses.update(statuses)
    item = _closure(tmp_path, hypothesis_id, window_statuses)
    loop = feedback.build_research_memory_feedback_loop((_proposal(hypothesis_id),), closures=(item,))
    return review.build_operator_trust_review(review_id=f"review-{hypothesis_id}", closures=(item,), feedback_loop=loop)


def test_offline_eligible_decision_can_be_produced(tmp_path: Path) -> None:
    result = _review(tmp_path, "eligible", {name: "passed" for name in closure.REQUIRED_WINDOWS})

    assert result.offline_eligibility_decision == review.ReviewDecision.ELIGIBLE_FOR_MORE_OFFLINE_RESEARCH
    assert result.machine_payload["eligible_for_more_offline_research"] is True


def test_missing_evidence_does_not_become_negative_evidence(tmp_path: Path) -> None:
    result = _review(tmp_path, "missing", {"out_of_sample": "missing"})

    assert result.offline_eligibility_decision == review.ReviewDecision.BLOCKED_MISSING_EVIDENCE
    assert "oos_not_available" in result.evidence_summary["missing_reason_codes"]
    assert "oos_not_available" not in result.evidence_summary["negative_reason_codes"]


def test_negative_cost_null_and_trade_count_decisions_are_explicit(tmp_path: Path) -> None:
    assert _review(tmp_path, "cost", {"cost_model": "failed"}).offline_eligibility_decision == review.ReviewDecision.REJECTED_COST_MODEL
    assert _review(tmp_path, "null", {"null_model": "failed"}).offline_eligibility_decision == review.ReviewDecision.REJECTED_NULL_MODEL
    assert _review(tmp_path, "trades", {"trade_count": "failed"}).offline_eligibility_decision == review.ReviewDecision.REJECTED_INSUFFICIENT_TRADES


def test_data_source_blockers_override_eligibility(tmp_path: Path) -> None:
    result = _review(tmp_path, "quality", {"data_quality": "failed"})

    assert result.offline_eligibility_decision == review.ReviewDecision.BLOCKED_DATA_NOT_ADMITTED


def test_do_not_retest_list_is_generated(tmp_path: Path) -> None:
    item = _closure(tmp_path, "suppress", {"null_model": "failed"})
    loop = feedback.build_research_memory_feedback_loop((_proposal("suppress"),), closures=(item,))
    result = review.build_operator_trust_review(review_id="review-suppress", closures=(), feedback_loop=loop)

    assert result.offline_eligibility_decision == review.ReviewDecision.DO_NOT_RETEST_UNLESS_CONDITIONS_CHANGE
    assert result.do_not_retest == ("suppress",)


def test_machine_and_human_outputs_are_aligned(tmp_path: Path) -> None:
    result = _review(tmp_path, "aligned", {"out_of_sample": "missing"})

    assert result.machine_payload["decision"] in result.operator_explanation
    assert result.machine_payload["next_action"] == result.next_action


def test_shadow_paper_live_and_execution_authority_are_always_false(tmp_path: Path) -> None:
    result = _review(tmp_path, "authority", {name: "passed" for name in closure.REQUIRED_WINDOWS})

    for value in result.authority.values():
        assert value is False
    assert result.machine_payload["eligible_for_shadow"] is False
    assert result.machine_payload["eligible_for_paper"] is False
    assert result.machine_payload["eligible_for_live"] is False
