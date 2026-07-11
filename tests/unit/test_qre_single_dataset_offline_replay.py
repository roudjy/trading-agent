from __future__ import annotations

from pathlib import Path

from packages.qre_research import governed_offline_artifacts as artifacts
from packages.qre_research import offline_research_dry_run as dry_run
from packages.qre_research import single_dataset_offline_replay as replay

REPO_ROOT = Path(__file__).resolve().parents[2]
FROZEN_OUTPUTS = (
    "research/research_latest.json",
    "research/strategy_matrix.csv",
)


def _dataset(**kwargs: object) -> replay.OfflineDatasetBoundary:
    return replay.OfflineDatasetBoundary(
        dataset_id="dataset-001",
        source_id="offline-source-001",
        source_mode="offline_cached",
        dataset_fingerprint="offline_cached:dataset-001:sha256:abc123",
        source_provenance="approved_offline_cache_manifest:dataset-001",
        data_provenance="offline_cached_sample:deterministic",
        **kwargs,
    )


def test_safe_dataset_admission_path_persists_artifact(tmp_path: Path) -> None:
    result = replay.run_single_dataset_offline_replay(
        replay_id="replay-001",
        dataset=_dataset(),
        candidate=replay.synthetic_replay_candidate("hypothesis-001"),
        budget=replay.default_replay_budget(),
        artifact_dir=tmp_path,
        created_at_utc="2026-01-01T00:00:00Z",
    )

    assert result.dry_run_result.admitted is True
    assert result.artifact_path == tmp_path / "replay-001.json"
    assert result.latest_path == tmp_path / "latest.json"
    assert artifacts.read_artifact(result.artifact_path) == result.artifact_envelope
    assert result.artifact_envelope["inputs"]["dataset_fingerprint"] == "offline_cached:dataset-001:sha256:abc123"
    assert result.artifact_envelope["inputs"]["source_provenance"] == "approved_offline_cache_manifest:dataset-001"
    assert result.operator_report.authority_statement["shadow_authority"] is False


def test_blocked_dataset_path_is_explicit_and_persisted(tmp_path: Path) -> None:
    result = replay.run_single_dataset_offline_replay(
        replay_id="replay-blocked",
        dataset=_dataset(source_approved=False, data_admitted=False),
        candidate=replay.synthetic_replay_candidate("hypothesis-blocked"),
        budget=replay.default_replay_budget(),
        artifact_dir=tmp_path,
        created_at_utc="2026-01-01T00:00:00Z",
    )

    reason_codes = {record.code for record in result.dry_run_result.reason_records}
    assert result.dry_run_result.admitted is False
    assert "source_identity_unresolved" in reason_codes
    assert "data_quality_failed" in reason_codes
    assert result.artifact_envelope["disposition"]["decision"] == "blocked_before_screening"
    assert set(result.artifact_envelope["evidence_pack"]["data_source_quality_blockers"]) == {
        "source_identity_unresolved",
        "data_quality_failed",
    }


def test_canonical_stage_order_and_evidence_distinction_are_preserved(tmp_path: Path) -> None:
    result = replay.run_single_dataset_offline_replay(
        replay_id="replay-evidence",
        dataset=_dataset(source_approved=False, data_admitted=False),
        candidate=replay.synthetic_replay_candidate("hypothesis-evidence"),
        budget=replay.default_replay_budget(),
        artifact_dir=tmp_path,
        created_at_utc="2026-01-01T00:00:00Z",
    )
    envelope = result.artifact_envelope

    assert tuple(record["stage"] for record in envelope["stage_records"]) == dry_run.DRY_RUN_STAGE_ORDER
    assert "source_identity_unresolved" in envelope["evidence_pack"]["missing_evidence"]
    assert "data_quality_failed" in envelope["evidence_pack"]["negative_evidence"]


def test_latest_json_is_only_written_inside_caller_artifact_dir(tmp_path: Path) -> None:
    result = replay.run_single_dataset_offline_replay(
        replay_id="replay-latest",
        dataset=_dataset(),
        candidate=replay.synthetic_replay_candidate("hypothesis-latest"),
        budget=replay.default_replay_budget(),
        artifact_dir=tmp_path,
        created_at_utc="2026-01-01T00:00:00Z",
    )

    assert result.latest_path == tmp_path / "latest.json"
    assert result.latest_path.exists()
    assert result.latest_path.parent == tmp_path


def test_frozen_outputs_are_untouched(tmp_path: Path) -> None:
    before = {path: (REPO_ROOT / path).read_bytes() for path in FROZEN_OUTPUTS}

    replay.run_single_dataset_offline_replay(
        replay_id="replay-frozen",
        dataset=_dataset(),
        candidate=replay.synthetic_replay_candidate("hypothesis-frozen"),
        budget=replay.default_replay_budget(),
        artifact_dir=tmp_path,
        created_at_utc="2026-01-01T00:00:00Z",
    )

    after = {path: (REPO_ROOT / path).read_bytes() for path in FROZEN_OUTPUTS}
    assert after == before


def test_replay_denies_all_execution_authority(tmp_path: Path) -> None:
    result = replay.run_single_dataset_offline_replay(
        replay_id="replay-authority",
        dataset=_dataset(),
        candidate=replay.synthetic_replay_candidate("hypothesis-authority"),
        budget=replay.default_replay_budget(),
        artifact_dir=tmp_path,
        created_at_utc="2026-01-01T00:00:00Z",
    )

    assert result.safety["offline_only"] is True
    for key, value in result.safety.items():
        if key not in {"offline_only", "single_dataset_boundary"}:
            assert value is False
