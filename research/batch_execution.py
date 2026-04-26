from __future__ import annotations

import json
import time
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

from agent.backtesting.engine import BacktestEngine, EvaluationScheduleError, FoldLeakageError
from research.candidate_pipeline import SCREENING_PROMOTED, screening_param_samples
from research.registry import get_enabled_strategies
from research.results import make_result_row
from research.screening_process import execute_screening_candidate_isolated
from research.screening_runtime import (
    FINAL_STATUS_ERRORED,
    FINAL_STATUS_PASSED,
    FINAL_STATUS_REJECTED,
    FINAL_STATUS_TIMED_OUT,
    build_screening_runtime_records,
)


def _compute_robustness(folds: list[dict[str, Any]]) -> dict[str, Any]:
    fold_count = len(folds)
    oos_bars = sum(f["test"][1] - f["test"][0] + 1 for f in folds) if folds else 0
    total_bars_covered = 0
    if folds:
        min_start = min(f["train"][0] for f in folds)
        max_end = max(f["test"][1] for f in folds)
        total_bars_covered = max_end - min_start + 1
    oos_coverage_ratio = round(oos_bars / total_bars_covered, 4) if total_bars_covered > 0 else 0.0
    return {
        "fold_count": fold_count,
        "oos_bar_coverage": oos_bars,
        "total_bars_covered": total_bars_covered,
        "oos_coverage_ratio": oos_coverage_ratio,
    }


def _sidecar_strategy_entry(
    *,
    strategy: dict[str, Any],
    asset: str,
    interval: str,
    report: dict[str, Any],
) -> dict[str, Any]:
    folds = report.get("folds", [])
    return {
        "strategy_name": strategy["name"],
        "asset": asset,
        "interval": interval,
        "selected_params": report.get("selected_params", {}),
        "selection_metric": report.get("selection_metric", "sharpe"),
        "is_summary": report.get("is_summary", {}),
        "oos_summary": report.get("oos_summary", {}),
        "folds": folds,
        "leakage_checks_ok": report.get("leakage_checks_ok", False),
        "robustness": _compute_robustness(folds),
    }


def _build_engine(
    *,
    start_datum: str,
    eind_datum: str,
    evaluation_config: dict[str, Any],
    regime_config: dict[str, Any] | None,
) -> BacktestEngine:
    try:
        return BacktestEngine(
            start_datum=start_datum,
            eind_datum=eind_datum,
            evaluation_config=evaluation_config,
            regime_config=regime_config,
        )
    except TypeError as exc:
        if "regime_config" in str(exc):
            try:
                return BacktestEngine(
                    start_datum=start_datum,
                    eind_datum=eind_datum,
                    evaluation_config=evaluation_config,
                )
            except TypeError as exc2:
                if "evaluation_config" not in str(exc2):
                    raise
                return BacktestEngine(
                    start_datum=start_datum,
                    eind_datum=eind_datum,
                )
        if "evaluation_config" not in str(exc):
            raise
        return BacktestEngine(
            start_datum=start_datum,
            eind_datum=eind_datum,
        )


def _strategy_lookup() -> dict[str, dict[str, Any]]:
    return {
        str(strategy["name"]): strategy
        for strategy in get_enabled_strategies()
    }


