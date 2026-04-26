from __future__ import annotations

import copy
import time
from collections import Counter
from datetime import UTC, datetime
from typing import Any, Callable, Iterable

from agent.backtesting.engine import EngineInterrupted, EngineResumeInvalid
from research.candidate_resume import CandidateResumeState
from research.candidate_pipeline import (
    COVERAGE_WARNING_GRID_UNAVAILABLE,
    SAMPLING_POLICY_GRID_UNAVAILABLE,
    SCREENING_PROMOTED,
    SCREENING_REJECTED,
    normalize_screening_decision,
    sampling_plan_for_param_grid,
)
from research.screening_criteria import apply_phase_aware_criteria

FINAL_STATUS_PASSED = "passed"
FINAL_STATUS_REJECTED = "rejected"
FINAL_STATUS_TIMED_OUT = "timed_out"
FINAL_STATUS_ERRORED = "errored"
FINAL_STATUS_SKIPPED = "skipped"


# v3.15.8: every screening outcome dict carries a ``sampling`` block.
# When the caller has not supplied a SamplingPlan-derived metadata
# dict (legacy / no-engine fast-path / tests that bypass the planner)
# this fallback shape is used so consumers never have to defensively
# probe for missing keys.
_UNAVAILABLE_SAMPLING_METADATA: dict[str, Any] = {
    "grid_size": None,
    "sampled_count": 0,
    "coverage_pct": None,
    "sampling_policy": SAMPLING_POLICY_GRID_UNAVAILABLE,
    "sampled_parameter_digest": "",
    "coverage_warning": COVERAGE_WARNING_GRID_UNAVAILABLE,
}


def _resolve_sampling_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    """Return a defensive copy of the caller-supplied sampling
    metadata, or a fully-populated grid_size_unavailable fallback.
    """
    if metadata is None:
        return dict(_UNAVAILABLE_SAMPLING_METADATA)
    return dict(metadata)


class ScreeningCandidateInterrupted(RuntimeError):
    def __init__(
        self,
        *,
        completed_samples: list[dict[str, Any]],
        active_sample_index: int,
        engine_snapshot,
    ) -> None:
        super().__init__("screening candidate interrupted")
        self.completed_samples = [dict(item) for item in completed_samples]
        self.active_sample_index = int(active_sample_index)
        self.engine_snapshot = engine_snapshot


class ScreeningResumeStateInvalid(RuntimeError):
    """Raised when a persisted screening resume snapshot is incompatible."""


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _elapsed_seconds(monotonic_source: Callable[[], float], started_at_monotonic: float) -> int:
    return max(0, int(round(monotonic_source() - started_at_monotonic)))


def _deadline_monotonic(*, started_at_monotonic: float, budget_seconds: int) -> float:
    return started_at_monotonic + max(0.0, float(budget_seconds))


def _remaining_budget_seconds(
    monotonic_source: Callable[[], float],
    deadline_monotonic: float,
) -> float:
    return deadline_monotonic - monotonic_source()


def _run_engine_sample(
    *,
    engine: Any,
    strategy_callable: Any,
    candidate: dict[str, Any],
    deadline_monotonic: float,
    resume_snapshot: Any,
):
    requirements = candidate.get("strategy_requirements") or {}
    reference_asset = requirements.get("reference_asset")
    run_kwargs: dict[str, Any] = {
        "assets": [candidate["asset"]],
        "interval": candidate["interval"],
        "deadline_monotonic": deadline_monotonic,
        "resume_snapshot": resume_snapshot,
    }
    if reference_asset:
        run_kwargs["reference_asset"] = reference_asset
    try:
        return engine.run(strategy_callable, **run_kwargs)
    except TypeError as exc:
        message = str(exc)
        unexpected = (
            "resume_snapshot" in message
            or "deadline_monotonic" in message
            or "reference_asset" in message
        )
        if unexpected:
            fallback_kwargs: dict[str, Any] = {
                "assets": [candidate["asset"]],
                "interval": candidate["interval"],
            }
            if reference_asset and "reference_asset" not in message:
                fallback_kwargs["reference_asset"] = reference_asset
            return engine.run(strategy_callable, **fallback_kwargs)
        raise


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


