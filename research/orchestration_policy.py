from __future__ import annotations

from typing import Any

from research.run_state import ActiveResearchRunError


CONTINUE_LATEST_ACTION_FRESH = "fresh"
CONTINUE_LATEST_ACTION_RESUME = "resume"
CONTINUE_LATEST_ACTION_RETRY_FAILED = "retry_failed_batches"
_TERMINAL_BATCH_STATUSES = {"completed", "partial", "skipped"}


def _run_id(payload: dict[str, Any] | None) -> str | None:
    if not isinstance(payload, dict):
        return None
    value = str(payload.get("run_id") or "").strip()
    return value or None


def _batch_stage(batch: dict[str, Any]) -> str:
    stage = str(batch.get("current_stage") or "screening").strip()
    return stage if stage in {"screening", "validation"} else "screening"


def resolve_continue_latest_policy(
    *,
    state_payload: dict[str, Any] | None,
    manifest_payload: dict[str, Any] | None,
    batches_payload: dict[str, Any] | None,
    retry_failed_batches: bool,
    execution_mode: str,
) -> dict[str, Any]:
    state_run_id = _run_id(state_payload)
    manifest_run_id = _run_id(manifest_payload)
    batches_run_id = _run_id(batches_payload)
    run_ids = {run_id for run_id in (state_run_id, manifest_run_id, batches_run_id) if run_id is not None}

    if not run_ids:
        return {
            "action": CONTINUE_LATEST_ACTION_FRESH,
            "resume": False,
            "retry_failed_batches": False,
            "source_run_id": None,
        }

    if len(run_ids) != 1 or not isinstance(state_payload, dict) or not isinstance(manifest_payload, dict) or not isinstance(batches_payload, dict):
        raise RuntimeError("continue-latest requested but latest run artifacts are incomplete or inconsistent")

    source_run_id = next(iter(run_ids))
    run_status = str(state_payload.get("status") or manifest_payload.get("status") or "").strip()
    if run_status == "running":
        raise ActiveResearchRunError(f"active research run already exists run_id={source_run_id} pid={state_payload.get('pid')}")

    previous_batches = list(batches_payload.get("batches") or [])
    if not previous_batches:
        return {
            "action": CONTINUE_LATEST_ACTION_FRESH,
            "resume": False,
            "retry_failed_batches": False,
            "source_run_id": None,
        }

    screening_resume_batches = [
        batch
        for batch in previous_batches
        if str(batch.get("status") or "pending") in {"pending", "running"}
        and _batch_stage(batch) == "screening"
    ]
    validation_resume_batches = [
        batch
        for batch in previous_batches
        if str(batch.get("status") or "pending") in {"pending", "running"}
        and _batch_stage(batch) == "validation"
    ]
    failed_batches = [
        batch
        for batch in previous_batches
        if str(batch.get("status") or "") == "failed"
    ]
    nonterminal_batches = [
        batch
        for batch in previous_batches
        if str(batch.get("status") or "pending") not in _TERMINAL_BATCH_STATUSES
    ]

    if run_status == "completed" and nonterminal_batches:
        raise RuntimeError("continue-latest requested but latest run artifacts are inconsistent with a completed run")

    if screening_resume_batches or validation_resume_batches:
        if execution_mode != "inline" and screening_resume_batches:
            raise RuntimeError(
                "continue-latest does not support screening continuation with execution_mode=process_pool; rerun with execution.max_workers=1 or use explicit manual controls"
            )
        return {
            "action": CONTINUE_LATEST_ACTION_RESUME,
            "resume": True,
            "retry_failed_batches": False,
            "source_run_id": source_run_id,
        }

    if failed_batches:
        if not retry_failed_batches:
            raise RuntimeError(
                "continue-latest found failed batches; rerun with --retry-failed-batches or use explicit fresh/manual resume controls"
            )
        return {
            "action": CONTINUE_LATEST_ACTION_RETRY_FAILED,
            "resume": True,
            "retry_failed_batches": True,
            "source_run_id": source_run_id,
        }

    return {
        "action": CONTINUE_LATEST_ACTION_FRESH,
        "resume": False,
        "retry_failed_batches": False,
        "source_run_id": None,
    }