def execute_screening_batch(
    *,
    batch: dict[str, Any],
    batch_candidates: list[dict[str, Any]],
    interval_ranges: dict[str, dict[str, str]],
    evaluation_config: dict[str, Any],
    regime_config: dict[str, Any] | None,
    screening_candidate_budget_seconds: int,
    screening_param_sample_limit: int,
) -> dict[str, Any]:
    started_monotonic = time.monotonic()
    updated_batch = deepcopy(batch)
    updated_batch["current_stage"] = "screening"
    updated_batch["started_at"] = updated_batch.get("started_at") or datetime.now(UTC).isoformat()
    updated_batch["finished_at"] = None
    updated_batch["error_type"] = None

    strategies_by_name = _strategy_lookup()
    runtime_records = build_screening_runtime_records(
        candidates=batch_candidates,
        budget_seconds=screening_candidate_budget_seconds,
    )
    runtime_records_by_id = {
        str(record["candidate_id"]): record
        for record in runtime_records
    }
    candidate_updates: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    provenance_events: list[Any] = []

    try:
        for candidate in batch_candidates:
            candidate_id = str(candidate["candidate_id"])
            strategy = strategies_by_name[str(candidate["strategy_name"])]
            sampled_params = screening_param_samples(
                strategy.get("params") or {},
                max_samples=screening_param_sample_limit,
            )
            runtime_record = runtime_records_by_id[candidate_id]
            runtime_record["runtime_status"] = "running"
            runtime_record["final_status"] = None
            runtime_record["started_at"] = datetime.now(UTC).isoformat()
            runtime_record["finished_at"] = None
            runtime_record["elapsed_seconds"] = 0
            runtime_record["samples_completed"] = 0
            runtime_record["samples_total"] = len(sampled_params)
            runtime_record["decision"] = None
            runtime_record["reason_code"] = None
            runtime_record["reason_detail"] = None

            try:
                start_datum = interval_ranges[str(candidate["interval"])]["start"]
                eind_datum = interval_ranges[str(candidate["interval"])]["end"]
                # v3.15.6: batch_execution has neither a preset nor a
                # tracker in scope. We pass ``screening_phase=None``
                # explicitly to forbid hidden inference from
                # screening_mode / preset_class / hypothesis_id /
                # diagnostic flags. Run-level propagation lives in
                # run_research.py.
                isolated_result = execute_screening_candidate_isolated(
                    strategy=strategy,
                    candidate=candidate,
                    interval_range={"start": start_datum, "end": eind_datum},
                    evaluation_config=evaluation_config,
                    regime_config=regime_config,
                    budget_seconds=screening_candidate_budget_seconds,
                    max_samples=screening_param_sample_limit,
                    engine_class=BacktestEngine,
                    screening_phase=None,
                )
                outcome = dict(isolated_result["outcome"])
            except Exception as exc:
                outcome = {
                    "legacy_decision": {
                        "status": "rejected_in_screening",
                        "reason": "screening_candidate_error",
                        "sampled_combination_count": runtime_record["samples_completed"],
                    },
                    "runtime_status": "running",
                    "final_status": FINAL_STATUS_ERRORED,
                    "started_at": runtime_record["started_at"],
                    "finished_at": datetime.now(UTC).isoformat(),
                    "elapsed_seconds": int(runtime_record["elapsed_seconds"]),
                    "samples_total": runtime_record["samples_total"],
                    "samples_completed": runtime_record["samples_completed"],
                    "decision": "rejected_in_screening",
                    "reason_code": "screening_candidate_error",
                    "reason_detail": str(exc),
                }
                isolated_result = {"provenance_events": []}
            provenance_events.extend(isolated_result.get("provenance_events") or [])

            runtime_record.update(outcome)
            runtime_record["elapsed_seconds"] = int(runtime_record.get("elapsed_seconds") or 0)
            runtime_record["samples_total"] = int(runtime_record.get("samples_total") or 0)
            runtime_record["samples_completed"] = int(runtime_record.get("samples_completed") or 0)

            decision = dict(outcome["legacy_decision"])
            candidate_updates.append(
                {
                    "candidate_id": candidate_id,
                    "screening": dict(decision),
                    "current_status": (
                        "promoted_to_validation"
                        if decision["status"] == SCREENING_PROMOTED
                        else "screening_rejected"
                    ),
                }
            )

            if runtime_record["final_status"] == FINAL_STATUS_TIMED_OUT:
                updated_batch["timed_out_count"] += 1
                updated_batch["completed_candidate_count"] += 1
                events.append(
                    {
                        "event": "screening_candidate_timeout",
                        "candidate_id": candidate_id,
                        "strategy": candidate["strategy_name"],
                        "asset": candidate["asset"],
                        "interval": candidate["interval"],
                        "elapsed_seconds": runtime_record["elapsed_seconds"],
                        "samples_completed": runtime_record["samples_completed"],
                        "samples_total": runtime_record["samples_total"],
                        "decision": runtime_record["decision"],
                        "reason_code": runtime_record["reason_code"],
                    }
                )
            elif runtime_record["final_status"] == FINAL_STATUS_ERRORED:
                updated_batch["errored_count"] += 1
                updated_batch["completed_candidate_count"] += 1
                events.append(
                    {
                        "event": "screening_candidate_error",
                        "candidate_id": candidate_id,
                        "strategy": candidate["strategy_name"],
                        "asset": candidate["asset"],
                        "interval": candidate["interval"],
                        "elapsed_seconds": runtime_record["elapsed_seconds"],
                        "samples_completed": runtime_record["samples_completed"],
                        "samples_total": runtime_record["samples_total"],
                        "decision": runtime_record["decision"],
                        "reason_code": runtime_record["reason_code"],
                        "reason_detail": runtime_record["reason_detail"],
                    }
                )
            elif decision["status"] == SCREENING_PROMOTED:
                updated_batch["promoted_candidate_count"] += 1
                events.append(
                    {
                        "event": "screening_candidate_decision",
                        "candidate_id": candidate_id,
                        "strategy": candidate["strategy_name"],
                        "asset": candidate["asset"],
                        "interval": candidate["interval"],
                        "elapsed_seconds": runtime_record["elapsed_seconds"],
                        "samples_completed": runtime_record["samples_completed"],
                        "samples_total": runtime_record["samples_total"],
                        "decision": runtime_record["decision"],
                        "reason_code": runtime_record["reason_code"],
                    }
                )
            else:
                updated_batch["screening_rejected_count"] += 1
                updated_batch["completed_candidate_count"] += 1
                events.append(
                    {
                        "event": "screening_candidate_decision",
                        "candidate_id": candidate_id,
                        "strategy": candidate["strategy_name"],
                        "asset": candidate["asset"],
                        "interval": candidate["interval"],
                        "elapsed_seconds": runtime_record["elapsed_seconds"],
                        "samples_completed": runtime_record["samples_completed"],
                        "samples_total": runtime_record["samples_total"],
                        "decision": runtime_record["decision"],
                        "reason_code": runtime_record["reason_code"],
                    }
                )

            events.append(
                {
                    "event": "screening_candidate_finished",
                    "candidate_id": candidate_id,
                    "strategy": candidate["strategy_name"],
                    "asset": candidate["asset"],
                    "interval": candidate["interval"],
                    "elapsed_seconds": runtime_record["elapsed_seconds"],
                    "samples_completed": runtime_record["samples_completed"],
                    "samples_total": runtime_record["samples_total"],
                    "final_status": runtime_record["final_status"],
                    "decision": runtime_record["decision"],
                    "reason_code": runtime_record["reason_code"],
                }
            )

        updated_batch["finished_at"] = datetime.now(UTC).isoformat()
        updated_batch["elapsed_seconds"] = max(0, int(round(time.monotonic() - started_monotonic)))
        if updated_batch["promoted_candidate_count"] == 0:
            if updated_batch["timed_out_count"] > 0 or updated_batch["errored_count"] > 0:
                updated_batch["status"] = "partial"
                updated_batch["current_stage"] = "screening"
                updated_batch["reason_code"] = "isolated_candidate_execution_issues"
                updated_batch["reason_detail"] = "batch completed with screening timeout/error isolation"
            else:
                updated_batch["status"] = "completed"
                updated_batch["current_stage"] = "screening"
        else:
            updated_batch["status"] = "pending"
            updated_batch["current_stage"] = "validation"
            updated_batch["finished_at"] = None

        return {
            "batch": updated_batch,
            "candidate_updates": candidate_updates,
            "screening_records": runtime_records,
            "events": events,
            "provenance_events": provenance_events,
            "completed_candidates": sum(
                1 for record in runtime_records if record.get("final_status") is not None
            ),
            "last_record": next(
                (
                    deepcopy(record)
                    for record in reversed(runtime_records)
                    if record.get("final_status") is not None
                ),
                None,
            ),
        }
    except Exception as exc:
        updated_batch["status"] = "failed"
        updated_batch["current_stage"] = "screening"
        updated_batch["finished_at"] = datetime.now(UTC).isoformat()
        updated_batch["elapsed_seconds"] = max(0, int(round(time.monotonic() - started_monotonic)))
        updated_batch["reason_code"] = "batch_execution_failed"
        updated_batch["reason_detail"] = str(exc)
        updated_batch["error_type"] = type(exc).__name__
        return {
            "batch": updated_batch,
            "candidate_updates": candidate_updates,
            "screening_records": runtime_records,
            "events": events,
            "provenance_events": provenance_events,
            "completed_candidates": sum(
                1 for record in runtime_records if record.get("final_status") is not None
            ),
            "last_record": next(
                (
                    deepcopy(record)
                    for record in reversed(runtime_records)
                    if record.get("final_status") is not None
                ),
                None,
            ),
        }


