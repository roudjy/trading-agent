"""Resume-path artifact-integrity resilience.

Corrupts prior-run sidecars on disk, reads them back, and confirms
the continuation policy fails closed with the typed reason code
surfaced inside `ArtifactIntegrityError`. This is the read-time half
of the v3.5 integrity layer — it guarantees that `--continue-latest`
cannot silently proceed on a mismatched or incomplete artifact set.

The unit suite (tests/unit/test_research_orchestration_policy.py)
exercises the same logic against in-memory dicts; this suite rounds
that through the real JSON round-trip so any regression in the
loader / policy boundary surfaces here instead of slipping into a
live `--continue-latest` invocation.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from research.integrity import (
    ARTIFACT_INCOMPLETE,
    ARTIFACT_RUNID_MISMATCH,
    ArtifactIntegrityError,
)
from research.orchestration_policy import (
    resolve_continue_latest_policy,
    validate_continuation_compatibility,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _load_triple(base: Path):
    state = json.loads((base / "run_state.v1.json").read_text("utf-8"))
    manifest = json.loads((base / "run_manifest.v1.json").read_text("utf-8"))
    batches = json.loads((base / "batches.v1.json").read_text("utf-8"))
    return state, manifest, batches


def _write_consistent_run(base: Path, run_id: str, status: str = "aborted") -> None:
    _write_json(
        base / "run_state.v1.json",
        {"run_id": run_id, "status": status, "pid": 12345},
    )
    _write_json(
        base / "run_manifest.v1.json",
        {"run_id": run_id, "status": status, "feature_version": "1.0"},
    )
    _write_json(
        base / "batches.v1.json",
        {
            "run_id": run_id,
            "batches": [
                {"batch_id": "batch-1", "status": "running", "current_stage": "validation"}
            ],
        },
    )


def test_resume_fails_closed_when_batches_runid_mismatches_state(tmp_path, monkeypatch):
    """Mismatched run_id across sidecars must abort continuation with a
    typed reason code rather than silently proceed on corrupted state.
    """
    monkeypatch.setattr("research.run_state._pid_is_live", lambda pid: False)

    _write_consistent_run(tmp_path, run_id="run-a")
    _write_json(
        tmp_path / "batches.v1.json",
        {
            "run_id": "run-b",
            "batches": [{"batch_id": "batch-1", "status": "running", "current_stage": "validation"}],
        },
    )

    state, manifest, batches = _load_triple(tmp_path)

    with pytest.raises(ArtifactIntegrityError) as excinfo:
        validate_continuation_compatibility(
            state_payload=state,
            manifest_payload=manifest,
            batches_payload=batches,
            retry_failed_batches=False,
            execution_mode="inline",
            context_label="resume",
        )
    assert excinfo.value.reason_code == ARTIFACT_RUNID_MISMATCH


def test_resume_fails_closed_when_manifest_sidecar_is_absent(tmp_path, monkeypatch):
    """Missing manifest sidecar must surface as ARTIFACT_INCOMPLETE."""
    monkeypatch.setattr("research.run_state._pid_is_live", lambda pid: False)

    _write_consistent_run(tmp_path, run_id="run-z")
    (tmp_path / "run_manifest.v1.json").unlink()

    state = json.loads((tmp_path / "run_state.v1.json").read_text("utf-8"))
    batches = json.loads((tmp_path / "batches.v1.json").read_text("utf-8"))

    with pytest.raises(ArtifactIntegrityError) as excinfo:
        validate_continuation_compatibility(
            state_payload=state,
            manifest_payload=None,
            batches_payload=batches,
            retry_failed_batches=False,
            execution_mode="inline",
            context_label="resume",
        )
    assert excinfo.value.reason_code == ARTIFACT_INCOMPLETE


def test_resume_fails_closed_when_state_sidecar_is_corrupt_json(tmp_path, monkeypatch):
    """Corrupt state.json (non-dict payload) must not be treated as a
    valid resume source."""
    monkeypatch.setattr("research.run_state._pid_is_live", lambda pid: False)

    _write_consistent_run(tmp_path, run_id="run-x")
    (tmp_path / "run_state.v1.json").write_text(json.dumps(["not", "a", "dict"]))

    corrupt_state = json.loads((tmp_path / "run_state.v1.json").read_text("utf-8"))
    manifest = json.loads((tmp_path / "run_manifest.v1.json").read_text("utf-8"))
    batches = json.loads((tmp_path / "batches.v1.json").read_text("utf-8"))

    with pytest.raises(ArtifactIntegrityError) as excinfo:
        validate_continuation_compatibility(
            state_payload=corrupt_state,
            manifest_payload=manifest,
            batches_payload=batches,
            retry_failed_batches=False,
            execution_mode="inline",
            context_label="resume",
        )
    assert excinfo.value.reason_code == ARTIFACT_INCOMPLETE


def test_continue_latest_fails_closed_on_mismatched_runid_roundtrip(tmp_path, monkeypatch):
    """continue-latest entrypoint must propagate the same typed failure."""
    monkeypatch.setattr("research.run_state._pid_is_live", lambda pid: False)

    _write_consistent_run(tmp_path, run_id="run-orig")
    _write_json(
        tmp_path / "run_manifest.v1.json",
        {"run_id": "run-ghost", "status": "aborted"},
    )

    state, manifest, batches = _load_triple(tmp_path)

    with pytest.raises(ArtifactIntegrityError) as excinfo:
        resolve_continue_latest_policy(
            state_payload=state,
            manifest_payload=manifest,
            batches_payload=batches,
            retry_failed_batches=False,
            execution_mode="inline",
        )
    assert excinfo.value.reason_code == ARTIFACT_RUNID_MISMATCH


def test_resume_succeeds_when_all_sidecars_agree_and_batches_resumable(tmp_path, monkeypatch):
    """Positive control: a clean, consistent sidecar set must validate."""
    monkeypatch.setattr("research.run_state._pid_is_live", lambda pid: False)

    _write_consistent_run(tmp_path, run_id="run-clean", status="aborted")
    state, manifest, batches = _load_triple(tmp_path)

    compat = validate_continuation_compatibility(
        state_payload=state,
        manifest_payload=manifest,
        batches_payload=batches,
        retry_failed_batches=False,
        execution_mode="inline",
        context_label="resume",
    )

    assert compat["source_run_id"] == "run-clean"
    assert compat["resumable_validation_batches"]