def execute_screening_candidate_samples(
    *,
    candidate: dict[str, Any],
    engine: Any,
    budget_seconds: int,
    strategy_samples: Iterable[tuple[dict[str, Any], Any]],
    samples_total: int,
    resume_state: CandidateResumeState | None = None,
    now_source: Callable[[], datetime] | None = None,
    monotonic_source: Callable[[], float] | None = None,
    on_progress: Callable[[dict[str, int]], None] | None = None,
    on_checkpoint: Callable[[list[dict[str, Any]]], None] | None = None,
    screening_phase: str | None = None,
    sampling_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    now = now_source or _utc_now
    monotonic = monotonic_source or time.monotonic
    started_at = now().astimezone(UTC)
    started_at_monotonic = monotonic()
    deadline_monotonic = _deadline_monotonic(
        started_at_monotonic=started_at_monotonic,
        budget_seconds=budget_seconds,
    )
    # v3.15.8: every return path of this function MUST surface the
    # ``sampling`` block so screening_evidence (v3.15.9) and
    # campaign_funnel_policy (v3.15.10) can rely on it being present.
    resolved_sampling_metadata = _resolve_sampling_metadata(sampling_metadata)

    def _timed_out_outcome(*, samples_completed: int) -> dict[str, Any]:
        elapsed_seconds = _elapsed_seconds(monotonic, started_at_monotonic)
        return {
            "legacy_decision": {
                "status": SCREENING_REJECTED,
                "reason": "candidate_budget_exceeded",
                "sampled_combination_count": samples_completed,
            },
            "runtime_status": "running",
            "final_status": FINAL_STATUS_TIMED_OUT,
            "started_at": started_at.isoformat(),
            "finished_at": now().astimezone(UTC).isoformat(),
            "elapsed_seconds": elapsed_seconds,
            "samples_total": samples_total,
            "samples_completed": samples_completed,
            "decision": SCREENING_REJECTED,
            "reason_code": "candidate_budget_exceeded",
            "reason_detail": f"candidate exceeded screening budget of {int(budget_seconds)} seconds",
            "sampling": dict(resolved_sampling_metadata),
        }

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
            "sampling": dict(resolved_sampling_metadata),
        }

    sample_results = [dict(item) for item in (resume_state.completed_samples if resume_state is not None else ())]
    active_sample_index = resume_state.active_sample_index if resume_state is not None else None
    active_snapshot = resume_state.active_snapshot if resume_state is not None else None
    # v3.15.7: track the most recent sample's metrics so the
    # aggregate outcome dict can surface ``diagnostic_metrics`` for
    # observability even when the loop terminates without a winning
    # sample.
    last_metrics: dict[str, Any] = {}

    for sample_index, (_params, strategy_callable) in enumerate(strategy_samples):
        if sample_index < len(sample_results):
            continue
        if _remaining_budget_seconds(monotonic, deadline_monotonic) <= 0:
            return _timed_out_outcome(samples_completed=len(sample_results))

        try:
            metrics = _run_engine_sample(
                engine=engine,
                strategy_callable=strategy_callable,
                candidate=candidate,
                deadline_monotonic=deadline_monotonic,
                resume_snapshot=active_snapshot if active_sample_index == sample_index else None,
            )
            last_metrics = metrics if isinstance(metrics, dict) else {}
        except EngineInterrupted as exc:
            raise ScreeningCandidateInterrupted(
                completed_samples=sample_results,
                active_sample_index=sample_index,
                engine_snapshot=exc.snapshot,
            ) from exc
        except EngineResumeInvalid as exc:
            raise ScreeningResumeStateInvalid(str(exc)) from exc
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
                "sampling": dict(resolved_sampling_metadata),
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
            else:
                # v3.15.7: phase-aware criteria dispatch. Pre-checks
                # above (no_oos_samples / insufficient_trades) are NOT
                # duplicated inside ``apply_phase_aware_criteria``.
                passed, reason = apply_phase_aware_criteria(metrics, screening_phase)
                if passed:
                    sample_results.append({"status": SCREENING_PROMOTED, "reason": None})
                else:
                    sample_results.append({"status": SCREENING_REJECTED, "reason": reason})
        if on_checkpoint is not None:
            on_checkpoint(sample_results)

        if _remaining_budget_seconds(monotonic, deadline_monotonic) <= 0:
            return _timed_out_outcome(samples_completed=len(sample_results))

        if on_progress is not None:
            on_progress(
                {
                    "elapsed_seconds": _elapsed_seconds(monotonic, started_at_monotonic),
                    "samples_completed": len(sample_results),
                    "samples_total": samples_total,
                }
            )

    legacy_decision = normalize_screening_decision(sample_results)
    final_status = FINAL_STATUS_PASSED if legacy_decision["status"] == SCREENING_PROMOTED else FINAL_STATUS_REJECTED
    reason_code = legacy_decision.get("reason")
    reason_detail = None
    if final_status == FINAL_STATUS_REJECTED and reason_code is not None:
        reason_detail = f"screening rejected after {len(sample_results)} sampled parameter combinations"
    # v3.15.7: additive outcome fields for phase-aware visibility.
    # ``pass_kind`` is set ONLY on screening pass (mirrors phase);
    # rejected → None (failure semantics live in reason_code).
    # NB: NO ``screening_phase`` key here — v3.15.6 invariant.
    pass_kind: str | None
    if legacy_decision["status"] == SCREENING_PROMOTED:
        pass_kind = screening_phase
    else:
        pass_kind = None
    screening_criteria_set = (
        "exploratory" if screening_phase == "exploratory" else "legacy"
    )
    # JSON-safe finite floats (engine.profit_factor uses
    # PROFIT_FACTOR_NO_LOSS_CAP; expectancy is a finite mean).
    # ``last_metrics`` holds the most recent sample's metrics dict
    # (or {} when no sample produced metrics yet).
    diagnostic_metrics = {
        "expectancy": float(last_metrics.get("expectancy", 0.0)),
        "profit_factor": float(last_metrics.get("profit_factor", 0.0)),
        "win_rate": float(last_metrics.get("win_rate", 0.0)),
        "max_drawdown": float(last_metrics.get("max_drawdown", 0.0)),
    }
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
        # v3.15.7 additive — non-frozen screening sidecar surfaces only.
        "pass_kind": pass_kind,
        "screening_criteria_set": screening_criteria_set,
        "diagnostic_metrics": diagnostic_metrics,
        # v3.15.8 additive — sampling-policy metadata for the
        # screening evidence artifact (v3.15.9) and campaign
        # funnel policy (v3.15.10). Always present, even on
        # legacy/no-engine/error/timeout paths.
        "sampling": dict(resolved_sampling_metadata),
    }


def execute_screening_candidate(
    *,
    strategy: dict[str, Any],
    candidate: dict[str, Any],
    engine: Any,
    budget_seconds: int,
    max_samples: int,
    resume_state: CandidateResumeState | None = None,
    now_source: Callable[[], datetime] | None = None,
    monotonic_source: Callable[[], float] | None = None,
    on_progress: Callable[[dict[str, int]], None] | None = None,
    on_checkpoint: Callable[[list[dict[str, Any]]], None] | None = None,
    screening_phase: str | None = None,
) -> dict[str, Any]:
    plan = sampling_plan_for_param_grid(
        strategy.get("params"),
        max_samples_for_legacy=max_samples,
    )
    return execute_screening_candidate_samples(
        candidate=candidate,
        engine=engine,
        budget_seconds=budget_seconds,
        strategy_samples=(
            (params, strategy["factory"](**params)) for params in plan.samples
        ),
        samples_total=plan.sampled_count,
        resume_state=resume_state,
        now_source=now_source,
        monotonic_source=monotonic_source,
        on_progress=on_progress,
        on_checkpoint=on_checkpoint,
        screening_phase=screening_phase,
        sampling_metadata=plan.metadata(),
    )
