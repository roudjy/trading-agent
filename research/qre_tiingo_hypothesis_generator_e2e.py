from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
import statistics
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from itertools import pairwise
from pathlib import Path
from typing import Any

EXPECTED_SOURCE_ID = "tiingo_eod_equities_free"
EXPECTED_SNAPSHOT_ID = "qdsnap_2b1258c6f592fa08"
EXPECTED_SOURCE_TIER = "SOURCE_SCREENING_ELIGIBLE"
TIMEFRAME = "1d"
REPORT_KIND = "qre_tiingo_hypothesis_generator_e2e"
SCHEMA_VERSION = "1.0"
SOURCE_RESOLUTION_PATH = Path("generated_research/alpha_discovery/source_resolution/latest.json")
DEFAULT_OUTPUT_DIR = Path("logs/qre_tiingo_hypothesis_generator_e2e")
EXPECTED_UNIVERSE = ("SPY", "QQQ", "IWM", "DIA", "TLT", "GLD", "XLK", "XLF", "XLE", "XLV")
OLD_CONTROLLED_UNIVERSE = frozenset({"AAPL", "ADYEN", "ASML", "EWJ", "MSFT", "SONY", "TM"})
REQUIRED_COLUMNS = ("symbol", "date", "open", "high", "low", "close", "volume")
SAFE_FLAGS = {
    "network_called": False,
    "run_research_called": False,
    "campaign_launcher_called": False,
    "validation_executed": False,
    "candidate_promotion_allowed": False,
    "strategy_registration_allowed": False,
    "execution_performed": False,
    "paper_shadow_live_allowed": False,
    "trading_authority": False,
}
HYPOTHESIS_FAMILIES = (
    "cross_sectional_momentum",
    "risk_on_risk_off_regime",
    "defensive_rotation",
    "volatility_compression_breakout",
    "mean_reversion_after_extreme_dispersion",
)


def _utcnow() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _stable_payload(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _stable_payload(value[key]) for key in sorted(value)}
    if isinstance(value, list | tuple):
        return [_stable_payload(item) for item in value]
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return round(value, 10)
    return value


