"""Pure helpers for research-side portfolio aggregation reporting."""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from research._oos_stream import normalize_oos_daily_return_stream
from research.promotion import build_strategy_id

VIEW_SPECS: tuple[tuple[str, str], ...] = (
    ("all_included", "strategy_run"),
    ("by_asset", "asset"),
    ("by_family", "family"),
)

ALIGNMENT_POLICY = {
    "basis": "timestamped_oos_daily_returns",
    "cross_interval_mixing": False,
    "ordering": "ascending_timestamp_utc",
    "policy": "exact_timestamp_intersection",
    "non_overlap_handling": (
        "portfolio_results_only_on_common_support; "
        "inactive_members_are_not_treated_as_cash_and_weights_are_not_redistributed"
    ),
}

CONTRIBUTION_DEFINITION = {
    "period_return_contribution": "sleeve_weight * sleeve_return_t",
    "cumulative_period_return_contribution": (
        "cumulative sum over aligned timestamps of period_return_contribution; "
        "this explains the aggregated period-return path and is not drawdown attribution"
    ),
}


def build_portfolio_aggregation_payload(
    evaluations: list[dict[str, Any]],
    as_of_utc,
    git_revision: str,
) -> dict[str, Any]:
    """Build additive portfolio aggregation sidecar payload.

    The payload is intentionally research-only:
    - uses timestamped OOS daily returns only
    - no cross-interval mixing
    - no live sizing or optimizer assumptions
    """
    runs = [_normalize_run(evaluation) for evaluation in evaluations]
    intervals = sorted({run["interval"] for run in runs})
    views = [
        _build_view(
            runs=[run for run in runs if run["interval"] == interval],
            interval=interval,
            view_name=view_name,
            sleeve_by=sleeve_by,
        )
        for interval in intervals
        for view_name, sleeve_by in VIEW_SPECS
    ]

    return {
        "version": "v1",
        "generated_at_utc": as_of_utc.isoformat(),
        "git_revision": git_revision,
        "alignment_policy": dict(ALIGNMENT_POLICY),
        "contribution_definition": dict(CONTRIBUTION_DEFINITION),
        "summary": {
            "input_run_count": len(runs),
            "interval_count": len(intervals),
            "view_count": len(views),
            "views_with_portfolio_stream": sum(1 for view in views if view["summary"]["observation_count"] > 0),
            "views_without_portfolio_stream": sum(1 for view in views if view["summary"]["observation_count"] == 0),
        },
        "views": views,
    }


