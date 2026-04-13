"""Pure helpers for additive regime diagnostics sidecar assembly."""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from agent.backtesting.regime import (
    COMBINED_LABELS,
    TREND_LABELS,
    VOLATILITY_LABELS,
    normalize_regime_config,
    regime_definition_payload,
)
from research.promotion import build_strategy_id

EVALUATION_VERSION = "regime_diagnostics_v1"


def build_regime_diagnostics_payload(
    evaluations: list[dict[str, Any]],
    as_of_utc,
    git_revision: str,
    config_hash: str,
    evaluation_config: dict[str, Any],
    regime_config: dict[str, Any] | None,
) -> dict[str, Any]:
    """Build the additive regime diagnostics sidecar payload."""
    normalized_regime_config = normalize_regime_config(regime_config)
    runs = [_normalize_run(evaluation) for evaluation in evaluations]
    strategies = [
        _build_strategy_summary(run)
        for run in sorted(runs, key=lambda item: item["strategy_id"])
    ]
    assets = _build_asset_summaries(runs)

    return {
        "version": "v1",
        "generated_at_utc": as_of_utc.isoformat(),
        "git_revision": git_revision,
        "lineage": {
            "config_hash": config_hash,
            "data_snapshot_id": None,
            "evaluation_version": EVALUATION_VERSION,
            "evaluation_config": dict(evaluation_config),
            "seed": None,
        },
        "config_used": normalized_regime_config,
        "regime_definitions": regime_definition_payload(normalized_regime_config),
        "summary": {
            "strategy_run_count": len(strategies),
            "asset_interval_count": len(assets),
            "total_oos_bar_count": sum(item["totals"]["oos_bar_count"] for item in strategies),
            "total_oos_trade_count": sum(item["totals"]["oos_trade_count"] for item in strategies),
        },
        "assets": assets,
        "strategies": strategies,
    }


def _normalize_run(evaluation: dict[str, Any]) -> dict[str, Any]:
    row = evaluation.get("row", {})
    selected_params = dict(evaluation.get("selected_params") or {})
    report = evaluation.get("evaluation_report") or {}
    streams = report.get("evaluation_streams") or {}
    bars = _normalize_bar_stream(streams.get("oos_bar_returns"))
    trades = _normalize_trade_stream(streams.get("oos_trade_events"))
    strategy_id = build_strategy_id(
        row.get("strategy_name", ""),
        row.get("asset", ""),
        row.get("interval", ""),
        selected_params,
    )

    return {
        "strategy_id": strategy_id,
        "strategy_name": row.get("strategy_name", ""),
        "family": row.get("family", evaluation.get("family", "")),
        "asset": row.get("asset", ""),
        "interval": row.get("interval", evaluation.get("interval", "")),
        "selected_params": selected_params,
        "bars": bars,
        "trades": trades,
        "data_quality": {
            "has_oos_bar_returns": bool(bars),
            "has_oos_trade_events": bool(trades),
        },
    }


def _normalize_bar_stream(raw_stream: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_stream, list):
        return []

    bars: list[dict[str, Any]] = []
    for point in raw_stream:
        if not isinstance(point, dict):
            continue
        timestamp = point.get("timestamp_utc")
        asset = point.get("asset")
        fold_index = point.get("fold_index")
        value = point.get("return")
        if not isinstance(timestamp, str) or not isinstance(asset, str):
            continue
        if not isinstance(fold_index, int) or not isinstance(value, (int, float)):
            continue
        bars.append(
            {
                "timestamp_utc": timestamp,
                "asset": asset,
                "fold_index": fold_index,
                "return": float(value),
                "trend_regime": str(point.get("trend_regime", "unknown")),
                "volatility_regime": str(point.get("volatility_regime", "unknown")),
                "combined_regime": str(point.get("combined_regime", "unknown")),
            }
        )

    bars.sort(key=lambda item: (item["fold_index"], item["timestamp_utc"]))
    return bars


