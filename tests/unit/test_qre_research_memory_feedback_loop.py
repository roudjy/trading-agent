from __future__ import annotations

from pathlib import Path

from packages.qre_research import hypothesis_generator_governance as governance
from packages.qre_research import multiwindow_evidence_closure as closure
from packages.qre_research import research_memory_feedback_loop as feedback
from packages.qre_research import single_dataset_offline_replay as replay


def _proposal(hypothesis_id: str, **kwargs: object) -> governance.HypothesisProposal:
    return governance.HypothesisProposal(
        hypothesis_id=hypothesis_id,
        mechanism="offline evidence memory",
        source_id="offline-source-memory",
        behavior_family="trend",
        expected_information_gain=20.0,
        **kwargs,
    )


def _closure(tmp_path: Path, hypothesis_id: str, statuses: dict[closure.WindowName, closure.WindowStatus]) -> closure.MultiwindowEvidenceClosure:
    dataset = replay.OfflineDatasetBoundary(
        dataset_id=f"dataset-{hypothesis_id}",
        source_id="offline-source-memory",
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


def _record(loop: feedback.ResearchMemoryFeedbackLoop, hypothesis_id: str) -> feedback.MemoryFeedbackRecord:
    return next(record for record in loop.records if record.hypothesis_id == hypothesis_id)


def test_failed_negative_evidence_suppresses_retest(tmp_path: Path) -> None:
    loop = feedback.build_research_memory_feedback_loop(
        (_proposal("negative"),),
        closures=(_closure(tmp_path, "negative", {"null_model": "failed"}),),
    )

    record = _record(loop, "negative")
    assert record.decision == "suppressed"
    assert record.suppress_if_unchanged is True
    assert loop.do_not_retest == ("negative",)


def test_missing_data_creates_next_action_not_permanent_rejection(tmp_path: Path) -> None:
    loop = feedback.build_research_memory_feedback_loop(
        (_proposal("missing"),),
        closures=(_closure(tmp_path, "missing", {"out_of_sample": "missing"}),),
    )

    record = _record(loop, "missing")
    assert record.decision == "next_action_required"
    assert record.next_action == "collect_missing_evidence"
    assert record.suppress_if_unchanged is False


def test_changed_condition_allows_reconsideration(tmp_path: Path) -> None:
    loop = feedback.build_research_memory_feedback_loop(
        (_proposal("changed"),),
        closures=(_closure(tmp_path, "changed", {"cost_model": "failed"}),),
        changed_conditions=("changed:cost_model_failed",),
    )

    record = _record(loop, "changed")
    assert record.decision == "prioritize"
    assert record.changed_condition_applied is True


def test_source_data_quality_blockers_remain_blockers(tmp_path: Path) -> None:
    loop = feedback.build_research_memory_feedback_loop(
        (_proposal("quality"),),
        closures=(_closure(tmp_path, "quality", {"data_quality": "failed"}),),
    )

    assert _record(loop, "quality").decision == "blocked"


def test_architecture_and_maturity_blockers_remain_blockers() -> None:
    loop = feedback.build_research_memory_feedback_loop(
        (
            _proposal("architecture", architecture_gate_passed=False),
            _proposal("maturity", maturity_gate_passed=False),
        ),
    )

    assert _record(loop, "architecture").decision == "blocked"
    assert _record(loop, "maturity").decision == "blocked"


def test_prioritization_record_explains_ranking(tmp_path: Path) -> None:
    loop = feedback.build_research_memory_feedback_loop(
        (_proposal("ranked"),),
        closures=(_closure(tmp_path, "ranked", {name: "passed" for name in closure.REQUIRED_WINDOWS}),),
    )

    record = loop.prioritization_records[0]
    assert record["hypothesis_id"] == "ranked"
    assert record["decision"] == "prioritize"
    assert record["rationale"]


def test_no_execution_authority_is_granted() -> None:
    loop = feedback.build_research_memory_feedback_loop((_proposal("safe"),))

    assert loop.safety["offline_only"] is True
    for key, value in loop.safety.items():
        if key != "offline_only":
            assert value is False
