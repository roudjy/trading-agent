from __future__ import annotations

import copy
import json
from datetime import UTC, datetime
from json import JSONDecodeError
from pathlib import Path
from typing import Any


BATCH_STATE_FILENAME = "run_batch_state.v1.json"
FRESH_ATTEMPT_REASON = "fresh_run"
RESUME_PENDING_ATTEMPT_REASON = "resume_pending_batch"
RESUME_STALE_ATTEMPT_REASON = "resume_stale_batch"
RETRY_FAILED_ATTEMPT_REASON = "retry_failed_batch"
TERMINAL_BATCH_STATUSES = {"completed", "partial", "skipped"}
ACTIVE_BATCH_STATUSES = {"pending", "running", "failed"}
VALID_BATCH_STAGES = {"screening", "validation"}


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, JSONDecodeError):
        return None


def _batch_state_path(*, history_root: Path, run_id: str, batch_id: str) -> Path:
    return history_root / run_id / "batches" / batch_id / BATCH_STATE_FILENAME


def _batch_sort_key(batch: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(batch.get("strategy_family") or ""),
        str(batch.get("interval") or ""),
        str(batch.get("batch_id") or ""),
    )


def build_batch_recovery_state_payload(
    *,
    source_run_id: str,
    batch: dict[str, Any],
    candidate_snapshots: list[dict[str, Any]],
    screening_records: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    evaluations: list[dict[str, Any]],
    walk_forward_reports: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "version": "v1",
        "source_run_id": source_run_id,
        "batch_id": str(batch["batch_id"]),
        "current_stage": str(batch.get("current_stage") or "screening"),
        "batch": copy.deepcopy(batch),
        "candidate_snapshots": sorted(
            (copy.deepcopy(item) for item in candidate_snapshots),
            key=lambda item: str(item["candidate_id"]),
        ),
        "screening_records": sorted(
            (copy.deepcopy(item) for item in screening_records),
            key=lambda item: str(item["candidate_id"]),
        ),
        "rows": sorted(
            (copy.deepcopy(item) for item in rows),
            key=lambda item: (
                str(item.get("strategy_name") or ""),
                str(item.get("asset") or ""),
                str(item.get("interval") or ""),
            ),
        ),
        "evaluations": sorted(
            (copy.deepcopy(item) for item in evaluations),
            key=lambda item: (
                str(item.get("row", {}).get("strategy_name") or ""),
                str(item.get("row", {}).get("asset") or ""),
                str(item.get("row", {}).get("interval") or ""),
            ),
        ),
        "walk_forward_reports": sorted(
            (copy.deepcopy(item) for item in walk_forward_reports),
            key=lambda item: (
                str(item.get("strategy_name") or ""),
                str(item.get("asset") or ""),
                str(item.get("interval") or ""),
            ),
        ),
    }


def load_batch_recovery_state(
    *,
    history_root: Path,
    run_id: str,
    batch_id: str,
) -> dict[str, Any] | None:
    return _load_json(_batch_state_path(history_root=history_root, run_id=run_id, batch_id=batch_id))


def write_batch_recovery_state(
    *,
    history_root: Path,
    run_id: str,
    payload: dict[str, Any],
    write_json_atomic,
) -> None:
    batch_id = str(payload["batch_id"])
    write_json_atomic(
        _batch_state_path(history_root=history_root, run_id=run_id, batch_id=batch_id),
        payload,
    )


def default_recovery_policy(*, heartbeat_timeout_s: int) -> dict[str, Any]:
    return {
        "batch_recovery_unit": "batch",
        "resume_rules": {
            "pending": "resumable",
            "running": "resumable_if_stale_or_incomplete",
            "failed": "retry_only_with_retry_failed_batches",
            "completed": "terminal",
            "skipped": "terminal",
            "partial": "terminal",
        },
        "stale_batch_detection": {
            "run_state_path": "research/run_state.v1.json",
            "heartbeat_timeout_s": int(heartbeat_timeout_s),
            "rule": "running batch is stale only when the prior run is no longer active",
        },
    }


def _copy_batch_state(batch: dict[str, Any]) -> dict[str, Any]:
    return {
        key: copy.deepcopy(value)
        for key, value in batch.items()
    }


def _carry_terminal_batch(*, target_batch: dict[str, Any], source_batch: dict[str, Any]) -> None:
    target_batch.clear()
    target_batch.update(_copy_batch_state(source_batch))