def _normalize_trade_stream(raw_stream: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_stream, list):
        return []

    trades: list[dict[str, Any]] = []
    for event in raw_stream:
        if not isinstance(event, dict):
            continue
        if not isinstance(event.get("asset"), str) or not isinstance(event.get("fold_index"), int):
            continue
        if not isinstance(event.get("entry_decision_timestamp_utc"), str):
            continue
        if not isinstance(event.get("entry_timestamp_utc"), str) or not isinstance(event.get("exit_timestamp_utc"), str):
            continue
        if not isinstance(event.get("side"), str) or not isinstance(event.get("pnl"), (int, float)):
            continue
        trades.append(
            {
                "asset": event["asset"],
                "fold_index": int(event["fold_index"]),
                "side": event["side"],
                "entry_decision_timestamp_utc": event["entry_decision_timestamp_utc"],
                "entry_timestamp_utc": event["entry_timestamp_utc"],
                "exit_timestamp_utc": event["exit_timestamp_utc"],
                "pnl": float(event["pnl"]),
                "entry_trend_regime": str(event.get("entry_trend_regime", "unknown")),
                "entry_volatility_regime": str(event.get("entry_volatility_regime", "unknown")),
                "entry_combined_regime": str(event.get("entry_combined_regime", "unknown")),
            }
        )

    trades.sort(key=lambda item: (item["fold_index"], item["entry_timestamp_utc"], item["exit_timestamp_utc"]))
    return trades


def _build_asset_summaries(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], dict[tuple[int, str], dict[str, Any]]] = {}

    for run in runs:
        key = (run["asset"], run["interval"])
        deduped = grouped.setdefault(key, {})
        for bar in run["bars"]:
            dedupe_key = (bar["fold_index"], bar["timestamp_utc"])
            deduped.setdefault(dedupe_key, bar)

    summaries = []
    for (asset, interval), deduped in sorted(grouped.items()):
        bars = [deduped[key] for key in sorted(deduped)]
        summaries.append(
            {
                "asset": asset,
                "interval": interval,
                "oos_bar_count": len(bars),
                "coverage": _coverage_breakdown(bars),
                "fold_breakdown": _asset_fold_breakdown(bars),
                "reconciliation": {
                    "trend_coverage_matches_total": _coverage_sum_matches_total(_coverage_entries(bars, "trend_regime", TREND_LABELS), len(bars)),
                    "volatility_coverage_matches_total": _coverage_sum_matches_total(_coverage_entries(bars, "volatility_regime", VOLATILITY_LABELS), len(bars)),
                    "combined_coverage_matches_total": _coverage_sum_matches_total(_coverage_entries(bars, "combined_regime", COMBINED_LABELS), len(bars)),
                },
            }
        )

    return summaries