def _build_view(
    runs: list[dict[str, Any]],
    interval: str,
    view_name: str,
    sleeve_by: str,
) -> dict[str, Any]:
    excluded_runs: list[dict[str, Any]] = []
    valid_runs: list[dict[str, Any]] = []
    seen_strategy_ids: set[str] = set()

    for run in sorted(runs, key=lambda item: item["strategy_id"]):
        if run["strategy_id"] in seen_strategy_ids:
            excluded_runs.append(_excluded_run(run, "duplicate_strategy_id_in_view"))
            continue
        seen_strategy_ids.add(run["strategy_id"])

        if run["stream_error"] is not None:
            excluded_runs.append(_excluded_run(run, run["stream_error"]))
            continue

        valid_runs.append(run)

    grouped_runs: dict[str, list[dict[str, Any]]] = {}
    for run in valid_runs:
        grouped_runs.setdefault(_sleeve_key(run, sleeve_by), []).append(run)

    sleeves: list[dict[str, Any]] = []
    for key in sorted(grouped_runs):
        sleeve, sleeve_exclusions = _build_sleeve(
            runs=grouped_runs[key],
            sleeve_key=key,
            sleeve_by=sleeve_by,
            interval=interval,
        )
        excluded_runs.extend(sleeve_exclusions)
        if sleeve is not None:
            sleeves.append(sleeve)

    included_runs = _included_runs_from_sleeves(sleeves)
    portfolio_timestamps = _common_timestamps([sleeve["_timestamps"] for sleeve in sleeves]) if sleeves else []
    portfolio_returns = [
        float(np.mean([_aligned_return_map(sleeve)[timestamp] for sleeve in sleeves]))
        for timestamp in portfolio_timestamps
    ] if portfolio_timestamps else []
    sleeve_weight = 1.0 / len(sleeves) if sleeves else 0.0

    diversification = _diversification(sleeves, portfolio_timestamps)
    finalized_sleeves = [
        _finalize_sleeve_for_view(
            sleeve=sleeve,
            portfolio_timestamps=portfolio_timestamps,
            sleeve_weight=sleeve_weight,
        )
        for sleeve in sleeves
    ]

    if sleeves and not portfolio_timestamps:
        status = "insufficient_common_support_across_sleeves"
    elif sleeves:
        status = "ok"
    else:
        status = "no_valid_sleeves"

    return {
        "view_id": f"{interval}|{view_name}",
        "view_name": view_name,
        "interval": interval,
        "sleeve_by": sleeve_by,
        "weighting_method": "equal_weight",
        "status": status,
        "alignment": {
            "policy": ALIGNMENT_POLICY["policy"],
            "input_run_count": len(runs),
            "eligible_run_count": len(valid_runs),
            "included_run_count": len(included_runs),
            "excluded_run_count": len(excluded_runs),
            "sleeve_count": len(finalized_sleeves),
            "common_window": _window_metadata(portfolio_timestamps),
            "dropped_observations_total": sum(
                max(0, len(sleeve["_timestamps"]) - len(portfolio_timestamps))
                for sleeve in sleeves
            ),
            "consequence": (
                "portfolio metrics reflect only timestamps shared by every included sleeve"
                if portfolio_timestamps
                else "no portfolio stream available because included sleeves do not share a common active window"
            ),
        },
        "included_runs": included_runs,
        "excluded_runs": sorted(
            excluded_runs,
            key=lambda item: (item["reason"], item["strategy_id"]),
        ),
        "summary": _return_summary(portfolio_returns, interval),
        "portfolio_stream": _portfolio_stream(portfolio_timestamps, portfolio_returns),
        "sleeves": [_public_sleeve(sleeve) for sleeve in finalized_sleeves],
        "diversification": diversification,
    }


