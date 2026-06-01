from __future__ import annotations

import copy
import math
import time
from collections import Counter
from collections.abc import Callable, Iterable
from contextlib import suppress
from datetime import UTC, datetime
from typing import Any

from agent.backtesting.engine import EngineInterrupted, EngineResumeInvalid
from agent.backtesting.exit_diagnostics import extract_interior_bar_returns
from agent.backtesting.thin_strategy import build_features_for, is_thin_strategy
from research.candidate_pipeline import (
    COVERAGE_WARNING_GRID_UNAVAILABLE,
    SAMPLING_POLICY_GRID_UNAVAILABLE,
    SCREENING_PROMOTED,
    SCREENING_REJECTED,
    normalize_screening_decision,
    sampling_plan_for_param_grid,
)
from research.candidate_resume import CandidateResumeState
from research.screening_criteria import (
    apply_phase_aware_criteria,
    build_exploratory_criteria_checks,
)

# v3.15.7 invariant coverage pins this source string:
# from research.screening_criteria import apply_phase_aware_criteria

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


def _finite_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _classify_signal_change_unknown_subcategory(
    *,
    trade: dict[str, Any],
    feature_row: dict[str, Any],
    has_feature_row: bool,
) -> str:
    if (
        trade.get("exit_decision_timestamp_utc") is None
        or trade.get("exit_kind") is None
    ):
        return "signal_change_missing_metadata"

    if not has_feature_row:
        return "signal_change_missing_feature_timestamp"

    required_features = ("pullback_distance", "ema_fast", "ema_slow")
    feature_values = {
        name: _finite_float(feature_row.get(name))
        for name in required_features
    }
    if any(value is None for value in feature_values.values()):
        return "signal_change_feature_unavailable"

    return "signal_change_ambiguous_transition"


def _exit_semantic_metadata(exit_reason: str) -> dict[str, str]:
    semantic_by_reason = {
        "pullback_resolved": {
            "exit_semantic_class": "clean_resolution_exit",
            "exit_semantic_label": "clean pullback resolution",
            "exit_semantic_warning": "",
            "exit_semantic_explanation": (
                "Pullback resolved without simultaneous trend-break evidence."
            ),
        },
        "trend_break": {
            "exit_semantic_class": "trend_break_risk_exit",
            "exit_semantic_label": "trend break",
            "exit_semantic_warning": "risk exit",
            "exit_semantic_explanation": (
                "Trend-following state broke before or at the exit decision."
            ),
        },
        "pullback_resolved_and_trend_break": {
            "exit_semantic_class": "ambiguous_late_or_choppy_exit",
            "exit_semantic_label": "simultaneous pullback resolution and trend break",
            "exit_semantic_warning": "not automatically healthy",
            "exit_semantic_explanation": (
                "Pullback resolution and trend-break evidence appeared together; "
                "keep separate from clean pullback resolution until reviewed."
            ),
        },
        "signal_change_unknown": {
            "exit_semantic_class": "unknown_exit",
            "exit_semantic_label": "unknown signal-change exit",
            "exit_semantic_warning": "requires diagnostic explanation",
            "exit_semantic_explanation": (
                "Signal-change exit could not be classified from available "
                "fold-local features or metadata."
            ),
        },
        "window_end": {
            "exit_semantic_class": "boundary_exit",
            "exit_semantic_label": "window-end exit",
            "exit_semantic_warning": "boundary context",
            "exit_semantic_explanation": (
                "Exit occurred because the fold/window ended; treat as boundary "
                "context rather than strategy exit quality."
            ),
        },
    }
    return dict(
        semantic_by_reason.get(
            exit_reason,
            {
                "exit_semantic_class": "unsupported_exit_reason",
                "exit_semantic_label": str(exit_reason or "unknown"),
                "exit_semantic_warning": "unsupported exit reason",
                "exit_semantic_explanation": (
                    "No advisory semantic mapping exists for this exit reason."
                ),
            },
        )
    )


def _exit_health_class(exit_reason: str) -> str:
    health_by_reason = {
        "pullback_resolved": "healthy_exit",
        "trend_break": "risk_exit",
        "pullback_resolved_and_trend_break": "late_or_choppy_exit",
        "signal_change_unknown": "unknown_exit",
        "window_end": "boundary_exit",
    }
    return health_by_reason.get(exit_reason, "neutral_exit")


def _boundary_proximity_bucket(
    *,
    bars_to_window_end: int | None,
    is_window_end_exit: bool,
) -> str:
    if bars_to_window_end is None:
        return "unknown_boundary_distance"
    if is_window_end_exit or bars_to_window_end == 0:
        return "window_end"
    if bars_to_window_end == 1:
        return "near_window_end_1_bar"
    if 2 <= bars_to_window_end <= 3:
        return "near_window_end_2_to_3_bars"
    return "not_near_window_end"


def _boundary_trade_key(trade: dict[str, Any]) -> tuple[str, Any, str]:
    return (
        str(trade.get("asset") or ""),
        trade.get("fold_index"),
        str(trade.get("exit_decision_timestamp_utc") or ""),
    )


