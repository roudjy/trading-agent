from __future__ import annotations

import copy
from collections import Counter
from datetime import UTC, datetime
from typing import Any


def build_campaign_id(*, run_id: str) -> str:
    return f"campaign-{run_id}"


def _batch_sort_key(batch: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(batch.get("strategy_family") or ""),
        str(batch.get("interval") or ""),
        str(batch.get("batch_id") or ""),
    )


def _parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or value.strip() == "":
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def _elapsed_seconds(
    *,
    started_at: str | None,
    finished_at: str | None,
    generated_at_utc: datetime,
) -> int:
    started = _parse_datetime(started_at)
    if started is None:
        return 0
    finished = _parse_datetime(finished_at) or generated_at_utc.astimezone(UTC)
    return max(0, int(round((finished - started).total_seconds())))


def summarize_batch_statuses(*, batches: list[dict[str, Any]]) -> dict[str, int]:
    ordered_batches = sorted(batches, key=_batch_sort_key)
    counts = Counter(str(batch.get("status") or "pending") for batch in ordered_batches)
    return {
        "batch_count": len(ordered_batches),
        "pending_batch_count": int(counts.get("pending", 0)),
        "running_batch_count": int(counts.get("running", 0)),
        "completed_batch_count": int(counts.get("completed", 0)),
        "partial_batch_count": int(counts.get("partial", 0)),
        "failed_batch_count": int(counts.get("failed", 0)),
        "skipped_batch_count": int(counts.get("skipped", 0)),
    }


def resolve_campaign_status(*, batches: list[dict[str, Any]]) -> str:
    statuses = [str(batch.get("status") or "pending") for batch in sorted(batches, key=_batch_sort_key)]
    if not statuses or all(status == "pending" for status in statuses):
        return "pending"
    if any(status in {"running", "pending"} for status in statuses):
        return "running"
    if all(status == "completed" for status in statuses):
        return "completed"
    if any(status == "failed" for status in statuses):
        return "failed"
    if any(status == "partial" for status in statuses):
        return "partial"
    return "partial"


def summarize_campaign_candidates(
    *,
    batches: list[dict[str, Any]],
    candidate_payload: dict[str, Any] | None,
    screening_payload: dict[str, Any] | None,
) -> dict[str, int]:
    candidate_summary = candidate_payload.get("summary") if isinstance(candidate_payload, dict) else {}
    screening_summary = screening_payload.get("summary") if isinstance(screening_payload, dict) else {}
    total_candidate_count = sum(int(batch.get("candidate_count") or 0) for batch in batches)
    promoted_candidate_count = int(
        candidate_summary.get(
            "validation_candidate_count",
            sum(int(batch.get("promoted_candidate_count") or 0) for batch in batches),
        )
    )
    validated_candidate_count = int(
        candidate_summary.get(
            "validated_count",
            sum(int(batch.get("validated_candidate_count") or 0) for batch in batches),
        )
    )
    plain_rejected_count = int(
        screening_summary.get(
            "rejected_count",
            candidate_summary.get(
                "screening_rejected_count",
                sum(int(batch.get("screening_rejected_count") or 0) for batch in batches),
            ),
        )
    )
    timed_out_candidate_count = int(
        screening_summary.get(
            "timed_out_count",
            sum(int(batch.get("timed_out_count") or 0) for batch in batches),
        )
    )
    errored_candidate_count = int(
        screening_summary.get(
            "errored_count",
            sum(int(batch.get("errored_count") or 0) for batch in batches),
        )
    )
    skipped_candidate_count = int(screening_summary.get("skipped_count", 0))
    rejected_candidate_count = (
        plain_rejected_count
        + timed_out_candidate_count
        + errored_candidate_count
        + skipped_candidate_count
    )
    return {
        "total_candidate_count": int(total_candidate_count),
        "promoted_candidate_count": int(promoted_candidate_count),
        "rejected_candidate_count": int(rejected_candidate_count),
        "validated_candidate_count": int(validated_candidate_count),
        "timed_out_candidate_count": int(timed_out_candidate_count),
        "errored_candidate_count": int(errored_candidate_count),
    }


