from __future__ import annotations

import copy
import hashlib
import json
import re
from collections import Counter
from datetime import UTC, datetime
from typing import Any


def _canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def _hash_payload(payload: Any) -> str:
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _slug(value: str) -> str:
    compact = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return compact or "unknown"


def _batch_sort_key(record: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(record["strategy_family"]),
        str(record["interval"]),
        str(record["batch_id"]),
    )


def build_batch_id(*, strategy_family: str, interval: str, candidate_ids: list[str]) -> str:
    payload = {
        "strategy_family": strategy_family,
        "interval": interval,
        "candidate_ids": list(candidate_ids),
    }
    stable_hash = _hash_payload(payload)[:8]
    return f"batch-{_slug(strategy_family)}-{_slug(interval)}-{stable_hash}"


def partition_execution_batches(*, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for candidate in sorted(
        candidates,
        key=lambda item: (
            str(item["strategy_family"]),
            str(item["interval"]),
            str(item["strategy_name"]),
            str(item["asset"]),
            str(item["candidate_id"]),
        ),
    ):
        key = (str(candidate["strategy_family"]), str(candidate["interval"]))
        grouped.setdefault(key, []).append(candidate)

    batches: list[dict[str, Any]] = []
    for batch_index, key in enumerate(sorted(grouped), start=1):
        strategy_family, interval = key
        batch_candidates = grouped[key]
        candidate_ids = [str(candidate["candidate_id"]) for candidate in batch_candidates]
        assets = sorted({str(candidate["asset"]) for candidate in batch_candidates})
        strategy_names = sorted({str(candidate["strategy_name"]) for candidate in batch_candidates})
        batches.append(
            {
                "batch_id": build_batch_id(
                    strategy_family=strategy_family,
                    interval=interval,
                    candidate_ids=candidate_ids,
                ),
                "batch_index": int(batch_index),
                "strategy_family": strategy_family,
                "interval": interval,
                "partition": {
                    "strategy_family": strategy_family,
                    "interval": interval,
                },
                "status": "pending",
                "current_stage": "screening",
                "started_at": None,
                "finished_at": None,
                "elapsed_seconds": 0,
                "candidate_count": len(candidate_ids),
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
                "candidate_summary": {
                    "asset_count": len(assets),
                    "strategy_count": len(strategy_names),
                    "assets": assets,
                    "strategies": strategy_names,
                },
                "attempt_count": 1,
                "execution_mode": None,
                "error_type": None,
                "reason_code": None,
                "reason_detail": None,
                "last_attempt_reason": "fresh_run",
            }
        )
    return sorted(batches, key=_batch_sort_key)


def build_run_batches_payload(
    *,
    run_id: str,
    as_of_utc: datetime,
    batches: list[dict[str, Any]],
) -> dict[str, Any]:
    ordered_batches = sorted((copy.deepcopy(batch) for batch in batches), key=_batch_sort_key)
    status_counts = Counter(str(batch["status"]) for batch in ordered_batches)
    return {
        "version": "v1",
        "run_id": run_id,
        "generated_at_utc": as_of_utc.astimezone(UTC).isoformat(),
        "summary": {
            "batch_count": len(ordered_batches),
            "pending_count": int(status_counts.get("pending", 0)),
            "running_count": int(status_counts.get("running", 0)),
            "completed_count": int(status_counts.get("completed", 0)),
            "partial_count": int(status_counts.get("partial", 0)),
            "failed_count": int(status_counts.get("failed", 0)),
            "skipped_count": int(status_counts.get("skipped", 0)),
        },
        "batches": ordered_batches,
    }


def build_batch_manifest_payload(
    *,
    run_id: str,
    batch: dict[str, Any],
) -> dict[str, Any]:
    return {
        "version": "v1",
        "run_id": run_id,
        "batch_id": str(batch["batch_id"]),
        "batch_index": int(batch["batch_index"]),
        "partition": copy.deepcopy(batch["partition"]),
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
        "result_success_count": int(batch.get("result_success_count") or 0),
        "result_failed_count": int(batch.get("result_failed_count") or 0),
        "candidate_summary": copy.deepcopy(batch.get("candidate_summary") or {}),
        "candidate_ids": list(batch.get("candidate_ids") or []),
        "attempt_count": int(batch.get("attempt_count") or 1),
        "execution_mode": batch.get("execution_mode"),
        "error_type": batch.get("error_type"),
        "reason_code": batch.get("reason_code"),
        "reason_detail": batch.get("reason_detail"),
        "last_attempt_reason": batch.get("last_attempt_reason"),
    }
