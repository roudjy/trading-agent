from __future__ import annotations

import copy
import time
from collections import Counter
from datetime import UTC, datetime
from typing import Any, Callable, Iterable

from agent.backtesting.engine import EngineInterrupted, EngineResumeInvalid
from agent.backtesting.thin_strategy import build_features_for, is_thin_strategy
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
from research.screening_criteria import build_exploratory_criteria_checks

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


def _trade_distribution(trade_pnls: list[Any]) -> dict[str, Any]:
    values = [float(value) for value in trade_pnls]
    wins = [value for value in values if value > 0.0]
    losses = [value for value in values if value < 0.0]

    def _avg(items: list[float]) -> float:
        return float(sum(items) / len(items)) if items else 0.0

    sorted_values = sorted(values)
    if not sorted_values:
        median = 0.0
    elif len(sorted_values) % 2 == 1:
        median = float(sorted_values[len(sorted_values) // 2])
    else:
        hi = len(sorted_values) // 2
        median = float((sorted_values[hi - 1] + sorted_values[hi]) / 2.0)

    avg_win = _avg(wins)
    avg_loss = _avg(losses)
    win_loss_ratio = (
        float(avg_win / abs(avg_loss))
        if avg_win > 0.0 and avg_loss < 0.0
        else 0.0
    )

    return {
        "trade_count": len(values),
        "avg_trade_pnl": round(_avg(values), 6),
        "median_trade_pnl": round(median, 6),
        "avg_win": round(avg_win, 6),
        "avg_loss": round(avg_loss, 6),
        "largest_win": round(max(wins), 6) if wins else 0.0,
        "largest_loss": round(min(losses), 6) if losses else 0.0,
        "win_loss_ratio": round(win_loss_ratio, 6),
    }

def _classify_trend_pullback_exit_reason(
    *,
    pullback_distance: Any,
    ema_fast: Any,
    ema_slow: Any,
    exit_kind: Any,
) -> str:
    if str(exit_kind or "") == "window_end":
        return "window_end"

    try:
        pd_dist = float(pullback_distance)
        fast = float(ema_fast)
        slow = float(ema_slow)
    except (TypeError, ValueError):
        return "signal_change_unknown"

    pullback_resolved = pd_dist > 0.0
    trend_break = fast <= slow

    if pullback_resolved and trend_break:
        return "pullback_resolved_and_trend_break"
    if pullback_resolved:
        return "pullback_resolved"
    if trend_break:
        return "trend_break"
    return "signal_change_unknown"


def _trend_pullback_exit_reason_summary(
    *,
    trade_events: list[Any],
    features_by_timestamp: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    reason_counts = Counter()
    pnl_by_reason: dict[str, list[float]] = {}

    for trade in trade_events:
        if not isinstance(trade, dict):
            continue

        decision_ts = trade.get("exit_decision_timestamp_utc")
        feature_row = features_by_timestamp.get(str(decision_ts), {})
        reason = _classify_trend_pullback_exit_reason(
            pullback_distance=feature_row.get("pullback_distance"),
            ema_fast=feature_row.get("ema_fast"),
            ema_slow=feature_row.get("ema_slow"),
            exit_kind=trade.get("exit_kind"),
        )
        reason_counts[reason] += 1
        try:
            pnl = float(trade.get("pnl", 0.0))
        except (TypeError, ValueError):
            pnl = 0.0
        pnl_by_reason.setdefault(reason, []).append(pnl)

    def _pnl_summary(values: list[float]) -> dict[str, Any]:
        losses = [value for value in values if value < 0.0]
        winners = [value for value in values if value > 0.0]
        return {
            "trade_count": int(len(values)),
            "avg_pnl": float(sum(values) / len(values)) if values else 0.0,
            "loss_count": int(len(losses)),
            "winner_count": int(len(winners)),
            "largest_loss": float(min(values)) if values else 0.0,
            "largest_win": float(max(values)) if values else 0.0,
        }

    trade_count = sum(reason_counts.values())
    return {
        "trade_count": int(trade_count),
        "exit_reason_counts": dict(sorted(reason_counts.items())),
        "exit_reason_pnl_summary": {
            reason: _pnl_summary(values)
            for reason, values in sorted(pnl_by_reason.items())
        },
        "pullback_resolved_count": int(reason_counts.get("pullback_resolved", 0)),
        "trend_break_count": int(reason_counts.get("trend_break", 0)),
        "pullback_resolved_and_trend_break_count": int(
            reason_counts.get("pullback_resolved_and_trend_break", 0)
        ),
        "window_end_count": int(reason_counts.get("window_end", 0)),
        "signal_change_unknown_count": int(
            reason_counts.get("signal_change_unknown", 0)
        ),
    }


def _trend_pullback_features_by_timestamp(
    *,
    engine: Any,
    strategy_callable: Any,
    candidate: dict[str, Any],
    evaluation_report: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    required_aliases = {"ema_fast", "ema_slow", "pullback_distance"}
    if not is_thin_strategy(strategy_callable):
        return {}

    requirements = getattr(strategy_callable, "_feature_requirements", None)
    if not requirements:
        return {}

    aliases = {
        str(getattr(requirement, "alias", ""))
        for requirement in requirements
    }
    if not required_aliases.issubset(aliases):
        return {}

    load_data = getattr(engine, "_laad_data", None)
    timestamp_to_utc_iso = getattr(engine, "_timestamp_to_utc_iso", None)
    if load_data is None or timestamp_to_utc_iso is None:
        return {}

    asset = str(candidate.get("asset") or "")
    interval = str(candidate.get("interval") or "")
    if not asset or not interval:
        return {}

    try:
        frame = load_data(asset, interval)
        if frame is None:
            return {}
    except Exception:
        return {}

    folds_by_asset = evaluation_report.get("folds_by_asset") or {}
    folds = folds_by_asset.get(asset) or evaluation_report.get("folds") or []
    if not folds:
        return {}

    by_timestamp: dict[str, dict[str, Any]] = {}
    for fold in folds:
        test_bounds = fold.get("test") if isinstance(fold, dict) else None
        if not isinstance(test_bounds, list) or len(test_bounds) != 2:
            continue

        try:
            test_start = int(test_bounds[0])
            test_end = int(test_bounds[1])
        except (TypeError, ValueError):
            continue

        try:
            fold_frame = frame.iloc[test_start : test_end + 1].copy()
            if len(fold_frame) == 0:
                continue
            features = build_features_for(requirements, fold_frame)
        except Exception:
            continue

        for timestamp in fold_frame.index:
            timestamp_utc = str(timestamp_to_utc_iso(timestamp))
            by_timestamp[timestamp_utc] = {
                "ema_fast": features["ema_fast"].get(timestamp),
                "ema_slow": features["ema_slow"].get(timestamp),
                "pullback_distance": features["pullback_distance"].get(timestamp),
            }

    return by_timestamp


def _safe_mean(values: list[float]) -> float:
    return float(sum(values) / len(values)) if values else 0.0


def _trade_key(record: dict[str, Any]) -> tuple[str, Any, str, str]:
    return (
        str(record.get("asset") or ""),
        record.get("fold_index"),
        str(record.get("entry_timestamp_utc") or ""),
        str(record.get("exit_timestamp_utc") or ""),
    )


def _exit_diagnostics_by_trade_key(
    exit_diagnostics: dict[str, Any] | None,
) -> dict[tuple[str, Any, str, str], dict[str, Any]]:
    if not isinstance(exit_diagnostics, dict):
        return {}

    by_key: dict[tuple[str, Any, str, str], dict[str, Any]] = {}
    per_window = exit_diagnostics.get("per_window")
    if not isinstance(per_window, list):
        return by_key

    for window in per_window:
        if not isinstance(window, dict):
            continue
        per_trade = window.get("per_trade")
        if not isinstance(per_trade, list):
            continue
        for diagnostic in per_trade:
            if not isinstance(diagnostic, dict):
                continue
            key = _trade_key(diagnostic)
            if key[0] and key[2] and key[3]:
                by_key[key] = diagnostic

    return by_key


def _trend_break_invalidation_summary(
    *,
    trade_events: list[Any],
    features_by_timestamp: dict[str, dict[str, Any]],
    exit_diagnostics: dict[str, Any] | None,
) -> dict[str, Any] | None:
    diagnostic_by_key = _exit_diagnostics_by_trade_key(exit_diagnostics)
    if not diagnostic_by_key:
        return None

    pnl_values: list[float] = []
    mae_values: list[float] = []
    mfe_values: list[float] = []
    capture_values: list[float] = []
    holding_values: list[float] = []
    exit_lag_values: list[float] = []
    zero_mfe_count = 0
    adverse_dominant_count = 0

    for trade in trade_events:
        if not isinstance(trade, dict):
            continue

        decision_ts = trade.get("exit_decision_timestamp_utc")
        feature_row = features_by_timestamp.get(str(decision_ts), {})
        reason = _classify_trend_pullback_exit_reason(
            pullback_distance=feature_row.get("pullback_distance"),
            ema_fast=feature_row.get("ema_fast"),
            ema_slow=feature_row.get("ema_slow"),
            exit_kind=trade.get("exit_kind"),
        )
        if reason != "trend_break":
            continue

        diagnostic = diagnostic_by_key.get(_trade_key(trade))
        if diagnostic is None:
            continue

        try:
            pnl_values.append(float(trade.get("pnl", 0.0)))
        except (TypeError, ValueError):
            pnl_values.append(0.0)

        try:
            mae = float(diagnostic.get("mae", 0.0))
        except (TypeError, ValueError):
            mae = 0.0
        try:
            mfe = float(diagnostic.get("mfe", 0.0))
        except (TypeError, ValueError):
            mfe = 0.0

        mae_values.append(mae)
        mfe_values.append(mfe)

        capture_ratio = diagnostic.get("capture_ratio")
        if capture_ratio is not None:
            try:
                capture_values.append(float(capture_ratio))
            except (TypeError, ValueError):
                pass

        try:
            holding_values.append(float(diagnostic.get("holding_bars", 0.0)))
        except (TypeError, ValueError):
            pass

        try:
            exit_lag_values.append(float(diagnostic.get("exit_lag_bars", 0.0)))
        except (TypeError, ValueError):
            pass

        if mfe <= 0.0:
            zero_mfe_count += 1
        if mae > mfe:
            adverse_dominant_count += 1

    if not pnl_values:
        return {
            "trade_count": 0,
            "avg_pnl": 0.0,
            "largest_loss": 0.0,
            "avg_mae": 0.0,
            "avg_mfe": 0.0,
            "avg_capture_ratio": 0.0,
            "avg_holding_bars": 0.0,
            "avg_exit_lag_bars": 0.0,
            "zero_mfe_count": 0,
            "adverse_dominant_count": 0,
        }

    return {
        "trade_count": int(len(pnl_values)),
        "avg_pnl": _safe_mean(pnl_values),
        "largest_loss": float(min(pnl_values)),
        "avg_mae": _safe_mean(mae_values),
        "avg_mfe": _safe_mean(mfe_values),
        "avg_capture_ratio": _safe_mean(capture_values),
        "avg_holding_bars": _safe_mean(holding_values),
        "avg_exit_lag_bars": _safe_mean(exit_lag_values),
        "zero_mfe_count": int(zero_mfe_count),
        "adverse_dominant_count": int(adverse_dominant_count),
    }


def _exit_metadata_summary(trade_events: list[Any]) -> dict[str, Any]:
    exit_kind_counts = Counter()
    decision_timestamp_count = 0

    for trade in trade_events:
        if not isinstance(trade, dict):
            continue
        exit_kind = str(trade.get("exit_kind") or "unknown")
        exit_kind_counts[exit_kind] += 1
        if trade.get("exit_decision_timestamp_utc") is not None:
            decision_timestamp_count += 1

    trade_count = sum(exit_kind_counts.values())
    return {
        "trade_count": int(trade_count),
        "exit_kind_counts": dict(sorted(exit_kind_counts.items())),
        "signal_change_count": int(exit_kind_counts.get("signal_change", 0)),
        "window_end_count": int(exit_kind_counts.get("window_end", 0)),
        "unknown_exit_kind_count": int(exit_kind_counts.get("unknown", 0)),
        "has_exit_decision_timestamps": (
            trade_count > 0 and decision_timestamp_count == trade_count
        ),
    }


def _sample_diagnostic(
    *,
    sample_index: int,
    params: dict[str, Any],
    status: str,
    reason: str | None,
    metrics: dict[str, Any],
    min_trades: int,
    trade_pnls: list[Any],
    trade_events: list[Any],
    trend_pullback_features_by_timestamp: dict[str, dict[str, Any]] | None = None,
    exit_diagnostics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    criteria_checks = build_exploratory_criteria_checks(metrics, min_trades)
    return {
        "sample_index": int(sample_index),
        "params": dict(params),
        "status": status,
        "reason": reason,
        "criteria_checks": criteria_checks,
        "trade_distribution": _trade_distribution(trade_pnls),
        "exit_metadata_summary": _exit_metadata_summary(trade_events),
        "trend_pullback_exit_reason_summary": (
            _trend_pullback_exit_reason_summary(
                trade_events=trade_events,
                features_by_timestamp=trend_pullback_features_by_timestamp or {},
            )
            if trend_pullback_features_by_timestamp is not None
            else None
        ),
        "trend_break_invalidation_summary": (
            _trend_break_invalidation_summary(
                trade_events=trade_events,
                features_by_timestamp=trend_pullback_features_by_timestamp or {},
                exit_diagnostics=exit_diagnostics,
            )
            if trend_pullback_features_by_timestamp is not None
            else None
        ),
        "metrics": {
            "expectancy": float(metrics.get("expectancy", 0.0)),
            "profit_factor": float(metrics.get("profit_factor", 0.0)),
            "win_rate": float(metrics.get("win_rate", 0.0)),
            "max_drawdown": float(metrics.get("max_drawdown", 0.0)),
            "totaal_trades": float(metrics.get("totaal_trades", 0.0) or 0.0),
            "trades_per_maand": float(metrics.get("trades_per_maand", 0.0) or 0.0),
        },
    }

def _sample_diagnostics_summary(sample_diagnostics: list[dict[str, Any]]) -> dict[str, Any]:
    reason_counts = Counter(
        str(item.get("reason") or "passed")
        for item in sample_diagnostics
    )
    promoted_count = sum(
        1 for item in sample_diagnostics
        if item.get("status") == SCREENING_PROMOTED
    )
    rejected_count = sum(
        1 for item in sample_diagnostics
        if item.get("status") == SCREENING_REJECTED
    )
    eligible_best_samples = [
        item for item in sample_diagnostics
        if item.get("criteria_checks", {}).get("sufficient_trades") is True
    ]
    best_sample_pool = eligible_best_samples or sample_diagnostics
    best_sample = max(
        best_sample_pool,
        key=lambda item: (
            float(item.get("metrics", {}).get("expectancy", 0.0)),
            float(item.get("metrics", {}).get("profit_factor", 0.0)),
            float(item.get("metrics", {}).get("totaal_trades", 0.0)),
        ),
        default=None,
    )

    if best_sample is None:
        best_sample_index = None
        best_metrics: dict[str, Any] = {}
    else:
        best_sample_index = int(best_sample["sample_index"])
        best_metrics = dict(best_sample.get("metrics", {}))

    return {
        "sample_count": len(sample_diagnostics),
        "promoted_sample_count": int(promoted_count),
        "rejected_sample_count": int(rejected_count),
        "rejection_reason_counts": dict(sorted(reason_counts.items())),
        "best_sample_index": best_sample_index,
        "best_expectancy": float(best_metrics.get("expectancy", 0.0)),
        "best_profit_factor": float(best_metrics.get("profit_factor", 0.0)),
        "best_totaal_trades": float(best_metrics.get("totaal_trades", 0.0)),
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
    promoted_metrics: dict[str, Any] | None = None
    sample_diagnostics: list[dict[str, Any]] = []

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
        trade_pnls = evaluation_samples.get("trade_pnls") or []
        evaluation_streams = report.get("evaluation_streams") or {}
        trade_events = evaluation_streams.get("oos_trade_events") or []
        build_exit_diagnostics = getattr(engine, "build_exit_diagnostics", None)
        if callable(build_exit_diagnostics):
            try:
                exit_diagnostics = build_exit_diagnostics()
            except Exception:
                exit_diagnostics = None
        else:
            exit_diagnostics = None
        sample_status = SCREENING_REJECTED
        sample_reason: str | None = None
        if not isinstance(daily_returns, list) or not daily_returns:
            sample_reason = "no_oos_samples"
        else:
            min_trades = int(getattr(engine, "min_trades", 10))
            if int(metrics.get("totaal_trades", 0)) < min_trades:
                sample_reason = "insufficient_trades"
            else:
                # v3.15.7: phase-aware criteria dispatch. Pre-checks
                # above (no_oos_samples / insufficient_trades) are NOT
                # duplicated inside ``apply_phase_aware_criteria``.
                passed, reason = apply_phase_aware_criteria(metrics, screening_phase)
                if passed:
                    sample_status = SCREENING_PROMOTED
                    promoted_metrics = dict(metrics)
                    sample_reason = None
                else:
                    sample_reason = reason

        sample_results.append({"status": sample_status, "reason": sample_reason})
        trend_pullback_features_by_timestamp = _trend_pullback_features_by_timestamp(
            engine=engine,
            strategy_callable=strategy_callable,
            candidate=candidate,
            evaluation_report=report,
        )
        sample_diagnostics.append(
            _sample_diagnostic(
                sample_index=sample_index,
                params=dict(_params),
                status=sample_status,
                reason=sample_reason,
                metrics=last_metrics,
                min_trades=int(getattr(engine, "min_trades", 10)),
                trade_pnls=list(trade_pnls),
                trade_events=list(trade_events),
                trend_pullback_features_by_timestamp=trend_pullback_features_by_timestamp,
                exit_diagnostics=exit_diagnostics,
            )
        )
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
    min_trades = int(getattr(engine, "min_trades", 10))
    last_trade_count = int(last_metrics.get("totaal_trades", 0) or 0)
    if legacy_decision["status"] != SCREENING_PROMOTED and last_trade_count < min_trades:
        legacy_decision = {
            "status": SCREENING_REJECTED,
            "reason": "insufficient_trades",
            "sampled_combination_count": len(sample_results),
        }
    final_status = FINAL_STATUS_PASSED if legacy_decision["status"] == SCREENING_PROMOTED else FINAL_STATUS_REJECTED
    reason_code = legacy_decision.get("reason")
    reason_detail = None
    if final_status == FINAL_STATUS_REJECTED and reason_code is not None:
        reason_detail = f"screening rejected after {len(sample_results)} sampled parameter combinations"
    # v3.15.7: additive outcome fields for phase-aware visibility.
    # ``pass_kind`` is set ONLY on screening pass (mirrors phase);
    # rejected -> None (failure semantics live in reason_code).
    # NB: NO ``screening_phase`` key here -- v3.15.6 invariant.
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
    # `selected_metrics` reports the sample that explains the aggregate decision:
    # promoted sample metrics for passes, last sample metrics for rejections.
    selected_metrics = (
        promoted_metrics
        if legacy_decision["status"] == SCREENING_PROMOTED and promoted_metrics is not None
        else last_metrics
    )
    diagnostic_metrics = {
        "expectancy": float(selected_metrics.get("expectancy", 0.0)),
        "profit_factor": float(selected_metrics.get("profit_factor", 0.0)),
        "win_rate": float(selected_metrics.get("win_rate", 0.0)),
        "max_drawdown": float(selected_metrics.get("max_drawdown", 0.0)),
        "totaal_trades": float(selected_metrics.get("totaal_trades", 0.0) or 0.0),
        "trades_per_maand": float(selected_metrics.get("trades_per_maand", 0.0) or 0.0),
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
        # v3.15.7 additive -- non-frozen screening sidecar surfaces only.
        "pass_kind": pass_kind,
        "screening_criteria_set": screening_criteria_set,
        "diagnostic_metrics": diagnostic_metrics,
        "sample_diagnostics": sample_diagnostics,
        "sample_diagnostics_summary": _sample_diagnostics_summary(sample_diagnostics),
        # v3.15.8 additive -- sampling-policy metadata for the
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