def _campaign_batch_row(batch: dict[str, Any]) -> dict[str, Any]:
    return {
        "batch_id": str(batch["batch_id"]),
        "batch_index": int(batch["batch_index"]),
        "strategy_family": str(batch["strategy_family"]),
        "interval": str(batch["interval"]),
        "status": str(batch["status"]),
        "current_stage": str(batch.get("current_stage") or "screening"),
        "started_at": batch.get("started_at"),
        "finished_at": batch.get("finished_at"),
        "elapsed_seconds": int(batch.get("elapsed_seconds") or 0),
        "candidate_count": int(batch.get("candidate_count") or 0),
        "completed_candidate_count": int(batch.get("completed_candidate_count") or 0),
        "promoted_candidate_count": int(batch.get("promoted_candidate_count") or 0),
        "validated_candidate_count": int(batch.get("validated_candidate_count") or 0),
        "screening_rejected_count": int(batch.get("screening_rejected_count") or 0),
        "timed_out_count": int(batch.get("timed_out_count") or 0),
        "errored_count": int(batch.get("errored_count") or 0),
        "validation_error_count": int(batch.get("validation_error_count") or 0),
        "attempt_count": int(batch.get("attempt_count") or 1),
        "execution_mode": batch.get("execution_mode"),
        "error_type": batch.get("error_type"),
        "reason_code": batch.get("reason_code"),
        "reason_detail": batch.get("reason_detail"),
        "last_attempt_reason": batch.get("last_attempt_reason"),
    }


def _active_batch_summary(batches: list[dict[str, Any]]) -> dict[str, Any] | None:
    for batch in sorted(batches, key=_batch_sort_key):
        if str(batch.get("status") or "") != "running":
            continue
        return {
            "batch_id": str(batch["batch_id"]),
            "batch_index": int(batch["batch_index"]),
            "strategy_family": str(batch["strategy_family"]),
            "interval": str(batch["interval"]),
            "status": str(batch["status"]),
            "current_stage": str(batch.get("current_stage") or "screening"),
            "completed_candidates": int(batch.get("completed_candidate_count") or 0),
            "total_candidates": int(batch.get("candidate_count") or 0),
            "elapsed_seconds": int(batch.get("elapsed_seconds") or 0),
        }
    return None


def build_run_campaign_payload(
    *,
    campaign_id: str,
    run_id: str,
    generated_at_utc: datetime,
    started_at: str | None,
    finished_at: str | None,
    batches: list[dict[str, Any]],
    candidate_payload: dict[str, Any] | None,
    screening_payload: dict[str, Any] | None,
    source_artifacts: dict[str, str],
) -> dict[str, Any]:
    ordered_batches = sorted((copy.deepcopy(batch) for batch in batches), key=_batch_sort_key)
    batch_summary = summarize_batch_statuses(batches=ordered_batches)
    candidate_summary = summarize_campaign_candidates(
        batches=ordered_batches,
        candidate_payload=candidate_payload,
        screening_payload=screening_payload,
    )
    status = resolve_campaign_status(batches=ordered_batches)
    resolved_finished_at = finished_at
    if resolved_finished_at is None and status not in {"pending", "running"}:
        resolved_finished_at = generated_at_utc.astimezone(UTC).isoformat()
    return {
        "version": "v1",
        "campaign_id": campaign_id,
        "run_id": run_id,
        "generated_at_utc": generated_at_utc.astimezone(UTC).isoformat(),
        "status": status,
        "started_at": started_at,
        "finished_at": resolved_finished_at,
        "elapsed_seconds": _elapsed_seconds(
            started_at=started_at,
            finished_at=resolved_finished_at,
            generated_at_utc=generated_at_utc,
        ),
        "summary": {
            **batch_summary,
            **candidate_summary,
        },
        "lineage": {
            "source_artifacts": copy.deepcopy(source_artifacts),
        },
        "batches": [_campaign_batch_row(batch) for batch in ordered_batches],
    }


def build_run_campaign_progress_payload(
    *,
    campaign_id: str,
    run_id: str,
    generated_at_utc: datetime,
    started_at: str | None,
    finished_at: str | None,
    batches: list[dict[str, Any]],
    candidate_payload: dict[str, Any] | None,
    screening_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    ordered_batches = sorted((copy.deepcopy(batch) for batch in batches), key=_batch_sort_key)
    status = resolve_campaign_status(batches=ordered_batches)
    resolved_finished_at = finished_at
    if resolved_finished_at is None and status not in {"pending", "running"}:
        resolved_finished_at = generated_at_utc.astimezone(UTC).isoformat()
    return {
        "version": "v1",
        "campaign_id": campaign_id,
        "run_id": run_id,
        "generated_at_utc": generated_at_utc.astimezone(UTC).isoformat(),
        "status": status,
        "started_at": started_at,
        "finished_at": resolved_finished_at,
        "elapsed_seconds": _elapsed_seconds(
            started_at=started_at,
            finished_at=resolved_finished_at,
            generated_at_utc=generated_at_utc,
        ),
        "summary": {
            **summarize_batch_statuses(batches=ordered_batches),
            **summarize_campaign_candidates(
                batches=ordered_batches,
                candidate_payload=candidate_payload,
                screening_payload=screening_payload,
            ),
        },
        "active_batch": _active_batch_summary(ordered_batches),
    }
