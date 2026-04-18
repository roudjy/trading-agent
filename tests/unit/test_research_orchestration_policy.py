from __future__ import annotations

import pytest

from research.orchestration_policy import (
    CONTINUE_LATEST_ACTION_FRESH,
    CONTINUE_LATEST_ACTION_RESUME,
    CONTINUE_LATEST_ACTION_RETRY_FAILED,
    resolve_continue_latest_policy,
    validate_continuation_compatibility,
)
from research.run_state import ActiveResearchRunError


def _artifacts(*, run_id: str = "run-1", status: str = "aborted", batches: list[dict] | None = None) -> tuple[dict, dict, dict]:
    return (
        {"run_id": run_id, "status": status, "pid": 123},
        {"run_id": run_id, "status": status},
        {"run_id": run_id, "batches": list(batches or [])},
    )


def test_continue_latest_resolves_fresh_without_prior_artifacts():
    resolution = resolve_continue_latest_policy(
        state_payload=None,
        manifest_payload=None,
        batches_payload=None,
        retry_failed_batches=False,
        execution_mode="inline",
    )

    assert resolution == {
        "action": CONTINUE_LATEST_ACTION_FRESH,
        "resume": False,
        "retry_failed_batches": False,
        "source_run_id": None,
    }


def test_continue_latest_resolves_resume_for_validation_batches():
    state, manifest, batches = _artifacts(
        batches=[{"batch_id": "batch-1", "status": "running", "current_stage": "validation"}],
    )

    resolution = resolve_continue_latest_policy(
        state_payload=state,
        manifest_payload=manifest,
        batches_payload=batches,
        retry_failed_batches=False,
        execution_mode="process_pool",
    )

    assert resolution["action"] == CONTINUE_LATEST_ACTION_RESUME
    assert resolution["resume"] is True
    assert resolution["retry_failed_batches"] is False
    assert resolution["source_run_id"] == "run-1"


def test_continue_latest_resolves_retry_failed_when_opted_in():
    state, manifest, batches = _artifacts(
        status="failed",
        batches=[{"batch_id": "batch-1", "status": "failed", "current_stage": "screening"}],
    )

    resolution = resolve_continue_latest_policy(
        state_payload=state,
        manifest_payload=manifest,
        batches_payload=batches,
        retry_failed_batches=True,
        execution_mode="process_pool",
    )

    assert resolution["action"] == CONTINUE_LATEST_ACTION_RETRY_FAILED
    assert resolution["resume"] is True
    assert resolution["retry_failed_batches"] is True
    assert resolution["source_run_id"] == "run-1"


def test_continue_latest_fails_closed_for_failed_batches_without_retry_opt_in():
    state, manifest, batches = _artifacts(
        status="failed",
        batches=[{"batch_id": "batch-1", "status": "failed", "current_stage": "screening"}],
    )

    with pytest.raises(RuntimeError, match="continue-latest found failed batches"):
        resolve_continue_latest_policy(
            state_payload=state,
            manifest_payload=manifest,
            batches_payload=batches,
            retry_failed_batches=False,
            execution_mode="inline",
        )


def test_continue_latest_fails_closed_for_process_pool_screening_continuation():
    state, manifest, batches = _artifacts(
        batches=[{"batch_id": "batch-1", "status": "running", "current_stage": "screening"}],
    )

    with pytest.raises(RuntimeError, match="does not support screening continuation with execution_mode=process_pool"):
        resolve_continue_latest_policy(
            state_payload=state,
            manifest_payload=manifest,
            batches_payload=batches,
            retry_failed_batches=False,
            execution_mode="process_pool",
        )


def test_continue_latest_fails_closed_for_live_running_run(monkeypatch):
    monkeypatch.setattr("research.run_state._pid_is_live", lambda pid: True)
    state, manifest, batches = _artifacts(
        status="running",
        batches=[{"batch_id": "batch-1", "status": "running", "current_stage": "screening"}],
    )

    with pytest.raises(ActiveResearchRunError, match="active research run already exists"):
        resolve_continue_latest_policy(
            state_payload=state,
            manifest_payload=manifest,
            batches_payload=batches,
            retry_failed_batches=False,
            execution_mode="inline",
        )


def test_validate_continuation_compatibility_fails_closed_for_manual_process_pool_screening_continuation():
    state, manifest, batches = _artifacts(
        status="aborted",
        batches=[{"batch_id": "batch-1", "status": "running", "current_stage": "screening"}],
    )

    with pytest.raises(RuntimeError, match="resume does not support screening continuation with execution_mode=process_pool"):
        validate_continuation_compatibility(
            state_payload=state,
            manifest_payload=manifest,
            batches_payload=batches,
            retry_failed_batches=False,
            execution_mode="process_pool",
            context_label="resume",
        )


def test_validate_continuation_compatibility_fails_closed_for_incomplete_artifacts():
    state, manifest, _ = _artifacts()

    with pytest.raises(RuntimeError, match="resume requested but latest run artifacts are incomplete or inconsistent"):
        validate_continuation_compatibility(
            state_payload=state,
            manifest_payload=manifest,
            batches_payload=None,
            retry_failed_batches=False,
            execution_mode="inline",
            context_label="resume",
        )


def test_validate_continuation_compatibility_fails_closed_for_completed_run_with_nonterminal_batches():
    state, manifest, batches = _artifacts(
        status="completed",
        batches=[{"batch_id": "batch-1", "status": "pending", "current_stage": "validation"}],
    )

    with pytest.raises(RuntimeError, match="resume requested but latest run artifacts are inconsistent with a completed run"):
        validate_continuation_compatibility(
            state_payload=state,
            manifest_payload=manifest,
            batches_payload=batches,
            retry_failed_batches=False,
            execution_mode="inline",
            context_label="resume",
        )