def _boundary_proximity_for_trade(
    *,
    trade: dict[str, Any],
    boundary_by_trade_key: dict[tuple[str, Any, str], dict[str, Any]],
) -> dict[str, Any]:
    boundary = boundary_by_trade_key.get(_boundary_trade_key(trade), {})
    try:
        bars_to_window_end = int(boundary["bars_to_window_end"])
    except (KeyError, TypeError, ValueError):
        bars_to_window_end = None

    is_window_end_exit = str(trade.get("exit_kind") or "") == "window_end"
    return {
        "bars_to_window_end": bars_to_window_end,
        "is_window_end_exit": bool(is_window_end_exit),
        "is_near_window_end": bool(
            bars_to_window_end is not None
            and 0 <= bars_to_window_end <= 3
        ),
        "boundary_proximity_bucket": _boundary_proximity_bucket(
            bars_to_window_end=bars_to_window_end,
            is_window_end_exit=is_window_end_exit,
        ),
    }


def _pnl_impact_summary(values: list[float]) -> dict[str, Any]:
    losses = [value for value in values if value < 0.0]
    winners = [value for value in values if value > 0.0]
    total_pnl = float(sum(values))
    sorted_values = sorted(values)
    if not sorted_values:
        median_pnl = 0.0
    elif len(sorted_values) % 2 == 1:
        median_pnl = float(sorted_values[len(sorted_values) // 2])
    else:
        hi = len(sorted_values) // 2
        median_pnl = float((sorted_values[hi - 1] + sorted_values[hi]) / 2.0)

    return {
        "trade_count": int(len(values)),
        "total_pnl": total_pnl,
        "avg_pnl": float(total_pnl / len(values)) if values else 0.0,
        "median_pnl": median_pnl,
        "loss_count": int(len(losses)),
        "winner_count": int(len(winners)),
        "loss_pnl_total": float(sum(losses)),
        "winner_pnl_total": float(sum(winners)),
        "loss_rate": float(len(losses) / len(values)) if values else 0.0,
        "win_rate": float(len(winners) / len(values)) if values else 0.0,
        "largest_loss": float(min(losses)) if losses else 0.0,
        "largest_win": float(max(winners)) if winners else 0.0,
    }


def _bucket_summary(values_by_bucket: dict[str, list[float]]) -> dict[str, Any]:
    return {
        "bucket_counts": {
            bucket: int(len(values))
            for bucket, values in sorted(values_by_bucket.items())
        },
        "bucket_pnl_summary": {
            bucket: _pnl_impact_summary(values)
            for bucket, values in sorted(values_by_bucket.items())
        },
    }


def _pnl_impact_by_dimension(
    values_by_key: dict[str, list[float]],
) -> dict[str, dict[str, Any]]:
    return {
        key: _pnl_impact_summary(values)
        for key, values in sorted(values_by_key.items())
    }


def _exit_health_ratio_summary(
    pnl_by_health_class: dict[str, list[float]],
) -> dict[str, Any]:
    total_trades = sum(len(values) for values in pnl_by_health_class.values())
    total_pnl = float(
        sum(sum(values) for values in pnl_by_health_class.values())
    )
    if abs(total_pnl) < 1e-12:
        total_pnl = 0.0
    by_health_class: dict[str, dict[str, Any]] = {}
    for health_class, values in sorted(pnl_by_health_class.items()):
        summary = _pnl_impact_summary(values)
        summary["trade_share"] = (
            float(summary["trade_count"] / total_trades)
            if total_trades
            else 0.0
        )
        summary["pnl_share"] = (
            float(summary["total_pnl"] / total_pnl)
            if total_pnl
            else 0.0
        )
        by_health_class[health_class] = summary

    return {
        "trade_count": int(total_trades),
        "total_pnl": total_pnl,
        "health_class_counts": {
            health_class: int(len(values))
            for health_class, values in sorted(pnl_by_health_class.items())
        },
        "by_health_class": by_health_class,
    }


def _trend_pullback_exit_reason_summary(
    *,
    trade_events: list[Any],
    features_by_timestamp: dict[str, dict[str, Any]],
    boundary_by_trade_key: dict[tuple[str, Any, str], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    reason_counts = Counter()
    pnl_by_reason: dict[str, list[float]] = {}
    unknown_subcategory_counts = Counter()
    pnl_by_unknown_subcategory: dict[str, list[float]] = {}
    boundary_lookup = boundary_by_trade_key or {}
    pnl_by_boundary_bucket: dict[str, list[float]] = {}
    pnl_by_asset: dict[str, list[float]] = {}
    pnl_by_fold_index: dict[str, list[float]] = {}
    pnl_by_health_class: dict[str, list[float]] = {}
    health_by_asset: dict[str, dict[str, list[float]]] = {}
    health_by_exit_reason: dict[str, dict[str, list[float]]] = {}
    health_by_unknown_subcategory: dict[str, dict[str, list[float]]] = {}
    health_by_boundary_bucket: dict[str, dict[str, list[float]]] = {}
    boundary_by_reason: dict[str, dict[str, list[float]]] = {}
    boundary_by_unknown_subcategory: dict[str, dict[str, list[float]]] = {}
    boundary_by_asset: dict[str, dict[str, list[float]]] = {}

    for trade in trade_events:
        if not isinstance(trade, dict):
            continue

        decision_ts = trade.get("exit_decision_timestamp_utc")
        feature_key = str(decision_ts)
        has_feature_row = feature_key in features_by_timestamp
        feature_row = features_by_timestamp.get(feature_key, {})
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
        health_class = _exit_health_class(reason)
        pnl_by_health_class.setdefault(health_class, []).append(pnl)
        health_by_exit_reason.setdefault(reason, {}).setdefault(
            health_class,
            [],
        ).append(pnl)
        boundary = _boundary_proximity_for_trade(
            trade=trade,
            boundary_by_trade_key=boundary_lookup,
        )
        boundary_bucket = str(boundary["boundary_proximity_bucket"])
        pnl_by_boundary_bucket.setdefault(boundary_bucket, []).append(pnl)
        health_by_boundary_bucket.setdefault(boundary_bucket, {}).setdefault(
            health_class,
            [],
        ).append(pnl)
        boundary_by_reason.setdefault(reason, {}).setdefault(
            boundary_bucket,
            [],
        ).append(pnl)
        asset = str(trade.get("asset") or "")
        if asset:
            pnl_by_asset.setdefault(asset, []).append(pnl)
            health_by_asset.setdefault(asset, {}).setdefault(
                health_class,
                [],
            ).append(pnl)
            boundary_by_asset.setdefault(asset, {}).setdefault(
                boundary_bucket,
                [],
            ).append(pnl)
        fold_index = trade.get("fold_index")
        if fold_index is not None:
            pnl_by_fold_index.setdefault(str(fold_index), []).append(pnl)
        if reason == "signal_change_unknown":
            unknown_subcategory = _classify_signal_change_unknown_subcategory(
                trade=trade,
                feature_row=feature_row,
                has_feature_row=has_feature_row,
            )
            unknown_subcategory_counts[unknown_subcategory] += 1
            pnl_by_unknown_subcategory.setdefault(
                unknown_subcategory,
                [],
            ).append(pnl)
            health_by_unknown_subcategory.setdefault(
                unknown_subcategory,
                {},
            ).setdefault(health_class, []).append(pnl)
            boundary_by_unknown_subcategory.setdefault(
                unknown_subcategory,
                {},
            ).setdefault(boundary_bucket, []).append(pnl)

    trade_count = sum(reason_counts.values())
    boundary_summary = _bucket_summary(pnl_by_boundary_bucket)
    boundary_summary["trade_count"] = int(trade_count)
    boundary_summary["by_exit_reason"] = {
        reason: _bucket_summary(values_by_bucket)
        for reason, values_by_bucket in sorted(boundary_by_reason.items())
    }
    boundary_summary["by_unknown_subcategory"] = {
        reason: _bucket_summary(values_by_bucket)
        for reason, values_by_bucket in sorted(
            boundary_by_unknown_subcategory.items()
        )
    }
    boundary_summary["by_asset"] = {
        asset: _bucket_summary(values_by_bucket)
        for asset, values_by_bucket in sorted(boundary_by_asset.items())
    }
    return {
        "trade_count": int(trade_count),
        "exit_reason_counts": dict(sorted(reason_counts.items())),
        "exit_reason_semantics": {
            reason: _exit_semantic_metadata(reason)
            for reason in sorted(reason_counts)
        },
        "exit_reason_pnl_summary": {
            reason: _pnl_impact_summary(values)
            for reason, values in sorted(pnl_by_reason.items())
        },
        "signal_change_unknown_subcategory_counts": dict(
            sorted(unknown_subcategory_counts.items())
        ),
        "signal_change_unknown_subcategory_pnl_summary": {
            reason: _pnl_impact_summary(values)
            for reason, values in sorted(pnl_by_unknown_subcategory.items())
        },
        "realized_pnl_impact": {
            "by_exit_reason": _pnl_impact_by_dimension(pnl_by_reason),
            "by_unknown_subcategory": _pnl_impact_by_dimension(
                pnl_by_unknown_subcategory
            ),
            "by_boundary_proximity_bucket": _pnl_impact_by_dimension(
                pnl_by_boundary_bucket
            ),
            "by_asset": _pnl_impact_by_dimension(pnl_by_asset),
            "by_fold_index": _pnl_impact_by_dimension(pnl_by_fold_index),
        },
        "exit_health_summary": {
            "advisory_only": True,
            "taxonomy": [
                "healthy_exit",
                "risk_exit",
                "late_or_choppy_exit",
                "boundary_exit",
                "unknown_exit",
                "neutral_exit",
            ],
            "overall": _exit_health_ratio_summary(pnl_by_health_class),
            "by_asset": {
                asset: _exit_health_ratio_summary(values_by_class)
                for asset, values_by_class in sorted(health_by_asset.items())
            },
            "by_exit_reason": {
                reason: {
                    "exit_health_class": _exit_health_class(reason),
                    "summary": _exit_health_ratio_summary(values_by_class),
                }
                for reason, values_by_class in sorted(health_by_exit_reason.items())
            },
            "by_unknown_subcategory": {
                subcategory: _exit_health_ratio_summary(values_by_class)
                for subcategory, values_by_class in sorted(
                    health_by_unknown_subcategory.items()
                )
            },
            "by_boundary_proximity_bucket": {
                bucket: _exit_health_ratio_summary(values_by_class)
                for bucket, values_by_class in sorted(
                    health_by_boundary_bucket.items()
                )
            },
        },
        "boundary_proximity_summary": boundary_summary,
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


def _trend_pullback_boundary_by_trade_key(
    *,
    engine: Any,
    candidate: dict[str, Any],
    evaluation_report: dict[str, Any],
) -> dict[tuple[str, Any, str], dict[str, Any]]:
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

    by_key: dict[tuple[str, Any, str], dict[str, Any]] = {}
    for fold_index, fold in enumerate(folds):
        test_bounds = fold.get("test") if isinstance(fold, dict) else None
        if not isinstance(test_bounds, list) or len(test_bounds) != 2:
            continue

        try:
            test_start = int(test_bounds[0])
            test_end = int(test_bounds[1])
        except (TypeError, ValueError):
            continue

        if test_start < 0 or test_end < test_start or test_end >= len(frame):
            continue

        fold_frame = frame.iloc[test_start : test_end + 1]
        for offset, timestamp in enumerate(fold_frame.index):
            bars_to_window_end = int((len(fold_frame) - 1) - offset)
            timestamp_utc = str(timestamp_to_utc_iso(timestamp))
            key = (asset, int(fold_index), timestamp_utc)
            by_key[key] = {
                "bars_to_window_end": bars_to_window_end,
                "is_near_window_end": bool(0 <= bars_to_window_end <= 3),
                "boundary_proximity_bucket": _boundary_proximity_bucket(
                    bars_to_window_end=bars_to_window_end,
                    is_window_end_exit=False,
                ),
            }

    return by_key


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


def _classify_trade_reason(
    *,
    trade: dict[str, Any],
    features_by_timestamp: dict[str, dict[str, Any]],
) -> str:
    decision_ts = trade.get("exit_decision_timestamp_utc")
    feature_row = features_by_timestamp.get(str(decision_ts), {})
    return _classify_trend_pullback_exit_reason(
        pullback_distance=feature_row.get("pullback_distance"),
        ema_fast=feature_row.get("ema_fast"),
        ema_slow=feature_row.get("ema_slow"),
        exit_kind=trade.get("exit_kind"),
    )


def _early_invalidation_rule_specs() -> dict[str, dict[str, float]]:
    return {
        "zero_mfe_holding_ge_3": {
            "max_mfe": 0.0,
            "min_holding_bars": 3.0,
        },
        "mae_gt_2pct_mfe_lt_025pct": {
            "min_mae": 0.02,
            "max_mfe": 0.0025,
        },
        "adverse_dominant_holding_ge_4": {
            "adverse_dominant": 1.0,
            "min_holding_bars": 4.0,
        },
    }


def _rule_matches_diagnostic(
    *,
    diagnostic: dict[str, Any],
    spec: dict[str, float],
) -> bool:
    try:
        mae = float(diagnostic.get("mae", 0.0))
    except (TypeError, ValueError):
        mae = 0.0
    try:
        mfe = float(diagnostic.get("mfe", 0.0))
    except (TypeError, ValueError):
        mfe = 0.0
    try:
        holding_bars = float(diagnostic.get("holding_bars", 0.0))
    except (TypeError, ValueError):
        holding_bars = 0.0

    if "min_mae" in spec and mae <= float(spec["min_mae"]):
        return False
    if "max_mfe" in spec and mfe > float(spec["max_mfe"]):
        return False
    if "min_holding_bars" in spec and holding_bars < float(spec["min_holding_bars"]):
        return False
    return not (spec.get("adverse_dominant") and mae <= mfe)


def _empty_simulation_rule_result() -> dict[str, Any]:
    return {
        "affected_trades": 0,
        "affected_trend_break_trades": 0,
        "affected_pullback_resolved_trades": 0,
        "affected_other_trades": 0,
        "trend_break_loss_at_risk": 0.0,
        "pullback_profit_at_risk": 0.0,
        "other_pnl_at_risk": 0.0,
        "net_loss_reduction_upper_bound": 0.0,
    }


def _trend_break_invalidation_simulation_summary(
    *,
    trade_events: list[Any],
    features_by_timestamp: dict[str, dict[str, Any]],
    exit_diagnostics: dict[str, Any] | None,
) -> dict[str, Any] | None:
    diagnostic_by_key = _exit_diagnostics_by_trade_key(exit_diagnostics)
    if not diagnostic_by_key:
        return None

    rules = {
        name: _empty_simulation_rule_result()
        for name in _early_invalidation_rule_specs()
    }

    matched_trade_count = 0
    for trade in trade_events:
        if not isinstance(trade, dict):
            continue
        diagnostic = diagnostic_by_key.get(_trade_key(trade))
        if diagnostic is None:
            continue

        matched_trade_count += 1
        reason = _classify_trade_reason(
            trade=trade,
            features_by_timestamp=features_by_timestamp,
        )
        try:
            pnl = float(trade.get("pnl", 0.0))
        except (TypeError, ValueError):
            pnl = 0.0

        for rule_name, spec in _early_invalidation_rule_specs().items():
            if not _rule_matches_diagnostic(diagnostic=diagnostic, spec=spec):
                continue

            result = rules[rule_name]
            result["affected_trades"] += 1

            if reason == "trend_break":
                result["affected_trend_break_trades"] += 1
                if pnl < 0.0:
                    result["trend_break_loss_at_risk"] += abs(pnl)
                    result["net_loss_reduction_upper_bound"] += abs(pnl)
            elif reason == "pullback_resolved":
                result["affected_pullback_resolved_trades"] += 1
                if pnl > 0.0:
                    result["pullback_profit_at_risk"] += pnl
                    result["net_loss_reduction_upper_bound"] -= pnl
            else:
                result["affected_other_trades"] += 1
                result["other_pnl_at_risk"] += pnl

    return {
        "matched_trade_count": int(matched_trade_count),
        "rules": {
            name: {
                "affected_trades": int(values["affected_trades"]),
                "affected_trend_break_trades": int(
                    values["affected_trend_break_trades"]
                ),
                "affected_pullback_resolved_trades": int(
                    values["affected_pullback_resolved_trades"]
                ),
                "affected_other_trades": int(values["affected_other_trades"]),
                "trend_break_loss_at_risk": float(
                    values["trend_break_loss_at_risk"]
                ),
                "pullback_profit_at_risk": float(
                    values["pullback_profit_at_risk"]
                ),
                "other_pnl_at_risk": float(values["other_pnl_at_risk"]),
                "net_loss_reduction_upper_bound": float(
                    values["net_loss_reduction_upper_bound"]
                ),
            }
            for name, values in sorted(rules.items())
        },
    }


def _side_sign(side: Any) -> float:
    return 1.0 if str(side).lower() == "long" else -1.0


def _bar_path_trigger_for_rule(
    *,
    trade: dict[str, Any],
    interior_returns: list[float],
    max_mfe: float = 0.0025,
    min_mae: float = 0.02,
) -> dict[str, Any] | None:
    side_sign = _side_sign(trade.get("side"))
    cumulative_raw = 1.0
    path: list[float] = [0.0]

    for bar_offset, raw_return in enumerate(interior_returns, start=1):
        try:
            rf = float(raw_return)
        except (TypeError, ValueError):
            continue
        cumulative_raw *= 1.0 + rf * side_sign
        path_value = (cumulative_raw - 1.0) * side_sign
        path.append(path_value)

        running_mfe = max(max(path), 0.0)
        running_mae = max(-min(path), 0.0)
        if running_mae > min_mae and running_mfe < max_mfe:
            return {
                "bars_to_trigger": int(bar_offset),
                "hypothetical_pnl": float(path_value),
                "running_mae": float(running_mae),
                "running_mfe": float(running_mfe),
            }

    return None


def _bar_path_threshold_specs() -> dict[str, dict[str, float]]:
    return {
        "mae_gt_2pct_mfe_lt_025pct": {
            "min_mae": 0.02,
            "max_mfe": 0.0025,
            "min_bars_to_trigger": 1.0,
        },
        "mae_gt_3pct_mfe_lt_025pct": {
            "min_mae": 0.03,
            "max_mfe": 0.0025,
            "min_bars_to_trigger": 1.0,
        },
        "mae_gt_2pct_zero_mfe": {
            "min_mae": 0.02,
            "max_mfe": 0.0,
            "min_bars_to_trigger": 1.0,
        },
        "mae_gt_3pct_zero_mfe": {
            "min_mae": 0.03,
            "max_mfe": 0.0,
            "min_bars_to_trigger": 1.0,
        },
        "mae_gt_2pct_mfe_lt_025pct_trigger_ge_2": {
            "min_mae": 0.02,
            "max_mfe": 0.0025,
            "min_bars_to_trigger": 2.0,
        },
        "mae_gt_3pct_mfe_lt_025pct_trigger_ge_2": {
            "min_mae": 0.03,
            "max_mfe": 0.0025,
            "min_bars_to_trigger": 2.0,
        },
    }


def _bar_path_trigger_for_spec(
    *,
    trade: dict[str, Any],
    interior_returns: list[float],
    spec: dict[str, float],
) -> dict[str, Any] | None:
    side_sign = _side_sign(trade.get("side"))
    cumulative_raw = 1.0
    path: list[float] = [0.0]

    min_mae = float(spec["min_mae"])
    max_mfe = float(spec["max_mfe"])
    min_bars_to_trigger = float(spec.get("min_bars_to_trigger", 1.0))

    for bar_offset, raw_return in enumerate(interior_returns, start=1):
        try:
            rf = float(raw_return)
        except (TypeError, ValueError):
            continue

        cumulative_raw *= 1.0 + rf * side_sign
        path_value = (cumulative_raw - 1.0) * side_sign
        path.append(path_value)

        running_mfe = max(max(path), 0.0)
        running_mae = max(-min(path), 0.0)

        if float(bar_offset) < min_bars_to_trigger:
            continue

        if running_mae > min_mae and running_mfe <= max_mfe:
            return {
                "bars_to_trigger": int(bar_offset),
                "hypothetical_pnl": float(path_value),
                "running_mae": float(running_mae),
                "running_mfe": float(running_mfe),
            }

    return None


def _empty_bar_path_rule_result() -> dict[str, Any]:
    return {
        "triggered_trade_count": 0,
        "triggered_trend_break_trades": 0,
        "triggered_pullback_resolved_trades": 0,
        "triggered_other_trades": 0,
        "avoided_loss": 0.0,
        "sacrificed_profit": 0.0,
        "other_pnl_delta": 0.0,
        "net_pnl_delta": 0.0,
        "avg_bars_to_trigger": 0.0,
        "_bars_to_trigger": [],
    }


def _finalize_bar_path_rule_result(values: dict[str, Any]) -> dict[str, Any]:
    bars = values.get("_bars_to_trigger") or []
    return {
        "triggered_trade_count": int(values["triggered_trade_count"]),
        "triggered_trend_break_trades": int(
            values["triggered_trend_break_trades"]
        ),
        "triggered_pullback_resolved_trades": int(
            values["triggered_pullback_resolved_trades"]
        ),
        "triggered_other_trades": int(values["triggered_other_trades"]),
        "avoided_loss": float(values["avoided_loss"]),
        "sacrificed_profit": float(values["sacrificed_profit"]),
        "other_pnl_delta": float(values["other_pnl_delta"]),
        "net_pnl_delta": float(values["net_pnl_delta"]),
        "avg_bars_to_trigger": _safe_mean([float(v) for v in bars]),
    }


def _trend_break_bar_path_threshold_comparison_summary(
    *,
    trade_events: list[Any],
    features_by_timestamp: dict[str, dict[str, Any]],
    bar_return_stream: list[Any],
) -> dict[str, Any] | None:
    if not bar_return_stream:
        return None

    specs = _bar_path_threshold_specs()
    rules = {
        name: _empty_bar_path_rule_result()
        for name in specs
    }
    matched_trade_count = 0

    for trade in trade_events:
        if not isinstance(trade, dict):
            continue

        try:
            interior_returns = extract_interior_bar_returns(
                trade=trade,
                bar_return_stream=bar_return_stream,
            )
        except (KeyError, ValueError):
            continue

        matched_trade_count += 1
        reason = _classify_trade_reason(
            trade=trade,
            features_by_timestamp=features_by_timestamp,
        )
        try:
            actual_pnl = float(trade.get("pnl", 0.0))
        except (TypeError, ValueError):
            actual_pnl = 0.0

        for rule_name, spec in specs.items():
            trigger = _bar_path_trigger_for_spec(
                trade=trade,
                interior_returns=interior_returns,
                spec=spec,
            )
            if trigger is None:
                continue

            values = rules[rule_name]
            values["triggered_trade_count"] += 1
            values["_bars_to_trigger"].append(float(trigger["bars_to_trigger"]))

            hypothetical_pnl = float(trigger["hypothetical_pnl"])
            pnl_delta = hypothetical_pnl - actual_pnl

            if reason == "trend_break":
                values["triggered_trend_break_trades"] += 1
                if pnl_delta > 0.0:
                    values["avoided_loss"] += pnl_delta
            elif reason == "pullback_resolved":
                values["triggered_pullback_resolved_trades"] += 1
                if pnl_delta < 0.0:
                    values["sacrificed_profit"] += abs(pnl_delta)
            else:
                values["triggered_other_trades"] += 1
                values["other_pnl_delta"] += pnl_delta

            values["net_pnl_delta"] = (
                values["avoided_loss"]
                - values["sacrificed_profit"]
                + values["other_pnl_delta"]
            )

    return {
        "matched_trade_count": int(matched_trade_count),
        "rules": {
            name: _finalize_bar_path_rule_result(values)
            for name, values in sorted(rules.items())
        },
    }


def _trend_break_bar_path_simulation_summary(
    *,
    trade_events: list[Any],
    features_by_timestamp: dict[str, dict[str, Any]],
    bar_return_stream: list[Any],
) -> dict[str, Any] | None:
    if not bar_return_stream:
        return None

    matched_trade_count = 0
    triggered_trade_count = 0
    triggered_trend_break_trades = 0
    triggered_pullback_resolved_trades = 0
    triggered_other_trades = 0
    avoided_loss = 0.0
    sacrificed_profit = 0.0
    other_pnl_delta = 0.0
    bars_to_trigger: list[float] = []

    for trade in trade_events:
        if not isinstance(trade, dict):
            continue

        try:
            interior_returns = extract_interior_bar_returns(
                trade=trade,
                bar_return_stream=bar_return_stream,
            )
        except (KeyError, ValueError):
            continue

        matched_trade_count += 1
        trigger = _bar_path_trigger_for_rule(
            trade=trade,
            interior_returns=interior_returns,
        )
        if trigger is None:
            continue

        triggered_trade_count += 1
        bars_to_trigger.append(float(trigger["bars_to_trigger"]))

        reason = _classify_trade_reason(
            trade=trade,
            features_by_timestamp=features_by_timestamp,
        )
        try:
            actual_pnl = float(trade.get("pnl", 0.0))
        except (TypeError, ValueError):
            actual_pnl = 0.0
        hypothetical_pnl = float(trigger["hypothetical_pnl"])
        pnl_delta = hypothetical_pnl - actual_pnl

        if reason == "trend_break":
            triggered_trend_break_trades += 1
            if pnl_delta > 0.0:
                avoided_loss += pnl_delta
        elif reason == "pullback_resolved":
            triggered_pullback_resolved_trades += 1
            if pnl_delta < 0.0:
                sacrificed_profit += abs(pnl_delta)
        else:
            triggered_other_trades += 1
            other_pnl_delta += pnl_delta

    return {
        "rule": "mae_gt_2pct_mfe_lt_025pct",
        "matched_trade_count": int(matched_trade_count),
        "triggered_trade_count": int(triggered_trade_count),
        "triggered_trend_break_trades": int(triggered_trend_break_trades),
        "triggered_pullback_resolved_trades": int(
            triggered_pullback_resolved_trades
        ),
        "triggered_other_trades": int(triggered_other_trades),
        "avoided_loss": float(avoided_loss),
        "sacrificed_profit": float(sacrificed_profit),
        "other_pnl_delta": float(other_pnl_delta),
        "net_pnl_delta": float(avoided_loss - sacrificed_profit + other_pnl_delta),
        "avg_bars_to_trigger": _safe_mean(bars_to_trigger),
    }


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
            with suppress(TypeError, ValueError):
                capture_values.append(float(capture_ratio))

        with suppress(TypeError, ValueError):
            holding_values.append(float(diagnostic.get("holding_bars", 0.0)))

        with suppress(TypeError, ValueError):
            exit_lag_values.append(float(diagnostic.get("exit_lag_bars", 0.0)))

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
    trend_pullback_boundary_by_trade_key: (
        dict[tuple[str, Any, str], dict[str, Any]] | None
    ) = None,
    exit_diagnostics: dict[str, Any] | None = None,
    bar_return_stream: list[Any] | None = None,
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
                boundary_by_trade_key=trend_pullback_boundary_by_trade_key or {},
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
        "trend_break_invalidation_simulation_summary": (
            _trend_break_invalidation_simulation_summary(
                trade_events=trade_events,
                features_by_timestamp=trend_pullback_features_by_timestamp or {},
                exit_diagnostics=exit_diagnostics,
            )
            if trend_pullback_features_by_timestamp is not None
            else None
        ),
        "trend_break_bar_path_simulation_summary": (
            _trend_break_bar_path_simulation_summary(
                trade_events=trade_events,
                features_by_timestamp=trend_pullback_features_by_timestamp or {},
                bar_return_stream=list(bar_return_stream or []),
            )
            if trend_pullback_features_by_timestamp is not None
            else None
        ),
        "trend_break_bar_path_threshold_comparison_summary": (
            _trend_break_bar_path_threshold_comparison_summary(
                trade_events=trade_events,
                features_by_timestamp=trend_pullback_features_by_timestamp or {},
                bar_return_stream=list(bar_return_stream or []),
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


def _health_class_share(
    health_summary: dict[str, Any],
    health_class: str,
) -> float:
    try:
        return float(
            health_summary["overall"]["by_health_class"]
            .get(health_class, {})
            .get("trade_share", 0.0)
        )
    except (AttributeError, KeyError, TypeError, ValueError):
        return 0.0


def _health_class_total_pnl(
    health_summary: dict[str, Any],
    health_class: str,
) -> float:
    try:
        return float(
            health_summary["overall"]["by_health_class"]
            .get(health_class, {})
            .get("total_pnl", 0.0)
        )
    except (AttributeError, KeyError, TypeError, ValueError):
        return 0.0


def _sample_exit_quality_score(sample: dict[str, Any]) -> float:
    exit_summary = sample.get("trend_pullback_exit_reason_summary") or {}
    health_summary = exit_summary.get("exit_health_summary") or {}
    healthy = _health_class_share(health_summary, "healthy_exit")
    risk = _health_class_share(health_summary, "risk_exit")
    late = _health_class_share(health_summary, "late_or_choppy_exit")
    unknown = _health_class_share(health_summary, "unknown_exit")
    boundary = _health_class_share(health_summary, "boundary_exit")
    return float(healthy - risk - late - unknown - boundary)


def _sample_exit_quality_audit(
    *,
    sample_diagnostics: list[dict[str, Any]],
    selected_best_sample_index: int | None,
) -> dict[str, Any]:
    if not sample_diagnostics:
        return {
            "advisory_only": True,
            "selected_best_sample_index": selected_best_sample_index,
            "performance_best_sample_index": selected_best_sample_index,
            "exit_quality_best_sample_index": None,
            "exit_quality_disagreement": False,
            "selected_sample_health_score": 0.0,
            "exit_quality_best_health_score": 0.0,
            "selected_sample_risk_exit_share": 0.0,
            "selected_sample_unknown_exit_share": 0.0,
            "selected_sample_boundary_exit_share": 0.0,
            "selected_sample_late_or_choppy_exit_share": 0.0,
            "selected_sample_total_pnl": 0.0,
            "selected_sample_risk_exit_total_pnl": 0.0,
            "advisory_message": "No sample diagnostics available for exit-quality audit.",
        }

    scored = [
        (int(sample.get("sample_index", index)), _sample_exit_quality_score(sample))
        for index, sample in enumerate(sample_diagnostics)
    ]
    exit_quality_best_index, exit_quality_best_score = max(
        scored,
        key=lambda item: (item[1], -item[0]),
    )
    selected_sample = next(
        (
            sample
            for sample in sample_diagnostics
            if sample.get("sample_index") == selected_best_sample_index
        ),
        None,
    )
    selected_health = (
        (selected_sample.get("trend_pullback_exit_reason_summary") or {}).get(
            "exit_health_summary"
        )
        or {}
        if isinstance(selected_sample, dict)
        else {}
    )
    selected_impact = (
        (selected_sample.get("trend_pullback_exit_reason_summary") or {}).get(
            "realized_pnl_impact"
        )
        or {}
        if isinstance(selected_sample, dict)
        else {}
    )

    selected_score = (
        _sample_exit_quality_score(selected_sample)
        if isinstance(selected_sample, dict)
        else 0.0
    )
    selected_total_pnl = 0.0
    try:
        selected_total_pnl = float(
            sum(
                item.get("total_pnl", 0.0)
                for item in (selected_impact.get("by_exit_reason") or {}).values()
                if isinstance(item, dict)
            )
        )
    except (AttributeError, TypeError, ValueError):
        selected_total_pnl = 0.0

    disagreement = (
        selected_best_sample_index is not None
        and int(selected_best_sample_index) != int(exit_quality_best_index)
    )
    if disagreement:
        message = (
            "Selected performance-best sample differs from advisory "
            "exit-quality-best sample; review before trusting exit quality."
        )
    else:
        message = (
            "Selected performance-best sample matches advisory exit-quality-best "
            "sample."
        )

    return {
        "advisory_only": True,
        "selected_best_sample_index": selected_best_sample_index,
        "performance_best_sample_index": selected_best_sample_index,
        "exit_quality_best_sample_index": int(exit_quality_best_index),
        "exit_quality_disagreement": bool(disagreement),
        "selected_sample_health_score": float(selected_score),
        "exit_quality_best_health_score": float(exit_quality_best_score),
        "selected_sample_risk_exit_share": _health_class_share(
            selected_health,
            "risk_exit",
        ),
        "selected_sample_unknown_exit_share": _health_class_share(
            selected_health,
            "unknown_exit",
        ),
        "selected_sample_boundary_exit_share": _health_class_share(
            selected_health,
            "boundary_exit",
        ),
        "selected_sample_late_or_choppy_exit_share": _health_class_share(
            selected_health,
            "late_or_choppy_exit",
        ),
        "selected_sample_total_pnl": float(selected_total_pnl),
        "selected_sample_risk_exit_total_pnl": _health_class_total_pnl(
            selected_health,
            "risk_exit",
        ),
        "advisory_message": message,
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
        "best_sample_exit_quality_audit": _sample_exit_quality_audit(
            sample_diagnostics=sample_diagnostics,
            selected_best_sample_index=best_sample_index,
        ),
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
        bar_return_stream = evaluation_streams.get("oos_bar_returns") or []
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
        trend_pullback_boundary_by_trade_key = _trend_pullback_boundary_by_trade_key(
            engine=engine,
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
                trend_pullback_boundary_by_trade_key=trend_pullback_boundary_by_trade_key,
                exit_diagnostics=exit_diagnostics,
                bar_return_stream=list(bar_return_stream),
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
