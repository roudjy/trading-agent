from __future__ import annotations

from typing import Any

from research import run_state as run_state_module
from research.run_state import ActiveResearchRunError


CONTINUE_LATEST_ACTION_FRESH = "fresh"
CONTINUE_LATEST_ACTION_RESUME = "resume"
CONTINUE_LATEST_ACTION_RETRY_FAILED = "retry_failed_batches"
_TERMINAL_BATCH_STATUSES = {"completed", "partial", "skipped"}
_RESUMABLE_BATCH_STATUSES = {"pending", "running"}


def _run_id(payload: dict[str, Any] | None) -> str | None:
    if not isinstance(payload, dict):
        return None
    value = str(payload.get("run_id") or "").strip()
    return value or None


def _batch_stage(batch: dict[str, Any]) -> str:
    stage = str(batch.get("current_stage") or "screening").strip()
    return stage if stage in {"screening", "validation"} else "screening"


def validate_continuation_compatibility(
    *,
    state_payload: dict[str, Any] | None,
    manifest_payload: dict[str, Any] | None,
    batches_payload: dict[str, Any] | None,
    retry_failed_batches: bool,
    execution_mode: str,
    context_label: str,
) -> dict[str, Any]:
    state_run_id = _run_id(state_payload)
    manifest_run_id = _run_id(manifest_payload)
    batches_run_id = _run_id(batches_payload)
    run_ids = {run_id for run_id in (state_run_id, manifest_run_id, batches_run_id) if run_id is not None}

    if not run_ids:
        raise RuntimeError(f"{context_label} requested but latest run artifacts are missing")

    if len(run_ids) != 1 or not isinstance(state_payload, dict) or not isinstance(manifest_payload, dict) or not isinstance(batches_payload, dict):
        raise RuntimeError(f"{context_label} requested but latest run artifacts are incomplete or inconsistent")

    source_run_id = next(iter(run_ids))
    run_status = str(state_payload.get("status") or manifest_payload.get("status") or "").strip()
    if run_status == "running":
        pid_value = state_payload.get("pid")
        if run_state_module._pid_is_live(pid_value if isinstance(pid_value, int) else None):
            raise ActiveResearchRunError(f"active research run already exists run_id={source_run_id} pid={pid_value}")

    previous_batches = list(batches_payload.get("batches") or [])
    if not previous_batches:
        raise RuntimeError(f"{context_label} requested but latest run batches are missing")

    resumable_screening_batches = []
    resumable_validation_batches = []
    failed_batches = []
    nonterminal_batches = []

    for batch in previous_batches:
        status = str(batch.get("status") or "pending").strip()
        stage = _batch_stage(batch)
        if status in _RESUMABLE_BATCH_STATUSES:
            nonterminal_batches.append(batch)
            if stage == "screening":
                resumable_screening_batches.append(batch)
            elif stage == "validation":
                resumable_validation_batches.append(batch)
        elif status == "failed":
            failed_batches.append(batch)
            nonterminal_batches.append(batch)

    if run_status == "completed" and nonterminal_batches:
        raise RuntimeError(f"{context_label} requested but latest run artifacts are inconsistent with a completed run")

    if execution_mode != "inline" and resumable_screening_batches:
        raise RuntimeError(
            f"{context_label} does not support screening continuation with execution_mode=process_pool; rerun with execution.max_workers=1 or use explicit fresh controls"
        )

    if failed_batches and not retry_failed_batches and not (resumable_screening_batches or resumable_validation_batches):
        raise RuntimeError(
            f"{context_label} found failed batches; rerun with --retry-failed-batches or use explicit fresh controls"
        )

    return {
        "source_run_id": source_run_id,
        "run_status": run_status,
        "resumable_screening_batches": resumable_screening_batches,
        "resumable_validation_batches": resumable_validation_batches,
        "failed_batches": failed_batches,
        "nonterminal_batches": nonterminal_batches,
    }


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

    compatibility = validate_continuation_compatibility(
        state_payload=state_payload,
        manifest_payload=manifest_payload,
        batches_payload=batches_payload,
        retry_failed_batches=retry_failed_batches,
        execution_mode=execution_mode,
        context_label="continue-latest",
    )

    if compatibility["resumable_screening_batches"] or compatibility["resumable_validation_batches"]:
        return {
            "action": CONTINUE_LATEST_ACTION_RESUME,
            "resume": True,
            "retry_failed_batches": False,
            "source_run_id": compatibility["source_run_id"],
        }

    if compatibility["failed_batches"]:
        return {
            "action": CONTINUE_LATEST_ACTION_RETRY_FAILED,
            "resume": True,
            "retry_failed_batches": True,
            "source_run_id": compatibility["source_run_id"],
        }

    return {
        "action": CONTINUE_LATEST_ACTION_FRESH,
        "resume": False,
        "retry_failed_batches": False,
        "source_run_id": None,
    }
