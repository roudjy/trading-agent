from __future__ import annotations

import json
from pathlib import Path

from research import qre_cache_only_metric_path as cache_metrics


def _coverage(symbols: list[str], *, timeframe: str = "1d") -> dict:
    return {
        "schema_version": "1.0",
        "report_kind": "qre_materialized_cache_coverage",
        "research_ready": True,
        "coverage": [
            {
                "source": "yfinance",
                "instrument": symbol,
                "timeframe": timeframe,
                "ready": True,
                "row_count": 10,
                "file_count": 2,
                "min_timestamp_utc": "2026-04-08T00:00:00Z",
                "max_timestamp_utc": "2026-04-17T00:00:00Z",
                "content_hash": f"sha256:{symbol.lower()}",
            }
            for symbol in symbols
        ],
    }


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_builds_true_cache_only_metric_evidence_for_exact_ready_universe(tmp_path: Path) -> None:
    coverage_path = tmp_path / "cache_coverage.json"
    _write_json(coverage_path, _coverage(["AAPL", "MSFT"]))

    evidence = cache_metrics.build_cache_only_metric_evidence(
        assets=["MSFT", "AAPL"],
        timeframe="1d",
        cache_coverage_path=coverage_path,
        cache_manifest_path=tmp_path / "missing_manifest.json",
    )

    assert evidence["metric_mode"] == "cache_only_metric_evidence"
    assert evidence["true_metrics_available"] is True
    assert evidence["bounded_metric_evidence_available"] is False
    assert evidence["controlled_universe"] == ["AAPL", "MSFT"]
    assert evidence["observation_count"] == 20
    assert evidence["cache_file_count"] == 4
    assert evidence["network_called"] is False
    assert evidence["run_research_called"] is False
    assert evidence["campaign_launcher_called"] is False
    assert evidence["per_asset"][0]["metric_readiness"] == "ready"


def test_missing_exact_universe_coverage_preserves_bounded_evidence(tmp_path: Path) -> None:
    coverage_path = tmp_path / "cache_coverage.json"
    _write_json(coverage_path, _coverage(["AAPL"]))

    evidence = cache_metrics.build_cache_only_metric_evidence(
        assets=["AAPL", "MSFT"],
        timeframe="1d",
        cache_coverage_path=coverage_path,
        cache_manifest_path=tmp_path / "missing_manifest.json",
    )

    assert evidence["metric_mode"] == "bounded_metric_evidence"
    assert evidence["true_metrics_available"] is False
    assert evidence["bounded_metric_evidence_available"] is True
    assert evidence["missing_cache_symbols"] == ["MSFT"]
    assert evidence["per_asset"][1]["blocker"] == cache_metrics.SAFE_METRIC_BLOCKER
    assert evidence["per_asset"][1]["cache_coverage_blocker"] == cache_metrics.MISSING_CACHE_BLOCKER
    assert "no safe cache-only exact-universe metric path" in evidence["evidence_statement"]


def test_malformed_or_missing_cache_artifacts_fail_closed_to_bounded_evidence(tmp_path: Path) -> None:
    evidence = cache_metrics.build_cache_only_metric_evidence(
        assets=["AAPL"],
        timeframe="1d",
        cache_coverage_path=tmp_path / "missing_coverage.json",
        cache_manifest_path=tmp_path / "missing_manifest.json",
    )

    assert evidence["metric_mode"] == "bounded_metric_evidence"
    assert evidence["true_metrics_available"] is False
    assert evidence["missing_cache_symbols"] == ["AAPL"]
    assert evidence["external_data_called"] is False