def _reset_batch_for_screening_retry(
    *,
    target_batch: dict[str, Any],
    source_batch: dict[str, Any],
    execution_mode: str,
    attempt_reason: str,
) -> None:
    attempt_count = int(source_batch.get("attempt_count") or 1) + 1
    candidate_ids = list(target_batch.get("candidate_ids") or [])
    candidate_summary = copy.deepcopy(target_batch.get("candidate_summary") or {})
    partition = copy.deepcopy(target_batch.get("partition") or {})
    batch_id = str(target_batch["batch_id"])
    batch_index = int(target_batch["batch_index"])
    strategy_family = str(target_batch["strategy_family"])
    interval = str(target_batch["interval"])
    candidate_count = int(target_batch.get("candidate_count") or 0)
    target_batch.clear()
    target_batch.update(
        {
            "batch_id": batch_id,
            "batch_index": batch_index,
            "strategy_family": strategy_family,
            "interval": interval,
            "partition": partition,
            "status": "pending",
            "current_stage": "screening",
            "started_at": None,
            "finished_at": None,
            "elapsed_seconds": 0,
            "candidate_count": candidate_count,
            "completed_candidate_count": 0,
            "promoted_candidate_count": 0,
            "validated_candidate_count": 0,
            "screening_rejected_count": 0,
            "timed_out_count": 0,
            "errored_count": 0,
            "validation_error_count": 0,
            "result_success_count": 0,
            "result_failed_count": 0,
            "candidate_ids": candidate_ids,
            "candidate_summary": candidate_summary,
            "attempt_count": attempt_count,
            "execution_mode": execution_mode,
            "error_type": None,
            "reason_code": None,
            "reason_detail": None,
            "last_attempt_reason": attempt_reason,
        }
    )


def _reset_batch_for_validation_retry(
    *,
    target_batch: dict[str, Any],
    source_batch: dict[str, Any],
    recovery_state: dict[str, Any],
    execution_mode: str,
    attempt_reason: str,
) -> None:
    baseline_batch = _copy_batch_state(recovery_state.get("batch") or {})
    if not baseline_batch:
        raise RuntimeError(
            f"missing recovery state for validation batch {target_batch['batch_id']}"
        )
    baseline_batch["status"] = "pending"
    baseline_batch["current_stage"] = "validation"
    baseline_batch["started_at"] = None
    baseline_batch["finished_at"] = None
    baseline_batch["elapsed_seconds"] = 0
    baseline_batch["validated_candidate_count"] = 0
    baseline_batch["validation_error_count"] = 0
    baseline_batch["result_success_count"] = 0
    baseline_batch["result_failed_count"] = 0
    baseline_batch["completed_candidate_count"] = (
        int(baseline_batch.get("screening_rejected_count") or 0)
        + int(baseline_batch.get("timed_out_count") or 0)
        + int(baseline_batch.get("errored_count") or 0)
    )
    baseline_batch["attempt_count"] = int(source_batch.get("attempt_count") or 1) + 1
    baseline_batch["execution_mode"] = execution_mode
    baseline_batch["error_type"] = None
    baseline_batch["reason_code"] = None
    baseline_batch["reason_detail"] = None
    baseline_batch["last_attempt_reason"] = attempt_reason
    target_batch.clear()
    target_batch.update(baseline_batch)


def _apply_candidate_snapshots(
    *,
    candidates_by_id: dict[str, dict[str, Any]],
    snapshots: list[dict[str, Any]],
) -> None:
    for snapshot in snapshots:
        candidate_id = str(snapshot["candidate_id"])
        if candidate_id not in candidates_by_id:
            continue
        candidates_by_id[candidate_id].clear()
        candidates_by_id[candidate_id].update(copy.deepcopy(snapshot))


def _apply_screening_records(
    *,
    screening_records_by_id: dict[str, dict[str, Any]],
    records: list[dict[str, Any]],
) -> None:
    for record in records:
        candidate_id = str(record["candidate_id"])
        if candidate_id not in screening_records_by_id:
            continue
        screening_records_by_id[candidate_id].clear()
        screening_records_by_id[candidate_id].update(copy.deepcopy(record))


