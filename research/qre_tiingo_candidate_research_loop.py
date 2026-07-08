from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import random
import statistics
import tempfile
from collections import defaultdict
from contextlib import suppress
from datetime import UTC, datetime
from itertools import pairwise
from pathlib import Path
from typing import Any, Final

from research.qre_tiingo_hypothesis_generator_e2e import apply_research_price_continuity

REPORT_KIND: Final[str] = "qre_tiingo_candidate_research_loop"
SCHEMA_VERSION: Final[int] = 1
LIFECYCLE_REPORT_KIND: Final[str] = "qre_tiingo_hypothesis_lifecycle"
UPSTREAM_REPORT_KIND: Final[str] = "qre_tiingo_hypothesis_generator_e2e"
DEFAULT_LIFECYCLE_INPUT: Final[Path] = Path("logs/qre_tiingo_hypothesis_lifecycle/latest.json")
DEFAULT_UPSTREAM_E2E_INPUT: Final[Path] = Path("logs/qre_tiingo_hypothesis_generator_e2e/latest.json")
DEFAULT_BARS_INPUT: Final[Path] = Path(
    "data/imports/tiingo_eod_equities_free/tiingo_eod_etf_20210101_20251231/bars.csv"
)
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_tiingo_candidate_research_loop")
DEFAULT_PRIOR_FEEDBACK_INPUT: Final[Path] = DEFAULT_OUTPUT_DIR / "latest.json"
SCREENING_PROTOCOL: Final[str] = "tiingo_research_candidate_screening_v1"
EXPECTED_UNIVERSE: Final[tuple[str, ...]] = (
    "SPY",
    "QQQ",
    "IWM",
    "DIA",
    "TLT",
    "GLD",
    "XLK",
    "XLF",
    "XLE",
    "XLV",
)
SAFETY: Final[dict[str, bool]] = {
    "research_only": True,
    "screening_only": True,
    "trading_authority": False,
    "creates_orders": False,
    "broker_authority": False,
    "risk_authority": False,
    "promotes_candidates": False,
    "registers_strategy": False,
    "validation_authority": False,
    "paper_authority": False,
    "shadow_authority": False,
    "live_authority": False,
}
LIFECYCLE_FALSE_AUTHORITY_KEYS: Final[tuple[str, ...]] = (
    "trading_authority",
    "creates_candidates",
    "runs_screening",
    "promotes_candidates",
    "registers_strategy",
    "validation_authority",
    "paper_authority",
    "shadow_authority",
    "live_authority",
)
ALLOWED_LOOP_VERDICTS: Final[set[str]] = {
    "pass_research_only_candidate_loop",
    "blocked_missing_or_unsafe_input",
    "blocked_no_admitted_hypotheses",
    "blocked_no_candidate_specs",
    "blocked_no_screening_data",
    "partial_feedback_only",
}
ALLOWED_SCREENING_DECISIONS: Final[set[str]] = {
    "screening_pass",
    "screening_fail",
    "null_not_beaten",
    "insufficient_evidence",
    "blocked_unsafe_input",
}
KNOWN_FAMILIES: Final[set[str]] = {
    "cross_sectional_momentum",
    "risk_on_risk_off_regime",
    "defensive_rotation",
    "volatility_compression_breakout",
    "mean_reversion_after_extreme_dispersion",
}


def _utcnow() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _stable_payload(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _stable_payload(value[key]) for key in sorted(value)}
    if isinstance(value, list | tuple):
        return [_stable_payload(item) for item in value]
    if isinstance(value, float):
        if not math.isfinite(value):
            return None
        return round(value, 10)
    return value


