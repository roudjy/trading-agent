from __future__ import annotations

import copy
import time
from collections import Counter
from datetime import UTC, datetime
from typing import Any, Callable

from research.candidate_pipeline import (
    SCREENING_PROMOTED,
    SCREENING_REJECTED,
    normalize_screening_decision,
    screening_param_samples,
)

FINAL_STATUS_PASSED = "passed"
FINAL_STATUS_REJECTED = "rejected"
FINAL_STATUS_TIMED_OUT = "timed_out"
FINAL_STATUS_ERRORED = "errored"
FINAL_STATUS_SKIPPED = "skipped"


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _elapsed_seconds(monotonic_source: Callable[[], float], started_at_monotonic: float) -> int:
    return max(0, int(round(monotonic_source() - started_at_monotonic)))


def _elapsed_raw_seconds(monotonic_source: Callable[[], float], started_at_monotonic: float) -> float:
    return max(0.0, monotonic_source() - started_at_monotonic)


def _screening_sort_key(record: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(record["strategy"]),
        str(record["asset"]),
        str(record["interval"]),
        str(record["candidate_id"]),
    )


def build_screening_runtime_records(
    *,
    candidates: list[dict[str, Any]],
    budget_seconds: int,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for candidate in sorted(candidates, key=lambda item: (item["strategy_name"], item["asset"], item["interval"], item["candidate_id"])):
        records.append(
            {
                "candidate_id": str(candidate["candidate_id"]),
                "strategy": str(candidate["strategy_name"]),
                "asset": str(candidate["asset"]),
                "interval": str(candidate["interval"]),
                "stage": "screening",
                "runtime_status": "pending",
                "final_status": None,
                "started_at": None,
                "finished_at": None,
                "elapsed_seconds": 0,
                "budget_seconds": int(budget_seconds),
                "samples_total": None,
                "samples_completed": 0,
                "decision": None,
                "reason_code": None,
                "reason_detail": None,
            }
        )
    return records


def build_screening_sidecar_payload(
    *,
    run_id: str,
    as_of_utc: datetime,
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    ordered_records = sorted((copy.deepcopy(record) for record in records), key=_screening_sort_key)
    runtime_counts = Counter(
        str(record["runtime_status"])
        for record in ordered_records
        if record.get("final_status") is None
    )
    final_counts = Counter(str(record["final_status"]) for record in ordered_records if record.get("final_status"))
    return {
        "version": "v1",
        "run_id": run_id,
        "generated_at_utc": as_of_utc.astimezone(UTC).isoformat(),
        "summary": {
            "candidate_count": len(ordered_records),
            "pending_count": int(runtime_counts.get("pending", 0)),
            "running_count": int(runtime_counts.get("running", 0)),
            "passed_count": int(final_counts.get(FINAL_STATUS_PASSED, 0)),
            "rejected_count": int(final_counts.get(FINAL_STATUS_REJECTED, 0)),
            "timed_out_count": int(final_counts.get(FINAL_STATUS_TIMED_OUT, 0)),
            "errored_count": int(final_counts.get(FINAL_STATUS_ERRORED, 0)),
            "skipped_count": int(final_counts.get(FINAL_STATUS_SKIPPED, 0)),
        },
        "candidates": ordered_records,
    }


def execute_screening_candidate(
    *,
    strategy: dict[str, Any],
    candidate: dict[str, Any],
    engine: Any,
    budget_seconds: int,
    max_samples: int,
    now_source: Callable[[], datetime] | None = None,
    monotonic_source: Callable[[], float] | None = None,
    on_progress: Callable[[dict[str, int]], None] | None = None,
) -> dict[str, Any]:
    now = now_source or _utc_now
    monotonic = monotonic_source or time.monotonic
    started_at = now().astimezone(UTC)
    started_at_monotonic = monotonic()

    if not hasattr(engine, "run"):
        return {
            "legacy_decision": {
                "status": SCREENING_PROMOTED,
                "reason": None,
                "sampled_combination_count": 0,
            },
            "runtime_status": "running",
            "final_status": FINAL_STATUS_PASSED,
            "started_at": started_at.isoformat(),
            "finished_at": now().astimezone(UTC).isoformat(),
            "elapsed_seconds": _elapsed_seconds(monotonic, started_at_monotonic),
            "samples_total": 0,
            "samples_completed": 0,
            "decision": SCREENING_PROMOTED,
            "reason_code": None,
            "reason_detail": None,
        }

    sampled_params = screening_param_samples(strategy.get("params") or {}, max_samples=max_samples)
    samples_total = len(sampled_params)
    sample_results: list[dict[str, Any]] = []

    for sample_index, params in enumerate(sampled_params, start=1):
        if _elapsed_raw_seconds(monotonic, started_at_monotonic) > float(budget_seconds):
            elapsed_seconds = _elapsed_seconds(monotonic, started_at_monotonic)
            return {
                "legacy_decision": {
                    "status": SCREENING_REJECTED,
                    "reason": "candidate_budget_exceeded",
                    "sampled_combination_count": len(sample_results),
                },
                "runtime_status": "running",
                "final_status": FINAL_STATUS_TIMED_OUT,
                "started_at": started_at.isoformat(),
                "finished_at": now().astimezone(UTC).isoformat(),
                "elapsed_seconds": elapsed_seconds,
                "samples_total": samples_total,
                "samples_completed": len(sample_results),
                "decision": SCREENING_REJECTED,
                "reason_code": "candidate_budget_exceeded",
                "reason_detail": f"candidate exceeded screening budget of {int(budget_seconds)} seconds",
            }

        try:
            metrics = engine.run(
                strategy["factory"](**params),
                assets=[candidate["asset"]],
                interval=candidate["interval"],
            )
        except Exception as exc:
            elapsed_seconds = _elapsed_seconds(monotonic, started_at_monotonic)
            return {
                "legacy_decision": {
                    "status": SCREENING_REJECTED,
                    "reason": "screening_candidate_error",
                    "sampled_combination_count": len(sample_results),
                },
                "runtime_status": "running",
                "final_status": FINAL_STATUS_ERRORED,
                "started_at": started_at.isoformat(),
                "finished_at": now().astimezone(UTC).isoformat(),
                "elapsed_seconds": elapsed_seconds,
                "samples_total": samples_total,
                "samples_completed": len(sample_results),
                "decision": SCREENING_REJECTED,
                "reason_code": "screening_candidate_error",
                "reason_detail": str(exc),
            }

        report = getattr(engine, "last_evaluation_report", None) or {}
        evaluation_samples = report.get("evaluation_samples") or {}
        daily_returns = evaluation_samples.get("daily_returns") or []
        if not isinstance(daily_returns, list) or not daily_returns:
            sample_results.append({"status": SCREENING_REJECTED, "reason": "no_oos_samples"})
        else:
            min_trades = int(getattr(engine, "min_trades", 10))
            if int(metrics.get("totaal_trades", 0)) < min_trades:
                sample_results.append({"status": SCREENING_REJECTED, "reason": "insufficient_trades"})
            elif not metrics.get("goedgekeurd", False):
                sample_results.append({"status": SCREENING_REJECTED, "reason": "screening_criteria_not_met"})
            else:
                sample_results.append({"status": SCREENING_PROMOTED, "reason": None})

        if on_progress is not None:
            on_progress(
                {
                    "elapsed_seconds": _elapsed_seconds(monotonic, started_at_monotonic),
                    "samples_completed": sample_index,
                    "samples_total": samples_total,
                }
            )

    legacy_decision = normalize_screening_decision(sample_results)
    final_status = FINAL_STATUS_PASSED if legacy_decision["status"] == SCREENING_PROMOTED else FINAL_STATUS_REJECTED
    reason_code = legacy_decision.get("reason")
    reason_detail = None
    if final_status == FINAL_STATUS_REJECTED and reason_code is not None:
        reason_detail = f"screening rejected after {len(sample_results)} sampled parameter combinations"
    return {
        "legacy_decision": legacy_decision,
        "runtime_status": "running",
        "final_status": final_status,
        "started_at": started_at.isoformat(),
        "finished_at": now().astimezone(UTC).isoformat(),
        "elapsed_seconds": _elapsed_seconds(monotonic, started_at_monotonic),
        "samples_total": samples_total,
        "samples_completed": len(sample_results),
        "decision": legacy_decision["status"],
        "reason_code": reason_code,
        "reason_detail": reason_detail,
    }