def _asset_fold_breakdown(bars: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[int, list[dict[str, Any]]] = {}
    for bar in bars:
        grouped.setdefault(bar["fold_index"], []).append(bar)

    return [
        {
            "fold_index": fold_index,
            "oos_bar_count": len(group),
            "coverage": _coverage_breakdown(group),
            "reconciliation": {
                "combined_coverage_matches_total": _coverage_sum_matches_total(
                    _coverage_entries(group, "combined_regime", COMBINED_LABELS),
                    len(group),
                )
            },
        }
        for fold_index, group in sorted(grouped.items())
    ]


def _build_strategy_summary(run: dict[str, Any]) -> dict[str, Any]:
    bars = run["bars"]
    trades = run["trades"]
    total_bar_count = len(bars)
    total_trade_count = len(trades)
    total_arithmetic_return_contribution = float(sum(bar["return"] for bar in bars)) if bars else 0.0

    return {
        "strategy_id": run["strategy_id"],
        "strategy_name": run["strategy_name"],
        "family": run["family"],
        "asset": run["asset"],
        "interval": run["interval"],
        "selected_params": run["selected_params"],
        "data_quality": dict(run["data_quality"]),
        "totals": {
            "oos_bar_count": total_bar_count,
            "oos_trade_count": total_trade_count,
            "arithmetic_return_contribution_total": total_arithmetic_return_contribution,
            "return_metrics": _bar_metrics([bar["return"] for bar in bars], run["interval"]),
        },
        "regime_breakdown": {
            "trend": _regime_breakdown(
                bars=bars,
                trades=trades,
                bar_label_key="trend_regime",
                trade_label_key="entry_trend_regime",
                labels=TREND_LABELS,
                interval=run["interval"],
            ),
            "volatility": _regime_breakdown(
                bars=bars,
                trades=trades,
                bar_label_key="volatility_regime",
                trade_label_key="entry_volatility_regime",
                labels=VOLATILITY_LABELS,
                interval=run["interval"],
            ),
            "combined": _regime_breakdown(
                bars=bars,
                trades=trades,
                bar_label_key="combined_regime",
                trade_label_key="entry_combined_regime",
                labels=COMBINED_LABELS,
                interval=run["interval"],
            ),
        },
        "fold_breakdown": _strategy_fold_breakdown(run),
        "reconciliation": {
            "trend_coverage_matches_total": _coverage_sum_matches_total(
                _coverage_entries(bars, "trend_regime", TREND_LABELS),
                total_bar_count,
            ),
            "volatility_coverage_matches_total": _coverage_sum_matches_total(
                _coverage_entries(bars, "volatility_regime", VOLATILITY_LABELS),
                total_bar_count,
            ),
            "combined_coverage_matches_total": _coverage_sum_matches_total(
                _coverage_entries(bars, "combined_regime", COMBINED_LABELS),
                total_bar_count,
            ),
            "trend_trade_counts_match_total": _trade_count_matches_total(
                trades,
                "entry_trend_regime",
                TREND_LABELS,
                total_trade_count,
            ),
            "volatility_trade_counts_match_total": _trade_count_matches_total(
                trades,
                "entry_volatility_regime",
                VOLATILITY_LABELS,
                total_trade_count,
            ),
            "combined_trade_counts_match_total": _trade_count_matches_total(
                trades,
                "entry_combined_regime",
                COMBINED_LABELS,
                total_trade_count,
            ),
            "combined_return_contribution_matches_total": _return_contribution_matches_total(
                bars,
                "combined_regime",
                COMBINED_LABELS,
                total_arithmetic_return_contribution,
            ),
        },
    }


def _strategy_fold_breakdown(run: dict[str, Any]) -> list[dict[str, Any]]:
    bars_by_fold: dict[int, list[dict[str, Any]]] = {}
    trades_by_fold: dict[int, list[dict[str, Any]]] = {}
    for bar in run["bars"]:
        bars_by_fold.setdefault(bar["fold_index"], []).append(bar)
    for trade in run["trades"]:
        trades_by_fold.setdefault(trade["fold_index"], []).append(trade)

    fold_indices = sorted(set(bars_by_fold) | set(trades_by_fold))
    breakdown = []
    for fold_index in fold_indices:
        bars = bars_by_fold.get(fold_index, [])
        trades = trades_by_fold.get(fold_index, [])
        breakdown.append(
            {
                "fold_index": fold_index,
                "oos_bar_count": len(bars),
                "oos_trade_count": len(trades),
                "combined": _regime_breakdown(
                    bars=bars,
                    trades=trades,
                    bar_label_key="combined_regime",
                    trade_label_key="entry_combined_regime",
                    labels=COMBINED_LABELS,
                    interval=run["interval"],
                ),
                "reconciliation": {
                    "combined_coverage_matches_total": _coverage_sum_matches_total(
                        _coverage_entries(bars, "combined_regime", COMBINED_LABELS),
                        len(bars),
                    ),
                    "combined_trade_counts_match_total": _trade_count_matches_total(
                        trades,
                        "entry_combined_regime",
                        COMBINED_LABELS,
                        len(trades),
                    ),
                },
            }
        )
    return breakdown


def _coverage_breakdown(bars: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    return {
        "trend": _coverage_entries(bars, "trend_regime", TREND_LABELS),
        "volatility": _coverage_entries(bars, "volatility_regime", VOLATILITY_LABELS),
        "combined": _coverage_entries(bars, "combined_regime", COMBINED_LABELS),
    }


def _coverage_entries(
    bars: list[dict[str, Any]],
    key: str,
    labels: tuple[str, ...],
) -> list[dict[str, Any]]:
    total = len(bars)
    counts = {label: 0 for label in labels}
    for bar in bars:
        label = str(bar.get(key, "unknown"))
        counts[label if label in counts else "unknown"] += 1
    return [
        {
            "label": label,
            "count": counts[label],
            "share": _share(counts[label], total),
        }
        for label in labels
    ]


def _regime_breakdown(
    *,
    bars: list[dict[str, Any]],
    trades: list[dict[str, Any]],
    bar_label_key: str,
    trade_label_key: str,
    labels: tuple[str, ...],
    interval: str,
) -> list[dict[str, Any]]:
    total_bar_count = len(bars)
    total_trade_count = len(trades)
    entries = []
    for label in labels:
        bar_subset = [bar for bar in bars if bar.get(bar_label_key, "unknown") == label]
        trade_subset = [trade for trade in trades if trade.get(trade_label_key, "unknown") == label]
        entries.append(
            {
                "label": label,
                "coverage_count": len(bar_subset),
                "coverage_share": _share(len(bar_subset), total_bar_count),
                "arithmetic_return_contribution": float(sum(bar["return"] for bar in bar_subset)) if bar_subset else 0.0,
                "return_metrics": _bar_metrics([bar["return"] for bar in bar_subset], interval),
                "trade_count": len(trade_subset),
                "trade_share": _share(len(trade_subset), total_trade_count),
                "trade_metrics": _trade_metrics([trade["pnl"] for trade in trade_subset]),
            }
        )
    return entries


def _bar_metrics(returns: list[float], interval: str) -> dict[str, Any]:
    if not returns:
        return {
            "count": 0,
            "compounded_return": None,
            "mean_return": None,
            "positive_return_rate": None,
            "volatility": None,
            "sharpe": None,
            "max_drawdown": None,
            "validity": {
                "compounded_return_valid": False,
                "mean_return_valid": False,
                "positive_return_rate_valid": False,
                "volatility_valid": False,
                "sharpe_valid": False,
                "max_drawdown_valid": False,
            },
        }

    values = np.asarray(returns, dtype=float)
    compounded_return = float(np.prod(1.0 + values) - 1.0)
    mean_return = float(values.mean())
    positive_return_rate = float(np.mean(values > 0.0))
    volatility_valid = values.size >= 2
    sharpe_valid = volatility_valid and float(values.std()) > 0.0
    volatility = (
        float(values.std() * math.sqrt(_annualization_factor(interval)))
        if volatility_valid
        else None
    )
    sharpe = (
        float((values.mean() / values.std()) * math.sqrt(_annualization_factor(interval)))
        if sharpe_valid
        else None
    )
    equity = np.cumprod(1.0 + values)
    peaks = np.maximum.accumulate(equity)
    drawdowns = (equity - peaks) / np.where(peaks > 0.0, peaks, 1.0)

    return {
        "count": int(values.size),
        "compounded_return": compounded_return,
        "mean_return": mean_return,
        "positive_return_rate": positive_return_rate,
        "volatility": volatility,
        "sharpe": sharpe,
        "max_drawdown": float(abs(drawdowns.min())) if values.size >= 1 else None,
        "validity": {
            "compounded_return_valid": values.size >= 1,
            "mean_return_valid": values.size >= 1,
            "positive_return_rate_valid": values.size >= 1,
            "volatility_valid": volatility_valid,
            "sharpe_valid": sharpe_valid,
            "max_drawdown_valid": values.size >= 1,
        },
    }


def _trade_metrics(pnls: list[float]) -> dict[str, Any]:
    if not pnls:
        return {
            "count": 0,
            "total_pnl": 0.0,
            "mean_pnl": None,
            "win_rate": None,
            "validity": {
                "mean_pnl_valid": False,
                "win_rate_valid": False,
            },
        }

    values = np.asarray(pnls, dtype=float)
    return {
        "count": int(values.size),
        "total_pnl": float(values.sum()),
        "mean_pnl": float(values.mean()),
        "win_rate": float(np.mean(values > 0.0)),
        "validity": {
            "mean_pnl_valid": True,
            "win_rate_valid": True,
        },
    }


def _annualization_factor(interval: str) -> int:
    return {
        "1d": 252,
        "1h": 24 * 365,
        "4h": 6 * 365,
        "15m": 4 * 24 * 365,
        "5m": 12 * 24 * 365,
    }.get(interval, 252)


def _share(count: int, total: int) -> float | None:
    if total <= 0:
        return None
    return round(count / total, 4)


def _coverage_sum_matches_total(entries: list[dict[str, Any]], total: int) -> bool:
    return sum(int(entry["count"]) for entry in entries) == total


def _trade_count_matches_total(
    trades: list[dict[str, Any]],
    key: str,
    labels: tuple[str, ...],
    total: int,
) -> bool:
    counts = {label: 0 for label in labels}
    for trade in trades:
        label = str(trade.get(key, "unknown"))
        counts[label if label in counts else "unknown"] += 1
    return sum(counts.values()) == total


def _return_contribution_matches_total(
    bars: list[dict[str, Any]],
    key: str,
    labels: tuple[str, ...],
    total: float,
) -> bool:
    contributions = {label: 0.0 for label in labels}
    for bar in bars:
        label = str(bar.get(key, "unknown"))
        contributions[label if label in contributions else "unknown"] += float(bar["return"])
    return math.isclose(sum(contributions.values()), total, rel_tol=1e-9, abs_tol=1e-9)
