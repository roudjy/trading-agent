"""Read-only cache-only metric evidence for the controlled QRE universe.

This module consumes existing local cache manifest artifacts only. It does not
fetch market data, execute research, launch campaigns, or mutate public
research outputs.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Final


SCHEMA_VERSION: Final[str] = "1.0"
REPORT_KIND: Final[str] = "qre_cache_only_metric_path"
DEFAULT_CACHE_COVERAGE_PATH: Final[Path] = Path("artifacts/cache/cache_coverage_latest.v1.json")
DEFAULT_CACHE_MANIFEST_PATH: Final[Path] = Path("logs/qre_data_cache_manifest/latest.json")
SAFE_METRIC_BLOCKER: Final[str] = "safe_metric_runner_missing_or_cache_unavailable"
MISSING_CACHE_BLOCKER: Final[str] = "cache_only_exact_universe_coverage_unavailable"


class CacheOnlyMetricPathError(RuntimeError):
    """Raised when cache-only metric evidence cannot be evaluated safely."""


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        parsed = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _coverage_rows(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    rows = payload.get("coverage") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def _coverage_index(rows: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    indexed: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        key = (str(row.get("instrument") or ""), str(row.get("timeframe") or ""))
        if key[0] and key[1]:
            indexed[key] = row
    return indexed


def _bounded_asset(symbol: str, *, blocker: str = SAFE_METRIC_BLOCKER) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "metric_readiness": "blocked",
        "blocker": blocker,
        "next_action": "add_cache_only_metric_path",
    }


def _cache_asset(symbol: str, row: dict[str, Any]) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "metric_readiness": "ready",
        "blocker": None,
        "next_action": None,
        "cache_source": row.get("source"),
        "timeframe": row.get("timeframe"),
        "row_count": row.get("row_count"),
        "file_count": row.get("file_count"),
        "min_timestamp_utc": row.get("min_timestamp_utc"),
        "max_timestamp_utc": row.get("max_timestamp_utc"),
        "content_hash": row.get("content_hash"),
    }


def _true_cache_metric_evidence(
    *,
    assets: list[str],
    timeframe: str,
    rows: list[dict[str, Any]],
    source_path: Path,
) -> dict[str, Any]:
    indexed = _coverage_index(rows)
    per_asset = [
        _cache_asset(symbol, indexed[(symbol, timeframe)])
        for symbol in assets
    ]
    row_counts = [int(row.get("row_count") or 0) for row in per_asset]
    file_counts = [int(row.get("file_count") or 0) for row in per_asset]
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "metric_mode": "cache_only_metric_evidence",
        "true_metrics_available": True,
        "bounded_metric_evidence_available": False,
        "per_asset": per_asset,
        "controlled_universe": assets,
        "timeframe": timeframe,
        "exact_universe_match": True,
        "cache_only": True,
        "network_called": False,
        "external_data_called": False,
        "run_research_called": False,
        "campaign_launcher_called": False,
        "metric_source": source_path.as_posix(),
        "observation_count": sum(row_counts),
        "cache_file_count": sum(file_counts),
        "trade_count": None,
        "oos_return": None,
        "max_drawdown": None,
        "sharpe": None,
        "deflated_sharpe": None,
        "evidence_statement": (
            "Cache-only exact-universe metric evidence is available from existing "
            "local read-only cache coverage; no network, campaign, or public-output "
            "mutation path was used."
        ),
    }


def bounded_metric_evidence(
    *,
    assets: list[str],
    timeframe: str,
    source_path: Path,
    missing_symbols: list[str] | None = None,
) -> dict[str, Any]:
    missing = sorted(missing_symbols or assets)
    per_asset = []
    for symbol in assets:
        row = _bounded_asset(symbol, blocker=SAFE_METRIC_BLOCKER)
        row["cache_coverage_blocker"] = MISSING_CACHE_BLOCKER if symbol in missing else None
        per_asset.append(row)
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "metric_mode": "bounded_metric_evidence",
        "true_metrics_available": False,
        "bounded_metric_evidence_available": True,
        "per_asset": per_asset,
        "controlled_universe": assets,
        "timeframe": timeframe,
        "exact_universe_match": False,
        "cache_only": True,
        "network_called": False,
        "external_data_called": False,
        "run_research_called": False,
        "campaign_launcher_called": False,
        "metric_source": source_path.as_posix(),
        "missing_cache_symbols": missing,
        "trade_count": None,
        "oos_return": None,
        "max_drawdown": None,
        "sharpe": None,
        "deflated_sharpe": None,
        "evidence_statement": (
            "True metrics are unavailable because no safe cache-only exact-universe "
            "metric path has full ready local cache coverage yet; bounded evidence "
            "preserves the safe next-action target."
        ),
    }


def build_cache_only_metric_evidence(
    *,
    assets: list[str],
    timeframe: str,
    cache_coverage_path: Path = DEFAULT_CACHE_COVERAGE_PATH,
    cache_manifest_path: Path = DEFAULT_CACHE_MANIFEST_PATH,
) -> dict[str, Any]:
    """Build exact-universe metric evidence from local cache artifacts only."""

    ordered_assets = sorted(str(asset) for asset in assets)
    coverage_payload = _read_json(cache_coverage_path)
    manifest_payload = _read_json(cache_manifest_path)
    coverage_rows = _coverage_rows(coverage_payload) or _coverage_rows(manifest_payload)
    indexed = _coverage_index(coverage_rows)
    missing = [
        symbol
        for symbol in ordered_assets
        if not bool((indexed.get((symbol, timeframe)) or {}).get("ready"))
    ]
    source_path = cache_coverage_path if coverage_payload is not None else cache_manifest_path
    if missing:
        return bounded_metric_evidence(
            assets=ordered_assets,
            timeframe=timeframe,
            source_path=source_path,
            missing_symbols=missing,
        )
    return _true_cache_metric_evidence(
        assets=ordered_assets,
        timeframe=timeframe,
        rows=coverage_rows,
        source_path=source_path,
    )


__all__ = [
    "CacheOnlyMetricPathError",
    "DEFAULT_CACHE_COVERAGE_PATH",
    "DEFAULT_CACHE_MANIFEST_PATH",
    "MISSING_CACHE_BLOCKER",
    "REPORT_KIND",
    "SAFE_METRIC_BLOCKER",
    "SCHEMA_VERSION",
    "bounded_metric_evidence",
    "build_cache_only_metric_evidence",
]