def _restore_batch_artifacts(
    *,
    recovery_state: dict[str, Any],
    candidates_by_id: dict[str, dict[str, Any]],
    screening_records_by_id: dict[str, dict[str, Any]],
    rows: list[dict[str, Any]],
    evaluations: list[dict[str, Any]],
    walk_forward_reports: list[dict[str, Any]],
) -> None:
    _apply_candidate_snapshots(
        candidates_by_id=candidates_by_id,
        snapshots=list(recovery_state.get("candidate_snapshots") or []),
    )
    _apply_screening_records(
        screening_records_by_id=screening_records_by_id,
        records=list(recovery_state.get("screening_records") or []),
    )
    rows.extend(copy.deepcopy(list(recovery_state.get("rows") or [])))
    evaluations.extend(copy.deepcopy(list(recovery_state.get("evaluations") or [])))
    walk_forward_reports.extend(copy.deepcopy(list(recovery_state.get("walk_forward_reports") or [])))


def _validate_resume_source(
    *,
    previous_batches: list[dict[str, Any]],
    planned_batches: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    previous_by_id = {
        str(batch["batch_id"]): batch
        for batch in previous_batches
    }
    planned_by_id = {
        str(batch["batch_id"]): batch
        for batch in planned_batches
    }
    if set(previous_by_id) != set(planned_by_id):
        raise RuntimeError("resume artifacts do not match the currently planned batch set")
    for batch_id, planned in planned_by_id.items():
        previous = previous_by_id[batch_id]
        if list(previous.get("candidate_ids") or []) != list(planned.get("candidate_ids") or []):
            raise RuntimeError(f"resume artifacts do not match current candidates for batch {batch_id}")
    return previous_by_id


def prepare_resume_state(
    *,
    resume: bool,
    retry_failed_batches: bool,
    heartbeat_timeout_s: int,
    history_root: Path,
    state_payload: dict[str, Any] | None,
    manifest_payload: dict[str, Any] | None,
    batches_payload: dict[str, Any] | None,
    planned_batches: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    screening_records: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    evaluations: list[dict[str, Any]],
    walk_forward_reports: list[dict[str, Any]],
    execution_mode: str,
) -> dict[str, Any]:
    lifecycle_mode = "resume" if resume else "fresh"
    if not resume:
        return {
            "lifecycle_mode": lifecycle_mode,
            "resumed_from_run_id": None,
            "continuation_summary": {
                "fresh_batch_count": len(planned_batches),
                "reused_terminal_batch_count": 0,
                "resumed_pending_batch_count": 0,
                "resumed_stale_batch_count": 0,
                "retried_failed_batch_count": 0,
            },
            "recovery_policy": default_recovery_policy(heartbeat_timeout_s=heartbeat_timeout_s),
        }

    if not isinstance(state_payload, dict) or not isinstance(manifest_payload, dict) or not isinstance(batches_payload, dict):
        raise RuntimeError("resume requested but required recovery artifacts are missing")

    source_run_id = str(manifest_payload.get("run_id") or state_payload.get("run_id") or "")
    if source_run_id == "":
        raise RuntimeError("resume requested but source run_id is missing")
    if str(batches_payload.get("run_id") or "") != source_run_id:
        raise RuntimeError("resume artifacts are inconsistent across latest run artifacts")

    previous_batches = list(batches_payload.get("batches") or [])
    previous_by_id = _validate_resume_source(
        previous_batches=previous_batches,
        planned_batches=planned_batches,
    )
    candidates_by_id = {
        str(candidate["candidate_id"]): candidate
        for candidate in candidates
    }
    screening_records_by_id = {
        str(record["candidate_id"]): record
        for record in screening_records
    }
    previous_run_status = str(state_payload.get("status") or manifest_payload.get("status") or "")

    summary = {
        "fresh_batch_count": 0,
        "reused_terminal_batch_count": 0,
        "resumed_pending_batch_count": 0,
        "resumed_stale_batch_count": 0,
        "retried_failed_batch_count": 0,
    }

    for batch in sorted(planned_batches, key=_batch_sort_key):
        previous = previous_by_id[str(batch["batch_id"])]
        previous_status = str(previous.get("status") or "pending")
        current_stage = str(previous.get("current_stage") or "screening")
        if current_stage not in VALID_BATCH_STAGES:
            current_stage = "screening"
        previous["current_stage"] = current_stage
        recovery_state = load_batch_recovery_state(
            history_root=history_root,
            run_id=source_run_id,
            batch_id=str(batch["batch_id"]),
        )

        if previous_status in TERMINAL_BATCH_STATUSES:
            _carry_terminal_batch(target_batch=batch, source_batch=previous)
            if recovery_state is not None:
                _restore_batch_artifacts(
                    recovery_state=recovery_state,
                    candidates_by_id=candidates_by_id,
                    screening_records_by_id=screening_records_by_id,
                    rows=rows,
                    evaluations=evaluations,
                    walk_forward_reports=walk_forward_reports,
                )
            summary["reused_terminal_batch_count"] += 1
            continue

        if previous_status == "pending":
            if current_stage == "validation":
                if recovery_state is None:
                    raise RuntimeError(
                        f"resume requested for validation batch {batch['batch_id']} without screening recovery state"
                    )
                _restore_batch_artifacts(
                    recovery_state=recovery_state,
                    candidates_by_id=candidates_by_id,
                    screening_records_by_id=screening_records_by_id,
                    rows=[],
                    evaluations=[],
                    walk_forward_reports=[],
                )
                _reset_batch_for_validation_retry(
                    target_batch=batch,
                    source_batch=previous,
                    recovery_state=recovery_state,
                    execution_mode=execution_mode,
                    attempt_reason=RESUME_PENDING_ATTEMPT_REASON,
                )
            else:
                _reset_batch_for_screening_retry(
                    target_batch=batch,
                    source_batch=previous,
                    execution_mode=execution_mode,
                    attempt_reason=RESUME_PENDING_ATTEMPT_REASON,
                )
            summary["resumed_pending_batch_count"] += 1
            continue

        if previous_status == "running":
            if previous_run_status not in {"aborted", "failed", "running"}:
                raise RuntimeError(
                    f"running batch {batch['batch_id']} cannot be resumed from prior run status {previous_run_status}"
                )
            if current_stage == "validation":
                if recovery_state is None:
                    raise RuntimeError(
                        f"resume requested for stale validation batch {batch['batch_id']} without screening recovery state"
                    )
                _restore_batch_artifacts(
                    recovery_state=recovery_state,
                    candidates_by_id=candidates_by_id,
                    screening_records_by_id=screening_records_by_id,
                    rows=[],
                    evaluations=[],
                    walk_forward_reports=[],
                )
                _reset_batch_for_validation_retry(
                    target_batch=batch,
                    source_batch=previous,
                    recovery_state=recovery_state,
                    execution_mode=execution_mode,
                    attempt_reason=RESUME_STALE_ATTEMPT_REASON,
                )
            else:
                _reset_batch_for_screening_retry(
                    target_batch=batch,
                    source_batch=previous,
                    execution_mode=execution_mode,
                    attempt_reason=RESUME_STALE_ATTEMPT_REASON,
                )
            summary["resumed_stale_batch_count"] += 1
            continue

        if previous_status == "failed":
            if not retry_failed_batches:
                raise RuntimeError(
                    f"resume requested but batch {batch['batch_id']} previously failed; rerun with retry_failed_batches=True"
                )
            if current_stage == "validation":
                if recovery_state is None:
                    raise RuntimeError(
                        f"retry requested for failed validation batch {batch['batch_id']} without screening recovery state"
                    )
                _restore_batch_artifacts(
                    recovery_state=recovery_state,
                    candidates_by_id=candidates_by_id,
                    screening_records_by_id=screening_records_by_id,
                    rows=[],
                    evaluations=[],
                    walk_forward_reports=[],
                )
                _reset_batch_for_validation_retry(
                    target_batch=batch,
                    source_batch=previous,
                    recovery_state=recovery_state,
                    execution_mode=execution_mode,
                    attempt_reason=RETRY_FAILED_ATTEMPT_REASON,
                )
            else:
                _reset_batch_for_screening_retry(
                    target_batch=batch,
                    source_batch=previous,
                    execution_mode=execution_mode,
                    attempt_reason=RETRY_FAILED_ATTEMPT_REASON,
                )
            summary["retried_failed_batch_count"] += 1
            continue

        raise RuntimeError(f"unsupported batch status for resume: {previous_status}")

    if (
        summary["resumed_pending_batch_count"] == 0
        and summary["resumed_stale_batch_count"] == 0
        and summary["retried_failed_batch_count"] == 0
    ):
        raise RuntimeError("resume requested but no resumable batches were found")

    summary["fresh_batch_count"] = len(planned_batches) - summary["reused_terminal_batch_count"]
    return {
        "lifecycle_mode": lifecycle_mode,
        "resumed_from_run_id": source_run_id,
        "continuation_summary": summary,
        "recovery_policy": default_recovery_policy(heartbeat_timeout_s=heartbeat_timeout_s),
    }