def execute_validation_batch(
    *,
    batch: dict[str, Any],
    batch_candidates: list[dict[str, Any]],
    interval_ranges: dict[str, dict[str, str]],
    evaluation_config: dict[str, Any],
    regime_config: dict[str, Any] | None,
    as_of_utc: datetime,
) -> dict[str, Any]:
    started_monotonic = time.monotonic()
    updated_batch = deepcopy(batch)
    updated_batch["current_stage"] = "validation"
    updated_batch["started_at"] = updated_batch.get("started_at") or datetime.now(UTC).isoformat()
    updated_batch["finished_at"] = None
    updated_batch["error_type"] = None

    strategies_by_name = _strategy_lookup()
    candidate_updates: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    evaluations: list[dict[str, Any]] = []
    walk_forward_reports: list[dict[str, Any]] = []
    provenance_events: list[Any] = []

    try:
        for candidate in batch_candidates:
            strategy = strategies_by_name[str(candidate["strategy_name"])]
            start_datum = interval_ranges[str(candidate["interval"])]["start"]
            eind_datum = interval_ranges[str(candidate["interval"])]["end"]
            engine = _build_engine(
                start_datum=start_datum,
                eind_datum=eind_datum,
                evaluation_config=evaluation_config,
                regime_config=regime_config,
            )
            try:
                requirements = candidate.get("strategy_requirements") or {}
                reference_asset = requirements.get("reference_asset")
                grid_kwargs: dict[str, Any] = {
                    "strategie_factory": strategy["factory"],
                    "param_grid": strategy["params"],
                    "assets": [candidate["asset"]],
                    "interval": candidate["interval"],
                }
                if reference_asset:
                    grid_kwargs["reference_asset"] = reference_asset
                try:
                    metrics = engine.grid_search(**grid_kwargs)
                except TypeError as exc:
                    if reference_asset and "reference_asset" in str(exc):
                        grid_kwargs.pop("reference_asset", None)
                        metrics = engine.grid_search(**grid_kwargs)
                    else:
                        raise
                params_used = metrics.get("beste_params", {})
                row = make_result_row(
                    strategy=strategy,
                    asset=candidate["asset"],
                    interval=candidate["interval"],
                    params=params_used,
                    as_of_utc=as_of_utc,
                    metrics=metrics,
                )
                evaluation_report = getattr(engine, "last_evaluation_report", None)
                if evaluation_report is not None:
                    walk_forward_reports.append(
                        _sidecar_strategy_entry(
                            strategy=strategy,
                            asset=candidate["asset"],
                            interval=candidate["interval"],
                            report=evaluation_report,
                        )
                    )
                    evaluations.append(
                        {
                            "family": strategy["family"],
                            "interval": candidate["interval"],
                            "selected_params": json.loads(row["params_json"]),
                            "evaluation_report": evaluation_report,
                            "row": row,
                        }
                    )
            except (EvaluationScheduleError, FoldLeakageError):
                raise
            except Exception as exc:
                row = make_result_row(
                    strategy=strategy,
                    asset=candidate["asset"],
                    interval=candidate["interval"],
                    params={},
                    as_of_utc=as_of_utc,
                    metrics={},
                    error=str(exc),
                )

            provenance_events.extend(getattr(engine, "_provenance_events", []))
            rows.append(row)
            candidate_updates.append(
                {
                    "candidate_id": str(candidate["candidate_id"]),
                    "validation": {
                        "status": "validated",
                        "result_success": bool(row["success"]),
                    },
                    "current_status": "validated",
                }
            )
            updated_batch["validated_candidate_count"] += 1
            updated_batch["completed_candidate_count"] += 1
            if row["success"]:
                updated_batch["result_success_count"] += 1
            else:
                updated_batch["result_failed_count"] += 1
                updated_batch["validation_error_count"] += 1

        updated_batch["finished_at"] = datetime.now(UTC).isoformat()
        updated_batch["elapsed_seconds"] = max(0, int(round(time.monotonic() - started_monotonic)))
        if (
            updated_batch["timed_out_count"] > 0
            or updated_batch["errored_count"] > 0
            or updated_batch["validation_error_count"] > 0
        ):
            updated_batch["status"] = "partial"
            updated_batch["current_stage"] = "validation"
            if updated_batch.get("reason_code") is None:
                updated_batch["reason_code"] = "isolated_candidate_execution_issues"
                updated_batch["reason_detail"] = "batch completed with candidate-level timeout/error isolation"
        else:
            updated_batch["status"] = "completed"
            updated_batch["current_stage"] = "validation"

        return {
            "batch": updated_batch,
            "candidate_updates": candidate_updates,
            "rows": rows,
            "evaluations": evaluations,
            "walk_forward_reports": walk_forward_reports,
            "provenance_events": provenance_events,
            "completed_candidates": len(batch_candidates),
        }
    except Exception as exc:
        updated_batch["status"] = "failed"
        updated_batch["current_stage"] = "validation"
        updated_batch["finished_at"] = datetime.now(UTC).isoformat()
        updated_batch["elapsed_seconds"] = max(0, int(round(time.monotonic() - started_monotonic)))
        updated_batch["reason_code"] = "batch_execution_failed"
        updated_batch["reason_detail"] = str(exc)
        updated_batch["error_type"] = type(exc).__name__
        return {
            "batch": updated_batch,
            "candidate_updates": candidate_updates,
            "rows": rows,
            "evaluations": evaluations,
            "walk_forward_reports": walk_forward_reports,
            "provenance_events": provenance_events,
            "completed_candidates": len(candidate_updates),
        }
