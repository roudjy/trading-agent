from __future__ import annotations

from pathlib import Path

from packages.qre_research import governed_offline_artifacts as artifacts
from packages.qre_research import multiwindow_evidence_closure as closure
from packages.qre_research import single_dataset_offline_replay as replay


def _replay(tmp_path: Path) -> replay.SingleDatasetReplayResult:
    dataset = replay.OfflineDatasetBoundary(
        dataset_id="dataset-closure",
        source_id="offline-source-closure",
        source_mode="offline_cached",
        dataset_fingerprint="offline_cached:dataset-closure:sha256:def456",
        source_provenance="approved_offline_cache_manifest:dataset-closure",
        data_provenance="offline_cached_sample:deterministic",
    )
    return replay.run_single_dataset_offline_replay(
        replay_id="replay-closure",
        dataset=dataset,
        candidate=replay.synthetic_replay_candidate("hypothesis-closure"),
        budget=replay.default_replay_budget(),
        artifact_dir=tmp_path,
        created_at_utc="2026-01-01T00:00:00Z",
    )


def test_all_required_evidence_windows_are_represented(tmp_path: Path) -> None:
    result = closure.run_multiwindow_evidence_closure(
        closure_id="closure-all",
        replay_result=_replay(tmp_path),
        window_statuses={name: "passed" for name in closure.REQUIRED_WINDOWS},
        artifact_dir=tmp_path,
    )

    assert tuple(window.name for window in result.evidence_windows) == closure.REQUIRED_WINDOWS
    assert result.evidence_complete is True
    assert result.disposition == "evidence_closed_for_offline_memory"


def test_missing_windows_are_explicit_and_not_negative(tmp_path: Path) -> None:
    result = closure.run_multiwindow_evidence_closure(
        closure_id="closure-missing",
        replay_result=_replay(tmp_path),
        window_statuses={"in_sample": "passed"},
        artifact_dir=tmp_path,
    )
    evidence_pack = result.artifact_envelope["evidence_pack"]

    assert result.disposition == "blocked_missing_evidence"
    assert "oos_not_available" in evidence_pack["missing_evidence"]
    assert "oos_not_available" not in evidence_pack["negative_evidence"]


def test_negative_evidence_is_not_confused_with_missing(tmp_path: Path) -> None:
    result = closure.run_multiwindow_evidence_closure(
        closure_id="closure-negative",
        replay_result=_replay(tmp_path),
        window_statuses={
            "in_sample": "passed",
            "out_of_sample": "passed",
            "null_model": "failed",
            "cost_model": "failed",
            "trade_count": "failed",
            "data_quality": "passed",
        },
        artifact_dir=tmp_path,
    )
    evidence_pack = result.artifact_envelope["evidence_pack"]

    assert result.disposition == "rejected_negative_evidence"
    assert "null_model_not_beaten" in evidence_pack["negative_evidence"]
    assert "cost_model_failed" in evidence_pack["negative_evidence"]
    assert "insufficient_trades" in evidence_pack["missing_evidence"]


def test_closure_persists_as_governed_artifact(tmp_path: Path) -> None:
    result = closure.run_multiwindow_evidence_closure(
        closure_id="closure-artifact",
        replay_result=_replay(tmp_path),
        window_statuses={name: "passed" for name in closure.REQUIRED_WINDOWS},
        artifact_dir=tmp_path,
    )

    assert result.artifact_path == tmp_path / "closure-artifact.json"
    assert result.latest_path == tmp_path / "latest.json"
    assert artifacts.read_artifact(result.artifact_path) == result.artifact_envelope


def test_memory_feedback_and_reason_distribution_include_window_failures(tmp_path: Path) -> None:
    result = closure.run_multiwindow_evidence_closure(
        closure_id="closure-memory",
        replay_result=_replay(tmp_path),
        window_statuses={"null_model": "failed"},
        artifact_dir=tmp_path,
    )

    assert result.memory_feedback_records
    assert closure.closure_reason_distribution((result,))["null_model_not_beaten"] == 1


def test_no_execution_authority_is_granted(tmp_path: Path) -> None:
    result = closure.run_multiwindow_evidence_closure(
        closure_id="closure-authority",
        replay_result=_replay(tmp_path),
        window_statuses={name: "passed" for name in closure.REQUIRED_WINDOWS},
        artifact_dir=tmp_path,
    )

    assert result.safety["offline_only"] is True
    for key, value in result.safety.items():
        if key != "offline_only":
            assert value is False
