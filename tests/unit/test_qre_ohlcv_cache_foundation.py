from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from packages.qre_data import cache_manifest, source_quality_readiness
from research import qre_cache_throughput_manifest
from research import qre_ohlcv_cache_foundation as foundation


def _write_parquet(path: Path, timestamps: list[datetime]) -> None:
    table = pa.table(
        {
            "instrument_id": ["btc-usd"] * len(timestamps),
            "interval": ["1h"] * len(timestamps),
            "timestamp_utc": timestamps,
            "close": [100.0 + i for i, _ in enumerate(timestamps)],
        }
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, path)


def _seed_cache_and_source_sidecars(tmp_path: Path) -> None:
    cache = tmp_path / "data" / "cache" / "market"
    _write_parquet(
        cache / "yfinance__AAPL__1d__20260401__20260402__abc123.parquet",
        [datetime(2026, 4, 1, 0, 0, tzinfo=UTC)],
    )
    manifest_payload = cache_manifest.build_cache_manifest(
        cache_dirs={"market": Path("data/cache/market")},
        repo_root=tmp_path,
        generated_at_utc="2026-06-26T00:00:00Z",
    )
    cache_manifest.write_manifest_outputs(
        manifest_payload,
        output_dir=Path("logs/qre_data_cache_manifest"),
        repo_root=tmp_path,
    )
    source_payload = source_quality_readiness.build_source_quality_report(
        manifest_payload,
        generated_at_utc="2026-06-26T00:00:00Z",
    )
    source_quality_readiness.write_source_quality_outputs(
        source_payload,
        output_dir=Path("logs/qre_data_source_quality_readiness"),
        repo_root=tmp_path,
    )


def test_foundation_reports_local_cache_ready_and_external_blockers_separately(
    tmp_path: Path,
) -> None:
    _seed_cache_and_source_sidecars(tmp_path)

    report = foundation.build_ohlcv_cache_foundation(
        repo_root=tmp_path,
        duckdb_available=True,
        polars_available=True,
    )

    assert report["report_kind"] == "qre_ohlcv_cache_foundation"
    assert report["summary"]["research_ready"] is True
    assert report["summary"]["cache_manifest_status"] == "ready"
    assert report["summary"]["source_quality_status"] == "ready"
    assert report["summary"]["throughput_status"] == "ready"
    assert report["summary"]["source_cache_linked"] is True
    assert report["summary"]["cache_file_count"] == 1
    assert report["summary"]["coverage_row_count"] == 1
    assert report["summary"]["local_source_status_counts"] == {"ready": 1}
    assert report["local_cache_foundation"]["sources"] == [
        {
            "source": "yfinance",
            "instrument": "AAPL",
            "timeframe": "1d",
            "ready": True,
            "file_count": 1,
            "row_count": 1,
            "min_timestamp_utc": "2026-04-01T00:00:00Z",
            "max_timestamp_utc": "2026-04-01T00:00:00Z",
            "content_hash": report["local_cache_foundation"]["sources"][0]["content_hash"],
        }
    ]
    assert report["future_external_source_blockers"]
    assert any(
        row["requires_operator_or_credentials"] for row in report["future_external_source_blockers"]
    )
    assert "Local OHLCV/cache foundation is ready" in report["summary"]["operator_summary"]


def test_foundation_fails_closed_when_cache_sidecars_are_missing(tmp_path: Path) -> None:
    report = foundation.build_ohlcv_cache_foundation(
        repo_root=tmp_path,
        duckdb_available=False,
        polars_available=False,
    )

    assert report["summary"]["research_ready"] is False
    assert report["summary"]["cache_manifest_status"] == "missing_manifest"
    assert report["summary"]["source_quality_status"] == "missing_source_quality_report"
    assert report["summary"]["throughput_status"] == "not_ready"
    assert report["summary"]["source_cache_linked"] is False
    assert report["summary"]["cache_file_count"] == 0
    assert report["summary"]["coverage_row_count"] == 0
    assert report["summary"]["local_source_status_counts"] == {}
    assert report["future_external_source_blockers"]
    assert "duckdb_module_unavailable" in report["summary"]["operator_summary"]


def test_write_outputs_persists_log_and_artifact_files(tmp_path: Path) -> None:
    _seed_cache_and_source_sidecars(tmp_path)
    report = foundation.build_ohlcv_cache_foundation(
        repo_root=tmp_path,
        duckdb_available=True,
        polars_available=True,
    )

    paths = foundation.write_outputs(report, repo_root=tmp_path)

    assert paths == {
        "latest": "logs/qre_ohlcv_cache_foundation/latest.json",
        "operator_summary": "logs/qre_ohlcv_cache_foundation/operator_summary.md",
        "cache_foundation_artifact": "artifacts/cache/cache_foundation_latest.v1.json",
    }
    latest_path = tmp_path / paths["latest"]
    artifact_path = tmp_path / paths["cache_foundation_artifact"]
    assert latest_path.is_file()
    assert artifact_path.is_file()
    payload = json.loads(latest_path.read_text(encoding="utf-8"))
    assert payload["summary"]["research_ready"] is True
    assert json.loads(artifact_path.read_text(encoding="utf-8"))["report_kind"] == (
        "qre_ohlcv_cache_foundation"
    )


def test_foundation_prefers_existing_throughput_sidecar_over_current_environment(
    tmp_path: Path,
) -> None:
    _seed_cache_and_source_sidecars(tmp_path)
    throughput = qre_cache_throughput_manifest.build_cache_throughput_manifest(
        repo_root=tmp_path,
        cache_manifest_path=Path("logs/qre_data_cache_manifest/latest.json"),
        generated_at_utc="2026-06-26T00:00:00Z",
        duckdb_available=True,
        polars_available=True,
    )
    qre_cache_throughput_manifest.write_outputs(
        throughput,
        repo_root=tmp_path,
        output_dir=Path("logs/qre_cache_throughput_manifest"),
    )

    report = foundation.build_ohlcv_cache_foundation(
        repo_root=tmp_path,
        duckdb_available=False,
        polars_available=False,
    )

    assert report["summary"]["throughput_status"] == "ready"
    assert report["summary"]["research_ready"] is True