def _build_sleeve(
    runs: list[dict[str, Any]],
    sleeve_key: str,
    sleeve_by: str,
    interval: str,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    sleeve_timestamps = _common_timestamps([run["timestamps"] for run in runs])
    if not sleeve_timestamps:
        return None, [_excluded_run(run, "no_common_support_within_sleeve") for run in runs]

    member_returns = [
        _aligned_returns(run["stream"], sleeve_timestamps)
        for run in runs
    ]
    sleeve_returns = [
        float(np.mean(values))
        for values in zip(*member_returns)
    ]
    aligned_count = len(sleeve_timestamps)

    members = []
    for run in sorted(runs, key=lambda item: item["strategy_id"]):
        members.append({
            "strategy_id": run["strategy_id"],
            "strategy_name": run["strategy_name"],
            "asset": run["asset"],
            "family": run["family"],
            "selected_params": run["selected_params"],
            "original_window": _window_metadata(run["timestamps"]),
            "sleeve_alignment": {
                "aligned_observation_count": aligned_count,
                "dropped_observation_count": max(0, len(run["timestamps"]) - aligned_count),
            },
        })

    return {
        "sleeve_key": sleeve_key,
        "sleeve_by": sleeve_by,
        "member_count": len(members),
        "members": members,
        "alignment": {
            "policy": ALIGNMENT_POLICY["policy"],
            "common_window": _window_metadata(sleeve_timestamps),
            "included_member_count": len(members),
            "dropped_observations_total": sum(
                max(0, len(run["timestamps"]) - aligned_count)
                for run in runs
            ),
        },
        "standalone_summary": _return_summary(sleeve_returns, interval),
        "_timestamps": sleeve_timestamps,
        "_returns": sleeve_returns,
    }, []


def _finalize_sleeve_for_view(
    sleeve: dict[str, Any],
    portfolio_timestamps: list[str],
    sleeve_weight: float,
) -> dict[str, Any]:
    aligned_returns = _aligned_returns_from_points(
        timestamps=sleeve["_timestamps"],
        returns=sleeve["_returns"],
        target_timestamps=portfolio_timestamps,
    )
    contribution_stream = []
    cumulative_contribution = 0.0
    for timestamp, value in zip(portfolio_timestamps, aligned_returns):
        period_contribution = sleeve_weight * value
        cumulative_contribution += period_contribution
        contribution_stream.append({
            "timestamp_utc": timestamp,
            "period_return_contribution": period_contribution,
            "cumulative_period_return_contribution": cumulative_contribution,
        })

    return {
        "sleeve_key": sleeve["sleeve_key"],
        "sleeve_by": sleeve["sleeve_by"],
        "weight": sleeve_weight,
        "member_count": sleeve["member_count"],
        "members": sleeve["members"],
        "alignment": {
            **sleeve["alignment"],
            "view_aligned_observation_count": len(portfolio_timestamps),
            "view_dropped_observations": max(0, len(sleeve["_timestamps"]) - len(portfolio_timestamps)),
        },
        "standalone_summary": sleeve["standalone_summary"],
        "contribution": {
            "final_cumulative_period_return_contribution": cumulative_contribution if contribution_stream else 0.0,
            "contribution_stream": contribution_stream,
        },
        "_timestamps": list(sleeve["_timestamps"]),
        "_returns": list(sleeve["_returns"]),
    }


def _diversification(sleeves: list[dict[str, Any]], portfolio_timestamps: list[str]) -> dict[str, Any]:
    sleeve_keys = [sleeve["sleeve_key"] for sleeve in sleeves]
    if not sleeves or not portfolio_timestamps:
        return {
            "sleeve_keys": sleeve_keys,
            "correlation_matrix": [],
            "average_pairwise_correlation": None,
            "diversification_ratio": None,
        }

    aligned = np.asarray([
        _aligned_returns_from_points(
            timestamps=sleeve["_timestamps"],
            returns=sleeve["_returns"],
            target_timestamps=portfolio_timestamps,
        )
        for sleeve in sleeves
    ], dtype=float)
    vols = np.std(aligned, axis=1)
    weights = np.full(len(sleeves), 1.0 / len(sleeves), dtype=float)
    portfolio_returns = aligned.mean(axis=0)
    portfolio_vol = float(np.std(portfolio_returns))

    correlation_matrix: list[list[float | None]] = []
    off_diagonal: list[float] = []
    for i in range(len(sleeves)):
        row: list[float | None] = []
        for j in range(len(sleeves)):
            if i == j:
                row.append(1.0)
                continue
            if vols[i] == 0.0 or vols[j] == 0.0:
                row.append(None)
                continue
            corr = float(np.corrcoef(aligned[i], aligned[j])[0, 1])
            row.append(corr)
            off_diagonal.append(corr)
        correlation_matrix.append(row)

    diversification_ratio = None
    if portfolio_vol > 0.0:
        diversification_ratio = float(np.dot(weights, vols) / portfolio_vol)

    return {
        "sleeve_keys": sleeve_keys,
        "correlation_matrix": correlation_matrix,
        "average_pairwise_correlation": float(np.mean(off_diagonal)) if off_diagonal else None,
        "diversification_ratio": diversification_ratio,
    }


def _public_sleeve(sleeve: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in sleeve.items()
        if key not in {"_timestamps", "_returns"}
    }


def _portfolio_stream(timestamps: list[str], returns: list[float]) -> list[dict[str, Any]]:
    equity = 1.0
    stream = []
    for timestamp, value in zip(timestamps, returns):
        equity *= 1.0 + value
        stream.append({
            "timestamp_utc": timestamp,
            "return": value,
            "cumulative_return": equity - 1.0,
        })
    return stream


def _return_summary(returns: list[float], interval: str) -> dict[str, Any]:
    if not returns:
        return {
            "observation_count": 0,
            "total_return": None,
            "annualized_return": None,
            "volatility": None,
            "sharpe": None,
            "max_drawdown": None,
        }

    values = np.asarray(returns, dtype=float)
    total_return = float(np.prod(1.0 + values) - 1.0)
    volatility = float(values.std() * math.sqrt(_annualization_factor(interval)))
    sharpe = None
    if values.size > 1 and values.std() > 0.0:
        sharpe = float((values.mean() / values.std()) * math.sqrt(_annualization_factor(interval)))

    annualized_return = None
    periods = values.size
    if periods > 0:
        annualized_return = float((1.0 + total_return) ** (_annualization_factor(interval) / periods) - 1.0)

    equity = np.cumprod(1.0 + values)
    peaks = np.maximum.accumulate(equity)
    drawdowns = (equity - peaks) / np.where(peaks > 0.0, peaks, 1.0)

    return {
        "observation_count": int(values.size),
        "total_return": total_return,
        "annualized_return": annualized_return,
        "volatility": volatility,
        "sharpe": sharpe,
        "max_drawdown": float(abs(drawdowns.min())) if drawdowns.size else 0.0,
    }


def _normalize_run(evaluation: dict[str, Any]) -> dict[str, Any]:
    row = evaluation.get("row", {})
    selected_params = dict(evaluation.get("selected_params") or {})
    strategy_id = build_strategy_id(
        row.get("strategy_name", ""),
        row.get("asset", ""),
        row.get("interval", ""),
        selected_params,
    )

    raw_stream = (((evaluation.get("evaluation_report") or {}).get("evaluation_streams") or {}).get("oos_daily_returns"))
    stream, stream_error = _normalize_stream(raw_stream)
    timestamps = [point["timestamp_utc"] for point in stream]

    return {
        "strategy_id": strategy_id,
        "strategy_name": row.get("strategy_name", ""),
        "asset": row.get("asset", ""),
        "family": row.get("family", evaluation.get("family", "")),
        "interval": row.get("interval", evaluation.get("interval", "")),
        "selected_params": selected_params,
        "stream": stream,
        "timestamps": timestamps,
        "stream_error": stream_error,
    }


def _normalize_stream(raw_stream: Any) -> tuple[list[dict[str, Any]], str | None]:
    """Thin delegate to :func:`research._oos_stream.normalize_oos_daily_return_stream`.

    Kept as a private alias so existing call-sites inside
    ``portfolio_reporting`` stay unchanged and byte-identity of
    v3.12+ artifacts is preserved.
    """
    return normalize_oos_daily_return_stream(raw_stream)


def _aligned_return_map(sleeve: dict[str, Any]) -> dict[str, float]:
    return dict(zip(sleeve["_timestamps"], sleeve["_returns"]))


def _aligned_returns(stream: list[dict[str, Any]], timestamps: list[str]) -> list[float]:
    values = {point["timestamp_utc"]: float(point["return"]) for point in stream}
    return [values[timestamp] for timestamp in timestamps]


def _aligned_returns_from_points(
    timestamps: list[str],
    returns: list[float],
    target_timestamps: list[str],
) -> list[float]:
    values = dict(zip(timestamps, returns))
    return [float(values[timestamp]) for timestamp in target_timestamps]


def _common_timestamps(timestamp_lists: list[list[str]]) -> list[str]:
    if not timestamp_lists:
        return []
    common = set(timestamp_lists[0])
    for timestamps in timestamp_lists[1:]:
        common &= set(timestamps)
    return sorted(common)


def _included_runs_from_sleeves(sleeves: list[dict[str, Any]]) -> list[dict[str, Any]]:
    included = []
    for sleeve in sleeves:
        for member in sleeve["members"]:
            included.append({
                "strategy_id": member["strategy_id"],
                "strategy_name": member["strategy_name"],
                "asset": member["asset"],
                "family": member["family"],
                "selected_params": member["selected_params"],
                "sleeve_key": sleeve["sleeve_key"],
            })
    return sorted(included, key=lambda item: item["strategy_id"])


def _excluded_run(run: dict[str, Any], reason: str) -> dict[str, Any]:
    return {
        "strategy_id": run["strategy_id"],
        "strategy_name": run["strategy_name"],
        "asset": run["asset"],
        "family": run["family"],
        "interval": run["interval"],
        "selected_params": run["selected_params"],
        "reason": reason,
    }


def _sleeve_key(run: dict[str, Any], sleeve_by: str) -> str:
    if sleeve_by == "strategy_run":
        return run["strategy_id"]
    if sleeve_by == "asset":
        return run["asset"]
    return run["family"]


def _window_metadata(timestamps: list[str]) -> dict[str, Any]:
    if not timestamps:
        return {
            "start_utc": None,
            "end_utc": None,
            "observation_count": 0,
        }
    return {
        "start_utc": timestamps[0],
        "end_utc": timestamps[-1],
        "observation_count": len(timestamps),
    }


def _annualization_factor(interval: str) -> int:
    return {
        "1d": 252,
        "1h": 252,
        "4h": 252,
        "15m": 252,
        "5m": 252,
    }.get(interval, 252)