def _digest(value: Any, *, length: int = 16) -> str:
    payload = json.dumps(_stable_payload(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:length]


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(_stable_payload(payload), indent=2, sort_keys=True, ensure_ascii=True) + "\n"
    if path.is_file() and path.read_text(encoding="utf-8-sig") == text:
        return
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    tmp.replace(path)


def _blocked_payload(reason: str, details: list[str]) -> dict[str, Any]:
    return {
        "report_kind": REPORT_KIND,
        "schema_version": SCHEMA_VERSION,
        "final_verdict": reason,
        "blocked_reasons": sorted(dict.fromkeys(details)),
        "trading_authority": False,
        "safety": dict(SAFE_FLAGS),
    }


def resolve_source(repo_root: Path) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    payload = _read_json(repo_root / SOURCE_RESOLUTION_PATH)
    if payload is None:
        return None, _blocked_payload("blocked_source_resolution", ["missing_or_malformed_source_resolution"])
    rows = payload.get("rows")
    if not isinstance(rows, list) or not rows:
        return None, _blocked_payload("blocked_source_resolution", ["source_resolution_has_no_rows"])
    row = rows[0] if isinstance(rows[0], dict) else {}
    reasons: list[str] = []
    if row.get("selected_source") != EXPECTED_SOURCE_ID:
        reasons.append("unexpected_selected_source")
    if row.get("selected_snapshot") != EXPECTED_SNAPSHOT_ID:
        reasons.append("unexpected_selected_snapshot")
    if row.get("current_source_tier") != EXPECTED_SOURCE_TIER:
        reasons.append("unexpected_source_tier")
    if row.get("trading_authority") is not False:
        reasons.append("trading_authority_must_be_false")
    blockers = row.get("unresolved_blockers")
    if blockers:
        reasons.append("unresolved_blockers_present")
    if reasons:
        return None, _blocked_payload("blocked_source_resolution", reasons)
    return dict(row), None


def _candidate_bar_paths(repo_root: Path) -> list[Path]:
    paths = [
        repo_root / "data/imports/tiingo_eod_equities_free/tiingo_eod_etf_20210101_20251231/bars.csv",
        repo_root / "generated_research/data_catalog/imports/tiingo_eod_equities_free/qdsnap_2b1258c6f592fa08/bars.csv",
    ]
    paths.extend(
        sorted(
            (repo_root / "generated_research/data_catalog/imports").glob(
                "**/qdsnap_2b1258c6f592fa08*/**/*.csv"
            )
        )
    )
    return paths


def _normalize_fieldnames(fieldnames: list[str] | None) -> dict[str, str]:
    available = {str(name).strip().lower(): str(name) for name in fieldnames or []}
    aliases = {
        "symbol": ("symbol", "ticker"),
        "date": ("date", "datetime", "timestamp", "timestamp_utc"),
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


def _parse_date(value: Any) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    if "T" in text:
        text = text.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(text).date()
        except ValueError:
            return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _to_float(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def load_tiingo_bars(repo_root: Path) -> tuple[list[dict[str, Any]] | None, dict[str, Any] | None]:
    for path in _candidate_bar_paths(repo_root):
        if not path.is_file():
            continue
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            columns = _normalize_fieldnames(reader.fieldnames)
            missing = [column for column in REQUIRED_COLUMNS if column not in columns]
            if missing:
                return None, _blocked_payload("blocked_data_unavailable", [f"missing_columns:{','.join(missing)}"])
            rows: list[dict[str, Any]] = []
            raw_symbols: set[str] = set()
            for raw in reader:
                symbol = str(raw.get(columns["symbol"]) or "").strip().upper()
                if symbol:
                    raw_symbols.add(symbol)
                if symbol not in EXPECTED_UNIVERSE:
                    continue
                row_date = _parse_date(raw.get(columns["date"]))
                open_ = _to_float(raw.get(columns["open"]))
                high = _to_float(raw.get(columns["high"]))
                low = _to_float(raw.get(columns["low"]))
                close = _to_float(raw.get(columns["close"]))
                volume = _to_float(raw.get(columns["volume"]))
                if row_date is None or None in (open_, high, low, close, volume):
                    continue
                rows.append(
                    {
                        "symbol": symbol,
                        "date": row_date.isoformat(),
                        "open": float(open_),
                        "high": float(high),
                        "low": float(low),
                        "close": float(close),
                        "volume": float(volume),
                    }
                )
        if raw_symbols and raw_symbols <= OLD_CONTROLLED_UNIVERSE:
            return None, _blocked_payload("blocked_data_unavailable", ["old_controlled_universe_detected"])
        if not rows:
            return None, _blocked_payload("blocked_data_unavailable", ["no_expected_tiingo_etf_rows"])
        rows.sort(key=lambda row: (row["symbol"], row["date"]))
        return rows, None
    return None, _blocked_payload("blocked_data_unavailable", ["missing_tiingo_bars_csv"])


def _daily_returns(closes: list[float]) -> list[float]:
    returns: list[float] = []
    for previous, current in pairwise(closes):
        if previous > 0:
            returns.append((current / previous) - 1.0)
    return returns


def _return_nd(closes: list[float], window: int) -> float | None:
    if len(closes) <= window or closes[-window - 1] <= 0:
        return None
    return (closes[-1] / closes[-window - 1]) - 1.0


def _vol_nd(closes: list[float], window: int) -> float | None:
    returns = _daily_returns(closes)[-window:]
    if len(returns) < window:
        return None
    return statistics.pstdev(returns) * math.sqrt(252)


def _rank_desc(values: dict[str, float | None]) -> dict[str, int]:
    valid = [(symbol, value) for symbol, value in values.items() if value is not None]
    valid.sort(key=lambda item: (-float(item[1]), item[0]))
    return {symbol: index + 1 for index, (symbol, _value) in enumerate(valid)}


def _business_day_count(start: date, end: date) -> int:
    count = 0
    current = start
    while current <= end:
        if current.weekday() < 5:
            count += 1
        current += timedelta(days=1)
    return count


def _correlation(left: list[float], right: list[float]) -> float | None:
    count = min(len(left), len(right))
    if count < 3:
        return None
    x = left[-count:]
    y = right[-count:]
    mean_x = statistics.fmean(x)
    mean_y = statistics.fmean(y)
    denom_x = sum((value - mean_x) ** 2 for value in x)
    denom_y = sum((value - mean_y) ** 2 for value in y)
    if denom_x <= 0 or denom_y <= 0:
        return None
    return sum((a - mean_x) * (b - mean_y) for a, b in zip(x, y, strict=True)) / math.sqrt(denom_x * denom_y)


def _correlation_matrix(symbol_returns: dict[str, list[float]]) -> dict[str, dict[str, float | None]]:
    matrix: dict[str, dict[str, float | None]] = {}
    symbols = sorted(symbol_returns)
    for left in symbols:
        matrix[left] = {}
        for right in symbols:
            value = 1.0 if left == right else _correlation(symbol_returns[left], symbol_returns[right])
            matrix[left][right] = None if value is None else round(value, 4)
    return matrix


def _correlation_clusters(matrix: dict[str, dict[str, float | None]]) -> list[list[str]]:
    remaining = set(matrix)
    clusters: list[list[str]] = []
    for symbol in sorted(matrix):
        if symbol not in remaining:
            continue
        cluster = [symbol]
        remaining.remove(symbol)
        for other in sorted(remaining):
            if all((matrix.get(member, {}).get(other) or 0.0) >= 0.75 for member in cluster):
                cluster.append(other)
                remaining.remove(other)
        clusters.append(cluster)
    return clusters


def build_data_profile(
    bars: list[dict[str, Any]],
    *,
    source_id: str = EXPECTED_SOURCE_ID,
    source_snapshot_id: str = EXPECTED_SNAPSHOT_ID,
    source_tier: str = EXPECTED_SOURCE_TIER,
) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in bars:
        if row["symbol"] in EXPECTED_UNIVERSE:
            grouped[str(row["symbol"])].append(row)
    for rows in grouped.values():
        rows.sort(key=lambda row: str(row["date"]))

    universe = tuple(symbol for symbol in EXPECTED_UNIVERSE if symbol in grouped)
    dates = [_parse_date(row["date"]) for row in bars if row["symbol"] in universe]
    dates = [value for value in dates if value is not None]
    date_start = min(dates).isoformat() if dates else None
    date_end = max(dates).isoformat() if dates else None
    expected_rows = 0
    if dates:
        expected_rows = _business_day_count(min(dates), max(dates)) * len(universe)
    row_count = sum(len(grouped[symbol]) for symbol in universe)
    coverage_ratio = None if not expected_rows else round(row_count / expected_rows, 6)

    per_symbol_row_count = {symbol: len(grouped[symbol]) for symbol in universe}
    closes = {symbol: [float(row["close"]) for row in grouped[symbol]] for symbol in universe}
    returns_by_symbol = {symbol: _daily_returns(closes[symbol]) for symbol in universe}
    return_20 = {symbol: _return_nd(closes[symbol], 20) for symbol in universe}
    return_60 = {symbol: _return_nd(closes[symbol], 60) for symbol in universe}
    return_120 = {symbol: _return_nd(closes[symbol], 120) for symbol in universe}
    vol_20 = {symbol: _vol_nd(closes[symbol], 20) for symbol in universe}
    vol_60 = {symbol: _vol_nd(closes[symbol], 60) for symbol in universe}
    valid_60 = [value for value in return_60.values() if value is not None]
    matrix = _correlation_matrix({symbol: returns_by_symbol[symbol][-60:] for symbol in universe})
    profile = {
        "source_id": source_id,
        "source_snapshot_id": source_snapshot_id,
        "source_tier": source_tier,
        "timeframe": TIMEFRAME,
        "universe": list(universe),
        "row_count": row_count,
        "symbol_count": len(universe),
        "date_start": date_start,
        "date_end": date_end,
        "coverage_ratio": coverage_ratio,
        "per_symbol_row_count": per_symbol_row_count,
        "per_symbol_return_20d": return_20,
        "per_symbol_return_60d": return_60,
        "per_symbol_return_120d": return_120,
        "per_symbol_vol_20d": vol_20,
        "per_symbol_vol_60d": vol_60,
        "momentum_rank_60d": _rank_desc(return_60),
        "volatility_rank_60d": _rank_desc(vol_60),
        "cross_sectional_dispersion_60d": None if len(valid_60) < 2 else statistics.pstdev(valid_60),
        "correlation_digest": "sha256:" + _digest(matrix, length=32),
        "correlation_clusters": _correlation_clusters(matrix),
        "risk_proxy_spy_tlt_60d": None
        if return_60.get("SPY") is None or return_60.get("TLT") is None
        else return_60["SPY"] - return_60["TLT"],
        "defensive_proxy_gld_spy_60d": None
        if return_60.get("GLD") is None or return_60.get("SPY") is None
        else return_60["GLD"] - return_60["SPY"],
        "insufficient_history": any(count < 121 for count in per_symbol_row_count.values()) or not universe,
        "insufficient_cross_section": len(universe) < 3,
    }
    fingerprint_basis = [{key: row[key] for key in REQUIRED_COLUMNS} for row in sorted(bars, key=lambda item: (item["symbol"], item["date"]))]
    profile["data_fingerprint"] = "sha256:" + _digest(fingerprint_basis, length=32)
    profile["data_profile_digest"] = "sha256:" + _digest(profile, length=32)
    return _stable_payload(profile)


def _top_symbols(rank: dict[str, int], count: int = 4) -> list[str]:
    return [symbol for symbol, _rank in sorted(rank.items(), key=lambda item: (item[1], item[0]))[:count]]


def _hypothesis(
    *,
    profile: dict[str, Any],
    feature_family: str,
    instruments: list[str],
    lookback: int,
    signal_definition: str,
    expected_direction: str,
    falsification_condition: str,
    feature_refs: list[str],
    confidence: float,
    blocked_reasons: list[str] | None = None,
) -> dict[str, Any]:
    base = {
        "source_id": profile["source_id"],
        "source_snapshot_id": profile["source_snapshot_id"],
        "generated_from_data_profile": True,
        "feature_family": feature_family,
        "instruments_used": instruments,
        "lookback_window": lookback,
        "signal_definition": signal_definition,
        "expected_direction": expected_direction,
        "falsification_condition": falsification_condition,
        "feature_refs": feature_refs,
        "data_profile_digest": profile["data_profile_digest"],
        "screening_only": True,
        "not_trade_signal": True,
        "trading_authority": False,
        "confidence": round(confidence, 4),
        "blocked_reasons": blocked_reasons or [],
    }
    identity = "tiingo_hyp_" + feature_family + "_" + _digest(base, length=16)
    return {"hypothesis_id": identity, "content_identity": identity, **base}


def generate_hypotheses(profile: dict[str, Any], *, max_hypotheses: int) -> list[dict[str, Any]]:
    blockers: list[str] = []
    if profile["insufficient_history"]:
        blockers.append("insufficient_history")
    if profile["insufficient_cross_section"]:
        blockers.append("insufficient_cross_section")
    if blockers:
        return []

    momentum_symbols = _top_symbols(dict(profile["momentum_rank_60d"]))
    low_vol_symbols = _top_symbols(dict(profile["volatility_rank_60d"]))
    dispersion = profile.get("cross_sectional_dispersion_60d") or 0.0
    risk_proxy = profile.get("risk_proxy_spy_tlt_60d") or 0.0
    defensive_proxy = profile.get("defensive_proxy_gld_spy_60d") or 0.0
    hypotheses = [
        _hypothesis(
            profile=profile,
            feature_family="cross_sectional_momentum",
            instruments=momentum_symbols,
            lookback=60,
            signal_definition="Rank ETFs by 60d return, compare top-ranked basket against equal-weight Tiingo ETF universe.",
            expected_direction="Higher 60d relative momentum should persist over the next 20d screening window.",
            falsification_condition="Shuffled-return control produces equal or stronger data-dependency score, or rank structure becomes unstable.",
            feature_refs=["per_symbol_return_60d", "momentum_rank_60d", "cross_sectional_dispersion_60d"],
            confidence=min(0.95, 0.45 + abs(dispersion) * 4.0),
        ),
        _hypothesis(
            profile=profile,
            feature_family="risk_on_risk_off_regime",
            instruments=[symbol for symbol in ("SPY", "QQQ", "IWM", "TLT") if symbol in profile["universe"]],
            lookback=60,
            signal_definition="Compare SPY 60d return against TLT 60d return as a screening-only risk regime proxy.",
            expected_direction="Positive SPY-minus-TLT momentum should favor risk-on ETF leadership in screening research.",
            falsification_condition="Risk proxy collapses toward zero or shuffled-return control produces the same regime content identity.",
            feature_refs=["risk_proxy_spy_tlt_60d", "per_symbol_return_60d"],
            confidence=min(0.95, 0.4 + abs(risk_proxy) * 2.0),
        ),
        _hypothesis(
            profile=profile,
            feature_family="defensive_rotation",
            instruments=[symbol for symbol in ("GLD", "SPY", "TLT", "XLV") if symbol in profile["universe"]],
            lookback=60,
            signal_definition="Compare GLD 60d return against SPY 60d return as a defensive rotation screening feature.",
            expected_direction="When GLD outperforms SPY, defensive ETF baskets may deserve separate research segmentation.",
            falsification_condition="Defensive proxy loses sign stability or matches shuffled-return control identity.",
            feature_refs=["defensive_proxy_gld_spy_60d", "per_symbol_return_60d"],
            confidence=min(0.95, 0.4 + abs(defensive_proxy) * 2.0),
        ),
        _hypothesis(
            profile=profile,
            feature_family="volatility_compression_breakout",
            instruments=low_vol_symbols,
            lookback=60,
            signal_definition="Identify lower-volatility ETFs by 60d realized volatility and screen whether subsequent breakouts differ by cluster.",
            expected_direction="Compressed realized volatility should create distinct breakout research candidates after trend confirmation.",
            falsification_condition="Volatility ranks are unstable or shuffled-return control preserves the same ranked instrument set.",
            feature_refs=["per_symbol_vol_60d", "volatility_rank_60d", "correlation_clusters"],
            confidence=0.55,
        ),
        _hypothesis(
            profile=profile,
            feature_family="mean_reversion_after_extreme_dispersion",
            instruments=momentum_symbols,
            lookback=60,
            signal_definition="Use cross-sectional 60d return dispersion to screen whether extreme ETF leadership subsequently mean-reverts.",
            expected_direction="Extreme 60d dispersion should create a testable follow-on mean-reversion research condition.",
            falsification_condition="Dispersion is not materially above zero or shuffled-return control produces equivalent identities.",
            feature_refs=["cross_sectional_dispersion_60d", "momentum_rank_60d"],
            confidence=min(0.9, 0.35 + abs(dispersion) * 5.0),
        ),
    ]
    return _stable_payload(hypotheses[: max(0, max_hypotheses)])


def shuffled_returns_bars(bars: list[dict[str, Any]], *, seed: int) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in bars:
        grouped[row["symbol"]].append(row)
    shuffled: list[dict[str, Any]] = []
    for symbol in sorted(grouped):
        rows = sorted(grouped[symbol], key=lambda row: row["date"])
        closes = [float(row["close"]) for row in rows]
        returns = _daily_returns(closes)
        rng.shuffle(returns)
        synthetic_close = [closes[0]]
        for value in returns:
            synthetic_close.append(synthetic_close[-1] * (1.0 + value))
        for idx, row in enumerate(rows):
            close = synthetic_close[idx]
            open_ = synthetic_close[idx - 1] if idx else close
            high = max(open_, close)
            low = min(open_, close)
            shuffled.append({**row, "open": open_, "high": high, "low": low, "close": close})
    return sorted(shuffled, key=lambda row: (row["symbol"], row["date"]))


def truncated_bars(bars: list[dict[str, Any]]) -> list[dict[str, Any]]:
    symbols = sorted({row["symbol"] for row in bars})[:2]
    truncated: list[dict[str, Any]] = []
    for symbol in symbols:
        rows = sorted([row for row in bars if row["symbol"] == symbol], key=lambda row: row["date"])
        truncated.extend(rows[:80])
    return sorted(truncated, key=lambda row: (row["symbol"], row["date"]))


def run_mode(bars: list[dict[str, Any]], *, mode: str, max_hypotheses: int, seed: int) -> dict[str, Any]:
    selected_bars = bars
    if mode == "shuffled_returns":
        selected_bars = shuffled_returns_bars(bars, seed=seed)
    elif mode == "truncated":
        selected_bars = truncated_bars(bars)
    profile = build_data_profile(selected_bars)
    hypotheses = generate_hypotheses(profile, max_hypotheses=max_hypotheses)
    data_profile_valid = not profile["insufficient_history"] and not profile["insufficient_cross_section"]
    blocked_reasons = []
    if profile["insufficient_history"]:
        blocked_reasons.append("insufficient_history")
    if profile["insufficient_cross_section"]:
        blocked_reasons.append("insufficient_cross_section")
    return {
        "mode": mode,
        "data_profile_valid": data_profile_valid,
        "blocked_reasons": blocked_reasons,
        "data_profile": profile,
        "hypotheses": hypotheses,
        "hypotheses_count": len(hypotheses),
        "content_identities": [hypothesis["content_identity"] for hypothesis in hypotheses],
        "safety": dict(SAFE_FLAGS),
    }


def _safe_payload(payload: dict[str, Any]) -> bool:
    safety = payload.get("safety") or {}
    return all(safety.get(key) is False for key in SAFE_FLAGS)


def _all_real_hypotheses_safe(real: dict[str, Any]) -> bool:
    hypotheses = real.get("hypotheses") or []
    universe = set(EXPECTED_UNIVERSE)
    return bool(hypotheses) and all(
        hypothesis.get("source_snapshot_id") == EXPECTED_SNAPSHOT_ID
        and hypothesis.get("generated_from_data_profile") is True
        and set(hypothesis.get("instruments_used") or []) <= universe
        and hypothesis.get("trading_authority") is False
        and hypothesis.get("not_trade_signal") is True
        for hypothesis in hypotheses
    )


def build_all_payload(modes: dict[str, dict[str, Any]]) -> dict[str, Any]:
    real = modes["real"]
    shuffled = modes["shuffled_returns"]
    truncated = modes["truncated"]
    real_ids = real["content_identities"]
    shuffled_ids = shuffled["content_identities"]
    truncated_blocked = bool(truncated["blocked_reasons"]) or truncated["hypotheses_count"] < real["hypotheses_count"]
    blockers: list[str] = []
    if real["hypotheses_count"] <= 0:
        blockers.append("real_mode_generated_no_hypotheses")
    if not _all_real_hypotheses_safe(real):
        blockers.append("real_hypotheses_not_data_profile_safe")
    if real_ids == shuffled_ids:
        blockers.append("real_and_shuffled_content_identities_identical")
    if not truncated_blocked:
        blockers.append("truncated_control_not_degraded")
    if not all(_safe_payload(mode_payload) for mode_payload in modes.values()):
        blockers.append("unsafe_safety_flags")

    data_dependency_proven = not blockers
    if data_dependency_proven:
        verdict = "pass_data_driven_hypothesis_generation"
    elif "real_and_shuffled_content_identities_identical" in blockers:
        verdict = "fail_static_or_template_driven"
    elif truncated["data_profile"]["insufficient_history"]:
        verdict = "blocked_insufficient_history" if real["hypotheses_count"] <= 0 else "fail_static_or_template_driven"
    elif truncated["data_profile"]["insufficient_cross_section"]:
        verdict = "blocked_insufficient_cross_section" if real["hypotheses_count"] <= 0 else "fail_static_or_template_driven"
    elif "unsafe_safety_flags" in blockers:
        verdict = "blocked_safety_boundary"
    else:
        verdict = "fail_static_or_template_driven"

    return {
        "report_kind": REPORT_KIND,
        "schema_version": SCHEMA_VERSION,
        "source_id": EXPECTED_SOURCE_ID,
        "source_snapshot_id": EXPECTED_SNAPSHOT_ID,
        "source_tier": EXPECTED_SOURCE_TIER,
        "timeframe": TIMEFRAME,
        "created_at_utc": _utcnow(),
        "modes": modes,
        "summary": {
            "real_data_hypotheses_count": real["hypotheses_count"],
            "shuffled_control_hypotheses_count": shuffled["hypotheses_count"],
            "truncated_control_hypotheses_count": truncated["hypotheses_count"],
            "real_content_identities": real_ids,
            "shuffled_content_identities": shuffled_ids,
            "truncated_content_identities": truncated["content_identities"],
            "data_dependency_proven": data_dependency_proven,
            "data_dependency_blockers": blockers,
            "final_verdict": verdict,
        },
        "safety": dict(SAFE_FLAGS),
    }


def build_report(repo_root: Path, *, mode: str, max_hypotheses: int, seed: int) -> tuple[dict[str, Any], int]:
    _row, blocked = resolve_source(repo_root)
    if blocked is not None:
        return blocked, 1
    bars, data_blocked = load_tiingo_bars(repo_root)
    if data_blocked is not None or bars is None:
        return data_blocked or _blocked_payload("blocked_data_unavailable", ["missing_bars"]), 1
    if mode == "all":
        modes = {
            item: run_mode(bars, mode=item, max_hypotheses=max_hypotheses, seed=seed)
            for item in ("real", "shuffled_returns", "truncated")
        }
        payload = build_all_payload(modes)
        return payload, 0 if payload["summary"]["final_verdict"] != "blocked_safety_boundary" else 1
    mode_payload = run_mode(bars, mode=mode, max_hypotheses=max_hypotheses, seed=seed)
    payload = {
        "report_kind": REPORT_KIND,
        "schema_version": SCHEMA_VERSION,
        "source_id": EXPECTED_SOURCE_ID,
        "source_snapshot_id": EXPECTED_SNAPSHOT_ID,
        "source_tier": EXPECTED_SOURCE_TIER,
        "timeframe": TIMEFRAME,
        "created_at_utc": _utcnow(),
        "mode": mode,
        **mode_payload,
        "safety": dict(SAFE_FLAGS),
    }
    return payload, 0


def _operator_summary(payload: dict[str, Any]) -> str:
    summary = payload.get("summary") or {}
    modes = payload.get("modes") or {}
    real = modes.get("real") or payload
    universe = (real.get("data_profile") or {}).get("universe") or []
    safety = payload.get("safety") or {}
    blockers = summary.get("data_dependency_blockers") or payload.get("blocked_reasons") or []
    lines = [
        "# QRE Tiingo Hypothesis Generator E2E",
        "",
        "- source_id: " + str(payload.get("source_id", EXPECTED_SOURCE_ID)),
        "- source_snapshot_id: " + str(payload.get("source_snapshot_id", EXPECTED_SNAPSHOT_ID)),
        "- source_tier: " + str(payload.get("source_tier", EXPECTED_SOURCE_TIER)),
        "- universe: " + ", ".join(str(item) for item in universe),
        "- real hypotheses count: " + str(summary.get("real_data_hypotheses_count", real.get("hypotheses_count", 0))),
        "- shuffled control hypotheses count: " + str(summary.get("shuffled_control_hypotheses_count", 0)),
        "- truncated control hypotheses count: " + str(summary.get("truncated_control_hypotheses_count", 0)),
        "- data dependency verdict: " + str(summary.get("data_dependency_proven", False)),
        "- safety boundaries: " + json.dumps(safety, sort_keys=True),
        "- blocked reasons: " + (", ".join(str(item) for item in blockers) if blockers else "none"),
        "- final verdict: " + str(summary.get("final_verdict") or payload.get("final_verdict")),
        "",
        "This artifact is research-only. It is not a trade signal, not strategy authority, not candidate promotion, and not paper/shadow/live authority.",
        "",
    ]
    return "\n".join(lines)


def write_outputs(repo_root: Path, output_dir: Path, payload: dict[str, Any]) -> None:
    resolved = (repo_root / output_dir).resolve()
    allowed = (repo_root / DEFAULT_OUTPUT_DIR).resolve()
    if resolved != allowed:
        raise ValueError("output_dir_must_be_logs_qre_tiingo_hypothesis_generator_e2e")
    resolved.mkdir(parents=True, exist_ok=True)
    _write_json(resolved / "latest.json", payload)
    (resolved / "operator_summary.md").write_text(_operator_summary(payload), encoding="utf-8", newline="\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m research.qre_tiingo_hypothesis_generator_e2e")
    parser.add_argument("--mode", choices=("real", "shuffled_returns", "truncated", "all"), default="all")
    parser.add_argument("--max-hypotheses", type=int, default=5)
    parser.add_argument("--seed", type=int, default=1729)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--repo-root", default=".")
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve()
    payload, status = build_report(repo_root, mode=args.mode, max_hypotheses=args.max_hypotheses, seed=args.seed)
    if args.write:
        try:
            write_outputs(repo_root, Path(args.output_dir), payload)
        except ValueError as exc:
            payload = _blocked_payload("blocked_safety_boundary", [str(exc)])
            status = 1
    print(json.dumps(_stable_payload(payload), indent=2, sort_keys=True))
    return status


__all__ = [
    "build_all_payload",
    "build_data_profile",
    "build_report",
    "generate_hypotheses",
    "load_tiingo_bars",
    "main",
    "resolve_source",
    "run_mode",
    "write_outputs",
]


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