def _digest(value: Any, *, length: int = 16) -> str:
    payload = json.dumps(
        _stable_payload(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:length]


def _sha(value: Any) -> str:
    return "sha256:" + _digest(value, length=64)


def _read_json(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    if not path.is_file():
        return None, "missing_artifact"
    try:
        parsed = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None, "malformed_artifact"
    if not isinstance(parsed, dict):
        return None, "malformed_artifact"
    return parsed, None


def _source_path(path: Path, repo_root: Path) -> str:
    resolved = path if path.is_absolute() else repo_root / path
    try:
        return resolved.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return resolved.as_posix()


def _run_config(*, max_candidates: int, null_iterations: int, seed: int) -> dict[str, Any]:
    return {
        "max_candidates": max_candidates,
        "null_iterations": null_iterations,
        "seed": seed,
        "screening_only": True,
        "research_only": True,
    }


def _empty_summary() -> dict[str, Any]:
    return {
        "loop_verdict": "blocked_missing_or_unsafe_input",
        "input_contracts_seen": 0,
        "input_contracts_admitted": 0,
        "candidates_materialized": 0,
        "candidates_screened": 0,
        "screening_pass": 0,
        "screening_fail": 0,
        "null_not_beaten": 0,
        "insufficient_evidence": 0,
        "feedback_records": 0,
        "feedback_consumed": False,
        "feedback_applied_count": 0,
        "next_run_feedback_ready": False,
        "suppressed_by_prior_feedback": 0,
        "modified_by_prior_feedback": 0,
        "retained_by_prior_feedback": 0,
    }


def _daily_digest_input(report: dict[str, Any]) -> dict[str, Any]:
    summary = report["summary"]
    return {
        "digest_kind": "qre_tiingo_candidate_research_loop_daily_input",
        "source": REPORT_KIND,
        "source_snapshot_id": report.get("source_snapshot_id", "unknown"),
        "counts": {
            "input_contracts_admitted": summary["input_contracts_admitted"],
            "candidates_materialized": summary["candidates_materialized"],
            "candidates_screened": summary["candidates_screened"],
            "screening_pass": summary["screening_pass"],
            "screening_fail": summary["screening_fail"],
            "null_not_beaten": summary["null_not_beaten"],
            "insufficient_evidence": summary["insufficient_evidence"],
            "feedback_records": summary["feedback_records"],
            "evidence_records": report.get("evidence_ledger_summary", {}).get("evidence_records", 0),
        },
        "next_actions": sorted(
            {
                str(record.get("next_candidate_action"))
                for record in report.get("feedback_records", [])
                if record.get("next_candidate_action")
            }
        ),
        "authority_summary": dict(SAFETY),
    }


def _base_report(
    *,
    lifecycle: dict[str, Any] | None,
    upstream: dict[str, Any] | None,
    run_config: dict[str, Any],
    blocked_reasons: list[str],
) -> dict[str, Any]:
    source_snapshot_id = "unknown"
    if isinstance(lifecycle, dict) and lifecycle.get("source_snapshot_id"):
        source_snapshot_id = str(lifecycle["source_snapshot_id"])
    elif isinstance(upstream, dict) and upstream.get("source_snapshot_id"):
        source_snapshot_id = str(upstream["source_snapshot_id"])
    return {
        "report_kind": REPORT_KIND,
        "schema_version": SCHEMA_VERSION,
        "generated_at": _utcnow(),
        "source_snapshot_id": source_snapshot_id,
        "source_lifecycle_report_kind": LIFECYCLE_REPORT_KIND,
        "source_hypothesis_report_kind": UPSTREAM_REPORT_KIND,
        "run_config": run_config,
        "summary": _empty_summary(),
        "input_contracts": [],
        "candidate_specs": [],
        "screening_results": [],
        "feedback_records": [],
        "evidence_ledger": [],
        "evidence_ledger_summary": _empty_evidence_ledger_summary(),
        "prior_feedback": {
            "feedback_consumed": False,
            "feedback_source_path": None,
            "feedback_records_seen": 0,
            "feedback_applied_count": 0,
            "feedback_application": [],
        },
        "next_run_plan": {},
        "daily_digest_input": {},
        "safety": dict(SAFETY),
        "blocked_reasons": sorted(dict.fromkeys(blocked_reasons)),
    }


def _empty_evidence_ledger_summary() -> dict[str, Any]:
    return {
        "evidence_records": 0,
        "retain_research_evidence": 0,
        "weak_research_evidence": 0,
        "insufficient_research_evidence": 0,
        "blocked_research_evidence": 0,
        "research_only": True,
        "trading_authority": False,
    }


def _blocked_report(
    *,
    lifecycle: dict[str, Any] | None,
    upstream: dict[str, Any] | None,
    run_config: dict[str, Any],
    loop_verdict: str,
    blocked_reasons: list[str],
    prior_feedback: dict[str, Any] | None = None,
) -> dict[str, Any]:
    report = _base_report(
        lifecycle=lifecycle,
        upstream=upstream,
        run_config=run_config,
        blocked_reasons=blocked_reasons,
    )
    report["summary"]["loop_verdict"] = loop_verdict
    if prior_feedback is not None:
        report["prior_feedback"] = prior_feedback
        report["summary"]["feedback_consumed"] = prior_feedback["feedback_consumed"]
        report["summary"]["feedback_applied_count"] = prior_feedback["feedback_applied_count"]
    report["daily_digest_input"] = _daily_digest_input(report)
    return report


def _validate_lifecycle(lifecycle: dict[str, Any] | None, load_error: str | None) -> list[str]:
    if load_error == "missing_artifact":
        return ["missing_lifecycle_artifact"]
    if load_error is not None or lifecycle is None:
        return ["malformed_lifecycle_artifact"]
    reasons: list[str] = []
    summary = lifecycle.get("summary") if isinstance(lifecycle.get("summary"), dict) else {}
    safety = lifecycle.get("safety") if isinstance(lifecycle.get("safety"), dict) else {}
    if lifecycle.get("report_kind") != LIFECYCLE_REPORT_KIND:
        reasons.append("unexpected_lifecycle_report_kind")
    if summary.get("lifecycle_verdict") != "pass_research_only_admission_boundary":
        reasons.append("lifecycle_verdict_not_pass")
    if summary.get("daily_digest_ready") is not True:
        reasons.append("lifecycle_daily_digest_not_ready")
    for key in LIFECYCLE_FALSE_AUTHORITY_KEYS:
        if safety.get(key) is not False:
            reasons.append(f"unsafe_lifecycle_authority:{key}")
    records = lifecycle.get("hypothesis_lifecycle")
    if not isinstance(records, list):
        reasons.append("missing_hypothesis_lifecycle_records")
    return sorted(dict.fromkeys(reasons))


def build_input_contracts(lifecycle: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows = lifecycle.get("hypothesis_lifecycle")
    records = rows if isinstance(rows, list) else []
    contracts: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for row in records:
        if not isinstance(row, dict):
            continue
        if row.get("decision") != "admitted" or row.get("status") != "admissible_for_research_candidate_formulation":
            skipped.append(
                {
                    "source_hypothesis_id": row.get("source_hypothesis_id"),
                    "decision": row.get("decision"),
                    "status": row.get("status"),
                    "reason": "not_admitted_lifecycle_record",
                }
            )
            continue
        digest_value = {
            "hypothesis_seed_id": row.get("hypothesis_seed_id"),
            "source_hypothesis_id": row.get("source_hypothesis_id"),
            "source_snapshot_id": row.get("source_snapshot_id"),
            "feature_family": row.get("feature_family"),
            "source_hypothesis_digest": (row.get("source_hypothesis_digest") or {}).get("digest")
            if isinstance(row.get("source_hypothesis_digest"), dict)
            else None,
        }
        contract_id = "contract_tiingo_" + _digest(digest_value)
        contract = {
            "contract_id": contract_id,
            "schema_version": 1,
            "source": LIFECYCLE_REPORT_KIND,
            "hypothesis_seed_id": str(row.get("hypothesis_seed_id")),
            "source_hypothesis_id": str(row.get("source_hypothesis_id")),
            "source_snapshot_id": str(row.get("source_snapshot_id")),
            "feature_family": str(row.get("feature_family")),
            "status": "admissible_for_research_candidate_formulation",
            "decision": "admitted",
            "source_hypothesis_digest": row.get("source_hypothesis_digest")
            if isinstance(row.get("source_hypothesis_digest"), dict)
            else {},
            "required_candidate_spec_fields": list(row.get("required_candidate_spec_fields") or []),
            "allowed_candidate_families": list(row.get("allowed_candidate_families") or []),
            "forbidden_authorities": list(row.get("forbidden_authorities") or []),
            "research_only": True,
            "screening_only": True,
            "trading_authority": False,
        }
        contract["contract_digest"] = _sha({key: value for key, value in contract.items() if key != "contract_digest"})
        contracts.append(contract)
    contracts.sort(key=lambda item: item["contract_id"])
    return contracts, skipped


def _candidate_template(feature_family: str, *, variant: str = "v1") -> dict[str, Any] | None:
    lookback = 40 if variant == "modified_by_prior_feedback" else 60
    if feature_family == "cross_sectional_momentum":
        return {
            "candidate_family": "cross_sectional_momentum",
            "signal_definition": {
                "type": "rank_trailing_adjusted_return",
                "lookback_trading_days": lookback,
                "price": "split_adjusted_research_close",
            },
            "selection_rule": {"type": "top_n", "count": 3},
            "rebalance_rule": {"frequency_trading_days": 20},
            "holding_period": {"trading_days": 20},
            "benchmark": {"type": "equal_weight_universe"},
            "universe": list(EXPECTED_UNIVERSE),
        }
    if feature_family == "risk_on_risk_off_regime":
        return {
            "candidate_family": "risk_on_risk_off_regime",
            "signal_definition": {
                "type": "spy_vs_tlt_relative_strength",
                "lookback_trading_days": lookback,
                "price": "split_adjusted_research_close",
            },
            "selection_rule": {
                "type": "risk_on_else_defensive",
                "risk_on_basket": ["SPY", "QQQ", "XLK"],
                "defensive_basket": ["TLT", "GLD", "XLV"],
            },
            "rebalance_rule": {"frequency_trading_days": 20},
            "holding_period": {"trading_days": 20},
            "benchmark": {"type": "equal_weight_universe"},
            "universe": list(EXPECTED_UNIVERSE),
        }
    if feature_family == "defensive_rotation":
        defensive_count = 1 if variant == "modified_by_prior_feedback" else 2
        return {
            "candidate_family": "defensive_rotation",
            "signal_definition": {
                "type": "defensive_score_vs_spy",
                "lookback_trading_days": 60,
                "price": "split_adjusted_research_close",
            },
            "selection_rule": {
                "type": "defensive_when_spy_negative_else_spy_qqq",
                "defensive_count": defensive_count,
                "defensive_basket": ["TLT", "GLD", "XLV"],
            },
            "rebalance_rule": {"frequency_trading_days": 20},
            "holding_period": {"trading_days": 20},
            "benchmark": {"type": "equal_weight_universe"},
            "universe": list(EXPECTED_UNIVERSE),
        }
    if feature_family == "volatility_compression_breakout":
        vol_lookback = 30 if variant == "modified_by_prior_feedback" else 20
        return {
            "candidate_family": "volatility_compression_breakout",
            "signal_definition": {
                "type": "volatility_compression_positive_return",
                "volatility_lookback_trading_days": vol_lookback,
                "return_lookback_trading_days": 20,
                "price": "split_adjusted_research_close",
            },
            "selection_rule": {"type": "lowest_vol_with_positive_return", "count": 3},
            "rebalance_rule": {"frequency_trading_days": 20},
            "holding_period": {"trading_days": 20},
            "benchmark": {"type": "equal_weight_universe"},
            "universe": list(EXPECTED_UNIVERSE),
        }
    if feature_family == "mean_reversion_after_extreme_dispersion":
        threshold = "p75" if variant == "modified_by_prior_feedback" else "rolling_median"
        return {
            "candidate_family": "mean_reversion_after_extreme_dispersion",
            "signal_definition": {
                "type": "cross_sectional_dispersion_return_rank",
                "return_lookback_trading_days": 20,
                "dispersion_threshold": threshold,
                "price": "split_adjusted_research_close",
            },
            "selection_rule": {"type": "bottom_n_when_dispersion_above_threshold", "count": 3},
            "rebalance_rule": {"frequency_trading_days": 20},
            "holding_period": {"trading_days": 20},
            "benchmark": {"type": "equal_weight_universe"},
            "universe": list(EXPECTED_UNIVERSE),
        }
    return None


def materialize_candidate_spec(
    contract: dict[str, Any],
    *,
    variant: str = "v1",
    feedback_note: str | None = None,
) -> tuple[dict[str, Any] | None, str | None]:
    family = str(contract.get("feature_family"))
    template = _candidate_template(family, variant=variant)
    if template is None:
        return None, "blocked_unknown_candidate_family"
    id_basis = {
        "contract_id": contract["contract_id"],
        "feature_family": family,
        "signal_definition": template["signal_definition"],
        "selection_rule": template["selection_rule"],
        "rebalance_rule": template["rebalance_rule"],
        "holding_period": template["holding_period"],
        "benchmark": template["benchmark"],
        "source_snapshot_id": contract["source_snapshot_id"],
        "variant": variant,
    }
    candidate = {
        "candidate_id": "cand_tiingo_" + _digest(id_basis),
        "candidate_schema_version": 1,
        "parent_contract_id": contract["contract_id"],
        "parent_hypothesis_seed_id": contract["hypothesis_seed_id"],
        "source_hypothesis_id": contract["source_hypothesis_id"],
        "source_snapshot_id": contract["source_snapshot_id"],
        "feature_family": family,
        "candidate_family": template["candidate_family"],
        "signal_definition": template["signal_definition"],
        "selection_rule": template["selection_rule"],
        "rebalance_rule": template["rebalance_rule"],
        "holding_period": template["holding_period"],
        "benchmark": template["benchmark"],
        "universe": template["universe"],
        "null_control_requirement": "required",
        "split_adjustment_requirement": "required",
        "screening_protocol": SCREENING_PROTOCOL,
        "screening_only": True,
        "research_only": True,
        "not_trade_signal": True,
        "trading_authority": False,
        "creates_orders": False,
        "forbidden_authorities": list(contract.get("forbidden_authorities") or []),
        "prior_feedback_variant": variant,
    }
    if feedback_note:
        candidate["prior_feedback_note"] = feedback_note
    candidate["candidate_digest"] = _sha({key: value for key, value in candidate.items() if key != "candidate_digest"})
    return candidate, None


def _normalize_columns(fieldnames: list[str] | None) -> dict[str, str]:
    available = {str(name).strip().lower(): str(name) for name in fieldnames or []}
    aliases = {
        "date": ("date", "datetime", "timestamp", "timestamp_utc"),
        "symbol": ("symbol", "ticker"),
        "open": ("open",),
        "high": ("high",),
        "low": ("low",),
        "close": ("close", "adjclose", "adj_close"),
        "volume": ("volume",),
    }
    columns: dict[str, str] = {}
    for target, names in aliases.items():
        for name in names:
            if name in available:
                columns[target] = available[name]
                break
    return columns


def _to_float(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def load_bars(path: Path) -> tuple[list[dict[str, Any]] | None, list[str]]:
    if not path.is_file():
        return None, ["missing_bars_input"]
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            columns = _normalize_columns(reader.fieldnames)
            missing = [name for name in ("date", "symbol", "open", "high", "low", "close", "volume") if name not in columns]
            if missing:
                return None, [f"malformed_bars_input:missing_columns:{','.join(missing)}"]
            bars: list[dict[str, Any]] = []
            for raw in reader:
                symbol = str(raw.get(columns["symbol"]) or "").strip().upper()
                if not symbol:
                    continue
                open_ = _to_float(raw.get(columns["open"]))
                high = _to_float(raw.get(columns["high"]))
                low = _to_float(raw.get(columns["low"]))
                close = _to_float(raw.get(columns["close"]))
                volume = _to_float(raw.get(columns["volume"]))
                if None in (open_, high, low, close, volume):
                    return None, ["malformed_bars_input:non_numeric_ohlcv"]
                bars.append(
                    {
                        "date": str(raw.get(columns["date"]) or "")[:10],
                        "symbol": symbol,
                        "open": float(open_),
                        "high": float(high),
                        "low": float(low),
                        "close": float(close),
                        "volume": float(volume),
                    }
                )
    except OSError:
        return None, ["malformed_bars_input:unreadable"]
    if not bars:
        return None, ["malformed_bars_input:no_rows"]
    adjusted, events, unresolved = apply_research_price_continuity(bars)
    if unresolved:
        return None, ["malformed_bars_input:unresolved_split_like_discontinuity"]
    for row in adjusted:
        row["split_adjustment_events_count"] = len(events)
    return adjusted, []


def _research_close(row: dict[str, Any]) -> float:
    return float(row.get("adjusted_close_for_research", row["close"]))


def _group_closes(bars: list[dict[str, Any]]) -> tuple[list[str], dict[str, list[float]]]:
    by_symbol: dict[str, dict[str, float]] = defaultdict(dict)
    for row in bars:
        by_symbol[str(row["symbol"])][str(row["date"])] = _research_close(row)
    common_dates = sorted(set.intersection(*(set(rows) for rows in by_symbol.values()))) if by_symbol else []
    closes = {
        symbol: [by_symbol[symbol][date] for date in common_dates]
        for symbol in sorted(by_symbol)
        if len(by_symbol[symbol]) >= 2
    }
    return common_dates, closes


def _return_over(closes: list[float], start: int, end: int) -> float | None:
    if start < 0 or end >= len(closes) or closes[start] <= 0:
        return None
    return closes[end] / closes[start] - 1.0


def _trailing_return(closes: list[float], idx: int, lookback: int) -> float | None:
    return _return_over(closes, idx - lookback, idx)


def _trailing_vol(closes: list[float], idx: int, lookback: int) -> float | None:
    if idx - lookback < 0:
        return None
    returns = [
        closes[pos] / closes[pos - 1] - 1.0
        for pos in range(idx - lookback + 1, idx + 1)
        if closes[pos - 1] > 0
    ]
    if len(returns) < lookback:
        return None
    return statistics.pstdev(returns)


def _select_symbols(candidate: dict[str, Any], closes: dict[str, list[float]], idx: int, history: list[float]) -> list[str]:
    family = candidate["feature_family"]
    universe = [symbol for symbol in candidate["universe"] if symbol in closes]
    if family == "cross_sectional_momentum":
        lookback = int(candidate["signal_definition"]["lookback_trading_days"])
        ranked = [
            (symbol, _trailing_return(closes[symbol], idx, lookback))
            for symbol in universe
        ]
        ranked = [(symbol, value) for symbol, value in ranked if value is not None]
        ranked.sort(key=lambda item: (-float(item[1]), item[0]))
        return [symbol for symbol, _value in ranked[: int(candidate["selection_rule"]["count"])]]
    if family == "risk_on_risk_off_regime":
        lookback = int(candidate["signal_definition"]["lookback_trading_days"])
        spy = _trailing_return(closes.get("SPY", []), idx, lookback)
        tlt = _trailing_return(closes.get("TLT", []), idx, lookback)
        basket = candidate["selection_rule"]["risk_on_basket"] if spy is not None and tlt is not None and spy > tlt else candidate["selection_rule"]["defensive_basket"]
        return [symbol for symbol in basket if symbol in closes]
    if family == "defensive_rotation":
        lookback = int(candidate["signal_definition"]["lookback_trading_days"])
        spy_return = _trailing_return(closes.get("SPY", []), idx, lookback)
        if spy_return is not None and spy_return >= 0:
            return [symbol for symbol in ("SPY", "QQQ") if symbol in closes]
        ranked = [
            (symbol, _trailing_return(closes[symbol], idx, lookback))
            for symbol in candidate["selection_rule"]["defensive_basket"]
            if symbol in closes
        ]
        ranked = [(symbol, value) for symbol, value in ranked if value is not None]
        ranked.sort(key=lambda item: (-float(item[1]), item[0]))
        return [symbol for symbol, _value in ranked[: int(candidate["selection_rule"]["defensive_count"])]]
    if family == "volatility_compression_breakout":
        vol_lookback = int(candidate["signal_definition"]["volatility_lookback_trading_days"])
        return_lookback = int(candidate["signal_definition"]["return_lookback_trading_days"])
        ranked = []
        for symbol in universe:
            ret = _trailing_return(closes[symbol], idx, return_lookback)
            vol = _trailing_vol(closes[symbol], idx, vol_lookback)
            if ret is not None and ret > 0 and vol is not None:
                ranked.append((symbol, vol))
        ranked.sort(key=lambda item: (float(item[1]), item[0]))
        return [symbol for symbol, _value in ranked[: int(candidate["selection_rule"]["count"])]]
    if family == "mean_reversion_after_extreme_dispersion":
        lookback = int(candidate["signal_definition"]["return_lookback_trading_days"])
        returns = {
            symbol: _trailing_return(closes[symbol], idx, lookback)
            for symbol in universe
        }
        valid = [float(value) for value in returns.values() if value is not None]
        if len(valid) < 3:
            return []
        dispersion = statistics.pstdev(valid)
        threshold_mode = candidate["signal_definition"]["dispersion_threshold"]
        threshold = statistics.median(history) if threshold_mode == "rolling_median" and history else 0.0
        if threshold_mode == "p75" and history:
            threshold = _percentile(history, 75)
        history.append(dispersion)
        if dispersion <= threshold:
            return []
        ranked = [(symbol, value) for symbol, value in returns.items() if value is not None]
        ranked.sort(key=lambda item: (float(item[1]), item[0]))
        return [symbol for symbol, _value in ranked[: int(candidate["selection_rule"]["count"])]]
    return []


def _compound(returns: list[float]) -> float:
    value = 1.0
    for item in returns:
        value *= 1.0 + item
    return value - 1.0


def _max_drawdown(returns: list[float]) -> float:
    equity = 1.0
    peak = 1.0
    worst = 0.0
    for item in returns:
        equity *= 1.0 + item
        peak = max(peak, equity)
        if peak > 0:
            worst = min(worst, equity / peak - 1.0)
    return abs(worst)


def _sharpe_like(returns: list[float]) -> float:
    if len(returns) < 2:
        return 0.0
    vol = statistics.pstdev(returns)
    if vol <= 0:
        return 0.0
    return statistics.fmean(returns) / vol * math.sqrt(252 / 20)


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = (len(ordered) - 1) * pct / 100.0
    lower = math.floor(idx)
    upper = math.ceil(idx)
    if lower == upper:
        return ordered[int(idx)]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (idx - lower)


def _screen_candidate_returns(
    candidate: dict[str, Any],
    closes: dict[str, list[float]],
) -> tuple[list[float], list[float], int, int, list[list[str]]]:
    universe = [symbol for symbol in candidate["universe"] if symbol in closes]
    if not universe:
        return [], [], 0, 0, []
    max_lookback = 60
    signal = candidate["signal_definition"]
    for key in ("lookback_trading_days", "volatility_lookback_trading_days", "return_lookback_trading_days"):
        if key in signal:
            max_lookback = max(max_lookback, int(signal[key]))
    holding = int(candidate["holding_period"]["trading_days"])
    frequency = int(candidate["rebalance_rule"]["frequency_trading_days"])
    length = min(len(closes[symbol]) for symbol in universe)
    candidate_returns: list[float] = []
    benchmark_returns: list[float] = []
    selections: list[list[str]] = []
    dispersion_history: list[float] = []
    for idx in range(max_lookback, length - holding, frequency):
        selected = _select_symbols(candidate, closes, idx, dispersion_history)
        if not selected:
            continue
        selected_returns = [_return_over(closes[symbol], idx, idx + holding) for symbol in selected]
        benchmark_period_returns = [_return_over(closes[symbol], idx, idx + holding) for symbol in universe]
        selected_values = [float(value) for value in selected_returns if value is not None]
        benchmark_values = [float(value) for value in benchmark_period_returns if value is not None]
        if selected_values and benchmark_values:
            candidate_returns.append(statistics.fmean(selected_values))
            benchmark_returns.append(statistics.fmean(benchmark_values))
            selections.append(selected)
    selection_count = sum(len(row) for row in selections)
    return candidate_returns, benchmark_returns, length, selection_count, selections


def _null_control(
    *,
    candidate: dict[str, Any],
    closes: dict[str, list[float]],
    selections: list[list[str]],
    null_iterations: int,
    seed: int,
) -> dict[str, Any]:
    universe = [symbol for symbol in candidate["universe"] if symbol in closes]
    holding = int(candidate["holding_period"]["trading_days"])
    frequency = int(candidate["rebalance_rule"]["frequency_trading_days"])
    signal = candidate["signal_definition"]
    max_lookback = 60
    for key in ("lookback_trading_days", "volatility_lookback_trading_days", "return_lookback_trading_days"):
        if key in signal:
            max_lookback = max(max_lookback, int(signal[key]))
    length = min(len(closes[symbol]) for symbol in universe) if universe else 0
    rng = random.Random(seed)
    null_total_returns: list[float] = []
    null_sharpes: list[float] = []
    selection_sizes = [len(item) for item in selections] or [1]
    for iteration in range(max(0, null_iterations)):
        returns: list[float] = []
        size = selection_sizes[iteration % len(selection_sizes)]
        for idx in range(max_lookback, length - holding, frequency):
            if not universe:
                continue
            sampled = rng.sample(universe, k=min(size, len(universe)))
            period = [_return_over(closes[symbol], idx, idx + holding) for symbol in sampled]
            values = [float(value) for value in period if value is not None]
            if values:
                returns.append(statistics.fmean(values))
        null_total_returns.append(_compound(returns))
        null_sharpes.append(_sharpe_like(returns))
    return {
        "null_iterations": null_iterations,
        "seed": seed,
        "null_total_return_p50": _percentile(null_total_returns, 50),
        "null_total_return_p75": _percentile(null_total_returns, 75),
        "null_sharpe_like_p50": _percentile(null_sharpes, 50),
        "beats_null_p50": False,
        "beats_null_p75": False,
        "equal_weight_benchmark": {"type": "equal_weight_universe"},
        "shuffled_selection_null": {"method": "seeded_random_selection_by_rebalance"},
    }


def screen_candidate(
    candidate: dict[str, Any],
    bars: list[dict[str, Any]] | None,
    *,
    null_iterations: int,
    seed: int,
    forced_decision: str | None = None,
    forced_reason: str | None = None,
) -> dict[str, Any]:
    base = {
        "candidate_id": candidate["candidate_id"],
        "parent_contract_id": candidate["parent_contract_id"],
        "parent_hypothesis_seed_id": candidate["parent_hypothesis_seed_id"],
        "source_snapshot_id": candidate["source_snapshot_id"],
        "screening_protocol": SCREENING_PROTOCOL,
        "screening_only": True,
        "research_only": True,
        "observation_count": 0,
        "rebalance_count": 0,
        "selection_count": 0,
        "candidate_total_return": 0.0,
        "benchmark_total_return": 0.0,
        "excess_return": 0.0,
        "candidate_annualized_return": 0.0,
        "candidate_annualized_vol": 0.0,
        "candidate_sharpe_like": 0.0,
        "max_drawdown": 0.0,
        "win_rate": 0.0,
        "turnover_proxy": 0.0,
        "null_control": {
            "null_iterations": null_iterations,
            "seed": seed,
            "null_total_return_p50": 0.0,
            "null_total_return_p75": 0.0,
            "null_sharpe_like_p50": 0.0,
            "beats_null_p50": False,
            "beats_null_p75": False,
            "equal_weight_benchmark": {"type": "equal_weight_universe"},
            "shuffled_selection_null": {"method": "seeded_random_selection_by_rebalance"},
        },
        "decision": "blocked_unsafe_input",
        "decision_reasons": [],
        "blocked_reasons": [],
        "trading_authority": False,
        "validation_authority": False,
        "promotes_candidates": False,
    }
    if forced_decision:
        base["decision"] = forced_decision
        base["decision_reasons"] = [forced_reason or forced_decision]
        return base
    if not bars:
        base["blocked_reasons"] = ["missing_or_malformed_screening_data"]
        return base
    _dates, closes = _group_closes(bars)
    candidate_returns, benchmark_returns, observations, selection_count, selections = _screen_candidate_returns(candidate, closes)
    base["observation_count"] = observations
    base["rebalance_count"] = len(candidate_returns)
    base["selection_count"] = selection_count
    if not candidate_returns or not benchmark_returns:
        base["decision"] = "insufficient_evidence"
        base["decision_reasons"] = ["no_screenable_rebalance_windows"]
        return base
    candidate_total = _compound(candidate_returns)
    benchmark_total = _compound(benchmark_returns)
    excess = candidate_total - benchmark_total
    periods_per_year = 252 / 20
    ann_return = (1.0 + candidate_total) ** (periods_per_year / max(1, len(candidate_returns))) - 1.0 if candidate_total > -1 else -1.0
    ann_vol = statistics.pstdev(candidate_returns) * math.sqrt(periods_per_year) if len(candidate_returns) > 1 else 0.0
    sharpe = _sharpe_like(candidate_returns)
    max_drawdown = _max_drawdown(candidate_returns)
    wins = sum(1 for left, right in zip(candidate_returns, benchmark_returns, strict=True) if left > right)
    turnover = 0.0
    if len(selections) > 1:
        changes = []
        for previous, current in pairwise(selections):
            previous_set = set(previous)
            current_set = set(current)
            changes.append(1.0 - (len(previous_set & current_set) / max(1, len(previous_set | current_set))))
        turnover = statistics.fmean(changes)
    null_control = _null_control(
        candidate=candidate,
        closes=closes,
        selections=selections,
        null_iterations=null_iterations,
        seed=seed,
    )
    null_control["beats_null_p50"] = candidate_total > null_control["null_total_return_p50"] and sharpe > null_control["null_sharpe_like_p50"]
    null_control["beats_null_p75"] = candidate_total > null_control["null_total_return_p75"]
    base.update(
        {
            "candidate_total_return": candidate_total,
            "benchmark_total_return": benchmark_total,
            "excess_return": excess,
            "candidate_annualized_return": ann_return,
            "candidate_annualized_vol": ann_vol,
            "candidate_sharpe_like": sharpe,
            "max_drawdown": max_drawdown,
            "win_rate": wins / len(candidate_returns),
            "turnover_proxy": turnover,
            "null_control": null_control,
        }
    )
    finite_metrics = all(
        math.isfinite(float(base[key]))
        for key in (
            "candidate_total_return",
            "benchmark_total_return",
            "excess_return",
            "candidate_annualized_return",
            "candidate_annualized_vol",
            "candidate_sharpe_like",
            "max_drawdown",
            "win_rate",
            "turnover_proxy",
        )
    )
    if observations < 252 or len(candidate_returns) < 12 or null_iterations < 16 or not finite_metrics:
        base["decision"] = "insufficient_evidence"
        base["decision_reasons"] = ["minimum_evidence_gates_failed"]
    elif not null_control["beats_null_p50"]:
        base["decision"] = "null_not_beaten"
        base["decision_reasons"] = ["candidate_did_not_beat_seeded_null_p50"]
    elif excess <= 0 or not math.isfinite(max_drawdown):
        base["decision"] = "screening_fail"
        base["decision_reasons"] = ["candidate_did_not_beat_equal_weight_benchmark"]
    else:
        base["decision"] = "screening_pass"
        base["decision_reasons"] = ["candidate_beat_equal_weight_and_seeded_null_p50"]
    return _stable_payload(base)


def feedback_from_screening(result: dict[str, Any]) -> dict[str, Any]:
    decision = str(result.get("decision"))
    mapping = {
        "screening_pass": (
            "retain_for_more_screening",
            "rematerialize_same_spec",
            "retain_hypothesis",
            ["candidate_passed_research_only_screening"],
        ),
        "null_not_beaten": (
            "modify_candidate_later",
            "materialize_modified_spec",
            "modify_hypothesis_parameters_later",
            ["candidate_did_not_beat_null_control"],
        ),
        "screening_fail": (
            "reject_candidate_for_now",
            "do_not_rematerialize_same_spec",
            "reject_hypothesis_for_now",
            ["candidate_failed_research_screening"],
        ),
        "insufficient_evidence": (
            "insufficient_evidence",
            "collect_more_data",
            "needs_more_evidence",
            ["candidate_has_insufficient_evidence"],
        ),
        "blocked_unsafe_input": (
            "block_candidate",
            "repair_input_contract",
            "block_hypothesis",
            ["candidate_input_blocked"],
        ),
    }
    feedback_decision, next_candidate_action, next_hypothesis_action, reasons = mapping[decision]
    basis = {
        "candidate_id": result.get("candidate_id"),
        "parent_contract_id": result.get("parent_contract_id"),
        "source_snapshot_id": result.get("source_snapshot_id"),
        "screening_decision": decision,
        "feedback_decision": feedback_decision,
    }
    return {
        "feedback_id": "fb_tiingo_" + _digest(basis),
        "feedback_schema_version": 1,
        "candidate_id": result.get("candidate_id"),
        "parent_contract_id": result.get("parent_contract_id"),
        "parent_hypothesis_seed_id": result.get("parent_hypothesis_seed_id"),
        "source_snapshot_id": result.get("source_snapshot_id"),
        "screening_decision": decision,
        "feedback_decision": feedback_decision,
        "feedback_reasons": reasons,
        "next_candidate_action": next_candidate_action,
        "next_hypothesis_action": next_hypothesis_action,
        "consumable_by_next_run": True,
        "research_only": True,
        "trading_authority": False,
    }


def _evidence_decision(screening_decision: str) -> str:
    if screening_decision == "screening_pass":
        return "retain_research_evidence"
    if screening_decision in {"null_not_beaten", "screening_fail"}:
        return "weak_research_evidence"
    if screening_decision == "insufficient_evidence":
        return "insufficient_research_evidence"
    return "blocked_research_evidence"


def build_evidence_entry(
    *,
    candidate: dict[str, Any],
    screening_result: dict[str, Any],
    feedback_record: dict[str, Any],
) -> dict[str, Any]:
    metrics_summary = {
        "observation_count": int(screening_result.get("observation_count") or 0),
        "rebalance_count": int(screening_result.get("rebalance_count") or 0),
        "candidate_total_return": float(screening_result.get("candidate_total_return") or 0.0),
        "benchmark_total_return": float(screening_result.get("benchmark_total_return") or 0.0),
        "excess_return": float(screening_result.get("excess_return") or 0.0),
        "candidate_sharpe_like": float(screening_result.get("candidate_sharpe_like") or 0.0),
        "max_drawdown": float(screening_result.get("max_drawdown") or 0.0),
        "win_rate": float(screening_result.get("win_rate") or 0.0),
    }
    null_control = (
        screening_result.get("null_control")
        if isinstance(screening_result.get("null_control"), dict)
        else {}
    )
    null_summary = {
        "null_iterations": int(null_control.get("null_iterations") or 0),
        "seed": int(null_control.get("seed") or 0),
        "beats_null_p50": bool(null_control.get("beats_null_p50") is True),
        "beats_null_p75": bool(null_control.get("beats_null_p75") is True),
    }
    metrics_digest = _sha(
        {
            "metrics_summary": metrics_summary,
            "null_control_summary": null_summary,
            "screening_decision": screening_result.get("decision"),
        }
    )
    evidence_decision = _evidence_decision(str(screening_result.get("decision")))
    evidence_basis = {
        "candidate_id": candidate.get("candidate_id"),
        "candidate_digest": candidate.get("candidate_digest"),
        "source_snapshot_id": candidate.get("source_snapshot_id"),
        "screening_decision": screening_result.get("decision"),
        "metrics_digest": metrics_digest,
    }
    return {
        "evidence_id": "ev_tiingo_" + _digest(evidence_basis),
        "evidence_schema_version": 1,
        "evidence_kind": "tiingo_candidate_screening_evidence",
        "candidate_id": candidate.get("candidate_id"),
        "candidate_digest": candidate.get("candidate_digest"),
        "parent_contract_id": candidate.get("parent_contract_id"),
        "parent_hypothesis_seed_id": candidate.get("parent_hypothesis_seed_id"),
        "source_hypothesis_id": candidate.get("source_hypothesis_id"),
        "source_snapshot_id": candidate.get("source_snapshot_id"),
        "feature_family": candidate.get("feature_family"),
        "candidate_family": candidate.get("candidate_family"),
        "screening_protocol": SCREENING_PROTOCOL,
        "data_basis": {
            "source_id": "tiingo_eod_equities_free",
            "timeframe": "1d",
            "split_adjustment_requirement": "required",
            "price_basis": "split_adjusted_research_prices",
        },
        "metrics_digest": metrics_digest,
        "metrics_summary": metrics_summary,
        "null_control_summary": null_summary,
        "screening_decision": screening_result.get("decision"),
        "feedback_decision": feedback_record.get("feedback_decision"),
        "evidence_decision": evidence_decision,
        "audit_flags": {
            "research_only": True,
            "screening_only": True,
            "trading_authority": False,
            "validation_authority": False,
            "paper_authority": False,
            "shadow_authority": False,
            "live_authority": False,
        },
    }


def summarize_evidence_ledger(evidence_ledger: list[dict[str, Any]]) -> dict[str, Any]:
    summary = _empty_evidence_ledger_summary()
    summary["evidence_records"] = len(evidence_ledger)
    for row in evidence_ledger:
        decision = str(row.get("evidence_decision"))
        if decision in summary:
            summary[decision] += 1
    return summary


def read_prior_feedback(path: Path) -> dict[str, Any]:
    payload, error = _read_json(path)
    if error is not None or not isinstance(payload, dict):
        return {
            "feedback_consumed": False,
            "feedback_source_path": path.as_posix(),
            "feedback_records_seen": 0,
            "feedback_applied_count": 0,
            "feedback_application": [],
        }
    records = payload.get("feedback_records")
    if not isinstance(records, list):
        records = []
    records = [record for record in records if isinstance(record, dict) and record.get("consumable_by_next_run") is True]
    return {
        "feedback_consumed": bool(records),
        "feedback_source_path": path.as_posix(),
        "feedback_records_seen": len(records),
        "feedback_applied_count": 0,
        "feedback_application": [],
        "_records": records,
    }


def _feedback_by_contract(prior_feedback: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = prior_feedback.get("_records")
    records = rows if isinstance(rows, list) else []
    by_contract: dict[str, dict[str, Any]] = {}
    for record in records:
        contract_id = str(record.get("parent_contract_id") or "")
        if contract_id:
            by_contract[contract_id] = record
    return by_contract


def _apply_prior_feedback(
    contract: dict[str, Any],
    feedback: dict[str, Any] | None,
) -> tuple[str, str | None, dict[str, Any] | None]:
    if feedback is None:
        return "materialize", None, None
    decision = str(feedback.get("feedback_decision"))
    application = {
        "contract_id": contract["contract_id"],
        "candidate_id": feedback.get("candidate_id"),
        "feedback_decision": decision,
        "applied": True,
    }
    if decision == "retain_for_more_screening":
        application["application"] = "retained_by_prior_feedback"
        return "materialize", "retained_by_prior_feedback", application
    if decision == "reject_candidate_for_now":
        application["application"] = "suppressed_by_prior_feedback"
        return "suppress", "suppressed_by_prior_feedback", application
    if decision == "modify_candidate_later":
        application["application"] = "modified_by_prior_feedback"
        return "modify", "modified_by_prior_feedback", application
    if decision == "insufficient_evidence":
        application["application"] = "needs_more_evidence_from_prior_feedback"
        return "defer_screening", "needs_more_evidence_from_prior_feedback", application
    if decision == "block_candidate":
        application["application"] = "blocked_by_prior_feedback"
        return "block", "blocked_by_prior_feedback", application
    application["applied"] = False
    application["application"] = "unknown_feedback_decision"
    return "materialize", None, application


def build_report(
    *,
    repo_root: Path = Path("."),
    lifecycle_input: Path = DEFAULT_LIFECYCLE_INPUT,
    upstream_e2e_input: Path = DEFAULT_UPSTREAM_E2E_INPUT,
    bars_input: Path = DEFAULT_BARS_INPUT,
    prior_feedback_input: Path = DEFAULT_PRIOR_FEEDBACK_INPUT,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    max_candidates: int = 5,
    null_iterations: int = 32,
    seed: int = 1729,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    lifecycle_path = lifecycle_input if lifecycle_input.is_absolute() else repo_root / lifecycle_input
    upstream_path = upstream_e2e_input if upstream_e2e_input.is_absolute() else repo_root / upstream_e2e_input
    bars_path = bars_input if bars_input.is_absolute() else repo_root / bars_input
    prior_path = prior_feedback_input if prior_feedback_input.is_absolute() else repo_root / prior_feedback_input
    config = _run_config(max_candidates=max_candidates, null_iterations=null_iterations, seed=seed)
    lifecycle, lifecycle_error = _read_json(lifecycle_path)
    upstream, _upstream_error = _read_json(upstream_path)
    prior_feedback = read_prior_feedback(prior_path)
    lifecycle_reasons = _validate_lifecycle(lifecycle, lifecycle_error)
    if lifecycle_reasons:
        return _blocked_report(
            lifecycle=lifecycle,
            upstream=upstream,
            run_config=config,
            loop_verdict="blocked_missing_or_unsafe_input",
            blocked_reasons=lifecycle_reasons,
            prior_feedback=prior_feedback,
        )
    assert lifecycle is not None
    contracts, skipped = build_input_contracts(lifecycle)
    if not contracts:
        return _blocked_report(
            lifecycle=lifecycle,
            upstream=upstream,
            run_config=config,
            loop_verdict="blocked_no_admitted_hypotheses",
            blocked_reasons=["no_admitted_lifecycle_records"],
            prior_feedback=prior_feedback,
        )

    feedback_map = _feedback_by_contract(prior_feedback)
    applications: list[dict[str, Any]] = []
    candidate_specs: list[dict[str, Any]] = []
    screening_results: list[dict[str, Any]] = []
    feedback_records: list[dict[str, Any]] = []
    evidence_ledger: list[dict[str, Any]] = []
    blocked_reasons: list[str] = []
    deferred_candidate_ids: set[str] = set()
    counters = {
        "suppressed_by_prior_feedback": 0,
        "modified_by_prior_feedback": 0,
        "retained_by_prior_feedback": 0,
    }

    for contract in contracts[: max(0, max_candidates)]:
        action, note, application = _apply_prior_feedback(contract, feedback_map.get(contract["contract_id"]))
        if application is not None:
            applications.append(application)
            if application.get("applied") is True:
                prior_feedback["feedback_applied_count"] += 1
        if note in counters:
            counters[note] += 1
        if action in {"suppress", "block"}:
            blocked_reasons.append(str(note))
            continue
        variant = "modified_by_prior_feedback" if action == "modify" else "v1"
        candidate, block_reason = materialize_candidate_spec(contract, variant=variant, feedback_note=note)
        if block_reason is not None or candidate is None:
            blocked_reasons.append(block_reason or "candidate_materialization_failed")
            continue
        candidate_specs.append(candidate)
        if action == "defer_screening":
            deferred_candidate_ids.add(candidate["candidate_id"])

    prior_feedback["feedback_application"] = applications
    if not candidate_specs:
        report = _blocked_report(
            lifecycle=lifecycle,
            upstream=upstream,
            run_config=config,
            loop_verdict="blocked_no_candidate_specs" if blocked_reasons else "blocked_no_admitted_hypotheses",
            blocked_reasons=blocked_reasons or ["no_candidate_specs_materialized"],
            prior_feedback=prior_feedback,
        )
        report["input_contracts"] = contracts
        report["summary"]["input_contracts_seen"] = len(contracts) + len(skipped)
        report["summary"]["input_contracts_admitted"] = len(contracts)
        report["summary"]["suppressed_by_prior_feedback"] = counters["suppressed_by_prior_feedback"]
        return report

    bars, bars_reasons = load_bars(bars_path)
    for candidate in candidate_specs:
        if candidate["candidate_id"] in deferred_candidate_ids:
            result = screen_candidate(
                candidate,
                None,
                null_iterations=null_iterations,
                seed=seed,
                forced_decision="insufficient_evidence",
                forced_reason="prior_feedback_requested_more_data",
            )
        elif bars_reasons:
            result = screen_candidate(candidate, None, null_iterations=null_iterations, seed=seed)
        else:
            result = screen_candidate(candidate, bars, null_iterations=null_iterations, seed=seed)
        screening_results.append(result)
        feedback_record = feedback_from_screening(result)
        feedback_records.append(feedback_record)
        evidence_ledger.append(
            build_evidence_entry(
                candidate=candidate,
                screening_result=result,
                feedback_record=feedback_record,
            )
        )

    summary = _empty_summary()
    summary["input_contracts_seen"] = len(contracts) + len(skipped)
    summary["input_contracts_admitted"] = len(contracts)
    summary["candidates_materialized"] = len(candidate_specs)
    summary["candidates_screened"] = sum(1 for result in screening_results if result["decision"] != "blocked_unsafe_input")
    for decision in ("screening_pass", "screening_fail", "null_not_beaten", "insufficient_evidence"):
        summary[decision] = sum(1 for result in screening_results if result["decision"] == decision)
    summary["feedback_records"] = len(feedback_records)
    summary["feedback_consumed"] = prior_feedback["feedback_consumed"]
    summary["feedback_applied_count"] = prior_feedback["feedback_applied_count"]
    summary["next_run_feedback_ready"] = bool(feedback_records)
    summary.update(counters)
    if bars_reasons:
        summary["loop_verdict"] = "blocked_no_screening_data"
        blocked_reasons.extend(bars_reasons)
    elif feedback_records and not candidate_specs:
        summary["loop_verdict"] = "partial_feedback_only"
    else:
        summary["loop_verdict"] = "pass_research_only_candidate_loop"
    report = _base_report(
        lifecycle=lifecycle,
        upstream=upstream,
        run_config=config,
        blocked_reasons=blocked_reasons,
    )
    report.update(
        {
            "input_contracts": contracts,
            "candidate_specs": candidate_specs,
            "screening_results": screening_results,
            "feedback_records": feedback_records,
            "evidence_ledger": evidence_ledger,
            "evidence_ledger_summary": summarize_evidence_ledger(evidence_ledger),
            "prior_feedback": {key: value for key, value in prior_feedback.items() if key != "_records"},
            "next_run_plan": _next_run_plan(feedback_records),
            "blocked_reasons": sorted(dict.fromkeys(blocked_reasons)),
        }
    )
    report["summary"] = summary
    report["daily_digest_input"] = _daily_digest_input(report)
    return _stable_payload(report)


def _next_run_plan(feedback_records: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "feedback_ready": bool(feedback_records),
        "feedback_records": len(feedback_records),
        "actions": sorted(
            {
                str(record.get("next_candidate_action"))
                for record in feedback_records
                if record.get("next_candidate_action")
            }
        ),
        "research_only": True,
        "trading_authority": False,
    }


def render_operator_summary(report: dict[str, Any]) -> str:
    summary = report["summary"]
    safety = report["safety"]
    lines = [
        "# Tiingo Candidate Research Loop",
        "",
        f"- Loop verdict: {summary['loop_verdict']}",
        f"- Input contracts seen: {summary['input_contracts_seen']}",
        f"- Input contracts admitted: {summary['input_contracts_admitted']}",
        f"- Candidates materialized: {summary['candidates_materialized']}",
        f"- Candidates screened: {summary['candidates_screened']}",
        f"- Screening pass: {summary['screening_pass']}",
        f"- Screening fail: {summary['screening_fail']}",
        f"- Null not beaten: {summary['null_not_beaten']}",
        f"- Insufficient evidence: {summary['insufficient_evidence']}",
        f"- Feedback records: {summary['feedback_records']}",
        f"- Evidence records: {report.get('evidence_ledger_summary', {}).get('evidence_records', 0)}",
        f"- Feedback consumed: {str(summary['feedback_consumed']).lower()}",
        f"- Feedback applied count: {summary['feedback_applied_count']}",
        f"- Next run feedback ready: {str(summary['next_run_feedback_ready']).lower()}",
        f"- Trading authority: {str(safety['trading_authority']).lower()}",
        f"- Candidate promotion: {str(safety['promotes_candidates']).lower()}",
        f"- Validation authority: {str(safety['validation_authority']).lower()}",
        f"- Paper/shadow/live authority: {str(safety['paper_authority'] or safety['shadow_authority'] or safety['live_authority']).lower()}",
        "",
        "Input contracts:",
        "contract_id | hypothesis_seed_id | feature_family | status",
        "---|---|---|---",
    ]
    for row in report.get("input_contracts", []):
        lines.append(
            f"{row.get('contract_id')} | {row.get('hypothesis_seed_id')} | {row.get('feature_family')} | {row.get('status')}"
        )
    if not report.get("input_contracts"):
        lines.append("none | none | none | none")
    lines.extend(
        [
            "",
            "Candidate specs:",
            "candidate_id | feature_family | candidate_family | screening_only | trading_authority",
            "---|---|---|---|---",
        ]
    )
    for row in report.get("candidate_specs", []):
        lines.append(
            f"{row.get('candidate_id')} | {row.get('feature_family')} | {row.get('candidate_family')} | {str(row.get('screening_only')).lower()} | {str(row.get('trading_authority')).lower()}"
        )
    if not report.get("candidate_specs"):
        lines.append("none | none | none | true | false")
    lines.extend(
        [
            "",
            "Screening results:",
            "candidate_id | decision | excess_return | candidate_sharpe_like | beats_null_p50 | reason",
            "---|---|---|---|---|---",
        ]
    )
    for row in report.get("screening_results", []):
        reason = ", ".join(str(item) for item in row.get("decision_reasons", []) or row.get("blocked_reasons", [])) or "none"
        null = row.get("null_control") if isinstance(row.get("null_control"), dict) else {}
        lines.append(
            f"{row.get('candidate_id')} | {row.get('decision')} | {row.get('excess_return')} | {row.get('candidate_sharpe_like')} | {str(null.get('beats_null_p50')).lower()} | {reason}"
        )
    if not report.get("screening_results"):
        lines.append("none | none | 0.0 | 0.0 | false | none")
    lines.extend(
        [
            "",
            "Feedback:",
            "feedback_id | candidate_id | feedback_decision | next_candidate_action | next_hypothesis_action",
            "---|---|---|---|---",
        ]
    )
    for row in report.get("feedback_records", []):
        lines.append(
            f"{row.get('feedback_id')} | {row.get('candidate_id')} | {row.get('feedback_decision')} | {row.get('next_candidate_action')} | {row.get('next_hypothesis_action')}"
        )
    if not report.get("feedback_records"):
        lines.append("none | none | none | none | none")
    lines.extend(
        [
            "",
            "No orders were created. No broker/risk authority exists. No validation, promotion, strategy registration, paper, shadow, or live authority was granted.",
            "",
        ]
    )
    return "\n".join(lines)


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
        os.replace(tmp_name, path)
    except Exception:
        with suppress(OSError):
            os.unlink(tmp_name)
        raise


def _json_text(value: Any) -> str:
    return json.dumps(_stable_payload(value), indent=2, sort_keys=True, ensure_ascii=True) + "\n"


def _jsonl_text(rows: list[dict[str, Any]]) -> str:
    return "".join(json.dumps(_stable_payload(row), sort_keys=True, ensure_ascii=True) + "\n" for row in rows)


def write_outputs(
    report: dict[str, Any],
    *,
    repo_root: Path = Path("."),
    output_dir: Path = DEFAULT_OUTPUT_DIR,
) -> dict[str, str]:
    repo_root = repo_root.resolve()
    resolved = output_dir if output_dir.is_absolute() else repo_root / output_dir
    resolved = resolved.resolve()
    allowed = (repo_root / DEFAULT_OUTPUT_DIR).resolve()
    if resolved != allowed:
        raise ValueError("output_dir_must_be_logs_qre_tiingo_candidate_research_loop")
    paths = {
        "latest": resolved / "latest.json",
        "input_contracts": resolved / "input_contracts.jsonl",
        "candidate_specs": resolved / "candidate_specs.jsonl",
        "screening_results": resolved / "screening_results.jsonl",
        "feedback_records": resolved / "feedback_records.jsonl",
        "evidence_ledger": resolved / "evidence_ledger.jsonl",
        "operator_summary": resolved / "operator_summary.md",
    }
    _atomic_write_text(paths["latest"], _json_text(report))
    _atomic_write_text(paths["input_contracts"], _jsonl_text(report.get("input_contracts", [])))
    _atomic_write_text(paths["candidate_specs"], _jsonl_text(report.get("candidate_specs", [])))
    _atomic_write_text(paths["screening_results"], _jsonl_text(report.get("screening_results", [])))
    _atomic_write_text(paths["feedback_records"], _jsonl_text(report.get("feedback_records", [])))
    _atomic_write_text(paths["evidence_ledger"], _jsonl_text(report.get("evidence_ledger", [])))
    _atomic_write_text(paths["operator_summary"], render_operator_summary(report))
    return {key: path.relative_to(repo_root).as_posix() for key, path in paths.items()}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m research.qre_tiingo_candidate_research_loop")
    parser.add_argument("--lifecycle-input", default=DEFAULT_LIFECYCLE_INPUT.as_posix())
    parser.add_argument("--upstream-e2e-input", default=DEFAULT_UPSTREAM_E2E_INPUT.as_posix())
    parser.add_argument("--bars-input", default=DEFAULT_BARS_INPUT.as_posix())
    parser.add_argument("--prior-feedback-input", default=DEFAULT_PRIOR_FEEDBACK_INPUT.as_posix())
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR.as_posix())
    parser.add_argument("--max-candidates", type=int, default=5)
    parser.add_argument("--null-iterations", type=int, default=32)
    parser.add_argument("--seed", type=int, default=1729)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--repo-root", default=".")
    args = parser.parse_args(argv)
    repo_root = Path(args.repo_root).resolve()
    report = build_report(
        repo_root=repo_root,
        lifecycle_input=Path(args.lifecycle_input),
        upstream_e2e_input=Path(args.upstream_e2e_input),
        bars_input=Path(args.bars_input),
        prior_feedback_input=Path(args.prior_feedback_input),
        output_dir=Path(args.output_dir),
        max_candidates=args.max_candidates,
        null_iterations=args.null_iterations,
        seed=args.seed,
    )
    if args.write:
        report["_artifact_paths"] = write_outputs(report, repo_root=repo_root, output_dir=Path(args.output_dir))
    print(json.dumps(_stable_payload(report), indent=2, sort_keys=True, ensure_ascii=True))
    return 0


__all__ = [
    "ALLOWED_LOOP_VERDICTS",
    "ALLOWED_SCREENING_DECISIONS",
    "DEFAULT_BARS_INPUT",
    "DEFAULT_LIFECYCLE_INPUT",
    "DEFAULT_OUTPUT_DIR",
    "REPORT_KIND",
    "SAFETY",
    "build_input_contracts",
    "build_evidence_entry",
    "build_report",
    "feedback_from_screening",
    "load_bars",
    "main",
    "materialize_candidate_spec",
    "render_operator_summary",
    "screen_candidate",
    "summarize_evidence_ledger",
    "write_outputs",
]


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
